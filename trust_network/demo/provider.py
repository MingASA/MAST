"""MiniMax configuration reader. Never logs or copies credentials."""
from dataclasses import dataclass, field
from pathlib import Path
import json
import re
import urllib.request
import urllib.error


class ProviderTraceError(RuntimeError):
    """Provider failure carrying the attempts that can be safely archived."""

    def __init__(self, message, attempts):
        super().__init__(message)
        self.attempts=attempts


@dataclass(frozen=True)
class ProviderConfig:
    model: str
    base_url: str
    api_key: str = field(repr=False)
    max_tokens: int = 2500
    temperature: float = .2

    def __post_init__(self):
        if not 0<=self.temperature<=2: raise ValueError('temperature must be in [0,2]')

    @classmethod
    def load(cls,path: Path):
        values={}
        for line in path.read_text().splitlines():
            line=line.strip()
            if line and not line.startswith('#') and '=' in line:
                key,value=line.removeprefix('export ').split('=',1)
                values[key.strip()]=value.strip().strip('\"\'')
        model=values.get('CAI_MODEL','MiniMax-M3').removeprefix('openai/')
        base=values.get('OPENAI_BASE_URL',values.get('OPENAI_API_BASE','')).rstrip('/')
        key=values.get('OPENAI_API_KEY','')
        if not key or not base.startswith('https://'): raise ValueError('missing credential or HTTPS endpoint')
        return cls(model,base,key)


def _request_body(config: ProviderConfig, system: str, prompt: str):
    body={'model':config.model,'messages':[{'role':'system','content':system},{'role':'user','content':prompt}],
          'max_completion_tokens':config.max_tokens,'temperature':config.temperature,'reasoning_split':True}
    if config.model=='MiniMax-M3': body['thinking']={'type':'disabled'}
    return body


def _parse_content(raw):
    choice=raw['choices'][0]
    if choice.get('finish_reason')=='length': raise RuntimeError('MiniMax response truncated')
    content=re.sub(r'<think>.*?</think>','',choice['message'].get('content',''),flags=re.S).strip()
    content=re.sub(r'^```(?:json)?\s*|\s*```$','',content)
    try:
        result=json.loads(content)
    except json.JSONDecodeError:
        try: result,_=json.JSONDecoder().raw_decode(content[content.index('{'):])
        except (ValueError,json.JSONDecodeError): result=None
    return result


def _complete_once_trace(config: ProviderConfig, system: str, prompt: str):
    body=_request_body(config,system,prompt)
    request=urllib.request.Request(config.base_url+'/chat/completions',data=json.dumps(body).encode(),
              headers={'Authorization':'Bearer '+config.api_key,'Content-Type':'application/json'})
    try:
        with urllib.request.urlopen(request,timeout=90) as response:
            response_text=response.read().decode('utf-8')
            raw=json.loads(response_text)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f'MiniMax HTTP {exc.code}; response body omitted to protect credentials') from None
    except urllib.error.URLError:
        raise RuntimeError('MiniMax network connection failed') from None
    if raw.get('base_resp',{}).get('status_code',0): raise RuntimeError('MiniMax application error')
    return _parse_content(raw),raw.get('usage',{}),body,response_text,raw


def _complete_once(config: ProviderConfig, system: str, prompt: str):
    result,usage,_,_,_=_complete_once_trace(config,system,prompt)
    return result,usage


def complete(config: ProviderConfig, system: str, prompt: str):
    usage={'total_tokens':0,'prompt_tokens':0,'completion_tokens':0,'attempts':0}
    for attempt in range(2):
        suffix='' if not attempt else '\n请确保返回完整、合法的JSON对象，不要Markdown，不要在字符串中使用未转义双引号。'
        result,current=_complete_once(config,system,prompt+suffix)
        for key in ('total_tokens','prompt_tokens','completion_tokens'): usage[key]+=current.get(key,0)
        usage['attempts']+=1
        if isinstance(result,dict): return result,usage
    raise RuntimeError('MiniMax returned invalid JSON after two attempts')


def complete_traced(config: ProviderConfig, system: str, prompt: str):
    """Complete with the normal retry policy and return a raw call trace.

    Request bodies contain no authorization header. Each attempt retains the
    exact response text when one was received, its parsed content, usage, and
    a sanitized error when the provider did not return a usable response.
    """
    totals={'total_tokens':0,'prompt_tokens':0,'completion_tokens':0}
    usage_known=True; attempts=[]
    for attempt in range(2):
        suffix='' if not attempt else '\n请确保返回完整、合法的JSON对象，不要Markdown，不要在字符串中使用未转义双引号。'
        entry={'attempt':attempt+1,'request':_request_body(config,system,prompt+suffix)}
        try:
            result,current,body,response_text,raw=_complete_once_trace(config,system,prompt+suffix)
            entry.update({'request':body,'response_text':response_text,'response':raw,
                          'parsed':result,'usage':current})
            attempts.append(entry)
            if not isinstance(current,dict): usage_known=False
            else:
                for key in totals:
                    value=current.get(key)
                    if type(value) is not int or value<0: usage_known=False
                    else: totals[key]+=value
            if isinstance(result,dict):
                usage=dict(totals,attempts=len(attempts)) if usage_known else None
                return result,usage,attempts
            entry['error']={'type':'InvalidJSONDecision','message':'response content was not a JSON object'}
        except Exception as exc:
            entry['error']={'type':type(exc).__name__,'message':str(exc)}
            attempts.append(entry)
            raise ProviderTraceError(str(exc),attempts) from None
    raise ProviderTraceError('MiniMax returned invalid JSON after two attempts',attempts)
