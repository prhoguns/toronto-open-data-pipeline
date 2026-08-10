"""Central configuration. Everything comes from environment variables with sane defaults."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

CKAN_BASE_URL = "https://ckan0.cf.opendata.inter.prod-toronto.ca/api/3/action"


@dataclass(frozen=True)
class DatasetSpec:
    """One source dataset on the City of Toronto open data portal.

    ``package_id`` is the CKAN package slug. ``resource_name`` picks a single
    resource inside the package. ``datastore`` says whether to page through the
    CKAN datastore API (for "live" resources) or download the file directly.
    """

    key: str
    package_id: str
    resource_name: str
    datastore: bool = False
    raw_table: str = ""

    @property
    def table(self) -> str:
        return self.raw_table or self.key


DATASETS: dict[str, DatasetSpec] = {
    "crime": DatasetSpec(
        key="crime",
        package_id="major-crime-indicators",
        resource_name="major-crime-indicators.csv",
        raw_table="major_crime_indicators",
    ),
    "ttc": DatasetSpec(
        key="ttc",
        package_id="ttc-subway-delay-data",
        resource_name="TTC Subway Delay Data since 2025",
        datastore=True,
        raw_table="ttc_subway_delays",
    ),
    "neighbourhoods": DatasetSpec(
        key="neighbourhoods",
        package_id="neighbourhoods",
        resource_name="Neighbourhoods - 4326.csv",
        raw_table="neighbourhoods",
    ),
    "profiles": DatasetSpec(
        key="profiles",
        package_id="neighbourhood-profiles",
        resource_name="neighbourhood-profiles-2021-158-model",
        raw_table="neighbourhood_profiles",
    ),
}


@dataclass(frozen=True)
class DbConfig:
    host: str = os.getenv("POSTGRES_HOST", "localhost")
    port: int = int(os.getenv("POSTGRES_PORT", "5433"))
    dbname: str = os.getenv("POSTGRES_DB", "toronto")
    user: str = os.getenv("POSTGRES_USER", "toronto")
    password: str = os.getenv("POSTGRES_PASSWORD", "toronto")

    @property
    def dsn(self) -> str:
        return (
            f"host={self.host} port={self.port} dbname={self.dbname} "
            f"user={self.user} password={self.password}"
        )


RAW_DIR = Path(os.getenv("RAW_DIR", "data/raw"))
RAW_SCHEMA = "raw"
