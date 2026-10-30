"""Bounded provider transports for the new Brain single-account PAPER supervisor.

No network unless explicitly configured and invoked by the AI worker.
Never log response bodies, exception text, keys, or full prompts.
"""
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_CEILING
import json
import urllib.request

from director.brain_free.provider import call as deepseek_call
from director.brain_free.config import Config as DeepSeekConfig


@dataclass(frozen=True)
class PriceLimit:
    """Conservative max *reserved* cost; not API invoiced-cost metering."""
    deepseek_input_m: str
    deepseek_output_m: str
    claude_input_m: str
    claude_output_m: str
    daily_usd: str
    max_input_bytes: int=120000
    max_output_tokens: int=4096
    reviewer_enabled: bool=True

    def _usd(self,item):
        try:
            n=Decimal(str(item))
            if not n.is_finite() or n<=0 or n>1000:
                raise ValueError('invalid_ai_price')
            return n
        except (TypeError,InvalidOperation):
            raise ValueError('invalid_ai_price') from None

    def reservation(self):
        if type(self.max_input_bytes)!=int or not 1000<=self.max_input_bytes<=130000 or (
            type(self.max_output_tokens)!=int or
            not 256<=self.max_output_tokens<=16384):
            raise ValueError('invalid_token_ceiling')
        per_input=self._usd(self.deepseek_input_m)
        per_output=self._usd(self.deepseek_output_m)
        if self.reviewer_enabled:
            per_input+=self._usd(self.claude_input_m)
            per_output+=self._usd(self.claude_output_m)
        daily=self._usd(self.daily_usd)
        # Bound tokens pessimistically by UTF-8 bytes; the provider itself
        # also gets an explicit max output tokens parameter.
        usd=(Decimal(self.max_input_bytes)*per_input+
             Decimal(self.max_output_tokens)*per_output)/Decimal(1000000)
        micro=int((usd*Decimal(1000000)).to_integral_value(rounding=ROUND_CEILING))
        budget=int((daily*Decimal(1000000)).to_integral_value(rounding=ROUND_CEILING))
        if micro<=0 or micro>budget:
            raise ValueError('daily_budget_below_single_analysis_reservation')
        return budget,micro


def provider_prompt_guard(system,user,max_bytes):
    if not isinstance(system,str) or not isinstance(user,str):
        raise ValueError('invalid_prompt')
    if len((system+user).encode('utf-8'))>max_bytes:
        raise ValueError('provider_prompt_exceeds_reserved_ceiling')


def make_primary(key,*,max_input_bytes=120000,max_tokens=4096,timeout_s=10,
                 inner=deepseek_call):
    if not key or type(max_tokens)!=int or not 256<=max_tokens<=16384 or (
        type(timeout_s)!=int or not 1<=timeout_s<=25):
        raise ValueError('invalid_primary_transport')
    config=DeepSeekConfig(model='deepseek-flash',thinking='high',
                          max_tokens=max_tokens,timeout_s=timeout_s)
    def invoke(system,user):
        provider_prompt_guard(system,user,max_input_bytes)
        return inner(key,system,user,config)
    return invoke


def claude_message(key,model,system,user,*,max_tokens=4096,timeout_s=10,
                   opener=urllib.request.urlopen):
    if not key or not model or not isinstance(model,str) or len(model)>100 or (
        not isinstance(system,str) or not isinstance(user,str)):
        raise ValueError('invalid_reviewer_transport')
    body={'model':model,'max_tokens':max_tokens,'system':system,
          'messages':[{'role':'user','content':user}]}
    req=urllib.request.Request('https://api.anthropic.com/v1/messages',
       data=json.dumps(body,allow_nan=False).encode('utf-8'),
       headers={'x-api-key':key,'anthropic-version':'2023-06-01',
                'Content-Type':'application/json'},method='POST')
    try:
        with opener(req,timeout=timeout_s) as resp:
            data=json.loads(resp.read(400001))
        if data.get('stop_reason')!='end_turn':
            raise ValueError('review_truncated_or_incomplete')
        blocks=data.get('content')
        if not isinstance(blocks,list) or not blocks:
            raise ValueError('invalid_reviewer_content')
        content=''.join(b['text'] for b in blocks
                        if isinstance(b,dict) and b.get('type')=='text'
                        and isinstance(b.get('text'),str))
        if not content or len(content)>120000:
            raise ValueError('invalid_reviewer_content')
        usage=data.get('usage') or {}
        safe={k:usage[k] for k in ('input_tokens','output_tokens')
              if type(usage.get(k))==int and 0<=usage[k]<=10000000}
        return content,safe
    except Exception:
        raise ValueError('review_provider_unavailable') from None


def make_reviewer(key,model,*,max_input_bytes=120000,max_tokens=4096,
                  timeout_s=10,inner=claude_message):
    if not key or not model or type(timeout_s)!=int or not 1<=timeout_s<=25:
        raise ValueError('invalid_reviewer_transport')
    def invoke(system,user):
        provider_prompt_guard(system,user,max_input_bytes)
        return inner(key,model,system,user,max_tokens=max_tokens,
                     timeout_s=timeout_s)
    return invoke
