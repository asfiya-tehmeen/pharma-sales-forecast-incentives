-- 01_load.sql: load raw files exactly as delivered (bronze). No cleaning here.
-- {raw} is replaced with the absolute path to data/raw by warehouse.py.

create schema if not exists bronze;

create or replace table bronze.sales_feed as
select *
from read_csv('{raw}/feed/sales_*.csv',
    header = true,
    filename = true,
    columns = {
        'file_id': 'VARCHAR', 'delivered_on': 'DATE', 'invoice_id': 'VARCHAR', 'line_no': 'INTEGER',
        'record_version': 'INTEGER', 'invoice_date': 'DATE', 'territory_code': 'VARCHAR',
        'product_code': 'VARCHAR', 'txn_type': 'VARCHAR', 'qty': 'INTEGER',
        'unit_price': 'DECIMAL(12,2)', 'net_value': 'DECIMAL(14,2)'
    });

create or replace table bronze.territories as select * from read_csv('{raw}/master/territories.csv', header = true);
create or replace table bronze.reps        as select * from read_csv('{raw}/master/reps.csv', header = true);
create or replace table bronze.products    as select * from read_csv('{raw}/master/products.csv', header = true);
create or replace table bronze.targets     as select * from read_csv('{raw}/master/targets_2025.csv', header = true);
