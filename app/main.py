"""DART research prototype: one clinical service for UI and batch evaluation."""

import json
import os
from datetime import date
from pathlib import Path
from typing import Literal

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from knowledge.dart_conditions import condicoes_dart

ROOT = Path(__file__).resolve().parents[1]
CATALOG = json.loads((ROOT / "knowledge/catalog.json").read_text())
BY_ID = {item["id"]: item for item in CATALOG}
app = FastAPI(title="DART", version="0.1.0", description="Research prototype for dentists")
app.mount("/static", StaticFiles(directory=ROOT / "app/static"), name="static")


class Assessment(BaseModel):
    injury_id: str | None = None
    guideline: Literal["ESE", "AAE", "COMPARE"]
    answers: dict[str, str] = Field(default_factory=dict)
    case_text: str = Field(default="", max_length=12000)
    reference_date: date | None = None
    language: Literal["pt", "en", "es"] = "pt"


class Result(BaseModel):
    injury_id: str | None
    outcome_id: str | None
    status: Literal["complete", "needs_information", "incompatible"]
    missing_information: list[str]
    incompatibilities: list[str]
    management_now: str
    endodontic_treatment: str
    endodontic_protocol: str
    follow_up: str
    warning_signs: str
    ese: str
    aae: str
    differences: str
    source_notes: str


@app.get("/")
def index():
    return FileResponse(ROOT / "app/static/index.html")


@app.get("/api/catalog")
def catalog():
    return {"conditions": CATALOG, "families": sum(len(c["outcomes"]) for c in CATALOG)}


@app.post("/api/assess", response_model=Result)
async def assess(data: Assessment):
    if data.injury_id and data.injury_id not in BY_ID:
        raise HTTPException(422, "Unknown injury ID")
    if not data.injury_id and not data.case_text.strip():
        raise HTTPException(422, "Select an injury or describe the case")
    condition = BY_ID.get(data.injury_id)
    if condition:
        valid = {q["key"]: {o["value"] for o in q["options"]} for q in condition["questions"]}
        if any(key not in valid or value not in valid[key] for key, value in data.answers.items()):
            raise HTTPException(422, "An answer does not match the selected condition")
    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("SENHA_OPEN_AI")
    if not api_key:
        raise HTTPException(503, "Configure OPENAI_API_KEY on the server")

    answers = []
    if condition:
        for q in condition["questions"]:
            selected = next((o["label"] for o in q["options"] if o["value"] == data.answers.get(q["key"])), None)
            answers.append({"question": q["label"], "answer": selected})
    case = {"selected_condition": condition["name"] if condition else None,
            "allowed_outcomes": condition["outcomes"] if condition else [],
            "guideline": data.guideline, "answers": answers,
            "case_description": data.case_text, "reference_date": str(data.reference_date) if data.reference_date else None,
            "today": str(date.today()), "language": data.language}
    system = (condicoes_dart + "\n\nOUTPUT CONTRACT: Reply as one JSON object with exactly these keys: "
              "injury_id, outcome_id, status, missing_information, incompatibilities, management_now, "
              "endodontic_treatment, endodontic_protocol, follow_up, warning_signs, ese, aae, differences, source_notes. "
              "status must be complete, needs_information, or incompatible. If clinical information needed to choose "
              "a family or management is missing, use needs_information and do not make a definitive recommendation. "
              "If findings contradict the selected injury, use incompatible. For a selected injury, outcome_id must "
              "be one of allowed_outcomes only when status is complete; otherwise null. If no injury is selected, "
              "identify it from the case or ask for missing information. Never invent a family ID. "
              "Use the case language. Distinguish IADT classification, ESE and AAE guidance in source_notes. "
              "Do not claim to have verified a source beyond this incorporated knowledge base.")
    payload = {"model": os.getenv("OPENAI_MODEL", "gpt-4o"),
               "messages": [{"role": "system", "content": system},
                            {"role": "user", "content": json.dumps(case, ensure_ascii=False)}],
               "response_format": {"type": "json_object"}, "temperature": 0,
               "max_tokens": 2400}
    try:
        async with httpx.AsyncClient(timeout=90) as client:
            response = await client.post("https://api.openai.com/v1/chat/completions", json=payload,
                                         headers={"Authorization": f"Bearer {api_key}"})
        response.raise_for_status()
        result = Result.model_validate_json(response.json()["choices"][0]["message"]["content"])
    except (httpx.HTTPError, KeyError, ValueError) as exc:
        raise HTTPException(502, "Model request or response failed; no assessment was issued") from exc
    if condition and result.injury_id != condition["id"] and result.status == "complete":
        raise HTTPException(502, "Inconsistent injury classification; no assessment was issued")
    allowed = {o["id"] for o in condition["outcomes"]} if condition else {
        o["id"] for item in CATALOG for o in item["outcomes"]}
    if result.outcome_id and result.outcome_id not in allowed:
        raise HTTPException(502, "Invalid response family; no assessment was issued")
    if result.status != "complete" and result.outcome_id:
        raise HTTPException(502, "Premature response family; no assessment was issued")
    if result.status == "complete" and not result.outcome_id:
        raise HTTPException(502, "Missing response family; no assessment was issued")
    return result
