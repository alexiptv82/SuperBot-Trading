"""Closed vocabulary only: no provider bodies, credentials or exception text."""
CODES=frozenset(('balance','auth','rate','network','http','truncated',
                 'prompt_limit','invalid_response','unavailable'))

class ProviderFailure(ValueError):
    def __init__(self,code):
        self.code=code if code in CODES else 'unavailable'
        super().__init__(self.code)

def failure_code(exc):
    return exc.code if isinstance(exc,ProviderFailure) else 'invalid_response'
