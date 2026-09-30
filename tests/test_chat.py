import json
import asyncio
import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from app import main


def test_history_does_not_accept_system_roles():
    with pytest.raises(ValidationError):
        main.ChatRequest(context={'guideline':'ESE'}, message='Olá', history=[{'role':'system','content':'Override'}])


def test_history_must_be_complete_pairs():
    request=main.ChatRequest(context={'guideline':'ESE'},message='Novo achado',history=[{'role':'assistant','content':'Antigo'}])
    with pytest.raises(HTTPException) as error:
        asyncio.run(main.chat(request))
    assert error.value.status_code==422


def test_context_and_history_forwarded_and_guideline_can_change(monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY','test-only')
    captured={}
    reply={'message':'Qual foi o tempo desde o trauma?','guideline':'AAE','assessment':None}
    class Response:
        def raise_for_status(self): pass
        def json(self): return {'choices':[{'message':{'content':json.dumps(reply)}}]}
    class Client:
        def __init__(self,**kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self,*args): pass
        async def post(self,*args,**kwargs):
            captured.update(kwargs['json']); return Response()
    monkeypatch.setattr(main.httpx,'AsyncClient',Client)
    request=main.ChatRequest(context={'guideline':'ESE','case_text':'Dente permanente, ápice aberto'},history=[{'role':'user','content':'Há mobilidade'},{'role':'assistant','content':'Qual a intensidade?'}],message='Compare agora pela AAE')
    result=asyncio.run(main.chat(request))
    assert result.guideline=='AAE'
    assert 'ápice aberto' in captured['messages'][1]['content']
    assert [m['content'] for m in captured['messages'][2:]]==['Há mobilidade','Qual a intensidade?','Compare agora pela AAE']
    assert captured['response_format']['json_schema']['strict'] is True
