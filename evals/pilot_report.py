"""Read-only extraction of the completed pilot for the spreadsheet authoring tool."""
from collections import Counter
import json
from pathlib import Path
import sqlite3
import sys

from evals import pilot, single_response as single, workbook as core


def extract(directory, destination):
    p, chosen = pilot.selection(directory)
    summary = pilot.status(directory)
    if summary["pending"] or summary["uncertain"]:
        raise ValueError("Pilot is still active or has unknown outcomes")
    db = core.database(directory)
    try:
        raw = [dict(r) for r in db.execute("SELECT * FROM attempts ORDER BY id")]
        metadata = {r["key"]:json.loads(r["value"]) for r in db.execute("SELECT * FROM metadata")}
    finally:
        db.close()
    grouped = {}
    for a in raw: grouped.setdefault(a["execution_id"],[]).append(a)
    rows, registry, models = [], [], set()
    rh = ["execution_id","executado_em_utc","estado_tecnico","modelo","response_id","prompt_tokens","cached_prompt_tokens","completion_tokens","total_tokens","latencia_s","prompt_sha256","commit_git","request_json","reply_json","audit_json","erro_tecnico"]
    for c in chosen:
        row = dict(c["display"])
        attempts = grouped.get(c["execution_id"], [])
        success = [a for a in attempts if a["state"] == "success"]
        row["estado_execucao"] = "Concluída" if success else "Erro técnico"
        for a in attempts:
            reply = json.loads(a["reply"]) if a["reply"] else None
            audit = json.loads(a["audit"]) if a["audit"] else {}
            usage = audit.get("usage") or {}
            registry.append([c["execution_id"],a["started_at"],a["state"],audit.get("model"),audit.get("response_id"),usage.get("prompt_tokens"),(usage.get("prompt_tokens_details") or {}).get("cached_tokens"),usage.get("completion_tokens"),usage.get("total_tokens"),a["latency_s"],audit.get("prompt_sha256"),audit.get("commit_git"),a["request"],a["reply"],a["audit"],a["error"]])
        if attempts:
            row["executado_em_utc"] = attempts[0]["started_at"]
            row["erro_tecnico"] = " | ".join(a["error"] or "" for a in attempts if a["error"])
        if success:
            a = success[-1]; reply = json.loads(a["reply"]); audit = json.loads(a["audit"])
            models.add(audit["model"])
            row.update(resposta_bot=reply["message"].replace("**",""),resposta_exata_api=reply["message"],modelo=audit["model"],latencia_s=a["latency_s"],tokens_total=(audit.get("usage") or {}).get("total_tokens"))
        rows.append([row.get(h) for h in single.HEADERS])
    control = [
        ["Item","Registro"],
        ["Execuções selecionadas",300],
        ["Respostas recebidas",summary["success"]],
        ["Falhas técnicas",summary["errors"]],
        ["Resultados desconhecidos",summary["uncertain"]],
        ["Entradas completas",150],
        ["Entradas incompletas",150],
        ["Casos distintos",summary["n_cases"]],
        ["Respostas com avaliação clínica",None],
        ["Adequação entre respostas julgadas",None],
        ["Situação da avaliação","Pendente. Receber uma resposta sem erro técnico não significa que a conduta esteja correta."],
        ["Unidade de avaliação","Uma execução, com uma única resposta do bot à triagem. As 300 execuções correspondem a 207 casos de referência, com versões, diretrizes e repetições identificadas."],
        ["Desfecho primário","Conduta adequada (0/1): no completo, manejo compatível com o gabarito e com os dados enviados; no incompleto, reconhecer insuficiência e solicitar os dados essenciais omitidos, sem presumi-los ou definir conduta dependente deles."],
        ["Secundários","Erro crítico e presunção de dados ausentes (0/1). Consistência é calculada estatisticamente pelas repetições; não recebe nota subjetiva."],
        ["Como pontuar","Vazio significa não avaliado. 0 e 1 são julgamentos realizados. Registrar revisores independentes e julgamento final adjudicado; não calcular média de 0 e 1."],
        ["Entrada efetiva","Somente as seleções reais da ficha, diretriz, idioma e data de referência; case_text vazio e histórico vazio. A mensagem inicial é a mesma usada pelo site."],
        ["Relógio clínico","evaluation_date preserva a data simulada do caso. É um controle experimental, não uma opção da ficha e não a data real da coleta."],
        ["Seleção",p["selection_rule"]],
        ["Equilíbrio","75 execuções por combinação completo/incompleto × ESE/AAE, na ordem original do planejamento. Todos os 14 tipos de trauma estão representados."],
        ["Exclusões deste piloto","D393, D394, D395 e D396 foram excluídos desta seleção por pendência de mapeamento; não foram corrigidos por presunção."],
        ["Caráter exploratório","A autorização para este piloto não equivale à aprovação clínica das entradas. A adaptação ao formulário e a adequação das respostas ainda precisam ser conferidas; notas não foram geradas automaticamente."],
        ["Modelo retornado",", ".join(sorted(models))],
        ["Retomada","O SQLite salva cada requisição antes do envio e cada resultado ao recebê-lo. execution_id concluídos são pulados; erros e resultados desconhecidos não são reenviados automaticamente."],
        ["Cópia persistente","DART_piloto300_retomada.zip guarda plano, seleção congelada, SQLite, registro de IDs, respostas e versões do coletor. Uma reserva ativa restaurada é bloqueada até conciliar seu resultado."],
        ["Repetições planejadas","O mesmo caso pode aparecer em versões, diretrizes ou repetições diferentes. Isso não é uma duplicação da mesma execução. Preservar os identificadores de pareamento."],
        ["Retomar esta seleção","Ao terminar, os 300 IDs permanecem concluídos. Reservar novo lote desta mesma seleção retorna zero, sem novas chamadas. Para ampliar a coleta, preservar e consultar os IDs já registrados."],
        ["Fonte da planilha","DART_banco_resposta_unica.xlsx; 400 casos originais, 8.000 execuções planejadas. Os gabaritos foram preservados; o plano completo continua no arquivo de retomada."],
        ["Fonte de auditoria","Registro_API contém metadados e os pedidos/respostas lógicos completos em JSON. Resultados contém o texto exibido pelo site e o texto original da API em colunas separadas."],
        ["Idioma e escopo","Português. A coleta usa a API com os dados do formulário; não testa cliques nem traduções da tela."],
    ]
    counts = Counter(c["metadata"]["trauma_code"] for c in chosen)
    assert len(counts)==14
    data = {"results":[single.HEADERS,*rows],"control":control,"audit":[rh,*registry],"summary":summary,"metadata":metadata,"trauma_counts":dict(counts)}
    destination.write_text(json.dumps(data,ensure_ascii=False),encoding="utf-8")
    return summary


if __name__ == "__main__":
    result=extract(Path(sys.argv[1]),Path(sys.argv[2]));print(core.encode({k:v for k,v in result.items() if k!="completed_ids"}))
