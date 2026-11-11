-- 04_dims.sql: dimensions (gold). staging.dim_date is built in Python (Hijri conversion) and loaded first.

create or replace table gold.dim_territory as
select territory_code, country, region, potential_diabetics,
       potential_diabetics / sum(potential_diabetics) over () as potential_share
from bronze.territories;

create or replace table gold.dim_rep as
select rep_id, territory_code, cast(start_date as date) as start_date, cast(end_date as date) as end_date
from bronze.reps;

create or replace table gold.dim_product as
select product_code, product_name, lifecycle, molecule_class,
       cast(list_price_sar as decimal(12,2)) as list_price_sar,
       cast(launch_month as date) as launch_month,
       cast(generic_entry_month as date) as generic_entry_month
from bronze.products;

create or replace table gold.dim_date as
select * from staging.dim_date;

-- Monthly calendar used by forecasting features.
create or replace table gold.dim_month as
select
    month_start,
    year(month_start) as year,
    month(month_start) as month,
    count(*) as days_in_month,
    sum(is_ramadan::int) as ramadan_days,
    sum(is_pre_ramadan::int) as pre_ramadan_days,
    sum(is_eid::int) as eid_days,
    sum(is_workday_ksa::int) as workdays_ksa,
    sum(is_workday_uae::int) as workdays_uae,
    sum(is_holiday_ksa::int) as holidays_ksa,
    sum(is_holiday_uae::int) as holidays_uae
from gold.dim_date
group by month_start
order by month_start;
