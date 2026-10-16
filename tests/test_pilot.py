from copy import deepcopy
import json
from zipfile import ZipFile

import httpx
import pytest

from evals import pilot, single_response as one, workbook as core
from tests.test_workbook_evals import make_plan, server


def source_plan(tmp_path):
    source = make_plan(tmp_path)
    manifest, old = core.load_plan(source)
    plan = []
    for i in range(300):
        c = deepcopy(old[0]); v, g = [(1, 1), (1, 2), (2, 1), (2, 2)][i // 75]
        cid = f"D{i+1:03d}"; eid = f"{cid}-V{v}-G{g}-R1"
        c["execution_id"] = eid; c["metadata"].update(execution_id=eid, case_id=cid, case_num=i+1, versao_code=v, diretriz_code=g, ordem_execucao=i+1)
        c["turns"] = [{"message": core.initial_message(), "expected_status": None}]
        c["context"].update(case_text="", guideline="ESE" if g == 1 else "AAE")
        c["entry_approved"] = False
        c["display"] = {**c["metadata"], "tipo_caso": "Completo" if v == 1 else "Incompleto", "alerta_mapeamento": "", "estado_execucao": "Planejada"}
        plan.append(c)
    raw = "".join(core.encode(c)+"\n" for c in plan)
    manifest.update(flow=one.FLOW, plan_sha256=core.digest(raw.encode()), result_headers=one.TECHNICAL_HEADERS)
    (source / "plan.jsonl").write_text(raw); (source / "manifest.json").write_text(core.encode(manifest))
    return source


def test_pilot_checkpoint_resume_and_restored_reservation_never_replays(tmp_path, monkeypatch):
    source = source_plan(tmp_path); directory = tmp_path / "pilot300"
    result = pilot.prepare(source, directory)
    assert result["selection_counts"] == {"V1-G1":75,"V1-G2":75,"V2-G1":75,"V2-G2":75}
    calls = []
    def handler(request):
        if request.method == "GET": return httpx.Response(200, json=server())
        body = json.loads(request.content); calls.append(body)
        assert body["history"] == [] and body["context"]["case_text"] == ""
        assert "SECRET_REFERENCE" not in request.content.decode()
        return httpx.Response(200,json={"message":"Resposta real simulada", "guideline":"ESE", "assessment":None},
             headers={"x-dart-audit":core.encode({**server(),"model":"snapshot","prompt_sha256":"prompt","usage":{"total_tokens":12}})})
    original = httpx.AsyncClient
    monkeypatch.setattr(pilot.httpx, "AsyncClient", lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs))
    r = pilot.reserve(directory, 2)
    assert pilot.batch(directory,"https://example.test",r["token"])["success"] == 2
    assert len(calls) == 2
    next_batch = pilot.reserve(directory, 2)
    assert not set(next_batch["execution_ids"]) & set(r["execution_ids"])
    archive = tmp_path / "checkpoint.zip"; pilot.archive(directory, archive)
    restored = tmp_path / "restore"
    with ZipFile(archive) as z:
        assert not any("leases/" in n for n in z.namelist())
        z.extractall(restored)
    restored = restored / "dart400_v3_piloto300"
    assert pilot.status(restored)["success"] == 2
    with pytest.raises(ValueError, match="lease"):
        pilot.batch(restored,"https://example.test",next_batch["token"])
    assert len(calls) == 2
    with pytest.raises(ValueError, match="Unclosed"):
        pilot.reserve(restored,2)


def test_unknown_request_is_not_automatically_retried(tmp_path):
    source = source_plan(tmp_path); directory = tmp_path / "pilot300"
    pilot.prepare(source, directory); r = pilot.reserve(directory,1)
    db = core.database(directory)
    db.execute("INSERT INTO attempts (execution_id,turn,state,started_at,request) VALUES (?,?,?,?,?)",(r["execution_ids"][0],1,"started",core.now(),"{}"));db.commit();db.close()
    with pytest.raises(ValueError,match="unknown outcome"):
        pilot.batch(directory,"https://example.test",r["token"])
    assert pilot.status(directory)["uncertain"] == 1
