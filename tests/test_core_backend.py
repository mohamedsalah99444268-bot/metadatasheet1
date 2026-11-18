"""Core backend tests: migrations, units, spec persistence, graph routing,
components/specs/compare/stats/monitoring/ai endpoints."""
from __future__ import annotations

import os
import tempfile
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.agents.classification_agent import classify_category, classify_condition
from backend.app.agents.comparison_agent import compare
from backend.app.agents.graph import EXPECTED_NODES, get_job_state_from_db, run_workflow
from backend.app.agents.state import AgentEvent, SpecificationEvidence
from backend.app.agents.validation_agent import cross_check
from backend.app.database import Base, get_db, run_migrations
from backend.app.models import AgentRun, AnalysisJob, AppSetting, Component, ComponentSpec, Document, SpecReviewLog
from backend.app.routes.ai import router as ai_router
from backend.app.routes.compare import router as compare_router
from backend.app.routes.components import router as components_router
from backend.app.routes.monitoring import router as monitoring_router
from backend.app.routes.specs import router as specs_router
from backend.app.routes.stats import router as stats_router
from backend.app.services import component_service, job_service
from backend.app.services.units import parse_value


def ev(field, value, page=1, source=None, **kw):
    return SpecificationEvidence(
        field_name=field, value=value, page_number=page, source_text=source or value, confidence=0.9, **kw
    )


SAMPLE_REPORT = {
    "document_id": None,
    "component_reference": "LM358",
    "status": "needs_review",
    "specifications": [
        ev("manufacturer", "Texas Instruments", validation_status="validated").model_dump(mode="json"),
        ev("part_number", "LM358", validation_status="validated").model_dump(mode="json"),
        ev("package", "SOIC-8", validation_status="validated").model_dump(mode="json"),
        ev("pin_count", "8 pins", unit="pins").model_dump(mode="json"),
        ev("supply_voltage", "3 V to 32 V", unit="V", section="Recommended Operating Conditions").model_dump(mode="json"),
        ev("temperature_range", "-40 to 85 °C").model_dump(mode="json"),
        ev("current", "0.7 mA").model_dump(mode="json"),
    ],
    "validation_results": [],
    "warnings": [],
}


# ---------- migrations ----------

def test_alembic_upgrade_creates_new_tables_and_is_idempotent():
    with tempfile.TemporaryDirectory() as tmp:
        url = f"sqlite:///{os.path.join(tmp, 'm.db')}"
        run_migrations(url)
        run_migrations(url)  # second run is a no-op
        engine = create_engine(url)
        tables = set(inspect(engine).get_table_names())
        for name in ("components", "component_specs", "agent_runs", "spec_review_log", "app_settings", "analysis_jobs", "alembic_version"):
            assert name in tables
        with engine.connect() as conn:
            names = {r[0] for r in conn.exec_driver_sql("select name from sqlite_master where type='index'")}
        assert "uq_components_manufacturer_part" in names
        engine.dispose()


def test_migration_on_db_bootstrapped_with_create_all():
    with tempfile.TemporaryDirectory() as tmp:
        url = f"sqlite:///{os.path.join(tmp, 'legacy.db')}"
        engine = create_engine(url)
        Base.metadata.create_all(engine)
        engine.dispose()
        run_migrations(url)
        engine = create_engine(url)
        assert "components" in inspect(engine).get_table_names()
        engine.dispose()


# ---------- units / classification / validation ----------

@pytest.mark.parametrize(
    "text,expected",
    [
        ("2.0 V to 3.6 V", (2.0, None, 3.6, "V")),
        ("2.0V-3.6V", (2.0, None, 3.6, "V")),
        ("-40 to 85 °C", (-40.0, None, 85.0, "°C")),
        ("10 mA", (None, 0.01, None, "A")),
        ("72 MHz", (None, 72e6, None, "Hz")),
        ("48 pins", (None, 48.0, None, "pins")),
        ("-0.3 V", (None, -0.3, None, "V")),
        ("", (None, None, None, None)),
    ],
)
def test_parse_value(text, expected):
    p = parse_value(text)
    assert (p.min_value, p.typ_value, p.max_value, p.unit) == expected


def test_parse_value_kind_and_declared_unit():
    assert parse_value("3.6", "V", "maximum").max_value == 3.6
    assert parse_value("3.6", "V", "maximum").unit == "V"


def test_classification_rules():
    assert classify_category("supply_voltage") == "electrical"
    assert classify_category("temperature_range") == "thermal"
    assert classify_category("part_number") == "identity"
    assert classify_category("frequency") == "timing"
    assert classify_condition(ev("supply_voltage", "4 V", section="Absolute Maximum Ratings")) == "absolute_maximum"
    assert classify_condition(ev("supply_voltage", "3.3 V")) == "electrical_characteristics"


def test_validation_flags_contradictions():
    specs = [
        ev("supply_voltage", "4.0 V", unit="V", condition_type="absolute_maximum", category="electrical"),
        ev("operating_voltage", "2 V to 5.5 V", unit="V", condition_type="recommended_operating", category="electrical"),
        ev("current", "12 mA", source="typ 10 mA", category="electrical", condition_type="general"),
        ev("frequency", "72 V", category="timing", condition_type="general"),
    ]
    for s in specs:
        s.validation_status = "validated"
    reasons = {r.reason for r in cross_check(specs)}
    assert "absolute_maximum_below_operating_maximum" in reasons
    assert "value_not_found_in_source_text" in reasons
    assert any(r.startswith("implausible_unit") for r in reasons)
    assert specs[0].validation_status == "conflict"


def test_validation_min_typ_max_order():
    specs = [
        ev("supply_voltage", "3.6", unit="V", value_kind="minimum", condition_type="general", category="electrical"),
        ev("supply_voltage", "2.0", unit="V", value_kind="maximum", condition_type="general", category="electrical"),
    ]
    reasons = {r.reason for r in cross_check(specs)}
    assert "min_typ_max_order_violated" in reasons


# ---------- graph routing ----------

def _fake_extraction(specs, ollama=False):
    def apply(state):
        updated = dict(state)
        updated.update(extraction_ok=True, ollama_available=ollama, specifications=[s.model_copy() for s in specs])
        updated["events"] = list(state.get("events", [])) + [AgentEvent(agent="extraction", status="completed", message="ok")]
        return updated

    return apply


def test_graph_runs_classification_and_indexing_nodes():
    specs = [ev("manufacturer", "TI"), ev("part_number", "LM358"), ev("package", "SOIC-8"), ev("supply_voltage", "5 V", unit="V")]
    with patch("backend.app.agents.graph.run_extraction_agent", side_effect=_fake_extraction(specs)):
        result = run_workflow({"component_reference": "LM358", "document_id": 7})
    agents = [e.agent for e in result["events"]]
    assert agents.index("classification") < agents.index("validation") < agents.index("indexing") < agents.index("report")
    assert "ollama_unavailable" in agents
    assert all(s.category for s in result["report"].specifications)
    assert result["index_status"] == "skipped"


class DbCase:
    def setup_method(self):
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, autoflush=False, autocommit=False)
        self.app = FastAPI()
        for r in (components_router, specs_router, compare_router, stats_router, monitoring_router, ai_router):
            self.app.include_router(r)

        def override():
            db = self.Session()
            try:
                yield db
            finally:
                db.close()

        self.app.dependency_overrides[get_db] = override
        self.client = TestClient(self.app)

    def teardown_method(self):
        self.engine.dispose()


class TestGraphPersistence(DbCase):
    def test_agent_runs_rows_and_db_job_state(self):
        specs = [ev("manufacturer", "TI"), ev("part_number", "LM358"), ev("package", "SOIC-8")]
        with self.Session() as db:
            job = job_service.create_job(db, input_source="manual", component_reference="LM358", document_id=None, job_id="job-1")
            db.commit()
            with patch("backend.app.agents.graph.run_extraction_agent", side_effect=_fake_extraction(specs)), patch(
                "backend.app.agents.graph.research_node",
                side_effect=lambda s: {**s, "datasheet_found": True, "events": list(s.get("events", []))},
            ), patch(
                "backend.app.agents.graph.download_node",
                side_effect=lambda s: {**s, "download_ok": True, "events": list(s.get("events", []))},
            ):
                result = run_workflow({"job_id": "job-1", "component_reference": "LM358"}, db=db)
            job_service.update_job_from_state(db, "job-1", result)
            runs = db.query(AgentRun).filter_by(job_id="job-1").all()
            names = [r.agent for r in runs]
            for node in ("research", "download", "extraction", "classification", "validation", "indexing", "report"):
                assert node in names
            assert all(r.duration_ms is not None and r.status != "started" for r in runs)
            state = get_job_state_from_db(db, "job-1")
            assert state["status"] == job.status
            comp = db.query(Component).one()
            assert comp.part_number == "LM358" and comp.package == "SOIC-8"
        detail = self.client.get("/api/monitoring/jobs/job-1").json()
        assert detail["progress"] == 100 and len(detail["runs"]) >= len(EXPECTED_NODES)


# ---------- persistence ----------

class TestPersistence(DbCase):
    def test_persist_report_and_keep_reviewed(self):
        with self.Session() as db:
            comp = component_service.persist_report(db, SAMPLE_REPORT, job_id="j1")
            db.commit()
            specs = {s.parameter: s for s in db.query(ComponentSpec).all()}
            assert comp.manufacturer == "Texas Instruments" and comp.pin_count == 8 and comp.category == "op_amp"
            sv = specs["supply_voltage"]
            assert (sv.min_value, sv.max_value, sv.unit, sv.condition_type, sv.category) == (3.0, 32.0, "V", "recommended_operating", "electrical")
            assert specs["current"].typ_value == pytest.approx(0.0007)
            assert specs["manufacturer"].validation_status == "pending"
            sv.validation_status = "accepted"
            db.commit()
            component_service.persist_report(db, SAMPLE_REPORT, job_id="j2")
            db.commit()
            again = db.query(ComponentSpec).filter_by(parameter="supply_voltage").all()
            assert len(again) == 1 and again[0].validation_status == "accepted"
            assert db.query(Component).count() == 1

    def test_backfill(self):
        with self.Session() as db:
            db.add(AnalysisJob(job_id="a", thread_id="a", input_source="manual", status="needs_review", report=SAMPLE_REPORT))
            db.commit()
            assert component_service.backfill_if_empty(db) == 1
            assert component_service.backfill_if_empty(db) == 0


# ---------- endpoints ----------

class TestEndpoints(DbCase):
    def _seed(self):
        with self.Session() as db:
            doc = Document(original_filename="lm358.pdf", sha256="x" * 64, storage_path="/tmp/none.pdf", page_count=10)
            db.add(doc)
            db.flush()
            a = component_service.persist_report(db, {**SAMPLE_REPORT, "document_id": doc.id}, job_id="j1")
            other = {**SAMPLE_REPORT, "specifications": [dict(s) for s in SAMPLE_REPORT["specifications"]]}
            other["specifications"][1] = ev("part_number", "LM2904").model_dump(mode="json")
            other["specifications"][4] = ev("supply_voltage", "3 V to 26 V", unit="V").model_dump(mode="json")
            b = component_service.persist_report(db, other, job_id="j2")
            db.add(AnalysisJob(job_id="j1", thread_id="j1", input_source="manual", status="running", component_reference="LM358"))
            db.add(AgentRun(job_id="j1", agent="research", status="completed", attempt=1, duration_ms=12))
            db.commit()
            return a.id, b.id, doc.id

    def test_components_list_facets_detail_delete(self):
        a, b, doc_id = self._seed()
        page = self.client.get("/api/components", params={"q": "lm", "sort": "spec_count", "order": "desc", "page_size": 1}).json()
        assert page["total"] == 2 and len(page["items"]) == 1 and page["page_size"] == 1
        item = page["items"][0]
        assert {"spec_count", "accepted_count", "pending_count", "rejected_count", "document_name", "thumbnail_category"} <= set(item)
        assert self.client.get("/api/components", params={"sort": "bad"}).status_code == 422
        assert self.client.get("/api/components", params={"manufacturer": "texas instruments"}).json()["total"] == 2
        facets = self.client.get("/api/components/facets").json()
        assert facets["manufacturers"] == [{"value": "Texas Instruments", "count": 2}]
        detail = self.client.get(f"/api/components/{a}").json()
        assert detail["documents"][0]["name"] == "lm358.pdf"
        assert "missing_parameters" in detail and "supply_voltage" not in detail["missing_parameters"]
        assert detail["history"][0]["job_id"] == "j1"
        assert self.client.delete(f"/api/components/{b}").status_code == 204
        assert self.client.get(f"/api/components/{b}").status_code == 404
        with self.Session() as db:
            assert db.get(Document, doc_id) is not None

    def test_reanalyze_and_report(self):
        a, b, _ = self._seed()
        with patch("backend.app.worker.enqueue_job") as enqueue:
            r = self.client.post(f"/api/components/{a}/reanalyze")
        assert r.status_code == 200 and enqueue.called
        assert self.client.post(f"/api/components/{b}/reanalyze").status_code == 409
        rep = self.client.get(f"/api/components/{a}/report", params={"format": "json"})
        assert rep.status_code == 200 and b"LM358" in rep.content
        pdf = self.client.get(f"/api/components/{a}/report", params={"format": "pdf"})
        assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")

    def test_reanalyze_uses_original_user_reference(self):
        a, _, doc_id = self._seed()
        with self.Session() as db:
            db.add(AnalysisJob(job_id="orig", thread_id="orig", input_source="datasheet", status="completed",
                               manufacturer="Texas Instruments", component_reference="LM358", document_id=doc_id))
            db.get(Component, a).part_number = "UFQFPN48"  # identity corrupted by an earlier extraction
            db.commit()
        with patch("backend.app.worker.enqueue_job"):
            job_id = self.client.post(f"/api/components/{a}/reanalyze").json()["job_id"]
        with self.Session() as db:
            job = db.query(AnalysisJob).filter_by(job_id=job_id).one()
            assert job.component_reference == "LM358" and job.input_source == "reanalysis"

    def test_specs_review_flow(self):
        a, _, _ = self._seed()
        specs = self.client.get("/api/specs", params={"component_id": a, "category": "electrical"}).json()
        assert specs["total"] >= 1
        sid = next(s["id"] for s in specs["items"] if s["parameter"] == "supply_voltage")
        assert self.client.post(f"/api/specs/{sid}/accept", json={"comment": "ok"}).json()["validation_status"] == "accepted"
        assert self.client.post(f"/api/specs/{sid}/reject").json()["validation_status"] == "rejected"
        edited = self.client.patch(f"/api/specs/{sid}", json={"value_text": "3 V to 30 V", "comment": "typo"}).json()
        assert edited["validation_status"] == "edited" and edited["max_value"] == 30.0
        assert self.client.patch(f"/api/specs/{sid}", json={"min_value": 5, "max_value": 1}).status_code == 422
        added = self.client.post(
            f"/api/components/{a}/specs",
            json={"parameter": "uart", "category": "interface", "condition_type": "general", "value_text": "1x UART"},
        ).json()
        assert added["extraction_method"] == "manual" and added["validation_status"] == "accepted"
        log = self.client.get(f"/api/specs/{sid}/log").json()
        assert [e["action"] for e in log] == ["accept", "reject", "edit"]
        assert log[2]["old_value"]["value_text"] == "3 V to 32 V"
        assert self.client.post("/api/specs/99999/accept").status_code == 404
        with self.Session() as db:
            assert db.query(SpecReviewLog).count() == 4

    def test_compare_verdicts(self):
        a, b, _ = self._seed()
        res = self.client.post("/api/compare", json={"component_ids": [a, b]}).json()
        rows = {r["parameter"]: r for r in res["rows"]}
        assert rows["supply_voltage"]["verdict"] == "different"
        assert rows["package"]["verdict"] == "same"
        assert res["compatibility"]["voltage"]["status"] == "compatible"
        assert res["compatibility"]["package"]["status"] == "compatible"
        assert res["compatibility"]["interfaces"]["status"] == "insufficient_evidence"
        assert res["interchangeable"] == "insufficient_evidence"
        assert self.client.post("/api/compare", json={"component_ids": [a]}).status_code == 422
        assert self.client.post("/api/compare", json={"component_ids": [a, 999]}).status_code == 404

    def test_stats_and_monitoring(self):
        self._seed()
        stats = self.client.get("/api/stats/overview").json()
        assert stats["totals"]["components"] == 2 and stats["totals"]["documents"] == 1
        assert stats["totals"]["active_jobs"] == 1
        assert len(stats["analyses_over_time"]) == 30
        assert stats["agent_performance"][0]["agent"] == "research"
        assert sum(stats["validation"].values()) == stats["totals"]["specs"]
        jobs = self.client.get("/api/monitoring/jobs", params={"status": "active"}).json()
        assert jobs["total"] == 1 and jobs["items"][0]["current_agent"] == "research"
        assert 0 < jobs["items"][0]["progress"] < 100
        assert self.client.get("/api/monitoring/jobs/nope").status_code == 404

    def test_ai_models(self):
        from backend.app.ai.ollama_client import get_ollama_service

        service = get_ollama_service()
        with patch.object(type(service), "list_installed_models", return_value=[{"name": "qwen2.5:1.5b", "size": 1}]), patch(
            "backend.app.ai.ollama_client.get_configured_model", return_value="qwen2.5:1.5b"
        ):
            body = self.client.get("/api/ai/models").json()
            assert body["default"] == "qwen2.5:1.5b" and body["ollama_reachable"] is True
            assert self.client.put("/api/ai/model", json={"model": "llama3"}).status_code == 409
            assert self.client.put("/api/ai/model", json={"model": "qwen2.5:1.5b"}).status_code == 200
        with self.Session() as db:
            assert db.get(AppSetting, "ollama_model").value == "qwen2.5:1.5b"


def test_compare_never_interchangeable_without_review():
    comps = [{"id": i, "part_number": f"P{i}", "package": "SOIC-8", "pin_count": 8} for i in (1, 2)]
    spec = lambda p, lo, hi, unit, cat="electrical", st="pending": {  # noqa: E731
        "id": 0, "parameter": p, "label": p, "category": cat, "condition_type": "recommended_operating", "value_text": f"{lo}-{hi}",
        "unit": unit, "min_value": lo, "typ_value": None, "max_value": hi, "validation_status": st, "confidence": 1,
    }
    base = [spec("supply_voltage", 3, 5, "V"), spec("current", 0, 0.01, "A"), spec("temperature_range", -40, 85, "°C"),
            {**spec("uart", 0, 0, None, "interface"), "min_value": None, "max_value": None, "value_text": "1"},
            {**spec("package", 0, 0, None, "mechanical"), "min_value": None, "max_value": None, "value_text": "SOIC-8"},
            {**spec("pin_count", 8, 8, "pins", "mechanical")}]
    pending = compare(comps, [base, base])
    assert pending["interchangeable"] == "insufficient_evidence"
    accepted = [{**s, "validation_status": "accepted"} for s in base]
    assert compare(comps, [accepted, accepted])["interchangeable"] is True
    hot = [{**s, "min_value": 10, "max_value": 20} if s["parameter"] == "supply_voltage" else s for s in accepted]
    assert compare(comps, [accepted, hot])["interchangeable"] is False


def test_comparison_prefers_plausible_operating_temperature_and_current_aliases():
    from backend.app.agents.comparison_agent import best_specs

    specs = [
        {"id": 1, "parameter": "temperature_range", "min_value": 0.0, "max_value": 3.0, "unit": "°C",
         "condition_type": "recommended_operating", "validation_status": "pending", "confidence": 0.9},
        {"id": 2, "parameter": "operating_temperature", "min_value": -40.0, "max_value": 85.0, "unit": "°C",
         "condition_type": "recommended_operating", "validation_status": "pending", "confidence": 0.8},
    ]
    chosen = best_specs(specs)
    assert "temperature_range" not in chosen  # garbled "0 to 3 C" dropped
    assert chosen["operating_temperature"]["min_value"] == -40.0


def test_comparison_current_prefers_supply_current_and_temperature_needs_both_ends():
    from backend.app.agents.comparison_agent import CURRENT_PARAMS, best_specs

    assert CURRENT_PARAMS[0] == "supply_current"
    chosen = best_specs([
        {"id": 1, "parameter": "operating_temperature", "min_value": None, "max_value": 85.0, "unit": "°C",
         "condition_type": "recommended_operating", "validation_status": "pending", "confidence": 0.9},
    ])
    assert "operating_temperature" not in chosen
