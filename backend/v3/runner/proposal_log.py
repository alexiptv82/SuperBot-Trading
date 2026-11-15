"""Osservatorio delle proposte del modello (solo PAPER, facoltativo, sola scrittura di un file a parte).

Il journal registra una proposta respinta come ``NO_TRADE / RISK_REJECTED`` senza lato, leva e stop: non si puo' sapere
quanti LONG propone il modello ne' perche' vengono scartati. Questo modulo annota, PRIMA che il motore decida, i soli
campi numerici/enumerati della proposta in ``proposal_observations.jsonl`` nella cartella della run.

Garanzie: nessun testo del modello, nessuna chiave; non tocca journal, rischio, mandato o esecuzione; un errore di
scrittura viene ignorato e non cambia la decisione; spento se non richiesto esplicitamente.
"""
from __future__ import annotations

import json
import os
import re
from decimal import Decimal
from pathlib import Path
from typing import Callable, Mapping, Optional

from backend.v3.brain_f2.contracts import BrainDecision, DecisionKind, MarketContext, OpenProposal

LOG_FILE = "proposal_observations.jsonl"
MAX_BYTES = 20_000_000
_LABEL = re.compile(r"^[A-Za-z0-9_]{1,64}$")
_SYMBOL = re.compile(r"^[A-Z0-9]{2,24}$")
_CODE = re.compile(r"^[a-z0-9_]{1,48}$")
KEYS = frozenset({"ts_ms", "symbol", "regime", "kind", "side", "leverage", "stop_bp", "confidence", "strategy_id",
                  "price", "error"})

Observer = Callable[[Mapping], None]


def proposal_record(context: MarketContext, decision: object = None, error: object = None) -> Optional[dict]:
    """Solo campi sicuri; ``None`` se il contesto non e' utilizzabile. Non solleva mai."""
    try:
        symbol = getattr(context, "symbol", None)
        ts = getattr(context, "timestamp_ms", None)
        if type(symbol) is not str or not _SYMBOL.fullmatch(symbol) or type(ts) is not int or ts <= 0:
            return None
        regime = getattr(context, "regime", None)
        rec: dict = {"ts_ms": ts, "symbol": symbol,
                     "regime": regime if type(regime) is str and _LABEL.fullmatch(regime) else None}
        price = Decimal(str(context.price))
        if price.is_finite() and price > 0:
            rec["price"] = str(price)
        if error is not None:
            code = str(error)
            rec.update(kind="ERROR", error=code if _CODE.fullmatch(code) else "errore")
            return rec
        if not isinstance(decision, BrainDecision):
            return None
        prop = decision.proposal
        if decision.kind == DecisionKind.OPEN and isinstance(prop, OpenProposal):
            entry, stop = Decimal(str(prop.entry_price)), Decimal(str(prop.stop_price))
            rec.update(kind="OPEN", side=prop.side if prop.side in (-1, 1) else None,
                       leverage=prop.leverage if type(prop.leverage) is int and 1 <= prop.leverage <= 200 else None)
            if entry.is_finite() and stop.is_finite() and entry > 0 and stop > 0:
                rec["stop_bp"] = int((abs(entry - stop) / entry * 10_000).to_integral_value())
            conf = prop.confidence
            if type(conf) in (int, float) and 0 <= conf <= 1:
                rec["confidence"] = round(float(conf), 2)
            sid = prop.strategy_id
            if type(sid) is str and _LABEL.fullmatch(sid):
                rec["strategy_id"] = sid
        else:
            rec["kind"] = "NO_TRADE"
        return rec
    except Exception:
        return None


def file_observer(data_dir: Path) -> Observer:
    """Accoda una riga JSON per proposta. Mai un link simbolico, mai oltre MAX_BYTES, mai un'eccezione verso il chiamante."""
    path = Path(data_dir) / LOG_FILE

    def observe(record: Mapping) -> None:
        try:
            if type(record) is not dict or not set(record) <= KEYS:
                return
            line = (json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n").encode("ascii")
            flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
            fd = os.open(path, flags, 0o600)
            try:
                if os.fstat(fd).st_size + len(line) <= MAX_BYTES:
                    os.write(fd, line)
            finally:
                os.close(fd)
        except Exception:
            return
    return observe
