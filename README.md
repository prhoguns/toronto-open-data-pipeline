# Toronto Open Data Pipeline

_Portfolio sprint timeline: January–September 2026. Reported results retain their actual run dates._

A production-style ELT pipeline that pulls City of Toronto open data (police Major Crime
Indicators, TTC subway delays, neighbourhood boundaries and 2021 census profiles) into
PostgreSQL, models it with dbt into a star schema, tests it, and schedules it with Airflow.
The marts feed a Power BI report on crime rates per 1,000 residents and TTC delay hotspots.

**Stack:** Python 3.12 · PostgreSQL 16 · dbt 1.9 · Apache Airflow 2.10 · scikit-learn · FastAPI · Docker Compose · Power BI

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

## Delay prediction model (ml/ and api/)

On top of the marts: a model that gives the probability of a **5-minute-plus subway delay on a given
line in a given hour**, from time-of-day, weekday, month and hourly weather (Open-Meteo, free).
It is retrained by the Airflow DAG after every successful `dbt test` — continuous training — and
served by FastAPI, which pulls the weather forecast for the requested hour.

```bash
docker compose run --rm pipeline python -m ml.train       # ~10 s; writes models/ttc_delay.joblib + metrics.json
docker compose --profile api up api                        # http://localhost:8000/docs
curl "localhost:8000/predict?line=YU&at=2026-09-22T08:00"
# {"line":"YU","at":"2026-09-22T08:00:00","p_delay_5min":0.268,"weather":{"temperature_2m":8.0,...}}
curl "localhost:8000/predict?line=SHP&at=2026-09-22T17:00&weather={\"snowfall\":5}"   # what-if
```

Evaluation is a **time-based holdout** (last 90 days), against the baseline a dashboard would show —
the historical rate for that (line, weekday, hour):

| | ROC-AUC | PR-AUC | Brier |
|---|---:|---:|---:|
| Gradient boosting: time + weather | 0.752 | 0.262 | 0.103 |
| + last 1 h / 24 h of delays on the line (experiment, not served) | 0.751 | 0.263 | 0.103 |
| Baseline: historical rate per line × weekday × hour | 0.749 | 0.279 | 0.104 |

**The honest reading:** the model does not beat the baseline. At hourly granularity, subway delay
risk is almost entirely a function of line and time of day; weather and recent history add nothing
measurable. That is a real result about the data — subway delays are dominated by passenger and
equipment incidents that weather does not predict — and it is why the project reports the baseline
instead of quoting the AUC alone. What would move the number: station-level targets, the delay
*code* as the thing to predict, and TTC service-alert text as a feature. What the project
demonstrates regardless: a training set built from the warehouse, a leakage-safe split, a saved
model with tracked metrics, retraining wired into the orchestrator, and a service that consumes it.

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

The Airflow container writes to `data/` and `models/`; on Linux make them writable first: `chmod -R a+rwX data models`.

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
ml/                training frame from the marts + weather, model training with time-based evaluation
api/               FastAPI prediction service
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

- [x] Retrain a delay model as the last DAG step; serve it with FastAPI
- [ ] Add `dbt source freshness` check to the DAG
- [ ] Publish dbt docs to GitHub Pages
- [ ] Azure version: ADF → ADLS → Databricks → Synapse (see [azure-toronto-data-platform](https://github.com/prhoguns/azure-toronto-data-platform))

## Acknowledgments

AI tools assisted with documentation and repository organization.
