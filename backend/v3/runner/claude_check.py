"""Verifica REALE dell'API di Claude prima della ripartenza del Brain unico (eseguita da root, codice nuovo).

Manda UNA richiesta di consulto identica a quella del Brain (stessa funzione ``consult.consult_payload``: modello,
sforzo, ``max_tokens``, ragionamento adattivo, prompt di consulto, fallback lato server, timeout) con dati di prova, poi
controlla: risposta HTTP 200, ``stop_reason`` completo, decisione nel formato atteso (``consult.parse_response``), uso
dei token leggibile e costo calcolabile (``metering.usage_units``). La chiave si legge dal file dell'ambiente del servizio
(``KEY=VALORE``, nessuna esecuzione di shell) e resta nel processo: non viene MAI stampata. Stampa solo codici.

Uscita 0 = Claude utilizzabile dal Brain; 1 = non utilizzabile (il motivo e' in ``CLAUDE_API=...``).
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

SAMPLE = {
    "symbol": "BTCUSDT", "price": "60000", "regime": "TREND_UP", "timestamp_ms": 1795500000000,
    "market": {"base_tf": "15m", "regime": "TREND_UP", "timeframes": [
        {"tf": "15m", "status": "ok", "atr_bp": 35, "ema_fast_dist_bp": 12, "ema_slow_dist_bp": 40, "rsi": 58},
        {"tf": "1h", "status": "ok", "atr_bp": 70, "ema_fast_dist_bp": 25, "ema_slow_dist_bp": 90, "rsi": 61},
        {"tf": "4h", "status": "ok", "atr_bp": 140, "ema_fast_dist_bp": 60, "ema_slow_dist_bp": 210, "rsi": 63}]},
    "portfolio": {"guardian_mode": "NORMAL", "open_trades": 0, "free_slots": 10, "open_risk_pct": "0"},
    "deepseek": {"side": 1, "stop_price": "59700", "confidence": 0.62, "reasons": ["trend_up", "pullback"],
                 "uncertain": True},
    "note": "Connectivity check before a PAPER restart: answer as you would for a real proposal."}


def read_key(env_file: Path) -> str:
    """``ANTHROPIC_API_KEY`` dal file ``KEY=VALORE`` del servizio; stringa vuota se assente."""
    try:
        for line in env_file.read_text(encoding="utf-8").splitlines():
            k, sep, v = line.strip().partition("=")
            if sep and k.strip() == "ANTHROPIC_API_KEY":
                return v.strip().strip('"').strip("'")
    except OSError:
        pass
    return ""


def verify(config, *, key: str, transport=None) -> tuple[bool, str, dict]:
    """(utilizzabile, codice, dettagli senza segreti). ``transport`` si inietta solo nei test."""
    from backend.v3.runner.consult import ENTRY_PROMPT, FALLBACK_BETA, consult_payload, parse_response
    from backend.v3.runner.metering import usage_units
    from backend.v3.transport import claude_transport
    cp = config.unico.claude if config.unico is not None else None
    if cp is None:
        return False, "CONSULENTE_NON_CONFIGURATO", {}
    if not key:
        return False, "CHIAVE_ASSENTE", {}
    os.environ["ANTHROPIC_API_KEY"] = key                   # solo in questo processo, per il trasporto
    send = transport or claude_transport(timeout_s=cp.timeout_s, betas=(FALLBACK_BETA,))
    try:
        resp = send(consult_payload(cp.model, cp.effort, cp.max_tokens, ENTRY_PROMPT, SAMPLE))
    except Exception:
        return False, "HTTP_O_RETE", {}
    body = getattr(resp, "body", None)
    if getattr(resp, "status_code", None) != 200 or not isinstance(body, dict):
        return False, "HTTP_O_RETE", {}
    if body.get("stop_reason") == "refusal":
        return False, "RIFIUTO_DEL_MODELLO", {}
    try:
        view = parse_response(body, position=False)
    except Exception:
        return False, "FORMATO_DELLA_DECISIONE", {"stop_reason": str(body.get("stop_reason"))[:20]}
    units = usage_units(body, cp.input_usd_per_million, cp.output_usd_per_million)
    usage = body.get("usage") or {}
    if units is None:
        return False, "TOKEN_NON_LEGGIBILI", {}
    return True, "DISPONIBILE", {"modello": cp.model, "verdetto": view.verdict,
                                 "token_ingresso": usage.get("input_tokens"), "token_uscita": usage.get("output_tokens"),
                                 "costo_usd": f"{units / 1_000_000:.4f}"}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="verifica dell'API di Claude per il Brain unico (nessun segreto stampato)")
    ap.add_argument("--config", required=True)
    ap.add_argument("--env-file", required=True)
    a = ap.parse_args(argv)
    from backend.v3.runner.config import load_runner_config
    try:
        config = load_runner_config(Path(a.config).read_bytes())
    except (OSError, ValueError):
        print("CLAUDE_API=CONFIGURAZIONE_ILLEGGIBILE")
        return 1
    ok, code, details = verify(config, key=read_key(Path(a.env_file)))
    print("CLAUDE_API=" + code + "".join(f" {k}={v}" for k, v in details.items()))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
