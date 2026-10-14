"""
live_connector.py — Ponte tra il motore desk e Bitget reale.

Attivo SOLO quando la variabile d'ambiente DESK_MODE=live.
In paper mode questo modulo non fa nulla: tutte le funzioni ritornano
immediatamente senza toccare la rete.

Uso in cli.py:
    from desk.live_connector import LiveConnector
    lc = LiveConnector()          # legge DESK_MODE dall'ambiente
    ...
    ok, order_id = lc.open(symbol, side, qty, leverage, sl, tp)
    ok, order_id = lc.close(symbol, side, qty)
    positions    = lc.fetch_positions()
    lc.log_order(ev, symbol, order_id, ok, detail)

Sicurezza:
- Se DESK_MODE=live ma le chiavi mancano → eccezione all'avvio (bot non parte)
- Ogni ordine viene scritto in live_orders.jsonl PRIMA di essere inviato
- Se Bitget rifiuta → ok=False, il chiamante NON deve aprire la posizione in engine
- reduce_only=True su ogni chiusura (protezione anti-doppia-apertura)
- clientOrderId univoco per idempotenza sui retry
"""
from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from typing import Optional

# ── costanti ────────────────────────────────────────────────────────────────
DESK_MODE    = os.getenv("DESK_MODE", "paper").strip().lower()
IS_LIVE      = DESK_MODE == "live"

API_KEY      = os.getenv("BITGET_API_KEY", "")
SECRET_KEY   = os.getenv("BITGET_SECRET_KEY", "")
PASSPHRASE   = os.getenv("BITGET_PASSPHRASE", "")

# max retry su errori di rete transitori (rate-limit, timeout)
MAX_RETRIES       = 3
RETRY_BASE_DELAY  = 1.0   # secondi, raddoppia ad ogni tentativo


def _check_credentials() -> None:
    """Lancia ValueError se siamo in live ma mancano le chiavi."""
    missing = [k for k, v in [
        ("BITGET_API_KEY",    API_KEY),
        ("BITGET_SECRET_KEY", SECRET_KEY),
        ("BITGET_PASSPHRASE", PASSPHRASE),
    ] if not v]
    if missing:
        raise ValueError(
            f"[LIVE_CONNECTOR] DESK_MODE=live ma mancano le variabili: {', '.join(missing)}. "
            "Il bot non può partire in modalità live senza chiavi API valide."
        )


def _new_client_order_id(symbol: str) -> str:
    """ID univoco per ogni ordine — usato da Bitget per idempotenza sui retry."""
    tag = symbol.replace("/", "").replace(":", "")[:10]
    return f"sb-{tag}-{int(time.time() * 1000)}-{uuid.uuid4().hex[:6]}"


def _symbol_ccxt(symbol: str) -> str:
    """Converte 'BTCUSDT' → 'BTC/USDT:USDT' (formato ccxt per perpetui lineari Bitget)."""
    if "/" in symbol:
        return symbol   # già nel formato giusto
    # BTCUSDT → BTC/USDT:USDT
    base = symbol.replace("USDT", "").replace("PERP", "").strip()
    return f"{base}/USDT:USDT"


def _retryable(exc) -> bool:
    """Ritorna True se l'eccezione è transitoria e vale la pena riprovare."""
    try:
        import ccxt
        return isinstance(exc, (
            ccxt.NetworkError,
            ccxt.RequestTimeout,
            ccxt.ExchangeNotAvailable,
            ccxt.DDoSProtection,
        ))
    except ImportError:
        return False


class LiveConnector:
    """
    Connettore live per Bitget. Istanziare una volta sola in cli.py.
    In paper mode tutti i metodi pubblici sono no-op e ritornano (True, "paper").
    """

    def __init__(self, data_dir: str = "."):
        self._live   = IS_LIVE
        self._client = None
        self._log    = Path(data_dir) / "live_orders.jsonl"

        if self._live:
            _check_credentials()
            self._client = self._build_client()
            print("[LIVE_CONNECTOR] modalità LIVE attiva — ordini reali su Bitget", flush=True)
        else:
            print("[LIVE_CONNECTOR] modalità PAPER — nessun ordine reale", flush=True)

    # ── costruzione client ccxt ──────────────────────────────────────────────

    def _build_client(self):
        try:
            import ccxt
        except ImportError:
            raise ImportError(
                "[LIVE_CONNECTOR] ccxt non installato. "
                "Esegui: pip install ccxt --break-system-packages"
            )
        return ccxt.bitget({
            "apiKey":   API_KEY,
            "secret":   SECRET_KEY,
            "password": PASSPHRASE,
            "options":  {"defaultType": "swap"},
        })

    # ── chiamata ccxt con retry ──────────────────────────────────────────────

    def _call(self, fn, *args, **kwargs):
        """Esegue fn(*args, **kwargs) con backoff esponenziale sugli errori transitori."""
        last_err = None
        for attempt in range(MAX_RETRIES + 1):
            try:
                return fn(*args, **kwargs)
            except Exception as e:
                if not _retryable(e) or attempt >= MAX_RETRIES:
                    raise
                last_err = e
                delay = RETRY_BASE_DELAY * (2 ** attempt)
                print(f"[LIVE_CONNECTOR] retry {attempt+1}/{MAX_RETRIES} dopo {delay:.1f}s: {e}", flush=True)
                time.sleep(delay)
        raise last_err  # non raggiunto, per sicurezza

    # ── log su file ─────────────────────────────────────────────────────────

    def _write_log(self, record: dict) -> None:
        """Scrive una riga in live_orders.jsonl. Non lancia mai eccezioni."""
        try:
            with open(self._log, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except Exception as e:
            print(f"[LIVE_CONNECTOR] impossibile scrivere log: {e}", flush=True)

    # ── API pubblica ─────────────────────────────────────────────────────────

    def open(
        self,
        symbol: str,
        side: int,           # +1 = long, -1 = short
        qty: float,          # numero di contratti (non USDT)
        leverage: int,
        sl: Optional[float] = None,
        tp: Optional[float] = None,
    ) -> tuple[bool, str]:
        """
        Apre una posizione su Bitget.
        Ritorna (True, order_id) se ok, (False, messaggio_errore) se fallisce.
        In paper mode ritorna (True, "paper") senza fare nulla.
        """
        if not self._live:
            return True, "paper"

        ccxt_sym   = _symbol_ccxt(symbol)
        ccxt_side  = "buy" if side == 1 else "sell"
        client_oid = _new_client_order_id(symbol)

        record = {
            "ts": int(time.time() * 1000), "ev": "open_attempt",
            "symbol": symbol, "ccxt_sym": ccxt_sym,
            "side": ccxt_side, "qty": qty, "leverage": leverage,
            "sl": sl, "tp": tp, "client_oid": client_oid,
        }
        self._write_log(record)

        try:
            # 1. Imposta la leva
            self._call(self._client.set_leverage, leverage, ccxt_sym,
                       params={"marginMode": "isolated"})

            # 2. Apre l'ordine di mercato con SL/TP opzionali
            params: dict = {"clientOrderId": client_oid}
            if sl is not None:
                params["stopLossPrice"] = sl
            if tp is not None:
                params["takeProfitPrice"] = tp

            order = self._call(
                self._client.create_order,
                ccxt_sym, "market", ccxt_side, qty, None, params
            )
            order_id = str(order.get("id", client_oid))
            self._write_log({**record, "ev": "open_ok", "order_id": order_id})
            print(f"[LIVE] OPEN {symbol} {'LONG' if side==1 else 'SHORT'}  qty={qty}  "
                  f"lev={leverage}x  order_id={order_id}", flush=True)
            return True, order_id

        except Exception as e:
            err = str(e)[:200]
            self._write_log({**record, "ev": "open_error", "error": err})
            print(f"[LIVE] OPEN FALLITA {symbol}: {err}", flush=True)
            return False, err

    def close(
        self,
        symbol: str,
        side: int,    # lato della posizione aperta (+1=long, -1=short)
        qty: float,   # numero di contratti da chiudere
    ) -> tuple[bool, str]:
        """
        Chiude una posizione su Bitget con reduce_only=True.
        Ritorna (True, order_id) se ok, (False, messaggio_errore) se fallisce.
        In paper mode ritorna (True, "paper") senza fare nulla.
        """
        if not self._live:
            return True, "paper"

        ccxt_sym   = _symbol_ccxt(symbol)
        close_side = "sell" if side == 1 else "buy"   # opposto all'apertura
        client_oid = _new_client_order_id(symbol)

        record = {
            "ts": int(time.time() * 1000), "ev": "close_attempt",
            "symbol": symbol, "ccxt_sym": ccxt_sym,
            "close_side": close_side, "qty": qty, "client_oid": client_oid,
        }
        self._write_log(record)

        try:
            params = {"clientOrderId": client_oid, "reduceOnly": True}
            order = self._call(
                self._client.create_order,
                ccxt_sym, "market", close_side, qty, None, params
            )
            order_id = str(order.get("id", client_oid))
            self._write_log({**record, "ev": "close_ok", "order_id": order_id})
            print(f"[LIVE] CLOSE {symbol}  qty={qty}  order_id={order_id}", flush=True)
            return True, order_id

        except Exception as e:
            err = str(e)[:200]
            self._write_log({**record, "ev": "close_error", "error": err})
            print(f"[LIVE] CLOSE FALLITA {symbol}: {err}", flush=True)
            return False, err

    def fetch_positions(self) -> list[dict]:
        """
        Legge le posizioni reali aperte su Bitget.
        Usato per riconciliazione al riavvio del bot.
        In paper mode ritorna lista vuota.
        """
        if not self._live:
            return []
        try:
            positions = self._call(self._client.fetch_positions)
            # filtra solo posizioni con size > 0
            return [
                p for p in positions
                if abs(float(p.get("contracts") or p.get("contractSize") or 0)) > 0
            ]
        except Exception as e:
            print(f"[LIVE_CONNECTOR] fetch_positions errore: {e}", flush=True)
            return []

    def qty_from_margin(self, symbol: str, margin_usd: float, leverage: int, price: float) -> float:
        """
        Calcola il numero di contratti da passare a Bitget dato un margine in USDT.
        qty = (margin * leverage) / price
        Arrotonda a 3 decimali (la maggior parte dei perp Bitget accetta 0.001).
        """
        if price <= 0:
            return 0.0
        notional = margin_usd * leverage
        qty = notional / price
        return round(qty, 3)

    def reconcile(self, engine_positions: dict) -> list[str]:
        """
        Confronta le posizioni in memoria del motore con quelle reali su Bitget.
        Ritorna una lista di avvertimenti da stampare al riavvio.
        In paper mode ritorna lista vuota.
        """
        if not self._live:
            return []

        warnings = []
        real = self.fetch_positions()
        real_syms = {p.get("symbol", "").replace("/", "").replace(":", "") for p in real}

        for sym in engine_positions:
            sym_clean = sym.replace("/", "").replace(":", "")
            if sym_clean not in real_syms:
                warnings.append(
                    f"[RICONCILIAZIONE] {sym} è in memoria locale ma NON trovata su Bitget — "
                    "potrebbe essere già chiusa sull'exchange"
                )

        for sym_clean in real_syms:
            found = any(
                p.replace("/", "").replace(":", "") == sym_clean
                for p in engine_positions
            )
            if not found:
                warnings.append(
                    f"[RICONCILIAZIONE] {sym_clean} è aperta su Bitget ma NON in memoria locale — "
                    "potrebbe essere stata aperta manualmente o da un altro processo"
                )

        return warnings
