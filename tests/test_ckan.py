import pytest

from pipeline.ckan import CkanClient
from pipeline.config import DATASETS
from pipeline.extract import _profiles_xlsx_to_csv, raw_path
from pipeline.load import _clean_ident


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def test_find_resource_returns_matching_resource(monkeypatch):
    client = CkanClient()
    payload = {
        "success": True,
        "result": {"resources": [{"name": "a", "id": "1"}, {"name": "b", "id": "2"}]},
    }
    monkeypatch.setattr(client.session, "get", lambda *a, **k: FakeResponse(payload))
    assert client.find_resource("pkg", "b")["id"] == "2"


def test_find_resource_missing_raises(monkeypatch):
    client = CkanClient()
    payload = {"success": True, "result": {"resources": [{"name": "a", "id": "1"}]}}
    monkeypatch.setattr(client.session, "get", lambda *a, **k: FakeResponse(payload))
    with pytest.raises(KeyError):
        client.find_resource("pkg", "zzz")


def test_iter_datastore_pages_until_total(monkeypatch):
    client = CkanClient()
    pages = iter(
        [
            {
                "success": True,
                "result": {"records": [{"_id": 1}, {"_id": 2}], "total": 3},
            },
            {"success": True, "result": {"records": [{"_id": 3}], "total": 3}},
        ]
    )
    monkeypatch.setattr(client.session, "get", lambda *a, **k: FakeResponse(next(pages)))
    assert [r["_id"] for r in client.iter_datastore("rid", page_size=2)] == [1, 2, 3]


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("EVENT_UNIQUE_ID", "event_unique_id"),
        ("Min Delay", "min_delay"),
        ("2021 Pop", "c_2021_pop"),
        ("  ", "col"),
    ],
)
def test_clean_ident(raw, expected):
    assert _clean_ident(raw) == expected


def test_raw_path_is_date_stamped(tmp_path):
    from datetime import date

    p = raw_path(DATASETS["crime"], date(2026, 1, 2), tmp_path)
    assert p.name == "major_crime_indicators_20260102.csv"


def test_profiles_unpivot(tmp_path):
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "hd2021_census_profile"
    ws.append(["Neighbourhood Name", "A", "B"])
    ws.append(["Neighbourhood Number", 1, 2])
    ws.append(["Total - Age groups of the population - 25% sample data", 100, 200])
    ws.append([None, None, None])
    xlsx = tmp_path / "p.xlsx"
    wb.save(xlsx)
    out = tmp_path / "p.csv"
    n = _profiles_xlsx_to_csv(xlsx, out)
    assert n == 2
    assert out.read_text().splitlines()[1] == "1,A,Total - Age groups of the population - 25% sample data,100"
