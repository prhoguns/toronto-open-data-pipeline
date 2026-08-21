# Walkthrough: how this pipeline works, piece by piece

Read this top to bottom once, then rebuild the project from an empty folder without looking.
That is the fastest way to be able to explain it in an interview.

## 1. The shape of the problem

The City of Toronto publishes datasets on a CKAN portal. CKAN is open-source data-portal
software; every dataset is a *package*, and each file or table inside it is a *resource*.
Two kinds of resource matter here:

- **Static files** (CSV, XLSX) – you ask CKAN for the package, find the resource, and download its URL.
- **Datastore resources** – CKAN holds the rows in its own database and you query them with
  `datastore_search`, 32,000 rows per call, paging with `offset`.

`pipeline/ckan.py` wraps both. `package_show` → `find_resource` → `download` or `iter_datastore`.

**Interview question you should be able to answer:** *Why page with offset instead of downloading the CSV?*
Because the "since 2025" TTC resource is only offered as a live datastore; there is no file.

## 2. Extract (`pipeline/extract.py`)

One function per dataset would be repetitive, so `config.py` describes each dataset with a
`DatasetSpec` (package id, resource name, datastore yes/no, target table). `extract_one`
reads the spec and does the right thing.

The census workbook is the awkward one: 2,600 metric rows × 158 neighbourhood columns.
`_profiles_xlsx_to_csv` *unpivots* it into `(neighbourhood_number, name, metric, value)`.
Long format means the loader does not need to know anything about census metrics.

Files land as `data/raw/<table>_<YYYYMMDD>.csv`. If the file for today exists, extract skips it.

## 3. Load (`pipeline/load.py`)

`COPY` is PostgreSQL's bulk-load command; it is 10–50× faster than `INSERT`. psycopg 3
streams the file straight into `cur.copy(...)`.

Every column is `TEXT`. This is deliberate: type casting in the loader means a single bad
value ("N/A" in a numeric column) kills the whole batch. Casting in dbt means the batch
lands and a *test* fails, which you can look at.

Idempotency: the first version did `DROP TABLE` then `CREATE`. It worked once. On the
second run Postgres refused because dbt's staging *views* depend on the raw tables.
The fix compares the incoming columns with `information_schema.columns`: same shape →
`TRUNCATE` and keep the table; different shape → `DROP … CASCADE` (dbt recreates the views
on its next `run`). Be ready to tell this story; it is what "production-minded" sounds like.

## 4. dbt (`dbt/`)

dbt turns `SELECT` statements into tables/views, in dependency order, with tests.

- `models/sources.yml` declares the raw tables so models can `{{ source('raw', 'x') }}`.
- **Staging** (`stg_*`, views): cast types, trim strings, rename to snake_case, *no business logic*.
- **Marts** (tables): a star schema.
  - `dim_date` is generated with `generate_series` – no source needed.
  - `dim_neighbourhood` joins boundaries to the pivoted census metrics.
  - `fct_crime_incidents` is the grain of the source (one row per offence per event) with a
    single business rule: exclude occurrences before 2014.
  - `agg_*` tables pre-aggregate for dashboards, including *rate per 1,000 residents*.
- **Tests**: `unique`, `not_null`, `accepted_values`, `relationships` in `schema.yml`, plus
  custom generic tests (`macros/test_*.sql`) and singular tests (`tests/*.sql`).
- `macros/generate_schema_name.sql` overrides dbt's default of prefixing schemas
  (`public_staging`) so you get clean `staging` / `marts` schemas.

Run `dbt docs generate && dbt docs serve` inside the container to see the lineage graph.

**Interview question:** *Why views for staging and tables for marts?* Views cost nothing to
build and always reflect raw; marts are queried by BI tools so they are materialized.

## 5. Airflow (`airflow/dags/toronto_open_data.py`)

The DAG uses the TaskFlow API (`@task`) for Python steps and `BashOperator` for dbt.
`extract_x >> load_x` for each dataset in parallel, then `dbt_seed >> dbt_run >> dbt_test`.
Retries and an SLA are set in `default_args`. `catchup=False` so enabling the DAG does not
backfill every day since `start_date`.

`Dockerfile.airflow` builds an image with the pipeline package and dbt installed so tasks run
in-process. `airflow dags test <dag> <date>` executes a whole run without a scheduler – good for CI.

## 6. Things to say when asked "what would you do next"

- Add `dbt source freshness` and alert on stale sources.
- Store raw files in object storage (S3/ADLS) instead of the local disk, partitioned by date.
- Switch `fct_crime_incidents` to an incremental model keyed on `event_id` once volume justifies it.
- Add a Great Expectations or dbt-expectations suite for distribution checks (e.g. rows per month ± 3σ).
- Move secrets out of `.env.example` into a secrets manager.

## 7. Rebuild it yourself – checklist

1. `docker compose up -d postgres`
2. Write `ckan.py` and get `package_show` working in a Python shell.
3. Download one CSV. Write `load_csv` for it. Query it in psql.
4. `dbt init`, point `profiles.yml` at the container, write one staging model, `dbt run`.
5. Add tests. Break one on purpose. Read the failure.
6. Add the second dataset. Then the third.
7. Write the DAG. Run `airflow dags test`.
8. Write the README last, with real numbers from your own run.
