"""Daily DAG: extract Toronto open data -> load to Postgres -> dbt build.

Each dataset extracts and loads in parallel; dbt runs once everything has landed.
Retries and a 2-hour SLA are set because the City's CKAN portal is occasionally slow.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta

from airflow.decorators import dag, task
from airflow.operators.bash import BashOperator

DBT_DIR = os.getenv("DBT_PROFILES_DIR", "/app/dbt")

default_args = {
    "owner": "philips",
    "retries": int(os.getenv("PIPELINE_TASK_RETRIES", "2")),
    "retry_delay": timedelta(minutes=10),
    "sla": timedelta(hours=2),
}


@dag(
    dag_id="toronto_open_data",
    schedule="0 6 * * *",  # 06:00 daily, after the City's overnight refresh
    start_date=datetime(2026, 9, 1),
    catchup=False,
    default_args=default_args,
    max_active_runs=1,
    tags=["toronto", "open-data", "dbt"],
)
def toronto_open_data():
    from pipeline.config import DATASETS

    @task
    def extract(key: str, ds: str | None = None) -> str:
        from datetime import date

        from pipeline.extract import extract_one

        return str(extract_one(DATASETS[key], date.fromisoformat(ds)))

    @task
    def load(key: str, path: str) -> int:
        from pathlib import Path

        from pipeline.load import load_csv

        return load_csv(Path(path), DATASETS[key].table)

    dbt_seed = BashOperator(
        task_id="dbt_seed",
        bash_command=f"dbt seed --project-dir {DBT_DIR} --profiles-dir {DBT_DIR}",
    )
    dbt_run = BashOperator(
        task_id="dbt_run",
        bash_command=f"dbt run --project-dir {DBT_DIR} --profiles-dir {DBT_DIR}",
    )
    dbt_test = BashOperator(
        task_id="dbt_test",
        bash_command=f"dbt test --project-dir {DBT_DIR} --profiles-dir {DBT_DIR}",
    )

    loads = []
    for key in DATASETS:
        extracted = extract.override(task_id=f"extract_{key}")(key)
        loads.append(load.override(task_id=f"load_{key}")(key, extracted))

    loads >> dbt_seed >> dbt_run >> dbt_test


toronto_open_data()
