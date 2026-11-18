import io
import json

import openpyxl
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.database import Base, get_db
from backend.app.routes.datasets import router as datasets_router
from backend.app.services import dataset_analysis_service as svc

CSV = (
    "id;name;value;flag;when\n"
    "1; alpha ;10;yes;2024-01-01\n"
    "2;beta;12;no;2024-01-02\n"
    "3;gamma;;yes;2024-01-03\n"
    "4;delta;11;no;2024-01-04\n"
    "5;alpha;1000;yes;2024-01-05\n"
    "5;alpha;1000;yes;2024-01-05\n"
    "6;beta;13;no;2024-01-06\n"
    "7;beta;9;yes;2024-01-07\n"
    "8;gamma;10;no;2024-01-08\n"
    "9;gamma;11;yes;2024-01-09\n"
    "10;delta;12;no;2024-01-10\n"
    "11;delta;13;yes;2024-01-11\n"
    "12;alpha;14;no;2024-01-12\n"
).encode("cp1252")


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(svc, "DATASET_DIR", tmp_path)
    svc._frame_cache.clear()
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    app = FastAPI()
    app.include_router(datasets_router)

    def override():
        db = factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override
    yield TestClient(app)
    engine.dispose()


def upload(client, data=CSV, name="mesures.csv"):
    response = client.post("/api/datasets/upload", files={"file": (name, data, "text/csv")})
    assert response.status_code == 200, response.text
    return response.json()


def test_upload_preview_and_list(client):
    summary = upload(client)
    assert summary["rows"] == 13 and summary["columns"] == 5
    assert summary["column_names"] == ["id", "name", "value", "flag", "when"]
    listed = client.get("/api/datasets").json()
    assert [item["id"] for item in listed] == [summary["id"]]
    preview = client.get(f"/api/datasets/{summary['id']}/preview?page=1&page_size=3").json()
    assert preview["total"] == 13 and len(preview["rows"]) == 3
    assert preview["rows"][2][2] is None  # NaN serialised as null
    json.dumps(preview, allow_nan=False)


def test_profile_detects_types_missing_outliers_duplicates(client):
    dataset_id = upload(client)["id"]
    response = client.get(f"/api/datasets/{dataset_id}/profile")
    assert response.status_code == 200
    profile = response.json()
    json.dumps(profile, allow_nan=False)
    columns = {c["name"]: c for c in profile["columns"]}
    assert columns["value"]["dtype"] == "numeric"
    assert columns["flag"]["dtype"] == "boolean"
    assert columns["when"]["dtype"] == "datetime"
    assert columns["name"]["dtype"] == "categorical"
    assert columns["value"]["missing"] == 1
    assert columns["value"]["outliers"] == 2
    assert set(columns["value"]["stats"]) == {"mean", "std", "min", "q1", "median", "q3", "max"}
    assert 10 <= len(columns["value"]["histogram"]) <= 20
    assert profile["duplicates"] == 1
    assert profile["correlation"]["columns"] == ["id", "value"]
    assert len(profile["correlation"]["matrix"]) == 2
    kinds = {s["kind"] for s in profile["suggestions"]}
    assert {"drop_duplicates", "fill_missing", "remove_outliers", "trim_whitespace"} <= kinds


def test_clean_creates_derived_dataset_and_exports(client):
    dataset_id = upload(client)["id"]
    response = client.post(
        f"/api/datasets/{dataset_id}/clean",
        json={
            "drop_duplicates": True,
            "drop_empty_rows": True,
            "fill_missing": {"value": "median"},
            "trim_whitespace": True,
            "remove_outliers": ["value"],
        },
    )
    assert response.status_code == 200, response.text
    derived = response.json()
    assert derived["id"] != dataset_id and derived["parent_id"] == dataset_id
    assert derived["rows"] == 11  # both outlier rows (incl. duplicate) removed, NaN filled
    profile = client.get(f"/api/datasets/{derived['id']}/profile").json()
    value = {c["name"]: c for c in profile["columns"]}["value"]
    assert value["missing"] == 0 and profile["duplicates"] == 0
    names = {c["name"]: c for c in profile["columns"]}["name"]
    assert all(v["value"] == v["value"].strip() for v in names["top_values"])

    csv_export = client.get(f"/api/datasets/{derived['id']}/export?format=csv")
    assert csv_export.status_code == 200
    assert csv_export.content.decode().splitlines()[0] == "id,name,value,flag,when"
    xlsx = client.get(f"/api/datasets/{derived['id']}/export?format=xlsx")
    assert xlsx.status_code == 200
    sheet = openpyxl.load_workbook(io.BytesIO(xlsx.content)).active
    assert sheet.max_row == 12

    # roundtrip: re-upload the exported xlsx
    again = upload(client, xlsx.content, "clean.xlsx")
    assert again["rows"] == 11


def test_clean_rejects_unknown_column_and_delete(client):
    dataset_id = upload(client)["id"]
    bad = client.post(f"/api/datasets/{dataset_id}/clean", json={"remove_outliers": ["nope"]})
    assert bad.status_code == 422
    assert client.delete(f"/api/datasets/{dataset_id}").status_code == 204
    assert client.get(f"/api/datasets/{dataset_id}/profile").status_code == 404
    assert list(svc.DATASET_DIR.iterdir()) == []


def test_upload_rejections(client, monkeypatch):
    assert client.post("/api/datasets/upload", files={"file": ("x.txt", b"a,b", "text/plain")}).status_code == 415
    assert client.post("/api/datasets/upload", files={"file": ("x.xlsx", b"not a zip", "application/x")}).status_code == 400
    monkeypatch.setenv("MAX_DATASET_BYTES", "1024")
    big = b"a,b\n" + b"1,2\n" * 1000
    assert client.post("/api/datasets/upload", files={"file": ("big.csv", big, "text/csv")}).status_code == 413


def test_inf_and_all_nan_columns_serialise():
    import numpy as np
    import pandas as pd

    frame = pd.DataFrame({"a": [1.0, np.inf, -np.inf, 2.0], "b": [np.nan] * 4, "c": [1, 2, 3, 4]})
    profile = svc.profile(frame)
    json.dumps(profile, allow_nan=False)
