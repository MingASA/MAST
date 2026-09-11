from trust_network.demo import provider
from trust_network.demo.provider import ProviderConfig
import json


def test_config_does_not_execute_or_expose_secret(tmp_path):
    p=tmp_path/'env'
    p.write_text('OPENAI_API_KEY=test-secret\nCAI_MODEL=openai/MiniMax-M3\nOPENAI_API_BASE=https://example.invalid/v1\nIGNORED=$(touch should-not-exist)\n')
    config=ProviderConfig.load(p)
    assert config.model=='MiniMax-M3'
    assert 'test-secret' not in repr(config)
    assert not (tmp_path/'should-not-exist').exists()


def test_json_retry_accounts_for_both_attempts(monkeypatch):
    calls=[]
    def reply(*args):
        calls.append(args)
        return (None if len(calls)==1 else {'action':'pass'}),{'total_tokens':12}
    monkeypatch.setattr(provider,'_complete_once',reply)
    result,usage=provider.complete(ProviderConfig('model','https://example.invalid','test'),'system','prompt')
    assert result['action']=='pass' and usage['attempts']==2
    assert usage['total_tokens']==24


def test_traced_retry_archives_each_request_and_response(monkeypatch):
    calls=[]
    def reply(config,system,prompt):
        calls.append(prompt)
        content='not-json' if len(calls)==1 else '{"action":"hold","reason":"check"}'
        raw={'choices':[{'message':{'content':content},'finish_reason':'stop'}],
             'usage':{'total_tokens':3,'prompt_tokens':2,'completion_tokens':1}}
        return ((None if len(calls)==1 else {'action':'hold','reason':'check'}),raw['usage'],
                {'model':config.model},json.dumps(raw),raw)
    monkeypatch.setattr(provider,'_complete_once_trace',reply)
    result,usage,attempts=provider.complete_traced(
        ProviderConfig('model','https://example.invalid','secret'),'system','prompt')
    assert result['action']=='hold' and usage=={
        'total_tokens':6,'prompt_tokens':4,'completion_tokens':2,'attempts':2}
    assert len(attempts)==2 and attempts[0]['error']['type']=='InvalidJSONDecision'
    assert json.loads(attempts[1]['response_text'])['choices'][0]['message']['content'].startswith('{')
    assert calls[1].startswith('prompt\n请确保返回完整')
    assert 'Authorization' not in json.dumps(attempts[0]['request'])


def test_traced_retries_transient_provider_failure(monkeypatch):
    calls=[]
    def reply(config,system,prompt):
        calls.append(prompt)
        if len(calls)==1:
            raise RuntimeError('MiniMax network connection failed')
        usage={'total_tokens':5,'prompt_tokens':3,'completion_tokens':2}
        raw={'choices':[{'message':{'content':'{"action":"hold","reason":"check"}'},
                         'finish_reason':'stop'},], 'usage':usage}
        return {'action':'hold','reason':'check'},usage,{'model':config.model},json.dumps(raw),raw
    monkeypatch.setattr(provider,'_complete_once_trace',reply)
    result,usage,attempts=provider.complete_traced(
        ProviderConfig('model','https://example.invalid','secret'),'system','prompt')
    assert result['action']=='hold' and usage['attempts']==2
    assert len(attempts)==2 and attempts[0]['error']['message']=='MiniMax network connection failed'
    assert calls[1].startswith('prompt\n请确保返回完整')
