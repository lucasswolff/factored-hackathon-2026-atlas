# Load the CSV datasets into Snowflake

The scripts create `FACTORED_ANALYTICS` with four schemas and 13 tables. The
tables initially store CSV values as `VARCHAR` so missing and mixed values load
reliably. Cast values in analysis queries with functions such as `TRY_TO_DATE`
and `TRY_TO_DECIMAL`.

## Run order

1. In a Snowflake worksheet, run `00_account.sql` as `ACCOUNTADMIN`. Before
   running it, replace `<CHOOSE_A_STRONG_TEMPORARY_PASSWORD>` with a temporary
   password. This creates `FACTORED_USER`, `FACTORED_ANALYST`, and the X-Small
   `FACTORED_WH` warehouse. The user changes the password at first login.
2. Copy `01_setup.sql` into a Snowflake worksheet. In the worksheet copy, replace
   `<AWS_ACCESS_KEY_ID>` and `<AWS_SECRET_ACCESS_KEY>` with the supplied read-only
   AWS credentials. Replace `<PATH_TO_CSV_ROOT>` with the path inside the bucket
   that contains `branches.csv`, `customers.csv`, and the partitioned folders.
   For example, if the key is `factored-data/branches.csv`, use `factored-data`.
   If the CSVs are at the bucket root, delete `<PATH_TO_CSV_ROOT>/` so the URL
   ends in `/` after the bucket name. The bucket name is already set in the SQL;
   its region is `us-east-2`.
3. Run the edited worksheet copy of `01_setup.sql` as `ACCOUNTADMIN`. It creates
   the schemas, tables, file format, and external stage, then grants the analyst
   role access to query and load the tables.
4. Connect as `FACTORED_USER` and check the stage:

   ```sql
   USE ROLE FACTORED_ANALYST;
   USE WAREHOUSE FACTORED_WH;
   USE DATABASE FACTORED_ANALYTICS;
   LIST @CORE.SOURCE_S3;
   ```

   Confirm that the listing includes `branches.csv` and the dataset folders.
   Then run `02_load.sql` as `FACTORED_USER`.

The SQL files in this folder contain placeholders, not AWS keys. Snowflake
supports `AWS_KEY_ID` and `AWS_SECRET_KEY` on an S3 external stage; see its
[CREATE STAGE documentation](https://docs.snowflake.com/en/sql-reference/sql/create-stage).

Check a loaded table with:

```sql
SELECT COUNT(*) FROM FACTORED_ANALYTICS.CORE.DAILY_EXCHANGE_RATES;
SELECT TRY_TO_DATE(date) AS rate_date,
       TRY_TO_DECIMAL(exchange_rate, 20, 10) AS rate
FROM FACTORED_ANALYTICS.CORE.DAILY_EXCHANGE_RATES
LIMIT 10;
```

After loading, [`03_audit.sql`](03_audit.sql) can reproduce the counts, joins, quality checks, and dispute baseline from the [local CSV audit](../docs/data_audit.md) as `FACTORED_USER`. The audit is read-only.

`COPY INTO` ordinarily skips files already loaded into the same table. The
account and table creation commands preserve existing objects and data.
