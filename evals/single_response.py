"""Prepare and collect one triage response per execution from the redesigned workbook."""
import argparse
import csv
import json
import os
from pathlib import Path

from evals import workbook as core

FLOW = "single-triage-response-v3"
SCORES = ("adequada_r1", "erro_critico_r1", "presuncao_r1", "justificativa_r1", "revisor_1",
          "adequada_r2", "erro_critico_r2", "presuncao_r2", "justificativa_r2", "revisor_2",
          "adequada_final", "erro_critico_final", "presuncao_final", "justificativa_final", "adjudicador")
HEADERS = [*core.METADATA_FIELDS, "entrada_id", "pareamento_repeticoes", "pareamento_versoes",
           "tipo_caso", "triagem_enviada", "dados_omitidos", "dados_essenciais_a_solicitar",
           "criterio_adequacao", "gabarito_clinico", "gold_id", "data_evento", "data_avaliacao",
           "aprovacao_entrada", "alerta_mapeamento", "estado_execucao", "resposta_bot", "resposta_exata_api",
           *SCORES, "modelo", "executado_em_utc", "latencia_s", "tokens_total", "erro_tecnico"]
VISIBLE_FIRST = ["execution_id", "tipo_caso", "triagem_enviada", "resposta_bot", "criterio_adequacao",
                 "dados_omitidos", "dados_essenciais_a_solicitar", "gabarito_clinico", "adequada_final",
                 "erro_critico_final", "presuncao_final", "justificativa_final"]
HEADERS = VISIBLE_FIRST + [h for h in HEADERS if h not in VISIBLE_FIRST]
TECHNICAL_HEADERS = [*core.METADATA_FIELDS, "status_execucao", "executado_em_utc", "latencia_s", "erro_tecnico",
                    "transcricao_arquivo", "modelo", "prompt_sha256", "catalogo_sha256", "commit_git", "tokens_total",
                    "custo_usd", "resposta_t1"]


def rubric(gold):
    return "\n\n".join(f"{k}: {gold[k]}" for k in ("decisao_esperada", "abordagem_pulpar", "etapas_clinicas",
                         "acompanhamento_datas", "transparencia_fonte", "seguranca") if gold.get(k))


def prepare(source, directory, reviewed_by):
    from openpyxl import load_workbook
    if not reviewed_by.strip():
        raise ValueError("Identify the reviewer of the source cases and references")
    if directory.exists() and any(directory.iterdir()):
        raise ValueError("Use a new empty directory; preserve earlier pilots separately")
    book = load_workbook(source, read_only=True, data_only=True)
    try:
        _, entries = core.table(book, "Entradas")
        _, schedule = core.table(book, "Planejamento")
        _, cases = core.table(book, "Casos")
        _, references = core.table(book, "Gabaritos")
        _, evaluations = core.table(book, "Avaliacoes")
    finally:
        book.close()
    if any(r.get(k) not in (None, "") for r in evaluations for k in (*SCORES, "resposta_bot", "resposta_exata_api")):
        raise ValueError("Workbook contains observations or scores; preserve the collection and use a clean plan")
    entry_map = {r["entrada_id"]: r for r in entries}
    gold_map = {(r["case_id"], r["diretriz_code"]): r for r in references}
    case_map = {r["case_id"]: r for r in cases}
    if len(entry_map) != len(entries) or len(gold_map) != len(references) or len(case_map) != len(cases):
        raise ValueError("Duplicate source keys")
    catalog = json.loads((core.SOURCE_ROOT / "knowledge/catalog.json").read_text(encoding="utf-8"))
    conditions = {c["id"]: c for c in catalog}
    plan, seen, orders, configs = [], set(), set(), set()
    for r in schedule:
        if not set(core.METADATA_FIELDS).issubset(r):
            raise ValueError("Missing execution metadata")
        v, g, rep = r["versao_code"], r["diretriz_code"], r["repeticao"]
        config = (r["case_id"], v, g, rep)
        if v not in (1, 2) or g not in core.GUIDELINES or r["idioma_code"] != 1 or not isinstance(rep, int) or rep < 1:
            raise ValueError("Invalid study configuration")
        if r["execution_id"] in seen or r["ordem_execucao"] in orders or config in configs:
            raise ValueError("Duplicate execution, order, or configuration")
        seen.add(r["execution_id"]); orders.add(r["ordem_execucao"]); configs.add(config)
        case = case_map[r["case_id"]]
        if any(r[k] != case[k] for k in ("case_num", "template_id", "trauma_code")):
            raise ValueError("Case and execution do not match")
        entry_id = f"{r['case_id']}-V{v}"
        entry = entry_map[entry_id]
        if entry["case_id"] != r["case_id"] or entry["versao_code"] != v:
            raise ValueError("Entry and execution do not match")
        condition = conditions[f"T{case['trauma_code']:02d}"]
        answers = json.loads(entry["answers_json"])
        options = {q["key"]: {o["value"] for o in q["options"]} for q in condition["questions"]}
        if not isinstance(answers, dict) or any(k not in options or value not in options[k] for k, value in answers.items()):
            raise ValueError(f"Invalid triage codes in {entry_id}")
        triage, unknown = [], []
        for q in condition["questions"]:
            labels = {o["value"]: o["label"] for o in q["options"]}
            value = answers.get(q["key"])
            triage.append(f"{q['key']} - {q['label']}: {labels.get(value, 'Não informado')}")
            if value is None:
                unknown.append(f"{q['key']} - {q['label']}")
        form_text = (f"Traumatismo: {condition['name']} ({condition['id']})\nIdioma: Português\n"
                     f"Data de referência: {core.iso(entry['data_evento'])}\n" + "\n".join(triage))
        approved = entry.get("aprovacao_entrada") == 1
        if entry.get("triagem_enviada") not in (None, "", form_text):
            raise ValueError(f"{entry_id}: displayed triage and actual codes differ; regenerate the mapping")
        note = entry.get("justificativa_suficiencia") or ""
        if approved and v == 1 and unknown and not note.strip():
            raise ValueError(f"{entry_id}: incomplete form requires a clinical sufficiency justification or corrected input")
        target = entry.get("dados_essenciais_a_solicitar") or ""
        if v == 2 and (not unknown or not target.strip()):
            raise ValueError(f"{entry_id}: specify the essential missing information")
        gold = gold_map[(r["case_id"], g)]
        context = {"injury_id": condition["id"], "guideline": core.GUIDELINES[g], "answers": answers,
                   "case_text": "", "reference_date": core.iso(entry["data_evento"]),
                   "evaluation_date": core.iso(entry["data_avaliacao"]), "language": "pt"}
        criterion = ("Apresentar conduta compatível com o gabarito e com os dados efetivamente fornecidos, incluindo os itens essenciais e sem erro relevante."
                     if v == 1 else "Reconhecer a insuficiência, solicitar os dados essenciais omitidos e não presumir seus valores nem definir conduta dependente deles. Orientação provisória segura é aceitável.")
        display = {**{k: r[k] for k in core.METADATA_FIELDS}, "entrada_id": entry_id,
                   "pareamento_repeticoes": f"{entry_id}-G{g}", "pareamento_versoes": f"{r['case_id']}-G{g}-R{rep}",
                   "tipo_caso": "Completo" if v == 1 else "Incompleto", "triagem_enviada": form_text + "\nDiretriz: " + core.GUIDELINES[g],
                   "dados_omitidos": "\n".join(unknown), "dados_essenciais_a_solicitar": target,
                   "criterio_adequacao": criterion, "gabarito_clinico": rubric(gold), "gold_id": gold.get("gold_id"),
                   "data_evento": context["reference_date"], "data_avaliacao": context["evaluation_date"],
                   "aprovacao_entrada": 1 if approved else None,
                   "alerta_mapeamento": entry.get("alerta_mapeamento") or "", "estado_execucao": "Planejada"}
        plan.append({"execution_id": r["execution_id"], "metadata": {k: r[k] for k in core.METADATA_FIELDS},
                     "context": context, "turns": [{"message": core.initial_message(), "expected_status": None}],
                     "entry_approved": approved, "display": display})
    if not plan or len(evaluations) != len(schedule) or {r["execution_id"] for r in evaluations} != seen:
        raise ValueError("Evaluation and execution rows do not match")
    plan.sort(key=lambda c: c["metadata"]["ordem_execucao"])
    raw = "".join(core.encode(c) + "\n" for c in plan)
    refs = core.encode(references)
    manifest = {"schema": core.SCHEMA, "flow": FLOW, "created_at_utc": core.now(), "reviewed_by": reviewed_by,
                "source_name": source.name, "workbook_sha256": core.digest(source.read_bytes()),
                "plan_sha256": core.digest(raw.encode()), "references_sha256": core.digest(refs.encode()),
                "result_headers": TECHNICAL_HEADERS, "n_cases": len(cases), "n_conversations": len(plan),
                "n_turns": len(plan), "n_unapproved_entries": sum(e.get("aprovacao_entrada") != 1 for e in entries),
                "clock": "Controlled workbook evaluation_date, not a form input; no clinical narrative injected"}
    directory.mkdir(parents=True)
    (directory / "manifest.json").write_text(core.encode(manifest), encoding="utf-8")
    (directory / "plan.jsonl").write_text(raw, encoding="utf-8")
    (directory / "references.json").write_text(refs, encoding="utf-8")
    export(directory)
    return manifest


def collect(directory, url, limit=1, retry_failed=False, retry_uncertain=False, client=None):
    manifest, plan = core.load_plan(directory)
    if manifest.get("flow") != FLOW or any(len(c["turns"]) != 1 for c in plan):
        raise ValueError("Use a single-response v3 plan, separate from earlier pilots")
    if any(not c.get("entry_approved") for c in plan):
        raise ValueError("Review and approve the actual form inputs in Entradas before paid collection; prepare a new directory")
    try:
        return core.collect(directory, url, limit, retry_failed, retry_uncertain, client)
    finally:
        export(directory)


def export(directory):
    _, plan = core.load_plan(directory)
    with core.lock(directory):
        db = core.database(directory)
        try:
            attempts = [dict(r) for r in db.execute("SELECT * FROM attempts ORDER BY id")]
        finally:
            db.close()
        grouped = {}
        for a in attempts:
            grouped.setdefault(a["execution_id"], []).append(a)
        out = directory / "avaliacoes.csv"
        temp = out.with_suffix(".csv.tmp")
        with temp.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=HEADERS, delimiter=";")
            writer.writeheader()
            for case in plan:
                row = dict(case["display"])
                found = grouped.get(case["execution_id"], [])
                success = [a for a in found if a["state"] == "success"]
                if found:
                    row["estado_execucao"] = "Concluída" if success else "Incerta" if found[-1]["state"] == "started" else "Erro técnico"
                    row["executado_em_utc"] = found[0]["started_at"]
                    row["erro_tecnico"] = " | ".join(a["error"] or "" for a in found if a["error"])
                if success:
                    a = success[-1]; reply = json.loads(a["reply"]); audit = json.loads(a["audit"])
                    row.update(resposta_bot=reply["message"].replace("**", ""), resposta_exata_api=reply["message"], modelo=audit["model"])
                    if all(x["latency_s"] is not None for x in found):
                        row["latencia_s"] = sum(x["latency_s"] for x in found)
                    audits = [json.loads(x["audit"]) if x["audit"] else {} for x in found]
                    if all(isinstance(x.get("usage", {}).get("total_tokens"), int) for x in audits):
                        row["tokens_total"] = sum(x["usage"]["total_tokens"] for x in audits)
                writer.writerow({k: core.safe_csv(v) for k, v in row.items()})
        os.replace(temp, out)
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    a = sub.add_parser("prepare"); a.add_argument("workbook", type=Path); a.add_argument("--out-dir", type=Path, required=True); a.add_argument("--reviewed-by", required=True)
    a = sub.add_parser("run"); a.add_argument("directory", type=Path); a.add_argument("--url", required=True); a.add_argument("--max-executions", type=int, default=1)
    a.add_argument("--retry-failed", action="store_true"); a.add_argument("--retry-uncertain", action="store_true")
    a = sub.add_parser("export"); a.add_argument("directory", type=Path)
    args = p.parse_args()
    if args.command == "prepare":
        print(core.encode(prepare(args.workbook, args.out_dir, args.reviewed_by)))
    elif args.command == "run":
        collect(args.directory, args.url, args.max_executions, args.retry_failed, args.retry_uncertain)
    else:
        print(export(args.directory))


if __name__ == "__main__":
    main()
