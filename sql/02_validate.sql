-- 02_validate.sql: validate the feed like a real distributor feed (silver).
-- Rules, in order:
--   1. Quarantine rows that break a hard rule: unknown product, unknown territory,
--      SALE with qty <= 0, RETURN with qty >= 0, net_value inconsistent with qty x price.
--   2. Remove exact re-sends: same (invoice_id, line_no, record_version) delivered more than once
--      (keep the earliest delivery).
--   3. Resolve restatements: for each (invoice_id, line_no) keep the highest record_version.
--   4. Assign every line to its sales month from invoice_date, never from the file it arrived in
--      (late files are counted, not dropped).
-- Negative quantities are VALID when txn_type = 'RETURN'; they are kept.

create schema if not exists silver;

create or replace table silver.feed_checked as
select
    f.*,
    row_number() over () as row_id,
    case
        when p.product_code is null then 'unknown_product'
        when t.territory_code is null then 'unknown_territory'
        when f.txn_type = 'SALE' and f.qty <= 0 then 'non_positive_sale'
        when f.txn_type = 'RETURN' and f.qty >= 0 then 'non_negative_return'
        when f.txn_type not in ('SALE', 'RETURN') then 'unknown_txn_type'
        when abs(f.net_value - f.qty * f.unit_price) > 0.01 then 'value_mismatch'
        else null
    end as reject_reason
from bronze.sales_feed f
left join bronze.products p using (product_code)
left join bronze.territories t using (territory_code);

create or replace table silver.quarantine as
select * from silver.feed_checked where reject_reason is not null;

create or replace table silver.sales_lines as
with valid as (
    select * from silver.feed_checked where reject_reason is null
),
dedup as (
    select *,
        row_number() over (partition by invoice_id, line_no, record_version
                           order by delivered_on, row_id) as dup_rank
    from valid
),
latest as (
    select *,
        row_number() over (partition by invoice_id, line_no
                           order by record_version desc) as version_rank,
        count(*) over (partition by invoice_id, line_no) as n_versions
    from dedup
    where dup_rank = 1
)
select
    invoice_id, line_no, record_version, invoice_date,
    cast(date_trunc('month', invoice_date) as date) as month_start,
    territory_code, product_code, txn_type, qty, unit_price, net_value,
    file_id, delivered_on,
    -- a file for month M is delivered on the 10th of month M+1; anything later is late
    delivered_on > cast(date_trunc('month', invoice_date) + interval 1 month + interval 9 day as date) as arrived_late,
    n_versions > 1 as was_restated
from latest
where version_rank = 1;

create or replace table silver.dq_summary as
select 'rows_received' as check_name, count(*) as n_rows, 'loaded to bronze' as action from bronze.sales_feed
union all
select 'quarantined_' || reject_reason, count(*), 'excluded; see silver.quarantine'
from silver.quarantine group by reject_reason
union all
select 'duplicate_rows_removed',
       (select count(*) from silver.feed_checked where reject_reason is null)
       - (select count(*) from (select distinct invoice_id, line_no, record_version
                                from silver.feed_checked where reject_reason is null)),
       'kept earliest delivery'
union all
select 'restated_lines_resolved', count(*), 'kept highest record_version'
from silver.sales_lines where was_restated
union all
select 'late_rows_reassigned', count(*), 'assigned to invoice month, not file month'
from silver.sales_lines where arrived_late
union all
select 'valid_return_lines_kept', count(*), 'negative qty kept (txn_type = RETURN)'
from silver.sales_lines where txn_type = 'RETURN'
union all
select 'clean_lines', count(*), 'passed to gold' from silver.sales_lines;
