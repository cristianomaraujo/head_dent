# Piloto exploratório de 300 respostas

Autorizado pelo responsável em 16/10/2026. É uma coleta exploratória para conferir o fluxo e a apresentação do banco. A autorização não foi registrada como aprovação clínica das entradas, nem como validação das condutas. As notas de adequação, erro crítico e presunção permanecem vazias.

## Seleção congelada

O arquivo `pilot.json` contém exatamente 300 `execution_id`: os primeiros 75 elegíveis de cada combinação versão completa/incompleta e ESE/AAE, respeitando a ordem aleatória do plano original. D393–D396 foram excluídos desta seleção por pendência de mapeamento. São 207 casos de referência e 14 tipos de trauma; repetições e versões seguem identificadas. A seleção é anterior às respostas e não muda com o desempenho.

Cada execução envia uma única solicitação de chat, com histórico vazio e `case_text` vazio, usando os campos da ficha e o relógio simulado. Não há segunda troca automática, revelação de dados nem pontuação clínica automática.

## Salvamento e prevenção de duplicação

- O SQLite registra a tentativa como `started` **antes** do POST e grava a resposta como `success` ao recebê-la.
- Uma reserva local de até 25 IDs é salva no checkpoint persistente antes de enviar o lote. As respostas são salvas novamente ao fechar o lote.
- IDs já observados não são reservados novamente. Erros e requisições interrompidas não são repetidos automaticamente.
- Uma interrupção pode deixar uma requisição com resultado/cobrança desconhecidos. Essa situação bloqueia reenvio automático.
- O checkpoint contém plano completo de 8.000 execuções, seleção das 300, registro de IDs, banco SQLite, transcrições, CSV principal e fontes exatas do coletor.
- A licença local do lote (`leases/`) **não** é incluída no ZIP. Se uma reserva ativa aparecer após restaurar o ZIP, seus resultados posteriores podem ser desconhecidos: conciliar primeiro, sem reenviar automaticamente aqueles IDs.
- Modelo efetivamente retornado, fontes, servidor, relógio, URL e coletor são congelados. Alterações interrompem a coleta para evitar mistura de versões.

O mesmo caso pode aparecer em versões, diretrizes ou repetições diferentes. Isso é parte do planejamento; a chave para não duplicar uma execução é `execution_id`, junto do plano congelado. Para ampliar posteriormente a coleta, preservar e consultar `execucoes_registradas.json` e o SQLite antes de formar novos lotes. Não apagar nem recriar uma coleta já observada.

## Comandos

Preparar uma seleção nova somente quando ainda não existe uma coleta:

```powershell
python -m evals.pilot prepare eval_runs/dart400_v3_validacao_final eval_runs/dart400_v3_piloto300
```

Verificar sem chamar o modelo:

```powershell
python -m evals.pilot status eval_runs/dart400_v3_piloto300
```

`reserve` cria a reserva; `batch` exige o token e a licença local correspondentes. Não executar `batch` sem antes salvar o arquivo de retomada. `evals.run_pilot` é o controlador usado nesta sessão: salva cada reserva e cada lote fechado no mesmo arquivo persistente, com proteção pela versão do arquivo. Se o salvamento não for confirmado, não inicia o próximo lote.

Para reconstruir a tabela principal sem novas chamadas:

```powershell
python -m evals.single_response export eval_runs/dart400_v3_piloto300
```

`avaliacoes.csv` mantém o banco completo, com linhas ainda não coletadas. O relatório Excel do piloto mostra somente as 300 execuções selecionadas. `pilot_report` extrai respostas, entradas e auditoria para a ferramenta de autoria de planilhas; não atribui notas clínicas.

## Retomada

Restaurar a mesma pasta a partir do checkpoint mais recente. Se a última reserva está fechada, novos lotes usam somente IDs ainda sem tentativa. Quando as 300 execuções já estão concluídas, `reserve` retorna vazio e não chama o modelo. Se a reserva está ativa e a licença local foi perdida, inspecionar o estado e conciliar a possível execução antes de prosseguir. Nunca usar uma opção de força para repetir chamadas sem verificar.

O checkpoint é versionado como um único arquivo, preservando o histórico de salvamentos. O estado do controlador registra a versão confirmada; um conflito de versão ou resultado de salvamento incerto exige inspeção antes de outra escrita. O mecanismo prioriza não repetir uma requisição cujo resultado possa existir.
