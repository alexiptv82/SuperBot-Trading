"""Client DeepSeek con la sola libreria standard. La chiave sta solo nell'intestazione Authorization: non entra mai in
un messaggio d'errore, in un registro o in un file. Nessuna ripetizione automatica: un errore e' un ciclo senza
decisione (le posizioni restano gestite da stop e TP del conto virtuale), mai una raffica di richieste a pagamento."""
import json
import time
import urllib.error
import urllib.request


class ModelError(Exception):
    """kind: auth | balance | rate | server | network | format | length. `usage` e' valorizzato se il fornitore ha risposto."""

    def __init__(self, kind: str, msg: str, usage: dict = None, status: int = None):
        super().__init__("%s: %s" % (kind, msg))
        self.kind, self.usage, self.status = kind, usage or {"hit": 0, "miss": 0, "out": 0}, status


def _scrub(text: str, key: str) -> str:
    text = str(text)
    return text.replace(key, "***") if key else text


def build_body(cfg, system: str, user: str) -> dict:
    body = {
        "model": cfg.model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "max_tokens": int(cfg.max_tokens),
        "temperature": float(cfg.temperature),
        "response_format": {"type": "json_object"},
        "stream": False,
    }
    if not cfg.thinking:
        body["thinking"] = {"type": "disabled"}
    return body


def parse_usage(u: dict) -> dict:
    u = u if isinstance(u, dict) else {}
    hit = int(u.get("prompt_cache_hit_tokens") or 0)
    miss = u.get("prompt_cache_miss_tokens")
    if miss is None:
        miss = max(0, int(u.get("prompt_tokens") or 0) - hit)
    det = u.get("completion_tokens_details") if isinstance(u.get("completion_tokens_details"), dict) else {}
    return {"hit": hit, "miss": int(miss), "out": int(u.get("completion_tokens") or 0),
            "reasoning": int(det.get("reasoning_tokens") or 0)}


def call(cfg, api_key: str, system: str, user: str, opener=urllib.request.urlopen, clock=time.time) -> dict:
    """Una richiesta. Ritorna {"content", "usage", "latency_ms", "finish_reason", "model"} oppure alza ModelError."""
    if not api_key:
        raise ModelError("auth", "chiave assente")
    url = cfg.base_url.rstrip("/") + "/chat/completions"
    data = json.dumps(build_body(cfg, system, user)).encode()
    req = urllib.request.Request(url, data=data, method="POST", headers={
        "Content-Type": "application/json", "Authorization": "Bearer " + api_key, "User-Agent": "superbot-ai-shadow"})
    t0 = clock()
    try:
        with opener(req, timeout=cfg.timeout_s) as r:
            raw = r.read()
    except urllib.error.HTTPError as e:
        try:
            body = _scrub(e.read()[:200].decode("utf-8", "replace"), api_key)
        except Exception:
            body = ""
        kind = {401: "auth", 403: "auth", 402: "balance", 429: "rate"}.get(e.code, "server" if e.code >= 500 else "format")
        raise ModelError(kind, "HTTP %d %s" % (e.code, body), status=e.code)
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise ModelError("network", _scrub(type(e).__name__ + " " + str(e)[:120], api_key))
    latency = int((clock() - t0) * 1000)
    try:
        payload = json.loads(raw)
        choice = payload["choices"][0]
        content = choice["message"].get("content") or ""
        usage = parse_usage(payload.get("usage"))
        finish = str(choice.get("finish_reason"))
    except (ValueError, KeyError, IndexError, TypeError, AttributeError):
        raise ModelError("format", "risposta non leggibile")
    if finish == "length":
        raise ModelError("length", "risposta troncata (max_tokens)", usage=usage)
    if not content.strip():
        raise ModelError("format", "contenuto vuoto", usage=usage)
    return {"content": content, "usage": usage, "latency_ms": latency, "finish_reason": finish,
            "model": str(payload.get("model") or cfg.model)}
