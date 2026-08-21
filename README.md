# Toronto Open Data Pipeline

A production-style ELT pipeline that pulls City of Toronto open data (police Major Crime
Indicators, TTC subway delays, neighbourhood boundaries and 2021 census profiles) into
PostgreSQL, models it with dbt into a star schema, tests it, and schedules it with Airflow.
The marts feed a Power BI report on crime rates per 1,000 residents and TTC delay hotspots.

**Stack:** Python 3.12 · PostgreSQL 16 · dbt 1.9 · Apache Airflow 2.10 · Docker Compose · Power BI

## Architecture

```mermaid
flowchart LR
    subgraph Source["open.toronto.ca (CKAN API)"]
        A1[Major Crime Indicators CSV<br/>452,949 rows]
        A2[TTC Subway Delays<br/>datastore, 45,475 rows]
        A3[Neighbourhoods 158 CSV]
        A4[Census Profiles 2021 XLSX]
    end
    subgraph Extract["pipeline/extract.py"]
        E[download / page datastore /<br/>unpivot xlsx → data/raw/*.csv]
    end
    subgraph Load["pipeline/load.py"]
        L[COPY → raw.* (all TEXT)]
    end
    subgraph dbt["dbt (11 models, 40 tests)"]
        S[staging views<br/>typed, trimmed]
        M[marts tables<br/>dim_date · dim_neighbourhood · dim_ttc_delay_code<br/>fct_crime_incidents · fct_ttc_delays<br/>agg_crime_monthly_neighbourhood · agg_ttc_delays_station_month]
    end
    P[Power BI]
    A1 & A2 & A3 & A4 --> E --> L --> S --> M --> P
    AF[Airflow DAG<br/>06:00 daily] -.orchestrates.-> E & L & S
```

Design decisions, and why:

| Decision | Reason |
|---|---|
| Land everything as `TEXT` in `raw` | A bad value in the source can never break a load. It fails a dbt test instead, where it's visible and explainable. |
| Full refresh, not incremental | The City republishes complete snapshots. Incremental logic would add complexity for no benefit at this volume (~1M rows, ~5 s to COPY). |
| Truncate-and-reload when the source shape is unchanged; `DROP … CASCADE` only if columns change | dbt views depend on the raw tables. The first version dropped the table every run and broke on the second run. |
| Census profile unpivoted to long format at extract time | ~2,600 metrics × 158 neighbourhoods. Long format keeps the loader generic; dbt picks the handful of metrics that matter. |
| Date-stamped raw files | A failed load can be re-run without re-downloading, and two days' snapshots can be diffed if the source changes. |
| Occurrences before 2014 excluded in the fact model (not staging) | The dataset includes late-reported historical cases that distort trends. Staging stays a faithful typed copy; the business rule lives in one place. |

## Results (run of 2026-09-22)

Pipeline run time end to end, on a laptop: **~40 seconds** (extract ~10 s, load ~5 s, dbt ~20 s).

| Table | Rows |
|---|---|
| `raw.*` (4 tables) | 909,698 |
| `marts.fct_crime_incidents` | 451,229 |
| `marts.fct_ttc_delays` | 45,475 |
| `marts.agg_crime_monthly_neighbourhood` | 81,839 |
| dbt tests | 40 passed, 0 failed |

Some things the marts show:

- **Auto theft** in Toronto went from 5,382 incidents (2019) to 12,520 (2023), then fell 23% to 9,610 in 2024.
- Highest 2024 crime rate per 1,000 residents: **Yonge-Bay Corridor (62.8)**, Mimico-Queensway (60.0), Downtown Yonge East (50.0). Rates use 2021 census population, so downtown cores with small resident counts but huge daytime populations rank high — a known limitation of per-resident rates.
- The **#1 cause of TTC subway delay minutes since 2025 is "Disorderly Patron"** (1,917 events, 12,141 minutes), ahead of any mechanical cause.
- **Eglinton Station** has the most total delay minutes on Line 1; Kipling and Kennedy lead Line 2.
- 4.9% of crimes are reported more than 30 days after they occurred.

## Quick start

Requirements: Docker with Compose v2. Nothing else.

```bash
git clone https://github.com/prhoguns/toronto-open-data-pipeline.git
cd toronto-open-data-pipeline
docker compose build
docker compose run --rm pipeline run        # extract → load → dbt seed/run/test
```

Postgres is exposed on `localhost:5433` (`toronto` / `toronto`). Connect Power BI, DBeaver or psql:

```bash
docker compose exec postgres psql -U toronto -d toronto -c "select * from marts.agg_ttc_delays_station_month order by total_delay_minutes desc limit 10"
```

Individual steps:

```bash
docker compose run --rm pipeline extract --only ttc     # one dataset
docker compose run --rm pipeline load
docker compose run --rm pipeline dbt
```

### Airflow

```bash
docker compose --profile airflow up airflow        # UI at http://localhost:8080 (admin password is printed in the logs)
```

Or run the DAG once, headless, exactly as the scheduler would:

```bash
docker compose --profile airflow run --rm airflow airflow dags test toronto_open_data 2026-09-22
```

### Tests and lint

```bash
docker compose run --rm --entrypoint bash pipeline -c "ruff check . && pytest"
```

## Project layout

```
pipeline/          extract (CKAN client), load (COPY), CLI
dbt/               sources, staging views, marts, seeds, custom tests, macros
airflow/dags/      toronto_open_data DAG (TaskFlow + BashOperator for dbt)
powerbi/           how to connect Power BI and the DAX measures used
docs/WALKTHROUGH.md step-by-step explanation of every piece
tests/             pytest unit tests (CKAN client, unpivot, identifier cleaning)
.github/workflows  CI: ruff + pytest + dbt compile on every push
```

## Data sources

- [Major Crime Indicators](https://open.toronto.ca/dataset/major-crime-indicators/) – Toronto Police Service
- [TTC Subway Delay Data](https://open.toronto.ca/dataset/ttc-subway-delay-data/) – Toronto Transit Commission
- [Neighbourhoods](https://open.toronto.ca/dataset/neighbourhoods/) and [Neighbourhood Profiles](https://open.toronto.ca/dataset/neighbourhood-profiles/) – City of Toronto

All data is published under the [Open Government Licence – Toronto](https://open.toronto.ca/open-data-license/).

## Roadmap

- [ ] Add `dbt source freshness` check to the DAG
- [ ] Publish dbt docs to GitHub Pages
- [ ] Azure version: ADF → ADLS → Databricks → Synapse (see [azure-toronto-data-platform](https://github.com/prhoguns/azure-toronto-data-platform))
