import asyncio
import pytest
from fastapi import HTTPException
from app import main


def test_language_is_not_limited_to_three_codes():
    for code in ['ja','ar','hi','sw','zh-Hant','Guarani']:
        assert main.Assessment(guideline='ESE',language=code).language==code


def test_translation_cache_and_immutable_keys(monkeypatch):
    main.TRANSLATIONS.clear()
    calls=[]
    async def fake(payload,schema):
        calls.append(payload)
        return schema(**{key:'Translated '+key for key in schema.model_fields})
    monkeypatch.setattr(main,'request_model',fake)
    request=main.LocalizationRequest(language='ja',injury_id='T01')
    first=asyncio.run(main.localize(request));second=asyncio.run(main.localize(request))
    assert first==second and len(calls)==1
    assert 'injury_T01' in first['texts']
    assert calls[0]['response_format']['json_schema']['strict'] is True


def test_localization_rejects_unknown_injury():
    with pytest.raises(HTTPException):
        asyncio.run(main.localize(main.LocalizationRequest(language='en',injury_id='unknown')))


def test_selected_language_overrides_portuguese_launch(monkeypatch):
    captured={}
    async def fake(payload,schema):
        captured.update(payload)
        return main.ChatReply(message="Welche Angaben fehlen?",guideline="ESE",assessment=None)
    monkeypatch.setenv('OPENAI_API_KEY','test-only')
    monkeypatch.setattr(main,'request_model',fake)
    result=asyncio.run(main.chat(main.ChatRequest(context={'guideline':'ESE','injury_id':'T01','language':'de'},message='Receba esta ficha de triagem')))
    system=captured['messages'][0]['content']
    assert 'AUTHORITATIVE RESPONSE LANGUAGE: de' in system
    assert 'maintain that language throughout the conversation' not in system
    assert 'historical messages' in system
    assert result.message=="Welche Angaben fehlen?"
