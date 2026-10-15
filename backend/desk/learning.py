"""Registro di apprendimento: i valori su cui il bot decide e cio' che ne e' seguito.

Serve a qualunque modello futuro (filtro di probabilita', calibrazione, analisi dei candidati scartati).
Non cambia in nulla le decisioni del bot. Regole:
- file unico, solo aggiunte (append-only), una riga JSON per evento, versione dello schema in ogni riga;
- NON viene azzerato dal reset del portafoglio: ogni riga porta portafoglio e numero di run, cosi' lo
  storico di tutte le run resta utilizzabile (e confrontabile) anche dopo un reset a 1000$;
- scrivere non deve mai fermare il bot: ogni errore e' assorbito (la funzione ritorna False);
- tetto di dimensione: oltre il tetto i soli "candidati" non si scrivono piu', i trade si'.

Eventi (campo "ev"):
  open        apertura: feature d'ingresso, decisione, 1R in dollari, piano di entrata diversificata
  split_fill  seconda gamba eseguita
  split_cancel seconda gamba annullata (con il motivo)
  close       chiusura (finale o parziale): net, net_r additivo, MAE/MFE, durata, gambe
  candidate   decisione di aprire NON eseguita (cooldown, soglia, R:R, rifiuto del conto) con le feature,
              per etichettarne l'esito in seguito con i prezzi di mercato (candidati scartati)
"""
from __future__ import annotations

import json
import math
import os
import time
from typing import Any, Optional

LEARN_FILE = "learning_log.jsonl"
SCHEMA = 1
MAX_BYTES_CANDIDATES = 40 * 1024 * 1024    # sopra questo i candidati scartati non si scrivono piu'
MAX_BYTES_ALL = 250 * 1024 * 1024          # tetto assoluto di sicurezza

# Etichette passive aggiunte a OGNI riga scritta (le imposta il ciclo del bot). Oggi: claude_win = 1 se in quel
# momento Claude poteva essere consultato dal calendario, 0 se no; assente se non c'e' un calendario.
# Servono solo a separare i dati "con Claude" da quelli "solo regole" nell'analisi: non influenzano nulla.
STAMP: dict = {}


def _num(x: Any, nd: int = 5) -> Optional[float]:
    """Numero JSON-sicuro: None per NaN/inf/non numerico (un NaN nel registro avvelenerebbe i modelli)."""
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    if math.isnan(v) or math.isinf(v):
        return None
    return round(v, nd)


def _sign(s: Any) -> int:
    """'su'/'bull' -> 1, 'giu'/'bear' -> -1, altro -> 0 (i fatti del segnale sono testi)."""
    t = str(s or "").lower()
    if t in ("su", "up") or "bull" in t:
        return 1
    if t in ("giu", "down") or "bear" in t:
        return -1
    return 0


def tier_of(symbol: str) -> str:
    base = symbol.upper().replace("USDT", "").replace("PERP", "").strip("/:")
    if base in ("BTC", "XAU", "XAG"):
        return "A"
    return "B" if base == "ETH" else "C"


def build_features(symbol: str, reading: Any, ctx: Optional[dict], dec: Optional[dict], now_ms: int,
                   btc_reading: Any = None, extra: Optional[dict] = None) -> dict:
    """Valori d'ingresso, tutti conoscibili al momento della decisione (nessun dato futuro).
    Funzione pura e tollerante: dati mancanti diventano None, non errori."""
    f: dict = {}
    if reading is not None:
        fa = getattr(reading, "facts", None) or {}
        f.update(
            sig_side=int(getattr(reading, "side", 0) or 0),
            sig_score=_num(getattr(reading, "score", None), 1),
            sig_long=_num(getattr(reading, "long_score", None), 1),
            sig_short=_num(getattr(reading, "short_score", None), 1),
            atr_pct=_num(getattr(reading, "atr_pct", None)),
            sig_sl_pct=_num(getattr(reading, "sl_pct", None)),
            sig_tp_pct=_num(getattr(reading, "tp_pct", None)),
            sig_type=str(getattr(reading, "trade_type", "") or ""),
            pattern=str(getattr(reading, "pattern", "") or ""),
            rsi1h=_num(fa.get("rsi1h"), 1),
            roc24h=_num(fa.get("roc24h")),
            vol_ratio=_num(fa.get("vol_ratio"), 2),
            ema20_50_1h=_sign(fa.get("ema20_50_1h")),
            ema50_200_4h=_sign(fa.get("ema50_200_4h")),
            daily_trend=_sign(fa.get("daily_trend")),
            seasonal=str(getattr(reading, "seasonal_note", "") or "")[:80],
            why=[str(w)[:60] for w in (getattr(reading, "why", None) or [])[:8]],
            price=_num(getattr(reading, "price", None), 8),
        )
    ctx = ctx or {}
    fund = (ctx.get("funding") or {}).get(symbol) or {}
    oi = (ctx.get("oi") or {}).get(symbol) or {}
    ls = (ctx.get("ls_ratio") or {}).get(symbol) or {}
    f.update(
        funding_rate=_num(fund.get("rate"), 8), funding_pred=_num(fund.get("predicted"), 8),
        funding_long_cost_8h_bp=_num(fund.get("long_cost_8h_bp"), 3),
        oi_usd=_num(oi.get("oi_usd"), 0), oi_change_24h=_num(oi.get("oi_change_24h"), 4),
        ls_ratio=_num(ls.get("ratio"), 3),
    )
    if btc_reading is not None:
        bfa = getattr(btc_reading, "facts", None) or {}
        f.update(btc_roc24h=_num(bfa.get("roc24h")), btc_score=_num(getattr(btc_reading, "score", None), 1),
                 btc_side=int(getattr(btc_reading, "side", 0) or 0))
    t = time.gmtime(now_ms / 1000)
    f.update(hour_utc=t.tm_hour, dow=t.tm_wday, tier=tier_of(symbol))
    if dec:
        sl, tp = dec.get("stop_loss_pct") or 0, dec.get("take_profit_pct") or 0
        f.update(
            conf=_num(dec.get("confidence"), 0), dec_type=str(dec.get("trade_type", "") or ""),
            dec_lev=_num(dec.get("leverage"), 0), dec_margin=_num(dec.get("margin_usd"), 2),
            dec_sl_pct=_num(sl), dec_tp_pct=_num(tp) if tp else None,
            dec_rr=_num(tp / sl, 2) if sl and tp else None,
            dec_action=str(dec.get("action", "")), reason=str(dec.get("reason", ""))[:160],
        )
    if extra:   # campi aggiuntivi gia' calcolati dal chiamante (es. calendario macro), tutti noti alla decisione
        f.update(extra)
    return f


def _clean(o: Any) -> Any:
    """Sostituisce NaN/inf con None in profondita': una riga non deve mai contenere valori non validi."""
    if isinstance(o, float):
        return None if (math.isnan(o) or math.isinf(o)) else o
    if isinstance(o, dict):
        return {str(k): _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    return o


def log_event(data_dir: str, ev: dict, candidate: bool = False) -> bool:
    """Aggiunge una riga al registro. Non solleva mai. Ritorna True se scritta."""
    try:
        os.makedirs(data_dir, exist_ok=True)
        path = os.path.join(data_dir, LEARN_FILE)
        try:
            size = os.path.getsize(path)
        except OSError:
            size = 0
        if size >= MAX_BYTES_ALL or (candidate and size >= MAX_BYTES_CANDIDATES):
            return False
        row = _clean({"schema": SCHEMA, **STAMP, **ev})
        row.setdefault("logged_ms", int(time.time() * 1000))
        line = json.dumps(row, ensure_ascii=False, default=str, allow_nan=False)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
        return True
    except Exception:
        return False


def read_events(data_dir: str, ev: Optional[str] = None) -> list:
    """Legge il registro (per test e analisi offline). Ignora le righe illeggibili."""
    path = os.path.join(data_dir, LEARN_FILE)
    out: list = []
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                if isinstance(row, dict) and (ev is None or row.get("ev") == ev):
                    out.append(row)
    except OSError:
        pass
    return out
