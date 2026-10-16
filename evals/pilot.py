"""Authorized exploratory pilot: bounded selection, checkpointed requests, no clinical scores."""
import argparse
import asyncio
from collections import Counter
import json
from importlib.metadata import version
from pathlib import Path
import platform
import shutil
import sqlite3
import time
import uuid
from zipfile import ZipFile, ZIP_DEFLATED

import httpx

from evals import workbook as core
from evals import single_response as single


def selection(directory):
    p = json.loads((directory / "pilot.json").read_text(encoding="utf-8"))
    _, plan = core.load_plan(directory)
    cases = {c["execution_id"]: c for c in plan}
    if len(p["execution_ids"]) != 300 or len(set(p["execution_ids"])) != 300:
        raise ValueError("Frozen pilot must contain 300 distinct execution IDs")
    chosen = [cases[k] for k in p["execution_ids"]]
    if any(c["display"].get("alerta_mapeamento") or c["metadata"]["case_id"] in p["excluded_cases"] for c in chosen):
        raise ValueError("Pilot contains a flagged mapping")
    if any(len(c["turns"]) != 1 or c["context"].get("case_text") or c["turns"][0]["message"] != core.initial_message() for c in chosen):
        raise ValueError("Pilot must reproduce the one-response triage workflow")
    return p, chosen


def prepare(source, directory):
    manifest, plan = core.load_plan(source)
    if manifest.get("flow") != single.FLOW:
        raise ValueError("Use a reviewed v3 single-response source")
    if directory.exists():
        raise ValueError("Pilot directory already exists; resume it, never overwrite")
    excluded = ["D393", "D394", "D395", "D396"]
    counts, ids = Counter(), []
    for c in plan:
        key = (c["metadata"]["versao_code"], c["metadata"]["diretriz_code"])
        if c["metadata"]["case_id"] in excluded or c["display"].get("alerta_mapeamento") or counts[key] >= 75:
            continue
        ids.append(c["execution_id"]); counts[key] += 1
        if len(ids) == 300:
            break
    if len(ids) != 300 or set(counts.values()) != {75}:
        raise ValueError("Cannot form the balanced pilot")
    directory.mkdir(parents=True)
    for name in ("manifest.json", "plan.jsonl", "references.json"):
        shutil.copy2(source / name, directory / name)
    p = {"protocol": "exploratory-pilot300-v1", "created_at_utc": core.now(),
         "authorization": "User explicitly requested 300 pilot tests with resumable saving on 2026-10-16.",
         "clinical_input_approval": "Still pending; pilot authorization is not clinical validation or approval.",
         "selection_rule": "First 75 eligible executions per version/guideline in original planned order; no selection by model response.",
         "excluded_cases": excluded, "execution_ids": ids, "source_plan_sha256": manifest["plan_sha256"],
         "source_library_file_id": "libfile_ff891332424c8191864a776e42b51de1"}
    (directory / "pilot.json").write_text(core.encode(p), encoding="utf-8")
    single.export(directory)
    return status(directory)


def status(directory):
    p, chosen = selection(directory)
    db = core.database(directory)
    try:
        rows = [dict(r) for r in db.execute("SELECT * FROM attempts ORDER BY id")]
    finally:
        db.close()
    ids = set(p["execution_ids"])
    rows = [r for r in rows if r["execution_id"] in ids]
    latest = {r["execution_id"]: r for r in rows}
    success = {r["execution_id"] for r in rows if r["state"] == "success"}
    return {"target": 300, "success": len(success), "errors": sum(r["state"] == "error" and k not in success for k, r in latest.items()),
            "uncertain": sum(r["state"] == "started" and k not in success for k, r in latest.items()),
            "pending": 300 - len(latest), "attempts": len(rows),
            "completed_ids": sorted(success), "n_cases": len({c["metadata"]["case_id"] for c in chosen}),
            "selection_counts": dict(Counter(f"V{c['metadata']['versao_code']}-G{c['metadata']['diretriz_code']}" for c in chosen))}


def reserve(directory, limit=25):
    if not 1 <= limit <= 25:
        raise ValueError("Reserve at most 25 executions")
    with core.lock(directory):
        prior = directory / "reservation.json"
        if prior.exists() and json.loads(prior.read_text())["phase"] != "complete":
            raise ValueError("Unclosed reservation; inspect local state. Restored checkpoints must not blindly resend reserved IDs.")
        p, _ = selection(directory)
        db = core.database(directory)
        try:
            observed = {r[0] for r in db.execute("SELECT DISTINCT execution_id FROM attempts")}
        finally:
            db.close()
        ids = [k for k in p["execution_ids"] if k not in observed][:limit]
        if not ids:
            return None
        token = uuid.uuid4().hex
        r = {"token": token, "phase": "reserved", "created_at_utc": core.now(), "execution_ids": ids,
             "restore_rule": "Lease is excluded from archives. If this reservation is active after restore, its outcomes may be unknown; do not resend automatically."}
        prior.write_text(core.encode(r), encoding="utf-8")
        leases = directory / "leases"; leases.mkdir(exist_ok=True)
        (leases / token).write_text(token)
        return r


async def _batch(directory, url, token, concurrency):
    if concurrency not in (1, 2):
        raise ValueError("Concurrency must be 1 or 2")
    if not url.startswith("https://"):
        raise ValueError("Use HTTPS")
    manifest, _ = core.load_plan(directory)
    p, chosen = selection(directory)
    r = json.loads((directory / "reservation.json").read_text())
    lease = directory / "leases" / token
    if r["token"] != token or not lease.exists() or r["phase"] == "complete":
        raise ValueError("No active local lease; restored reservations require reconciliation, not automatic replay")
    cases = {c["execution_id"]: c for c in chosen}
    if any(k not in cases for k in r["execution_ids"]):
        raise ValueError("Reservation does not match the frozen selection")
    db = core.database(directory)
    fatal, done = [], 0
    try:
        for k in r["execution_ids"]:
            rows = db.execute("SELECT state FROM attempts WHERE execution_id=?", (k,)).fetchall()
            if any(x[0] == "started" for x in rows):
                raise ValueError("Interrupted request with unknown outcome; inspect before retrying")
        for key in ("plan_sha256", "references_sha256", "workbook_sha256"):
            core.bind(db, key, manifest[key])
        core.bind(db, "pilot_selection", p)
        core.bind(db, "collector", {"pilot_sha256": core.digest(Path(__file__).read_bytes()),
             "core_sha256": core.digest(Path(core.__file__).read_bytes()), "single_sha256": core.digest(Path(single.__file__).read_bytes()),
             "python": platform.python_version(), "httpx": version("httpx"), "openpyxl": version("openpyxl")})
        async with httpx.AsyncClient(timeout=110) as client:
            response = await client.get(url.rstrip("/") + "/api/evaluation-info")
            response.raise_for_status(); server = response.json()
            if server.get("evaluation_contract") != 1:
                raise ValueError("Evaluation server contract unavailable")
            core.bind(db, "server", server); core.bind(db, "url", url.rstrip("/"))
            r["phase"] = "running"; (directory / "reservation.json").write_text(core.encode(r))
            queue = asyncio.Queue()
            for k in r["execution_ids"]:
                if db.execute("SELECT 1 FROM attempts WHERE execution_id=?", (k,)).fetchone() is None:
                    queue.put_nowait(k)
            async def worker():
                nonlocal done
                while not queue.empty() and not fatal:
                    k = queue.get_nowait(); case = cases[k]
                    payload = {"context": case["context"], "history": [], "message": case["turns"][0]["message"]}
                    cursor = db.execute("INSERT INTO attempts (execution_id,turn,state,started_at,request) VALUES (?,?,?,?,?)", (k, 1, "started", core.now(), core.encode(payload)))
                    db.commit(); attempt = cursor.lastrowid; start = time.monotonic(); reply = audit = None
                    try:
                        response = await client.post(url.rstrip("/") + "/api/chat", json=payload)
                        response.raise_for_status(); reply = response.json()
                        if not isinstance(reply, dict) or not isinstance(reply.get("message"), str) or not reply["message"].strip() or reply.get("guideline") not in ("ESE", "AAE", "COMPARE"):
                            raise ValueError("Malformed response")
                        audit = json.loads(response.headers.get("x-dart-audit", "null"))
                        if not isinstance(audit, dict) or not core.audit_matches(audit, server):
                            fatal.append("Server/audit configuration changed"); raise ValueError(fatal[-1])
                        try:
                            core.bind(db, "reported_model", audit["model"])
                        except ValueError as e:
                            fatal.append(str(e)); raise
                        db.execute("UPDATE attempts SET state='success',reply=?,audit=?,latency_s=? WHERE id=?", (core.encode(reply), core.encode(audit), time.monotonic()-start, attempt))
                    except (httpx.HTTPError, ValueError, TypeError, KeyError) as e:
                        db.execute("UPDATE attempts SET state='error',reply=?,audit=?,error=?,latency_s=? WHERE id=?", (core.encode(reply) if reply is not None else None, core.encode(audit) if audit is not None else None, str(e), time.monotonic()-start, attempt))
                    db.commit(); done += 1
                    print(core.encode({"batch_received": done, "execution_id": k}), flush=True)
            await asyncio.gather(*[worker() for _ in range(concurrency)])
        r["phase"] = "complete"; r["closed_at_utc"] = core.now(); r["fatal"] = fatal
        (directory / "reservation.json").write_text(core.encode(r)); lease.unlink()
        if fatal:
            raise ValueError("; ".join(fatal))
    finally:
        db.close()


def batch(directory, url, token, concurrency=2):
    try:
        with core.lock(directory):
            asyncio.run(_batch(directory, url, token, concurrency))
    finally:
        core.export(directory)
        single.export(directory)
    return status(directory)


def archive(directory, destination):
    # Called between batches; a SQLite backup produces a self-contained snapshot without WAL files.
    with core.lock(directory):
        source = core.database(directory)
        backup = directory / "checkpoint.sqlite3"
        target = sqlite3.connect(backup)
        try:
            source.backup(target)
        finally:
            target.close(); source.close()
        ledger_db = sqlite3.connect(backup)
        ledger_db.row_factory = sqlite3.Row
        ledger_rows = [dict(x) for x in ledger_db.execute("SELECT execution_id,turn,state,started_at,id FROM attempts ORDER BY id")]
        ledger_db.close()
        ledger = {"source_plan_sha256": json.loads((directory / "manifest.json").read_text())["plan_sha256"],
                  "created_at_utc": core.now(), "records": ledger_rows,
                  "rule": "Skip completed execution_id values. Errors and unknown outcomes require inspection before any resend. Reserved IDs in an active reservation also require reconciliation after restore."}
        (directory / "execucoes_registradas.json").write_text(core.encode(ledger), encoding="utf-8")
        names = ["manifest.json", "plan.jsonl", "references.json", "pilot.json", "reservation.json",
                 "collection-metadata.json", "avaliacoes.csv", "transcricoes.jsonl", "execucoes_registradas.json"]
        destination.parent.mkdir(parents=True, exist_ok=True)
        with ZipFile(destination, "w", ZIP_DEFLATED, compresslevel=6) as z:
            for name in names:
                if (directory / name).exists():
                    z.write(directory / name, arcname="dart400_v3_piloto300/" + name)
            z.write(backup, arcname="dart400_v3_piloto300/collection.sqlite3")
            for module in (Path(__file__), Path(core.__file__), Path(single.__file__)):
                z.write(module, arcname="collector_source/evals/" + module.name)
            z.writestr("RETOMADA.txt", "Resume the same folder and frozen plan. Completed execution_id values are never resent. Never automatically retry an active reservation after restoring: its missing local lease means the outcome can be unknown. Inspect the ledger first. Original 8000-entry plan is retained so later collection can skip these same completed IDs. Clinical scores remain pending.")
        backup.unlink()
    return str(destination)


def main():
    p = argparse.ArgumentParser(description=__doc__); sub = p.add_subparsers(dest="command", required=True)
    a = sub.add_parser("prepare"); a.add_argument("source", type=Path); a.add_argument("directory", type=Path)
    a = sub.add_parser("status"); a.add_argument("directory", type=Path)
    a = sub.add_parser("reserve"); a.add_argument("directory", type=Path); a.add_argument("--limit", type=int, default=25)
    a = sub.add_parser("batch"); a.add_argument("directory", type=Path); a.add_argument("--url", required=True); a.add_argument("--token", required=True); a.add_argument("--concurrency", type=int, default=2)
    a = sub.add_parser("archive"); a.add_argument("directory", type=Path); a.add_argument("destination", type=Path)
    args = p.parse_args()
    if args.command == "prepare": result = prepare(args.source, args.directory)
    elif args.command == "status": result = status(args.directory)
    elif args.command == "reserve": result = reserve(args.directory, args.limit)
    elif args.command == "batch": result = batch(args.directory, args.url, args.token, args.concurrency)
    else: result = archive(args.directory, args.destination)
    if isinstance(result, dict) and "completed_ids" in result:
        result = {k:v for k,v in result.items() if k != "completed_ids"}
    print(core.encode(result), flush=True)


if __name__ == "__main__":
    main()
