from fastapi.testclient import TestClient
import json

from app.main import CATALOG, app

client = TestClient(app)


def test_catalog_covers_14_injuries_and_68_families():
    response = client.get("/api/catalog")
    assert response.status_code == 200
    assert len(CATALOG) == 14
    assert response.json()["families"] == 68
    assert len({o["id"] for c in CATALOG for o in c["outcomes"]}) == 68
    assert all(q["options"] for c in CATALOG for q in c["questions"])


def test_invalid_answer_rejected_without_model_call():
    response = client.post("/api/assess", json={"injury_id": "T01", "guideline": "ESE", "answers": {"A": "99"}})
    assert response.status_code == 422


def test_missing_case_rejected_without_model_call():
    response = client.post("/api/assess", json={"guideline": "COMPARE"})
    assert response.status_code == 422


def test_model_cannot_assign_family_from_another_injury(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-only")

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            result = {"injury_id": "T01", "outcome_id": "T02-R01", "status": "complete",
                      "missing_information": [], "incompatibilities": [],
                      "management_now": "", "endodontic_treatment": "",
                      "endodontic_protocol": "", "follow_up": "", "warning_signs": "",
                      "ese": "", "aae": "", "differences": "", "source_notes": ""}
            return {"choices": [{"message": {"content": json.dumps(result)}}]}

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def post(self, *args, **kwargs):
            return FakeResponse()

    monkeypatch.setattr("app.main.httpx.AsyncClient", FakeClient)
    response = client.post("/api/assess", json={"injury_id": "T01", "guideline": "ESE"})
    assert response.status_code == 502
    assert "Invalid response family" in response.json()["detail"]
