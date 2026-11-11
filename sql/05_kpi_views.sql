-- 05_kpi_views.sql: KPI views an SFE team would use.
-- Payout parameters must match config.py (a test checks SQL vs Python):
--   attainment < 90%  -> 0
--   90% to 100%       -> 50% to 100% of target bonus, linear
--   above 100%        -> +2% payout per +1% attainment, capped at 150%

-- Attainment vs target, by territory and product, for the target year.
create or replace view gold.v_attainment_product as
select
    s.territory_code, s.product_code,
    sum(s.value_net) as actual_value,
    sum(t.target_value) as target_value,
    sum(s.value_net) / nullif(sum(t.target_value), 0) as attainment
from gold.fact_sales s
join gold.fact_targets t using (territory_code, product_code, month_start)
group by all;

-- Attainment vs target, by territory (the level the incentive pays on).
create or replace view gold.v_attainment as
select
    territory_code,
    sum(actual_value) as actual_value,
    sum(target_value) as target_value,
    sum(actual_value) / sum(target_value) as attainment
from gold.v_attainment_product
group by territory_code;

create or replace macro gold.payout_pct(a) as
    case
        when a < 0.90 then 0.0
        when a < 1.00 then 0.50 + (a - 0.90) / 0.10 * 0.50
        else least(1.0 + 2.0 * (a - 1.0), 1.50)
    end;

-- Payout per rep: territory payout % x target bonus, prorated by months held in the target year.
create or replace view gold.v_payout as
with tenure as (
    select r.rep_id, r.territory_code,
           count(*) as months_in_role
    from gold.dim_rep r
    join (select distinct month_start from gold.fact_targets) m
      on m.month_start between r.start_date and r.end_date
    group by all
)
select
    te.rep_id, te.territory_code, te.months_in_role,
    a.attainment,
    gold.payout_pct(a.attainment) as payout_pct,
    round(gold.payout_pct(a.attainment) * 40000 * te.months_in_role / 12.0, 2) as payout_sar
from tenure te
join gold.v_attainment a using (territory_code);

-- Like-for-like growth: same territory-product-month vs one year earlier, counting only months
-- where the territory had a rep in BOTH years, and excluding the launch product (no base year).
create or replace view gold.v_lfl_growth as
with pairs as (
    select
        cur.territory_code, cur.product_code, year(cur.month_start) as year,
        cur.value_net as value_cur, prev.value_net as value_prev
    from gold.fact_sales cur
    join gold.fact_sales prev
      on prev.territory_code = cur.territory_code
     and prev.product_code = cur.product_code
     and prev.month_start = cur.month_start - interval 1 year
    join gold.dim_product p on p.product_code = cur.product_code
    where cur.rep_id is not null and prev.rep_id is not null
      and p.launch_month is null
)
select territory_code, product_code, year,
       count(*) as lfl_months,
       sum(value_cur) as value_cur, sum(value_prev) as value_prev,
       sum(value_cur) / sum(value_prev) - 1 as lfl_growth
from pairs
group by all;

create or replace view gold.v_lfl_growth_national as
select product_code, year, sum(value_cur) / sum(value_prev) - 1 as lfl_growth
from gold.v_lfl_growth group by all;
