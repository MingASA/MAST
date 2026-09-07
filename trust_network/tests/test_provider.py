from trust_network.demo import provider
from trust_network.demo.provider import ProviderConfig


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
