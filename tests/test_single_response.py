import csv
from datetime import datetime
import json

import httpx
import pytest

from evals import single_response as one
from evals import workbook as core
from tests.test_workbook_evals import transport


def reviewed_book(tmp_path, monkeypatch, approved=1):
    import openpyxl
    case = {"case_id": "D181", "case_num": 181, "template_id": "T07-M2", "trauma_code": 7}
    entries = [{"entrada_id": f"D181-V{v}", "case_id": "D181", "versao_code": v,
                "answers_json": json.dumps({"A": "2", "B": "1", "C": "1", "D": "1", "E": "1"} if v == 1 else {}),
                "aprovacao_entrada": approved, "justificativa_suficiencia": "", "dados_essenciais_a_solicitar": "estrutura; associado" if v == 2 else "",
                "data_evento": datetime(2026, 10, 1), "data_avaliacao": datetime(2026, 10, 1), "alerta_mapeamento": ""} for v in (1, 2)]
    schedule = [{"execution_id": f"D181-V{v}-G{g}-R1", "case_num": 181, "case_id": "D181", "template_id": "T07-M2",
                 "trauma_code": 7, "versao_code": v, "diretriz_code": g, "idioma_code": 1, "repeticao": 1,
                 "ordem_execucao": i, "analise_principal_code": 0} for i, (v, g) in enumerate([(1, 1), (1, 2), (2, 1), (2, 2)], 1)]
    refs = [{"case_id": "D181", "diretriz_code": g, "gold_id": f"D181-G{g}", "decisao_esperada": "SECRET_REFERENCE"} for g in (1, 2)]
    class Sheet:
        def __init__(self, records):
            keys = list(records[0]); self.rows = [keys, *[[r.get(k) for k in keys] for r in records]]
        def iter_rows(self, **kwargs): return iter(self.rows)
    class Book(dict):
        def close(self): pass
    evaluations = [{"execution_id": r["execution_id"], "resposta_bot": None, "adequada_final": None} for r in schedule]
    book = Book(Entradas=Sheet(entries), Planejamento=Sheet(schedule), Casos=Sheet([case]), Gabaritos=Sheet(refs), Avaliacoes=Sheet(evaluations))
    def reader(*args, **kwargs):
        assert kwargs == {"read_only": True, "data_only": True}
        return book
    monkeypatch.setattr(openpyxl, "load_workbook", reader)
    source = tmp_path / "bank.xlsx"; source.write_bytes(b"fixture")
    return source, entries, evaluations, book


def test_one_response_per_execution_and_empty_scores(tmp_path, monkeypatch):
    source, _, _, _ = reviewed_book(tmp_path, monkeypatch)
    directory = tmp_path / "v3"
    manifest = one.prepare(source, directory, "project-owner")
    _, plan = core.load_plan(directory)
    assert manifest["n_turns"] == manifest["n_conversations"] == 4
    assert all(len(c["turns"]) == 1 and c["context"]["case_text"] == "" for c in plan)
    assert plan[2]["context"]["answers"] == {}
    assert plan[2]["display"]["dados_essenciais_a_solicitar"] == "estrutura; associado"
    calls = []
    with transport(calls) as client:
        one.collect(directory, "https://test.example", limit=1, client=client)
    assert len(calls) == 1 and calls[0]["history"] == []
    assert calls[0]["message"] == core.initial_message()
    assert "SECRET_REFERENCE" not in json.dumps(calls[0])
    with (directory / "avaliacoes.csv").open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f, delimiter=";"))
    assert len(rows) == 4 and rows[0]["estado_execucao"] == "Concluída" and rows[1]["estado_execucao"] == "Planejada"
    assert rows[0]["resposta_exata_api"].startswith("'=")
    assert all(not r[k] for r in rows for k in one.SCORES)


def test_input_review_required_before_any_network_request(tmp_path, monkeypatch):
    source, _, _, _ = reviewed_book(tmp_path, monkeypatch, approved=None)
    directory = tmp_path / "v3"
    manifest = one.prepare(source, directory, "project-owner")
    assert manifest["n_unapproved_entries"] == 2
    calls = []
    with transport(calls) as client:
        with pytest.raises(ValueError, match="approve the actual form"):
            one.collect(directory, "https://test.example", client=client)
    assert calls == []


def test_does_not_silently_treat_incomplete_mapping_as_complete(tmp_path, monkeypatch):
    source, _, _, book = reviewed_book(tmp_path, monkeypatch)
    # A reviewed complete case loses one mapped field; approval alone cannot hide this.
    fields = book["Entradas"].rows[0]
    book["Entradas"].rows[1][fields.index("answers_json")] = '{"A":"2","B":"1","D":"1","E":"1"}'
    with pytest.raises(ValueError, match="sufficiency justification"):
        one.prepare(source, tmp_path / "v3", "project-owner")
