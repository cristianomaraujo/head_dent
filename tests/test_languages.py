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
