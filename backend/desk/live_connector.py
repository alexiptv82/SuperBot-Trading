"""
live_connector.py — Ponte tra il motore desk e Bitget reale.

Attivo SOLO quando la variabile d'ambiente DESK_MODE=live.
In paper mode questo modulo non fa nulla: ogni funzione ritorna subito senza toccare la rete.

Principio: l'EXCHANGE e' la verita'. Il motore (engine.py) resta il "cervello" che decide e fa i conti
del paper; questo modulo copia sull'exchange quello che il motore fa, e controlla che l'exchange
risponda come previsto. Niente di quello che c'e' qui cambia una decisione o un parametro di strategia.

Scala del capitale: il motore ragiona sempre su un conto di riferimento (1000$). Se il capitale assegnato e'
diverso, ogni ORDINE verso Bitget e' moltiplicato per `scale` = capitale / riferimento (apertura, DCA,
seconda gamba) e il confronto con l'exchange usa la stessa scala. Le chiusure e i parziali lavorano gia'
sulla quantita' REALE letta dall'exchange. Base fissa: i profitti non si reinvestono e un calo non riduce le
puntate. Con scale = 1 il comportamento e' identico a prima.

Regole di sicurezza (tutte verificate dai test con un exchange finto, tests/test_live_connector.py):
- Una lettura fallita NON e' "nessuna posizione": se non riesco a leggere l'exchange non agisco.
- Prima di ogni apertura: margine ISOLATO e leva impostati e riletti; modalita' posizione (one-way /
  hedge) letta dall'account e rispettata (mai cambiata); simbolo presente; quantita' arrotondata alla
  precisione e al minimo del contratto.
- Stop loss e take profit viaggiano nello STESSO ordine di ingresso (preset): non esiste un momento
  in cui la posizione e' aperta senza stop sull'exchange.
- Dopo l'ordine si rilegge la posizione reale: se non e' isolata, o la leva non coincide, la si chiude
  subito e l'apertura risulta fallita.
- Le chiusure usano la quantita' REALE letta dall'exchange e sono sempre "solo riduzione".
- Se sull'exchange c'e' qualcosa che il motore non conosce (posizione estranea, lato opposto, quantita'
  molto diversa) il connettore BLOCCA le nuove aperture (`open_blocked`) e lo segnala; non tocca nulla.
- Ogni ordine e ogni esito (prezzo reale, quantita' reale, commissioni) finisce in live_orders.jsonl.
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

# differenza di quantita' tollerata tra motore ed exchange (arrotondamenti del lotto, slippage)
QTY_TOL_REL   = 0.03
# attese (secondi) tra una lettura dell'esecuzione e la successiva, subito dopo un ordine a mercato
FILL_WAITS    = (0.3, 0.8, 1.5)
# una posizione appena aperta puo' non comparire subito nell'elenco: nessun giudizio prima di questi secondi
OPEN_GRACE_S  = 20.0

# Scala massima ammessa tra capitale assegnato e conto di riferimento del motore (1000$). Oltre questa soglia
# e' quasi certamente un errore di battitura (es. 10000 al posto di 1000): meglio non partire che mandare
# ordini 10 volte piu' grandi di quelli che il motore ha deciso.
MAX_SCALE = 5.0

ONE_WAY = "one_way_mode"
HEDGE   = "hedge_mode"


class LiveError(Exception):
    """Errore di lettura/comunicazione con l'exchange: chi lo riceve NON deve dedurne 'posizione chiusa'."""


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


def _check_scale(scale, live: bool) -> float:
    """Scala validata. In live un valore assente, non numerico, <= 0 o oltre MAX_SCALE impedisce la partenza
    (ValueError): un ordine sbagliato di proporzioni e' peggio di un bot fermo. In paper non conta."""
    try:
        v = float(scale)
    except (TypeError, ValueError):
        v = float("nan")
    ok = v == v and 0.0 < v <= MAX_SCALE and v != float("inf")
    if live and not ok:
        raise ValueError(
            f"[LIVE_CONNECTOR] scala del capitale non valida ({scale!r}): deve essere > 0 e al massimo "
            f"{MAX_SCALE:g} (capitale assegnato / conto di riferimento). Controlla DESK_*_CAPITAL.")
    return v if ok else 1.0


def _new_client_order_id(symbol: str) -> str:
    """ID univoco per ogni ordine — usato da Bitget per idempotenza sui retry."""
    tag = symbol.replace("/", "").replace(":", "")[:10]
    return f"sb-{tag}-{int(time.time() * 1000)}-{uuid.uuid4().hex[:6]}"


def _symbol_ccxt(symbol: str) -> str:
    """Converte 'BTC' o 'BTCUSDT' → 'BTC/USDT:USDT' (formato ccxt per perpetui lineari Bitget)."""
    if "/" in symbol:
        return symbol   # già nel formato giusto
    base = symbol.replace("USDT", "").replace("PERP", "").strip()
    return f"{base}/USDT:USDT"


def _base(symbol: str) -> str:
    """'BTC/USDT:USDT' → 'BTC'; 'BTCUSDT' → 'BTC'; 'BTC' → 'BTC'."""
    s = symbol.split("/")[0].split(":")[0]
    return s[:-4] if s.endswith("USDT") and len(s) > 4 else s


def _f(x, default: float = 0.0) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


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
    In paper mode tutti i metodi pubblici sono no-op.
    """

    def __init__(self, data_dir: str = ".", client=None, live: Optional[bool] = None,
                 sleep=time.sleep, scale: float = 1.0):
        self._live   = IS_LIVE if live is None else bool(live)
        self.scale   = _check_scale(scale, self._live)
        self._client = client
        self._log    = Path(data_dir) / "live_orders.jsonl"
        self._sleep  = sleep
        self.interlock: Optional[str] = None       # motivo per cui le NUOVE aperture sono bloccate
        self.last_fill: dict = {}                  # esito reale dell'ultima operazione (prezzo, quantita', fee)
        self._opened_at: dict = {}                 # simbolo -> secondi (time.time) dell'ultima apertura/aggiunta
        self.stale_protection: dict = {}           # simbolo -> (sl, tp) desiderati che l'exchange non ha ancora
        self.pending_close: dict = {}              # simbolo -> lato: il motore ha chiuso, l'exchange no (da ritentare)

        if self._live:
            if self._client is None:
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
            "timeout":  15000,
            "enableRateLimit": True,
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
                self._sleep(delay)
        raise last_err  # non raggiunto, per sicurezza

    # ── log su file ─────────────────────────────────────────────────────────

    def _write_log(self, record: dict) -> None:
        """Scrive una riga in live_orders.jsonl. Non lancia mai eccezioni."""
        try:
            with open(self._log, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        except Exception as e:
            print(f"[LIVE_CONNECTOR] impossibile scrivere log: {e}", flush=True)

    # ── letture dall'exchange ────────────────────────────────────────────────

    def _market(self, ccxt_sym: str) -> dict:
        """Mercato ccxt del simbolo; LiveError se non esiste su Bitget (non si apre a occhi chiusi)."""
        try:
            self._call(self._client.load_markets)
            m = self._client.market(ccxt_sym)
        except Exception as e:
            raise LiveError(f"simbolo {ccxt_sym} non disponibile su Bitget: {str(e)[:120]}")
        if m.get("swap") is False or m.get("active") is False:
            raise LiveError(f"simbolo {ccxt_sym} non negoziabile (perpetuo non attivo)")
        return m

    def _positions_raw(self) -> list:
        try:
            rows = self._call(self._client.fetch_positions)
        except Exception as e:
            raise LiveError(f"lettura posizioni fallita: {str(e)[:150]}")
        return list(rows or [])

    def snapshot(self) -> dict:
        """Posizioni reali aperte, per simbolo base: {"BTC": {side, qty, entry, mark, liq, leverage,
        margin_mode, pos_mode, multi}}. Solleva LiveError se la lettura fallisce (MAI "vuoto" per errore).
        `multi` = True se sullo stesso simbolo ci sono due gambe (long e short insieme)."""
        out: dict = {}
        for p in self._positions_raw():
            info = p.get("info") or {}
            qty = abs(_f(p.get("contracts"), _f(info.get("total"))))
            if qty <= 0:
                continue
            side_txt = p.get("side") or info.get("holdSide")
            side = 1 if str(side_txt).lower() == "long" else -1
            sym = _base(p.get("symbol") or info.get("symbol") or "")
            mm = str(p.get("marginMode") or info.get("marginMode") or "").lower()
            mm = "isolated" if mm.startswith("isol") else ("cross" if mm.startswith("cross") else mm)
            row = {
                "side": side, "qty": qty,
                "entry": _f(p.get("entryPrice"), _f(info.get("openPriceAvg"))),
                "mark": _f(p.get("markPrice"), _f(info.get("markPrice"))),
                "liq": _f(p.get("liquidationPrice"), _f(info.get("liquidationPrice"))) or None,
                "leverage": int(_f(p.get("leverage"), _f(info.get("leverage"))) or 0) or None,
                "margin_mode": mm, "pos_mode": info.get("posMode"),
                "multi": False, "ccxt_symbol": p.get("symbol"),
            }
            if sym in out:                      # seconda gamba sullo stesso simbolo
                out[sym]["multi"] = True
                continue
            out[sym] = row
        return out

    @staticmethod
    def _pos_mode(cfg: dict) -> str:
        """Modalita' posizione dell'account (one-way / hedge). Mai cambiata da qui: ci si adatta.
        Se Bitget non la riporta si usa DESK_LIVE_POS_MODE (one_way_mode | hedge_mode); altrimenti errore."""
        mode = cfg.get("pos_mode") or os.getenv("DESK_LIVE_POS_MODE", "").strip().lower()
        if mode not in (ONE_WAY, HEDGE):
            raise LiveError(f"modalita' posizione non riconosciuta ({mode!r})")
        return mode

    def _symbol_config(self, ccxt_sym: str) -> dict:
        """Impostazioni dell'account per il simbolo: modalita' posizione, margine, leve isolate."""
        try:
            res = self._call(self._client.fetch_leverage, ccxt_sym)
        except Exception as e:
            raise LiveError(f"lettura impostazioni account fallita: {str(e)[:150]}")
        info = (res or {}).get("info") or {}
        mm = str(info.get("marginMode") or "").lower()
        return {
            "pos_mode": info.get("posMode"),
            "margin_mode": "isolated" if mm.startswith("isol") else ("cross" if mm.startswith("cross") else mm),
            "long_lev": int(_f(info.get("isolatedLongLever")) or 0) or None,
            "short_lev": int(_f(info.get("isolatedShortLever")) or 0) or None,
        }

    # ── blocco di sicurezza ──────────────────────────────────────────────────

    def open_blocked(self) -> Optional[str]:
        """Motivo per cui oggi non si devono aprire nuove posizioni, o None se tutto in ordine."""
        return self.interlock if self._live else None

    def set_interlock(self, reason: Optional[str]) -> None:
        if reason != self.interlock:
            if reason:
                print(f"[LIVE BLOCCO] nuove aperture bloccate: {reason}", flush=True)
                self._write_log({"ts": int(time.time() * 1000), "ev": "interlock_on", "reason": reason})
            elif self.interlock:
                print("[LIVE BLOCCO] rimosso: exchange e motore sono allineati", flush=True)
                self._write_log({"ts": int(time.time() * 1000), "ev": "interlock_off"})
        self.interlock = reason

    # ── ordini: parti comuni ─────────────────────────────────────────────────

    def _fill_info(self, order_id: Optional[str], ccxt_sym: str, client_oid: str) -> dict:
        """Esito reale di un ordine a mercato (prezzo medio, quantita' eseguita, commissioni).
        Meglio un esito parziale/vuoto che un errore: e' solo per la registrazione."""
        for wait in (0.0,) + FILL_WAITS:
            if wait:
                self._sleep(wait)
            try:
                o = self._call(self._client.fetch_order, order_id, ccxt_sym) if order_id else None
            except Exception:
                o = None
            if o and _f(o.get("filled")) > 0:
                fee = o.get("fee") or {}
                return {"order_id": order_id, "avg": _f(o.get("average")) or None,
                        "filled": _f(o.get("filled")), "fee": _f(fee.get("cost")) if fee else None,
                        "status": o.get("status")}
        return {"order_id": order_id, "avg": None, "filled": None, "fee": None, "status": "sconosciuto"}

    def _read_pos(self, base: str) -> Optional[dict]:
        """Posizione reale di un simbolo (None = nessuna). Solleva LiveError se la lettura fallisce."""
        return self.snapshot().get(base)

    def _round_qty(self, ccxt_sym: str, qty: float) -> float:
        """Quantita' alla precisione del contratto (troncata, mai per eccesso)."""
        try:
            # 1e-9 relativo: assorbe il rumore dei decimali (0.1*0.35 = 0.0349999...) senza mai arrotondare in su
            return _f(self._client.amount_to_precision(ccxt_sym, qty * (1 + 1e-9)))
        except Exception as e:
            raise LiveError(f"quantita' {qty:g} sotto il minimo del contratto: {str(e)[:100]}")

    @staticmethod
    def _mm(pos: dict) -> str:
        """Margine da dichiarare in un ordine che agisce su una posizione ESISTENTE: quello che ha davvero
        (se l'exchange l'ha aperta in cross, la si chiude dichiarando cross, altrimenti viene rifiutata)."""
        return "isolated" if pos.get("margin_mode") == "isolated" else "cross"

    def _check_min(self, market: dict, qty: float, price: Optional[float]) -> Optional[str]:
        lim = market.get("limits") or {}
        mn = _f((lim.get("amount") or {}).get("min"))
        if qty <= 0 or (mn and qty < mn):
            return f"quantita' {qty} sotto il minimo del contratto ({mn})"
        mc = _f((lim.get("cost") or {}).get("min"))
        if mc and price and qty * price < mc:
            return f"valore {qty * price:.2f}$ sotto il minimo ({mc}$)"
        return None

    def _send_order(self, ccxt_sym: str, side: str, qty: float, params: dict, base: str,
                    before_qty: float, expect_more: bool):
        """Invia l'ordine a mercato. Se la risposta e' un errore ma l'ordine puo' essere passato lo stesso
        (timeout dopo l'invio), lo si scopre rileggendo la posizione. Ritorna (order|None, errore|None)."""
        try:
            return self._call(self._client.create_order, ccxt_sym, "market", side, qty, None, params), None
        except Exception as e:
            err = str(e)[:200]
        try:    # l'ordine potrebbe essere passato lo stesso: lo si deduce dalla quantita' reale
            now = self._read_pos(base)
            now_qty = now["qty"] if now else 0.0
            changed = now_qty > before_qty * (1 + 1e-9) if expect_more else now_qty < before_qty * (1 - 1e-9)
            if changed:
                return {"id": None, "info": {"recovered_after_error": err}}, None
        except LiveError:
            return None, err + " (e la posizione non si e' potuta rileggere: controlla su Bitget)"
        return None, err

    # ── API pubblica ─────────────────────────────────────────────────────────

    def qty_from_margin(self, symbol: str, margin_usd: float, leverage: int, price: float) -> float:
        """Contratti da passare a Bitget dato un margine in USDT: (margine * leva) / prezzo, troncato
        alla precisione del contratto (arrotondare per eccesso aumenterebbe il rischio)."""
        if price <= 0:
            return 0.0
        qty = (margin_usd * leverage) / price
        if not self._live or self._client is None:
            return round(qty, 3)
        try:
            return self._round_qty(_symbol_ccxt(symbol), qty)
        except Exception:
            return round(qty, 3)

    def open(
        self,
        symbol: str,
        side: int,           # +1 = long, -1 = short
        qty: float,          # numero di contratti (non USDT)
        leverage: int,
        sl: Optional[float] = None,
        tp: Optional[float] = None,
        ref_price: Optional[float] = None,
    ) -> tuple[bool, str]:
        """
        Apre una posizione su Bitget (con stop e take profit nello stesso ordine).
        Ritorna (True, order_id) se ok, (False, messaggio_errore) se fallisce.
        Dopo un True, `self.last_fill` contiene prezzo/quantita'/commissioni reali.
        In paper mode ritorna (True, "paper") senza fare nulla.
        """
        if not self._live:
            return True, "paper"

        ccxt_sym   = _symbol_ccxt(symbol)
        base       = _base(symbol)
        ccxt_side  = "buy" if side == 1 else "sell"
        client_oid = _new_client_order_id(symbol)
        self.last_fill = {}
        engine_qty = qty
        qty = qty * self.scale          # quantita' del motore -> quantita' reale in scala

        record = {
            "ts": int(time.time() * 1000), "ev": "open_attempt",
            "symbol": symbol, "ccxt_sym": ccxt_sym,
            "side": ccxt_side, "qty": qty, "engine_qty": engine_qty, "scale": self.scale, "leverage": leverage,
            "sl": sl, "tp": tp, "client_oid": client_oid,
        }
        self._write_log(record)

        def fail(msg: str) -> tuple[bool, str]:
            self._write_log({**record, "ev": "open_error", "error": msg})
            print(f"[LIVE] OPEN FALLITA {symbol}: {msg}", flush=True)
            return False, msg

        try:
            if self.interlock:
                return fail(f"aperture bloccate: {self.interlock}")
            if not sl or sl <= 0:
                return fail("stop loss obbligatorio sull'exchange")
            market = self._market(ccxt_sym)
            qty = self._round_qty(ccxt_sym, qty)
            problem = self._check_min(market, qty, ref_price)
            if problem:
                return fail(problem)

            # 1. l'exchange deve essere piatto su questo simbolo (nessuna posizione estranea da "aggiungere")
            if self._read_pos(base) is not None:
                return fail("su Bitget esiste gia' una posizione su questo simbolo")

            # 2. margine ISOLATO e leva: si imposta, si RILEGGE, e solo allora si apre
            cfg = self._symbol_config(ccxt_sym)
            oneway = self._pos_mode(cfg) == ONE_WAY
            if cfg["margin_mode"] != "isolated":
                self._call(self._client.set_margin_mode, "isolated", ccxt_sym)
            lev_params = {} if oneway else {"holdSide": "long" if side == 1 else "short"}
            self._call(self._client.set_leverage, leverage, ccxt_sym, lev_params)
            cfg = self._symbol_config(ccxt_sym)
            if cfg["margin_mode"] != "isolated":
                return fail("impossibile impostare il margine ISOLATO su questo simbolo")
            got = cfg["long_lev"] if side == 1 else cfg["short_lev"]
            if got != leverage:
                return fail(f"leva su Bitget {got}x diversa da quella voluta {leverage}x")

            # 3. ordine a mercato con stop/take profit preset (un solo ordine, nessuna finestra senza stop)
            params: dict = {"marginMode": "isolated", "clientOrderId": client_oid,
                            "stopLoss": {"triggerPrice": sl}}
            if tp:
                params["takeProfit"] = {"triggerPrice": tp}
            if oneway:
                params["oneWayMode"] = True
            order, err = self._send_order(ccxt_sym, ccxt_side, qty, params, base,
                                          before_qty=0.0, expect_more=True)
            if order is None:
                return fail(err or "ordine rifiutato")
            order_id = str(order.get("id") or client_oid)

            # 4. verifica sulla posizione REALE
            pos = None
            for wait in (0.0,) + FILL_WAITS:
                if wait:
                    self._sleep(wait)
                pos = self._read_pos(base)
                if pos:
                    break
            if pos is None:
                self.set_interlock("ordine inviato ma la posizione non risulta su Bitget: controlla")
                return fail("ordine inviato ma nessuna posizione trovata dopo l'esecuzione")
            self._opened_at[base] = time.time()
            if pos["side"] != side or pos["multi"] or pos["margin_mode"] != "isolated" \
                    or (pos["leverage"] and pos["leverage"] != leverage):
                ok_close, det = self._close_all_of(base, ccxt_sym, pos, oneway, "verifica_apertura")
                self.set_interlock("apertura non conforme (lato/margine/leva): posizione chiusa, controlla")
                return fail(f"posizione aperta NON conforme (lato={pos['side']}, margine={pos['margin_mode']}, "
                            f"leva={pos['leverage']}): chiusa subito ({det})")

            fill = self._fill_info(order.get("id"), ccxt_sym, client_oid)
            fill.update(real_qty=pos["qty"], real_entry=pos["entry"], requested_qty=qty,
                        engine_qty=engine_qty, scale=self.scale,
                        leverage=pos["leverage"], margin_mode=pos["margin_mode"])
            self.last_fill = fill
            self._write_log({**record, "ev": "open_ok", "order_id": order_id, "fill": fill})
            print(f"[LIVE] OPEN {symbol} {'LONG' if side==1 else 'SHORT'}  qty={pos['qty']}  "
                  f"lev={leverage}x  entry={pos['entry']}  order_id={order_id}", flush=True)
            return True, order_id

        except LiveError as e:
            return fail(str(e)[:200])
        except Exception as e:
            return fail(f"{type(e).__name__}: {str(e)[:180]}")

    def add(self, symbol: str, side: int, qty: float, leverage: int,
            sl: Optional[float] = None, tp: Optional[float] = None,
            ref_price: Optional[float] = None) -> tuple[bool, str]:
        """Aggiunge contratti a una posizione esistente (DCA, seconda gamba dell'entrata diversificata).
        Fallisce se la posizione non c'e' (non si "riapre" mai per sbaglio) o e' sul lato opposto."""
        if not self._live:
            return True, "paper"
        ccxt_sym, base = _symbol_ccxt(symbol), _base(symbol)
        ccxt_side = "buy" if side == 1 else "sell"
        client_oid = _new_client_order_id(symbol)
        self.last_fill = {}
        engine_qty = qty
        qty = qty * self.scale          # quantita' del motore -> quantita' reale in scala
        record = {"ts": int(time.time() * 1000), "ev": "add_attempt", "symbol": symbol, "qty": qty,
                  "engine_qty": engine_qty, "scale": self.scale, "side": ccxt_side, "client_oid": client_oid}
        self._write_log(record)

        def fail(msg: str) -> tuple[bool, str]:
            self._write_log({**record, "ev": "add_error", "error": msg})
            print(f"[LIVE] ADD FALLITA {symbol}: {msg}", flush=True)
            return False, msg

        try:
            if self.interlock:
                return fail(f"aggiunte bloccate: {self.interlock}")
            market = self._market(ccxt_sym)
            qty = self._round_qty(ccxt_sym, qty)
            problem = self._check_min(market, qty, ref_price)
            if problem:
                return fail(problem)
            before = self._read_pos(base)
            if before is None:
                return fail("su Bitget non c'e' la posizione da incrementare")
            if before["side"] != side or before["multi"] or before["margin_mode"] != "isolated":
                return fail("la posizione su Bitget non corrisponde (lato/margine)")
            cfg = self._symbol_config(ccxt_sym)
            oneway = self._pos_mode(cfg) == ONE_WAY
            params: dict = {"marginMode": "isolated", "clientOrderId": client_oid}
            if sl:      # i contratti aggiunti hanno il loro stop nello stesso ordine (come all'apertura)
                params["stopLoss"] = {"triggerPrice": sl}
            if tp:
                params["takeProfit"] = {"triggerPrice": tp}
            if oneway:
                params["oneWayMode"] = True
            order, err = self._send_order(ccxt_sym, ccxt_side, qty, params, base,
                                          before_qty=before["qty"], expect_more=True)
            if order is None:
                return fail(err or "ordine rifiutato")
            after = None
            for wait in (0.0,) + FILL_WAITS:
                if wait:
                    self._sleep(wait)
                after = self._read_pos(base)
                if after and after["qty"] > before["qty"] * (1 + 1e-9):
                    break
            self._opened_at[base] = time.time()
            fill = self._fill_info(order.get("id"), ccxt_sym, client_oid)
            fill.update(engine_qty=engine_qty, scale=self.scale,
                        real_qty=after["qty"] if after else None, real_entry=after["entry"] if after else None,
                        added_qty=round(after["qty"] - before["qty"], 10) if after else None)
            self.last_fill = fill
            order_id = str(order.get("id") or client_oid)
            self._write_log({**record, "ev": "add_ok", "order_id": order_id, "fill": fill})
            print(f"[LIVE] ADD {symbol} +{qty}  order_id={order_id}", flush=True)
            if sl:
                self.set_protection(symbol, side, sl, tp)
            return True, order_id
        except LiveError as e:
            return fail(str(e)[:200])
        except Exception as e:
            return fail(f"{type(e).__name__}: {str(e)[:180]}")

    def reduce(self, symbol: str, side: int, fraction: float) -> tuple[bool, str]:
        """Chiude una frazione della posizione reale (TP parziale). Solo riduzione."""
        if not self._live:
            return True, "paper"
        ccxt_sym, base = _symbol_ccxt(symbol), _base(symbol)
        client_oid = _new_client_order_id(symbol)
        self.last_fill = {}
        record = {"ts": int(time.time() * 1000), "ev": "reduce_attempt", "symbol": symbol,
                  "fraction": fraction, "client_oid": client_oid}
        self._write_log(record)

        def fail(msg: str) -> tuple[bool, str]:
            self._write_log({**record, "ev": "reduce_error", "error": msg})
            print(f"[LIVE] REDUCE FALLITA {symbol}: {msg}", flush=True)
            return False, msg

        try:
            self._market(ccxt_sym)
            before = self._read_pos(base)
            if before is None:
                return fail("su Bitget non c'e' la posizione da ridurre")
            if before["side"] != side or before["multi"]:
                return fail("la posizione su Bitget non corrisponde (lato)")
            qty = self._round_qty(ccxt_sym, before["qty"] * fraction)
            if qty <= 0 or qty >= before["qty"]:
                return fail(f"quantita' da chiudere non valida ({qty} su {before['qty']})")
            cfg = self._symbol_config(ccxt_sym)
            oneway = self._pos_mode(cfg) == ONE_WAY
            params: dict = {"marginMode": self._mm(before), "clientOrderId": client_oid, "reduceOnly": True}
            if oneway:
                params["oneWayMode"] = True
            close_side = "sell" if side == 1 else "buy"
            order, err = self._send_order(ccxt_sym, close_side, qty, params, base,
                                          before_qty=before["qty"], expect_more=False)
            if order is None:
                return fail(err or "ordine rifiutato")
            fill = self._fill_info(order.get("id"), ccxt_sym, client_oid)
            fill.update(closed_qty=qty, qty_before=before["qty"])
            self.last_fill = fill
            order_id = str(order.get("id") or client_oid)
            self._write_log({**record, "ev": "reduce_ok", "order_id": order_id, "fill": fill})
            print(f"[LIVE] REDUCE {symbol} -{qty} ({fraction:.0%})  order_id={order_id}", flush=True)
            return True, order_id
        except LiveError as e:
            return fail(str(e)[:200])
        except Exception as e:
            return fail(f"{type(e).__name__}: {str(e)[:180]}")

    def _close_all_of(self, base: str, ccxt_sym: str, pos: dict, oneway: bool, why: str) -> tuple[bool, str]:
        """Chiude TUTTA la posizione letta (quantita' reale), solo riduzione. Non solleva."""
        client_oid = _new_client_order_id(base)
        try:
            qty = self._round_qty(ccxt_sym, pos["qty"])
            params: dict = {"marginMode": self._mm(pos), "clientOrderId": client_oid, "reduceOnly": True}
            if oneway:
                params["oneWayMode"] = True
            close_side = "sell" if pos["side"] == 1 else "buy"
            order = self._call(self._client.create_order, ccxt_sym, "market", close_side, qty, None, params)
            self._write_log({"ts": int(time.time() * 1000), "ev": "close_all_ok", "symbol": base,
                             "why": why, "qty": qty, "order_id": order.get("id")})
            return True, str(order.get("id") or client_oid)
        except Exception as e:
            err = str(e)[:160]
            self._write_log({"ts": int(time.time() * 1000), "ev": "close_all_error", "symbol": base,
                             "why": why, "error": err})
            return False, err

    def close(self, symbol: str, side: int, qty: Optional[float] = None) -> tuple[bool, str]:
        """
        Chiude la posizione su Bitget (solo riduzione). La quantita' e' sempre quella REALE dell'exchange
        (il parametro `qty` resta per compatibilita' e non viene usato). Se l'exchange e' gia' piatto
        sul simbolo ritorna (True, "gia_chiusa"): niente da fare, il motore puo' chiudere.
        Ritorna (False, errore) se non si riesce a leggere o a chiudere.
        In paper mode ritorna (True, "paper").
        """
        if not self._live:
            return True, "paper"
        ccxt_sym, base = _symbol_ccxt(symbol), _base(symbol)
        self.last_fill = {}
        record = {"ts": int(time.time() * 1000), "ev": "close_attempt", "symbol": symbol,
                  "ccxt_sym": ccxt_sym, "side": side}
        self._write_log(record)

        def fail(msg: str) -> tuple[bool, str]:
            self._write_log({**record, "ev": "close_error", "error": msg})
            print(f"[LIVE] CLOSE FALLITA {symbol}: {msg}", flush=True)
            return False, msg

        try:
            self._market(ccxt_sym)
            pos = self._read_pos(base)
            if pos is None:
                self._write_log({**record, "ev": "close_ok", "order_id": "gia_chiusa"})
                self.pending_close.pop(base, None)
                return True, "gia_chiusa"
            if pos["side"] != side or pos["multi"]:
                return fail("la posizione su Bitget non corrisponde (lato): non la tocco")
            cfg = self._symbol_config(ccxt_sym)
            oneway = self._pos_mode(cfg) == ONE_WAY
            client_oid = _new_client_order_id(symbol)
            params: dict = {"marginMode": self._mm(pos), "clientOrderId": client_oid, "reduceOnly": True}
            if oneway:
                params["oneWayMode"] = True
            close_side = "sell" if side == 1 else "buy"
            q = self._round_qty(ccxt_sym, pos["qty"])
            order, err = self._send_order(ccxt_sym, close_side, q, params, base,
                                          before_qty=pos["qty"], expect_more=False)
            if order is None:
                return fail(err or "ordine rifiutato")
            fill = self._fill_info(order.get("id"), ccxt_sym, client_oid)
            fill.update(closed_qty=q, qty_before=pos["qty"])
            left = None
            try:
                left = self._read_pos(base)
            except LiveError:
                pass
            if left is not None and left["qty"] > 0:
                fill["qty_left"] = left["qty"]
                self.last_fill = fill
                return fail(f"dopo la chiusura restano {left['qty']} contratti (riprovo al prossimo controllo)")
            self.last_fill = fill
            self.pending_close.pop(base, None)
            order_id = str(order.get("id") or client_oid)
            self._write_log({**record, "ev": "close_ok", "order_id": order_id, "fill": fill})
            print(f"[LIVE] CLOSE {symbol}  qty={q}  order_id={order_id}", flush=True)
            return True, order_id
        except LiveError as e:
            return fail(str(e)[:200])
        except Exception as e:
            return fail(f"{type(e).__name__}: {str(e)[:180]}")

    def set_protection(self, symbol: str, side: int, sl: Optional[float], tp: Optional[float]) -> tuple[bool, str]:
        """Porta stop loss e take profit sull'exchange ai valori del motore (dopo un DCA o un TP parziale).
        Prima si piazzano i NUOVI livelli, poi si annullano i vecchi: la posizione non resta mai senza
        protezione. Se qualcosa non va si ricorda il valore voluto (`stale_protection`) e il controllo
        successivo riprova; nel frattempo resta valida la protezione che c'era e il motore continua a
        controllare gli stop da solo. Non solleva mai."""
        if not self._live:
            return True, "paper"
        ccxt_sym, base = _symbol_ccxt(symbol), _base(symbol)
        try:
            self._market(ccxt_sym)
            pos = self._read_pos(base)
            if pos is None or pos["side"] != side:
                raise LiveError("posizione non trovata (o lato diverso) su Bitget")
            cfg = self._symbol_config(ccxt_sym)
            oneway = self._pos_mode(cfg) == ONE_WAY
            # holdSide: hedge = 'long'/'short'; one-way = 'buy'/'sell' (vedi doc ccxt create_order)
            hold = ("buy" if side == 1 else "sell") if oneway else ("long" if side == 1 else "short")
            qty = self._round_qty(ccxt_sym, pos["qty"])
            old = []
            try:
                old = self._call(self._client.fetch_open_orders, ccxt_sym, None, None,
                                 {"stop": True, "planType": "profit_loss"}) or []
            except Exception:
                old = []        # senza elenco non posso annullare i vecchi: piazzo i nuovi e basta
            new_ids = []
            wanted = []
            if sl:
                wanted.append(("stopLossPrice", sl))
            if tp:
                wanted.append(("takeProfitPrice", tp))
            for key, price in wanted:
                o = self._call(self._client.create_order, ccxt_sym, "market",
                               "buy" if side == 1 else "sell", qty, None,
                               {key: price, "holdSide": hold,
                                "clientOrderId": _new_client_order_id(symbol)})
                new_ids.append(str(o.get("id")))
            for o in old:
                oid = str(o.get("id"))
                info = o.get("info") or {}
                if oid in new_ids:
                    continue
                if str(info.get("holdSide") or hold).lower() not in (hold, "long" if side == 1 else "short"):
                    continue            # e' dell'altra gamba: non si tocca
                try:
                    self._call(self._client.cancel_order, oid, ccxt_sym,
                               {"stop": True, "planType": info.get("planType") or "profit_loss"})
                except Exception as e:
                    print(f"[LIVE] annullo vecchio stop {oid} fallito: {str(e)[:100]}", flush=True)
            self.stale_protection.pop(base, None)
            self._write_log({"ts": int(time.time() * 1000), "ev": "protection_ok", "symbol": symbol,
                             "sl": sl, "tp": tp, "new_ids": new_ids})
            return True, ",".join(new_ids)
        except Exception as e:
            err = str(e)[:160]
            self.stale_protection[base] = (sl, tp)
            self._write_log({"ts": int(time.time() * 1000), "ev": "protection_error", "symbol": symbol,
                             "sl": sl, "tp": tp, "error": err})
            print(f"[LIVE] aggiornamento stop/TP fallito {symbol}: {err}", flush=True)
            return False, err

    def fetch_positions(self) -> list[dict]:
        """Posizioni reali (formato ccxt, solo con quantita' > 0). Solleva LiveError se la lettura
        fallisce: un errore NON deve sembrare 'nessuna posizione'. In paper mode: lista vuota."""
        if not self._live:
            return []
        return [p for p in self._positions_raw()
                if abs(_f(p.get("contracts") or (p.get("info") or {}).get("total"))) > 0]

    # ── riconciliazione ──────────────────────────────────────────────────────

    def compare(self, engine_positions: dict, snap: dict, now: Optional[float] = None) -> dict:
        """Confronta motore ed exchange. Non agisce: descrive. Ritorna
        {"flat": [simboli aperti nel motore ma piatti su Bitget],
         "foreign": [simboli su Bitget che il motore non ha],
         "mismatch": [(simbolo, descrizione)]}."""
        now = time.time() if now is None else now
        flat, foreign, mismatch = [], [], []
        for sym, pos in engine_positions.items():
            base = _base(sym)
            x = snap.get(base)
            if x is None:
                if now - self._opened_at.get(base, 0.0) >= OPEN_GRACE_S:
                    flat.append(sym)
                continue
            if x["multi"]:
                mismatch.append((sym, "su Bitget ci sono due gambe (long e short)"))
            elif x["side"] != pos.side:
                mismatch.append((sym, "lato opposto tra motore ed exchange"))
            elif x["margin_mode"] != "isolated":
                mismatch.append((sym, f"margine {x['margin_mode']} invece di isolato"))
            else:
                expected = pos.qty * self.scale          # la quantita' del motore, in scala reale
                diff = abs(x["qty"] - expected)
                try:
                    lot = _f((((self._client.market(_symbol_ccxt(sym)) or {}).get("limits") or {})
                              .get("amount") or {}).get("min")) if self._client else 0.0
                except Exception:
                    lot = 0.0
                tol = max(QTY_TOL_REL * expected, 2 * lot)
                if diff > tol:
                    mismatch.append((sym, f"quantita' diversa: motore {expected:.6g}, Bitget {x['qty']:.6g}"))
        mine = {_base(s) for s in engine_positions}
        for base in snap:
            if base not in mine and base not in self.pending_close:
                foreign.append(base)
        return {"flat": flat, "foreign": foreign, "mismatch": mismatch}

    def reconcile(self, engine_positions: dict) -> list[str]:
        """Compatibilita' con l'avvio del bot: confronta e ritorna avvisi leggibili (solo descrive).
        In paper mode lista vuota. Se la lettura fallisce lo dice (non fa finta che vada tutto bene)."""
        if not self._live:
            return []
        try:
            snap = self.snapshot()
        except LiveError as e:
            return [f"[RICONCILIAZIONE] impossibile leggere Bitget: {e}"]
        cmp_ = self.compare(engine_positions, snap)
        out = []
        for s in cmp_["flat"]:
            out.append(f"[RICONCILIAZIONE] {s} è in memoria locale ma NON trovata su Bitget — "
                       "potrebbe essere già chiusa sull'exchange")
        for s in cmp_["foreign"]:
            out.append(f"[RICONCILIAZIONE] {s} è aperta su Bitget ma NON in memoria locale — "
                       "posizione estranea (manuale o di un altro bot)")
        for s, d in cmp_["mismatch"]:
            out.append(f"[RICONCILIAZIONE] {s}: {d}")
        return out
