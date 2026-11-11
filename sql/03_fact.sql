-- 03_fact.sql: monthly fact tables (gold). Grain: territory x product x month.
-- Every territory x product x month in the window is present (zero-filled), so gaps are explicit.

create schema if not exists gold;

create or replace table gold.fact_sales as
with months as (
    select cast(range as date) as month_start
    from range(date '2023-01-01', date '2026-01-01', interval 1 month)
),
grid as (
    select t.territory_code, p.product_code, m.month_start
    from bronze.territories t cross join bronze.products p cross join months m
),
agg as (
    select territory_code, product_code, month_start,
           sum(qty) as units_net,
           sum(case when txn_type = 'SALE' then qty else 0 end) as units_gross,
           -sum(case when txn_type = 'RETURN' then qty else 0 end) as units_returned,
           sum(net_value) as value_net
    from silver.sales_lines
    group by all
)
select
    g.territory_code, g.product_code, g.month_start,
    r.rep_id,                                   -- null = territory vacant that month
    coalesce(a.units_net, 0)       as units_net,
    coalesce(a.units_gross, 0)     as units_gross,
    coalesce(a.units_returned, 0)  as units_returned,
    coalesce(a.value_net, 0)       as value_net
from grid g
left join agg a using (territory_code, product_code, month_start)
left join bronze.reps r
    on r.territory_code = g.territory_code
   and g.month_start between r.start_date and r.end_date
order by 1, 2, 3;

create or replace table gold.fact_targets as
select
    t.territory_code, t.product_code, cast(t.month_start as date) as month_start,
    r.rep_id,
    cast(t.target_value as decimal(14,2)) as target_value
from bronze.targets t
left join bronze.reps r
    on r.territory_code = t.territory_code
   and t.month_start between r.start_date and r.end_date;
