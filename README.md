# DART — Dental Assessment and Response to Trauma

Research prototype for dentists evaluating traumatic injuries to **permanent teeth**. It includes 14 injury categories, guided questions, a complete-case mode, separate ESE/AAE/compare modes, and a batch evaluation runner. The original HEAD-DENT Streamlit application is retained as `Head-Dent.py`.

The incorporated knowledge is in `knowledge/dart_conditions.py`. `knowledge/catalog.json` is an extraction of its questions and 68 standardized response families. Clinical recommendations in that file were supplied and reviewed by the project owner; this software has **not** undergone clinical validation. Do not use it as an autonomous diagnostic or treatment system.

## Local setup

Requires Python 3.11+ and an OpenAI API key. Keep the key on the server, never in browser code or Git.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dart.txt
export OPENAI_API_KEY="your-key"
uvicorn app.main:app --reload
```

Open <http://127.0.0.1:8000>. Set `OPENAI_MODEL` to select a model; default is `gpt-4o`. The former `SENHA_OPEN_AI` environment variable also works. No case history is saved by the application. Do not enter identifiable patient data in the research prototype. Restrict network access before any public deployment.

## Layout

| Path | Purpose |
| --- | --- |
| `app/main.py` | API, request checks, OpenAI call, response validation |
| `app/static/` | Responsive web interface and supplied DART branding |
| `knowledge/dart_conditions.py` | Supplied DART clinical knowledge and distinctions between guidelines |
| `knowledge/catalog.json` | 14 categories, questions, and response family IDs |
| `evals/run.py` | Repeated, automated assessment of expert-reviewed cases |
| `tests/` | Structural and request validation tests |

## Clinical evaluation

The two supplied primary sources are **ESE, International Endodontic Journal (2021), 54:1473–1481** and **AAE, Journal of Endodontics (2026), 52:1237–1253, DOI 10.1016/j.joen.2026.04.002**. IADT/Dental Trauma Guide classification is represented in the supplied knowledge file; the source site is not bundled. No PDFs are redistributed in this repository.

Each expert-reviewed case is one JSON object per line with `case_id`, `reviewed_by`, `expected_outcome_id`, and `input` matching `/api/assess`. Replace the placeholder in `evals/case_example.jsonl` with deidentified reviewed cases; the example is **not a clinical gold standard**. Include ESE and AAE cases for all 68 families (136 combinations), comparison cases, incomplete and contradictory cases, and repeated runs. Record clinical agreement, critical errors, source attribution, omissions, and stability; a matching ID alone does not establish safe management.

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
python -m evals.run reviewed-cases.jsonl --repeats 10 --output eval-results.csv
```

GitHub Actions runs structural tests on pushes and pull requests. Batch evaluations requiring paid model calls remain an explicit local command; no key is stored in CI.

## Limits of this first version

The clinical decisions and follow-up schedules still rely on the language model interpreting the supplied knowledge. The server verifies answer options, result structure, and family IDs, but does **not** independently verify clinical correctness, guideline attribution, or date arithmetic. Converting each of the 68 families into reviewed, executable decision rules and calculating follow-up dates in code are the next steps before prospective clinical use.

### Conversational DART

The interface opens with a guided triage form. The dentist selects an injury and available findings, leaving unknown fields as “Não informado”. **Iniciar conversa** sends the triage to `/api/chat`; the bot speaks first, asking for clinically necessary missing information or providing guidance when sufficient information is available. The form then gives way to the conversation. **Novo caso** clears the history and returns to triage. There is no full-case text entry or separate assessment result in the interface.

`/api/chat` accepts `context` (the assessment input), `history` (alternating user/assistant pairs), and `message`. It returns conversational `message`, current `guideline`, and optional structured `assessment` for evaluation tools. Later findings and explicit guideline changes are considered across turns. History remains in browser memory until reload or **Novo caso**; conversations allow up to 20 rounds, including the initial bot response. The API stores no conversations in a database. Automated software tests do not establish clinical accuracy.

For repeated expert-labeled conversational tests, use `python -m evals.chat cases.jsonl --repeats 10 --url http://127.0.0.1:8000`. Each JSONL case has `case_id`, `reviewed_by`, `context`, and `turns`; each turn has `message`, `expected_status` (`complete`, `needs_information`, `incompatible`, or `no_assessment`) and optionally `expected_outcome_id`. Results include a CSV and full response transcripts. Calls to a live server use the configured paid model. Clinical ground truth must be supplied by reviewers; matching outcome/status alone does not validate the response text.
