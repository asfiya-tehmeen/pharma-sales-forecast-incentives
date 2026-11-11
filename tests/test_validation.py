"""The SQL validation must recover the clean ledger exactly from the messy feed."""
import pandas as pd


def dq(con):
    return con.execute("select check_name, n_rows from silver.dq_summary").df().set_index("check_name").n_rows


def test_fact_equals_true_ledger(world, built):
    fact = built.execute("""select territory_code, product_code, month_start, units_net, value_net
                        from gold.fact_sales""").df()
    led = world.ledger.assign(month_start=world.ledger.invoice_date.dt.to_period("M").dt.to_timestamp())
    truth = led.groupby(["territory_code", "product_code", "month_start"]).agg(
        units=("qty", "sum"), value=("net_value", "sum")).reset_index()
    m = fact.merge(truth, how="left", on=["territory_code", "product_code", "month_start"]).fillna(0)
    assert (m.units_net == m.units).all()
    assert (m.value_net.astype(float) - m.value).abs().max() < 0.01
    assert len(fact) == 40 * 3 * 36


def test_invalid_rows_quarantined(world, built):
    q = built.execute("select reject_reason, count(*) n from silver.quarantine group by 1").df().set_index("reject_reason").n
    assert q["non_positive_sale"] == world.answer_key["messiness"]["invalid_negative_sale_rows"]
    assert q["unknown_product"] == world.answer_key["messiness"]["orphan_product_rows"]
    leaked = built.execute("select count(*) from silver.sales_lines where invoice_id like 'TST%'").fetchone()[0]
    assert leaked == 0


def test_returns_kept(world, built):
    assert dq(built)["valid_return_lines_kept"] == world.answer_key["messiness"]["valid_return_lines"]
    neg = built.execute("select count(*) from silver.sales_lines where qty < 0 and txn_type <> 'RETURN'").fetchone()[0]
    assert neg == 0


def test_duplicates_removed(world, built):
    m = world.answer_key["messiness"]
    assert dq(built)["duplicate_rows_removed"] == m["duplicate_rows_same_file"] + m["duplicate_rows_resent"]
    dupes = built.execute("""select count(*) from (select invoice_id, line_no from silver.sales_lines
                         group by all having count(*) > 1)""").fetchone()[0]
    assert dupes == 0


def test_restatements_latest_version_wins(world, built):
    assert dq(built)["restated_lines_resolved"] == world.answer_key["messiness"]["restated_lines"]
    v = built.execute("select min(record_version) from silver.sales_lines where was_restated").fetchone()[0]
    assert v == 2


def test_late_rows_assigned_to_invoice_month(world, built):
    late = built.execute("""select distinct territory_code, month_start from silver.sales_lines
                        where arrived_late and not was_restated""").df()
    assert len(late) == world.answer_key["messiness"]["late_territory_months"]
    # every line sits in the month of its invoice date
    bad = built.execute("""select count(*) from silver.sales_lines
                       where month_start <> date_trunc('month', invoice_date)""").fetchone()[0]
    assert bad == 0


def test_vacant_months_have_null_rep(world, built):
    for w in world.answer_key["E5_vacancies"]["windows"]:
        n = built.execute(f"""select count(distinct month_start) from gold.fact_sales
                          where territory_code = '{w['territory_code']}' and rep_id is null""").fetchone()[0]
        months = len(pd.date_range(w["first_month"], w["last_month"], freq="MS"))
        assert n == months


def test_targets_loaded(world, built):
    total = built.execute("select sum(target_value) from gold.fact_targets").fetchone()[0]
    assert abs(float(total) - world.targets.target_value.sum()) < 1.0
