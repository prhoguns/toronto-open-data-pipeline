"""Extract step: pull each dataset from CKAN into data/raw/ as CSV.

Files are date-stamped so a failed load can be re-run without re-downloading,
and so you can diff two days' snapshots if the source changes shape.
"""

from __future__ import annotations

import csv
import logging
from datetime import date
from pathlib import Path

import openpyxl

from pipeline.ckan import CkanClient
from pipeline.config import DATASETS, RAW_DIR, DatasetSpec

log = logging.getLogger(__name__)


def raw_path(spec: DatasetSpec, run_date: date, raw_dir: Path = RAW_DIR) -> Path:
    return raw_dir / f"{spec.table}_{run_date:%Y%m%d}.csv"


def _datastore_to_csv(client: CkanClient, resource_id: str, dest: Path) -> int:
    dest.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with dest.open("w", newline="", encoding="utf-8") as fh:
        writer: csv.DictWriter | None = None
        for rec in client.iter_datastore(resource_id):
            if writer is None:
                writer = csv.DictWriter(fh, fieldnames=list(rec.keys()))
                writer.writeheader()
            writer.writerow(rec)
            n += 1
    return n


def _profiles_xlsx_to_csv(xlsx: Path, dest: Path) -> int:
    """Unpivot the 2021 census profile workbook (metrics as rows, neighbourhoods as
    columns) into a long table: neighbourhood_number, neighbourhood_name, metric, value.

    Long format keeps the loader dumb and lets dbt decide which of the ~2,600
    metrics matter.
    """
    wb = openpyxl.load_workbook(xlsx, read_only=True)
    ws = wb["hd2021_census_profile"]
    rows = ws.iter_rows(values_only=True)
    names = next(rows)[1:]
    numbers = next(rows)[1:]
    n = 0
    with dest.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["neighbourhood_number", "neighbourhood_name", "metric", "value"])
        for row in rows:
            metric = row[0]
            if metric is None:
                continue
            metric = str(metric).strip()
            for num, name, val in zip(numbers, names, row[1:], strict=False):
                if num is None:
                    continue
                w.writerow([num, name, metric, val])
                n += 1
    return n


def extract_one(
    spec: DatasetSpec,
    run_date: date,
    client: CkanClient | None = None,
    raw_dir: Path = RAW_DIR,
) -> Path:
    client = client or CkanClient()
    dest = raw_path(spec, run_date, raw_dir)
    if dest.exists():
        log.info("%s already extracted for %s, skipping", spec.key, run_date)
        return dest

    res = client.find_resource(spec.package_id, spec.resource_name)
    if spec.datastore:
        n = _datastore_to_csv(client, res["id"], dest)
        log.info("%s: %d rows via datastore", spec.key, n)
    elif res["format"].upper() == "XLSX":
        tmp = dest.with_suffix(".xlsx")
        client.download(res["url"], tmp)
        n = _profiles_xlsx_to_csv(tmp, dest)
        tmp.unlink()
        log.info("%s: %d rows unpivoted from xlsx", spec.key, n)
    else:
        client.download(res["url"], dest)
    return dest


def extract_all(
    run_date: date | None = None, keys: list[str] | None = None
) -> dict[str, Path]:
    run_date = run_date or date.today()
    client = CkanClient()
    out = {}
    for key in keys or DATASETS:
        out[key] = extract_one(DATASETS[key], run_date, client)
    return out
