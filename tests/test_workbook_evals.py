import csv
from datetime import datetime
import json

import httpx
import pytest

from app import main
from evals import workbook as ev
from fastapi.testclient import TestClient


def make_plan(tmp_path):
    directory = tmp_path / "run"
    directory.mkdir()
    plan = [{"execution_id": "D001-V2-G1-R1", "metadata": {
        "execution_id": "D001-V2-G1-R1", "case_id": "D001", "case_num": 1,
        "template_id": "T01-M1", "trauma_code": 1, "versao_code": 2,
        "diretriz_code": 1, "idioma_code": 1, "repeticao": 1,
        "ordem_execucao": 1, "analise_principal_code": 0},
        "context": {"guideline": "ESE", "injury_id": "T01", "answers": {},
                    "case_text": "Caso parcial", "reference_date": "2026-09-30",
                    "evaluation_date": "2026-10-01", "language": "pt"},
        "turns": [{"message": "Dados iniciais", "expected_status": "needs_information"},
                  {"message": "Complemento: ápice aberto", "expected_status": "complete"},
                  {"message": "Quais são as datas?", "expected_status": "complete"}]}]
    raw = ev.encode(plan[0]) + "\n"
    refs = ev.encode([{"gold_id": "SECRET_REFERENCE"}])
    manifest = {"schema": 1, "plan_sha256": ev.digest(raw.encode()),
                "references_sha256": ev.digest(refs.encode()), "workbook_sha256": "bank-hash",
                "result_headers": list(plan[0]["metadata"]) + ["status_execucao", "correto_final", "completo_final", "erro_critico_final",
                    "executado_em_utc", "latencia_s", "erro_tecnico", "transcricao_arquivo", "modelo", "prompt_sha256",
                    "catalogo_sha256", "commit_git", "tokens_total", "custo_usd", "resposta_t1", "resposta_t2", "resposta_t3"]}
    (directory / "plan.jsonl").write_text(raw, encoding="utf-8")
    (directory / "references.json").write_text(refs, encoding="utf-8")
    (directory / "manifest.json").write_text(ev.encode(manifest), encoding="utf-8")
    return directory


def server():
    return {"evaluation_contract": 1, "configured_model": "example-model", "knowledge_sha256": "knowledge",
            "catalog_sha256": "catalog", "service_sha256": "service", "commit_git": "commit",
            "model_parameters": {"temperature": 0, "max_tokens": 4000}}


def transport(calls, fail_at=None, info=None, model="snapshot-1"):
    def handler(request):
        if request.method == "GET":
            return httpx.Response(200, json=info or server())
        payload = json.loads(request.content)
        calls.append(payload)
        assert "SECRET_REFERENCE" not in json.dumps(payload)
        if len(calls) == fail_at:
            return httpx.Response(500, json={"detail": "temporary error"})
        turn = len(payload["history"]) // 2 + 1
        audit = {**server(), "model": model, "prompt_sha256": "prompt", "usage": {"total_tokens": 10}}
        return httpx.Response(200, json={"message": "=not a formula" if turn == 1 else "Resposta " + str(turn),
                 "guideline": "ESE", "assessment": {"status": "needs_information" if turn == 1 else "complete"}},
                 headers={"x-dart-audit": ev.encode(audit)})
    return httpx.Client(transport=httpx.MockTransport(handler))


def output(directory):
    with (directory / "resultados.csv").open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream, delimiter=";"))


def test_three_turns_resume_and_unscored_export(tmp_path):
    directory = make_plan(tmp_path)
    calls = []
    with transport(calls) as client:
        assert ev.collect(directory, "https://test.example", client=client) == 1
        assert ev.collect(directory, "https://test.example", client=client) == 0
    assert len(calls) == 3
    assert [len(c["history"]) for c in calls] == [0, 2, 4]
    assert calls[1]["message"] == "Complemento: ápice aberto"
    assert calls[0]["context"]["evaluation_date"] == "2026-10-01"
    row = output(directory)[0]
    assert row["status_execucao"] == "1" and row["tokens_total"] == "30"
    assert row["correto_final"] == row["completo_final"] == row["erro_critico_final"] == row["custo_usd"] == ""
    assert row["resposta_t1"].startswith("'=not")
    assert row["status_match_t1"] == "1"
    raw = [json.loads(l) for l in (directory / "transcricoes.jsonl").read_text().splitlines()]
    assert raw[0]["reply"]["message"] == "=not a formula"


def test_failure_is_preserved_and_retry_does_not_repeat_successful_turn(tmp_path):
    directory = make_plan(tmp_path)
    calls = []
    with transport(calls, fail_at=2) as client:
        ev.collect(directory, "https://test.example", client=client)
        assert output(directory)[0]["status_execucao"] == "2"
        ev.collect(directory, "https://test.example", client=client)
        assert len(calls) == 2  # no implicit retry of a failed request
        ev.collect(directory, "https://test.example", retry_failed=True, client=client)
    assert len(calls) == 4
    assert [len(c["history"]) for c in calls] == [0, 2, 2, 4]
    row = output(directory)[0]
    assert row["status_execucao"] == "1" and row["attempts_total"] == "4" and row["erro_tecnico"]
    assert row["tokens_total"] == ""  # failed attempt usage unknown, never claim a complete token total


def test_uncertain_request_requires_explicit_retry(tmp_path):
    directory = make_plan(tmp_path)
    db = ev.database(directory)
    db.execute("INSERT INTO attempts (execution_id,turn,state,started_at,request) VALUES (?,?,?,?,?)",
               ("D001-V2-G1-R1", 1, "started", ev.now(), "{}"))
    db.commit(); db.close()
    calls = []
    with transport(calls) as client:
        with pytest.raises(ValueError, match="unknown billing"):
            ev.collect(directory, "https://test.example", client=client)
        assert not calls
        ev.collect(directory, "https://test.example", retry_uncertain=True, client=client)
    assert len(calls) == 3
    assert "unknown" in output(directory)[0]["erro_tecnico"]


def test_server_configuration_and_reported_model_are_frozen(tmp_path):
    directory = make_plan(tmp_path)
    calls = []
    with transport(calls, fail_at=2) as client:
        ev.collect(directory, "https://test.example", client=client)
    with transport(calls, info={**server(), "service_sha256": "changed"}) as client:
        with pytest.raises(ValueError, match="server changed"):
            ev.collect(directory, "https://test.example", retry_failed=True, client=client)
    assert len(calls) == 2
    with transport(calls, model="new-snapshot") as client:
        with pytest.raises(ValueError, match="reported_model changed"):
            ev.collect(directory, "https://test.example", retry_failed=True, client=client)
    assert len(calls) == 3


def test_reference_change_rejected_before_collection(tmp_path):
    directory = make_plan(tmp_path)
    (directory / "references.json").write_text("[]")
    with pytest.raises(ValueError, match="changed"):
        ev.load_plan(directory)


def test_reader_preserves_pairing_review_attestation_and_dates(tmp_path, monkeypatch):
    import openpyxl
    case = {"case_id": "D001", "case_num": 1, "template_id": "T01-M1", "trauma_code": 1,
            "caso_completo": "Completo", "caso_dados_faltantes": "Parcial", "resposta_complementar": "Ápice aberto",
            "dados_a_solicitar": "apice", "triagem_completa_json": "{}", "triagem_incompleta_json": "{}",
            "data_evento": datetime(2026, 9, 30), "data_avaliacao": datetime(2026, 10, 1)}
    golds = [{"case_id": "D001", "diretriz_code": g, "data_aprovacao": datetime(2026, 10, 15)} for g in (1, 2)]
    headers = ["execution_id", "case_num", "case_id", "template_id", "trauma_code", "versao_code", "diretriz_code",
               "idioma_code", "repeticao", "ordem_execucao", "analise_principal_code", "status_execucao"]
    rows = [[f"D001-V{v}-G{g}-R1", 1, "D001", "T01-M1", 1, v, g, 1, 1, i, 0, 0]
            for i, (v, g) in enumerate([(1, 1), (1, 2), (2, 1), (2, 2)], 1)]
    class Sheet:
        def __init__(self, values): self.values = values
        def iter_rows(self, **kwargs): return iter(self.values)
    class Book(dict):
        def close(self): pass
    fake = Book(Casos=Sheet([list(case), list(case.values())]),
                Gabaritos=Sheet([list(golds[0]), *[list(g.values()) for g in golds]]),
                Resultados=Sheet([headers, *rows]))
    def reader(path, **kwargs):
        assert kwargs == {"read_only": True, "data_only": True}
        return fake
    monkeypatch.setattr(openpyxl, "load_workbook", reader)
    source = tmp_path / "reviewed.xlsx"; source.write_bytes(b"fixture")
    directory = tmp_path / "prepared"
    manifest = ev.prepare(source, directory, "project-owner", "Confirmed review")
    _, plan = ev.load_plan(directory)
    assert manifest["n_cases"] == 1 and manifest["n_conversations"] == 4
    assert manifest["reviewed_by"] == "project-owner"
    assert plan[2]["context"]["case_text"] == "Parcial"
    assert plan[2]["context"]["reference_date"] == "2026-09-30"
    assert plan[2]["turns"][1]["message"].endswith("Ápice aberto")
    with pytest.raises(ValueError, match="immutable"):
        ev.prepare(source, directory, "project-owner")


def test_evaluation_clock_and_audit_headers_are_real_response_metadata(monkeypatch):
    captured = {}
    monkeypatch.setenv("OPENAI_API_KEY", "test-only")
    response_body = {"id": "response-id", "model": "model-snapshot", "usage": {"total_tokens": 123},
                     "choices": [{"message": {"content": json.dumps({"message": "Pergunta", "guideline": "ESE", "assessment": None})}}]}
    class Upstream:
        def raise_for_status(self): pass
        def json(self): return response_body
    class FakeClient:
        def __init__(self, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def post(self, *args, **kwargs):
            captured.update(kwargs["json"])
            return Upstream()
    monkeypatch.setattr(main.httpx, "AsyncClient", FakeClient)
    client = TestClient(main.app)
    result = client.post("/api/chat", json={"context": {"guideline": "ESE", "case_text": "Caso",
                    "reference_date": "2026-09-30", "evaluation_date": "2026-10-01"}, "message": "Inicie"})
    assert result.status_code == 200
    audit = json.loads(result.headers["x-dart-audit"])
    assert audit["model"] == "model-snapshot" and audit["usage"]["total_tokens"] == 123
    assert audit["prompt_sha256"] == ev.digest(captured["messages"][0]["content"].encode())
    assert '"today": "2026-10-01"' in captured["messages"][1]["content"]
    info = client.get("/api/evaluation-info").json()
    assert info["service_sha256"] == audit["service_sha256"]
    assert "test-only" not in json.dumps(info)
