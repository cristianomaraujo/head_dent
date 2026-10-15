# Testagens do DART a partir do Excel

O responsável pelo projeto confirmou a revisão dos casos e referências em 15/10/2026. A confirmação é registrada como revisão do responsável; o programa não a transforma em duas revisões independentes. Não é necessário reenviar a chave da OpenAI: o executor acessa a API do DART, que utiliza a chave já configurada no servidor.

## Preparação do servidor

Publique a versão atualizada de `feat/dart-platform` no Railway. A página `/api/evaluation-info` deve retornar o modelo configurado e hashes de versão. Se essa rota não existir, o executor para antes de enviar casos ao modelo. O modelo usado é o de `OPENAI_MODEL` no Railway; confirme essa escolha antes da coleta principal.

O campo opcional `evaluation_date` preserva a data de avaliação simulada da planilha. `reference_date` continua sendo a data do trauma/reimplante. No uso habitual, sem `evaluation_date`, o servidor continua usando a data atual.

## Instalação no computador

É necessário Python 3.11 ou posterior e o código do repositório. No GitHub, selecione a branch `feat/dart-platform`, clique em **Code > Download ZIP**, extraia o arquivo e abra um terminal dentro da pasta extraída. No Windows, a opção **Abrir no Terminal** aparece ao clicar com o botão direito na pasta.

Instale as dependências:

```powershell
python -m pip install -r requirements-evals.txt
```

Copie a planilha revisada para essa pasta e renomeie sua cópia como `casos.xlsx`. O programa apenas lê o arquivo e não altera a planilha original.

## Preparar o banco, sem chamadas pagas

```powershell
python -m evals.workbook prepare casos.xlsx --out-dir eval_runs/dart400 --reviewed-by project-owner --review-note "Revisao dos casos e referencias confirmada pelo responsavel em 2026-10-15"
```

Essa etapa lê as abas `Casos`, `Gabaritos` e `Resultados`, verifica chaves e códigos, preserva as duas versões, as duas diretrizes e as repetições planejadas, e congela os arquivos do plano. Para o banco de 400 casos, prepara 8.000 conversas e 24.000 turnos. Nenhuma chamada ao DART ou à OpenAI ocorre nessa etapa.

Os gabaritos ficam em `references.json`, separados dos dados enviados ao bot. O conteúdo dos gabaritos nunca é incluído nas solicitações da coleta.

## Primeira execução: uma conversa

```powershell
python -m evals.workbook run eval_runs/dart400 --url https://headdent-production.up.railway.app --max-conversations 1
```

Esse comando pode gerar até três chamadas pagas, uma por turno. Ele usa a ordem aleatória previamente registrada na planilha, e não necessariamente o caso D001. Essa checagem técnica não deve ser usada para ajustar o prompt e depois apresentar o mesmo banco como teste independente.

Abra `eval_runs/dart400/resultados.csv` no Excel e confira as respostas e a conclusão dos três turnos. `collection_state=complete` indica coleta concluída, não correção clínica.

## Continuar em lotes

```powershell
python -m evals.workbook run eval_runs/dart400 --url https://headdent-production.up.railway.app --max-conversations 100
```

Execute novamente o mesmo comando para coletar o próximo lote. Conversas concluídas são puladas. O limite é o máximo de conversas iniciadas ou retomadas nessa invocação, não um total cumulativo. Para percorrer o restante do banco em uma única execução, use `--max-conversations 8000`; o tempo de execução e o custo dependem do modelo e do tamanho das respostas. Mantenha o computador ligado e com internet.

O SQLite salva cada turno antes de continuar. Uma retomada reaproveita o histórico dos turnos bem-sucedidos. Requisições que falharam não são repetidas automaticamente. Para reenviar o turno que falhou, preservando todas as tentativas:

```powershell
python -m evals.workbook run eval_runs/dart400 --url https://headdent-production.up.railway.app --max-conversations 10 --retry-failed
```

Se o processo for interrompido durante uma requisição, o resultado e a cobrança podem ser desconhecidos. O programa sinaliza a situação e exige `--retry-uncertain` para reenviar. Isso pode duplicar uma chamada que o servidor chegou a processar; a tentativa anterior permanece registrada como incerta. Falhas técnicas permanecem nos resultados e nos denominadores operacionais.

Se o modelo efetivamente retornado ou a configuração do servidor mudar, a coleta para. Use uma nova versão do estudo para comparar outra configuração. O programa também impede misturar URLs, planos ou versões do executor numa mesma coleta.

## Arquivos gerados e avaliação clínica

`resultados.csv` tem uma linha por execução planejada, com os identificadores da planilha, textos das respostas e metadados. Usa UTF-8 com BOM e separador `;` para facilitar a abertura no Excel em português. Ele é um arquivo CSV, não uma atualização automática das abas e fórmulas do `.xlsx` original. Para integrar os dados ao banco, importe o CSV pelo menu **Dados > De Texto/CSV** e relacione as tabelas por `execution_id`.

`transcricoes.jsonl` guarda o conteúdo bruto de todas as tentativas: mensagens, respostas estruturadas, erros, modelo retornado, consumo disponível e horário. `collection.sqlite3` é o registro de retomada. `manifest.json` identifica o banco e a revisão declarada; `collection-metadata.json` registra as versões do servidor e do executor. Preserve toda a pasta para manter a rastreabilidade e a capacidade de retomada.

As colunas `status_match_t1`, `status_match_t2` e `status_match_t3` apenas comparam o estado técnico retornado com o esperado. Elas não são medidas de correção, completude ou segurança clínica. Os campos dos avaliadores, adjudicação, erros críticos e custo ficam vazios. O custo deve ser apurado com preços e faturamento do período; ausência de consumo informado em uma tentativa não significa custo zero.

As respostas clínicas devem ser avaliadas pelo texto visível ao dentista. Identificadores e campos internos ficam disponíveis para auditoria, mas não substituem essa avaliação. Preserve escores dos dois avaliadores e os escores finais adjudicados em uma cópia de trabalho. O CSV da coleta é regenerado a cada execução: não digite avaliações manualmente nele, pois seriam sobrescritas. Os arquivos brutos preservam o texto exato; o CSV protege textos que poderiam ser interpretados como fórmulas pelo Excel.

Para reconstruir os arquivos de exportação sem chamar o modelo:

```powershell
python -m evals.workbook export eval_runs/dart400
```

Não inclua a pasta de coleta no Git público. Os 400 casos são unidades agrupadas em famílias; versões, diretrizes e repetições do mesmo caso não devem ser tratadas como observações independentes.

## Testes de software, sem uso de modelo pago

```powershell
python -m pytest -q
```

Os testes simulam respostas da API para conferir pareamento, revelação dos dados, preservação do relógio clínico, retomada, falhas, modelo, metadados e exportação. Eles não medem desempenho clínico do DART.
