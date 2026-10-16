# Avaliação de uma resposta por execução

O protocolo `single-triage-response-v3` substitui, para o objetivo atual do estudo, os pilotos anteriores de três trocas. Os arquivos antigos devem ser preservados e não agregados à nova coleta. O programa não modifica o chatbot nem as regras clínicas.

## Desfechos e unidade

Cada execução tem histórico vazio e termina após a primeira resposta do bot à ficha de triagem. O desfecho primário é `adequada_final` (0/1): em casos completos, manejo compatível com os dados fornecidos e com os itens essenciais do gabarito; em incompletos, reconhecimento da insuficiência e solicitação dos dados essenciais omitidos, sem presumi-los ou indicar conduta definitiva dependente deles. Orientação provisória segura é aceitável.

Erro crítico e presunção de dados são secundários binários. Registrar os julgamentos de dois revisores e a adjudicação separadamente. Consistência não é nota atribuída pelo avaliador: as cinco repetições são identificadas para análise estatística. Caso, família, versão, diretriz e repetição permanecem identificados; essas observações são dependentes.

São 400 casos, 800 entradas (completa e incompleta por caso), duas diretrizes e cinco repetições: 8.000 execuções e até 8.000 chamadas, antes de eventuais falhas/reenvios. A ordem mesclada do planejamento original foi preservada.

## Conferir os dados realmente enviados

A nova planilha tem as abas `Avaliacoes`, `Entradas`, `Casos`, `Gabaritos`, `Planejamento`, `Dicionario`, `Codigos_origem` e `Metodo`. As narrativas de `Casos` são referências do avaliador, não conteúdo injetado no contexto inicial. A API recebe somente as seleções da ficha, diretriz, idioma e data de referência, com `case_text=""`, além do relógio simulado `evaluation_date`. A mensagem inicial equivale à do site. Não é um teste de cliques ou de tradução da interface.

Antes da coleta paga, conferir cada entrada na aba `Entradas`: se as seleções sustentam a conduta de referência nos completos e se a omissão está alinhada ao que se espera solicitar nos incompletos. Preencher `aprovacao_entrada=1`, identificador do revisor e data. A revisão anterior dos casos e diretrizes foi preservada; esta conferência é da adaptação ao formulário. Não classificar como erro do bot uma conduta que dependa de informação que a ficha não lhe forneceu.

As entradas completas D393–D396 têm o campo C sem seleção. O programa não infere um valor. Corrigir o mapeamento, ou registrar uma justificativa clínica explícita de que os dados já fornecidos bastam à conduta avaliada. Um campo não preenchido não implica necessariamente insuficiência clínica, mas requer justificativa antes de tratar aquela ficha como completa. Se os códigos forem alterados, regenerar a descrição da triagem; o programa rejeita divergência entre códigos e texto exibido.

Os dados essenciais a solicitar vieram do banco revisado e devem ser conferidos contra os campos reais retidos. Não exigir perguntas irrelevantes nem todos os campos em branco como se fossem necessariamente essenciais. As aprovações começam vazias; nenhuma avaliação clínica foi inventada.

## Usar o executor

Instalar `requirements-evals.txt`, salvar a planilha como `casos_v3.xlsx` e preparar uma nova pasta:

```powershell
python -m evals.single_response prepare casos_v3.xlsx --out-dir eval_runs/dart400_v3 --reviewed-by project-owner
```

A preparação não usa o modelo; congela entradas, gabaritos, ordem e hashes. Pode ser feita para conferir o banco antes das aprovações, mas a coleta bloqueia antes de qualquer chamada caso ainda haja entrada não aprovada. Após alterar aprovações ou seleções no Excel, preparar outra pasta, sem sobrescrever a anterior.

Após a conferência das entradas, começar com uma execução (uma chamada):

```powershell
python -m evals.single_response run eval_runs/dart400_v3 --url https://headdent-production.up.railway.app --max-executions 1
```

Para um lote posterior, definir explicitamente `--max-executions 100`. Nunca há avanço automático para a segunda ou terceira troca. O coletor preserva modelo, fonte, relógio, tentativas, consumo informado e erros; o controle de retomada e de requisição incerta é o mesmo documentado em `TESTAGENS.md`.

## Tabulação

`avaliacoes.csv` é a tabela principal, com uma linha por execução, triagem, resposta real, referência e campos clínicos vazios. Relacionar ao Excel por `execution_id`, preservando as avaliações manuais numa cópia de trabalho. Os arquivos exportados são regenerados; não digitar notas diretamente no CSV da coleta. `resultados.csv` e `conferencia.csv` são registros auxiliares do coletor compartilhado; a referência para o novo desenho é `avaliacoes.csv`.

Vazio significa não avaliado; 0 é julgamento negativo. Falha técnica ou ausência de resposta não recebe automaticamente nota de adequação: relatar separadamente o fluxo de perdas e as falhas. O Excel mostra a proporção adequada apenas entre respostas com julgamento final preenchido; essa descrição não substitui a análise pareada/agrupada do estudo.

Para regenerar a tabela sem chamadas:

```powershell
python -m evals.single_response export eval_runs/dart400_v3
```

Os testes de software são simulados e não medem adequação clínica:

```powershell
python -m pytest -q
```
