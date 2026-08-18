"""Command-line entry point.

python -m pipeline.cli extract            # download all sources for today
python -m pipeline.cli load               # COPY today's files into Postgres
python -m pipeline.cli run                # extract + load + dbt build
python -m pipeline.cli extract --only crime ttc
"""

from __future__ import annotations

import argparse
import logging
import os
import subprocess
import sys
from datetime import date

from pipeline.config import DATASETS
from pipeline.extract import extract_all, raw_path
from pipeline.load import load_csv

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)
log = logging.getLogger("pipeline")


def cmd_extract(args: argparse.Namespace) -> None:
    extract_all(args.run_date, args.only)


def cmd_load(args: argparse.Namespace) -> None:
    total = 0
    for key in args.only or DATASETS:
        spec = DATASETS[key]
        total += load_csv(raw_path(spec, args.run_date), spec.table)
    log.info("load complete: %s rows total", f"{total:,}")


def cmd_dbt(args: argparse.Namespace) -> None:
    dbt_dir = os.getenv("DBT_PROFILES_DIR", "dbt")
    for step in ("seed", "run", "test"):
        cmd = ["dbt", step, "--project-dir", dbt_dir, "--profiles-dir", dbt_dir]
        log.info("$ %s", " ".join(cmd))
        subprocess.run(cmd, check=True)


def cmd_run(args: argparse.Namespace) -> None:
    cmd_extract(args)
    cmd_load(args)
    cmd_dbt(args)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pipeline")
    parser.add_argument("--run-date", type=date.fromisoformat, default=date.today())
    parser.add_argument(
        "--only", nargs="+", choices=list(DATASETS), help="subset of datasets"
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("extract").set_defaults(func=cmd_extract)
    sub.add_parser("load").set_defaults(func=cmd_load)
    sub.add_parser("dbt").set_defaults(func=cmd_dbt)
    sub.add_parser("run").set_defaults(func=cmd_run)
    args = parser.parse_args(argv)
    args.func(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
