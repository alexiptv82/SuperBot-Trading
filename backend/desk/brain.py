"""Cervello V2: decisioni Claude con DCA, scalp vs medio, errori ricorrenti, funding/OI.

Regole d'oro:
- Claude PROPONE, il codice DECIDE: ogni valore viene validato dai tetti del conto.
- La chiave arriva solo da variabile d'ambiente, mai stampata.
- Budget: tetto giornaliero configurabile (default 0.70$/giorno per V2).
"""
from __future__ import annotations

import json
import os
import time
import urllib.request

MODEL = os.getenv("DESK_MODEL", "claude-sonnet-5-5")
PRICE_IN, PRICE_OUT = 3.0 / 1e6, 15.0 / 1e6   # claude-sonnet-5-5 prezzi aggiornati
DAILY_CAP = float(os.getenv("DESK_DAILY_CAP_USD", "0.70"))
CALL_RESERVE = 0.04
API_URL = "https://api.anthropic.com/v1/messages"

SYSTEM = """Sei il cervello di un trader professionista di futures crypto — PAPER TRADING con $1000 finti.

MISSIONE: operare come un trader scalper aggressivo H24 su fino a 10 posizioni contemporanee.
Usa grafici, volumi, momentum, notizie, funding rate, long/short ratio e pattern per trovare opportunita' precise.

STRATEGIA PRINCIPALE — SCALP AGGRESSIVO:
- SCALP (trade_type=scalp): PRIORITA'. Nuovo ingresso: margine 100-250$, leva >=20x solo se il rischio e il tier lo consentono.
  TP stretto 0.3-1%, SL stretto 0.2-0.6%, durata minuti-poche ore.
  Preferisci segnali netti: breakout confermato, momentum forte, volume sopra media.
- MEDIO (trade_type=medio): secondario. Nuovo ingresso: margine 100-250$, leva >=20x solo se stop e liquidazione lo consentono.
  TP 1-4%, SL 0.5-2%, durata ore-giorni. Solo su setup multi-timeframe molto solidi.
  Fino a 2 DCA consentiti (3 ingressi totali), solo se trend strutturale regge.

LEVA MASSIMA PER ASSET (applicata automaticamente dal codice):
- BTC, XAU, XAG: max 45x  |  ETH: max 30x  |  Altri: max 25x

SOGLIA MINIMA CONFIDENZA PER APRIRE:
- Asset TIER A (BTC, ETH, XAU, XAG): confidenza >= 60/100
- Asset TIER C (altcoin, tutto il resto): confidenza >= 70/100
- Non aprire mai sotto queste soglie, anche se ti sembra buono.

ENTRATA DIVERSIFICATA (opzionale, solo se lo ritieni intelligente):
- Puoi proporre "open_long_split" o "open_short_split" per dividere il margine in 2 ingressi:
  50% subito, il resto con ordine limite dopo un ritracciamento (campo "split_retrace_pct" in
  percentuale, 0.3-0.8; se manca usa 0.5). Il margine che indichi e' il TOTALE delle due gambe.
- La seconda gamba scade dopo 3h (scalp) o 12h (medio) se il prezzo non ritraccia, e si annulla se
  chiudi, fai partial_close o DCA. Lo stop e' lo stesso per entrambe le gambe.
- Il ritracciamento e' limitato al 60% della distanza dello stop; se lo stop e' troppo vicino il
  codice apre tutto subito. PRIMA GAMBA almeno 100$, quindi per uno split reale proponi almeno 200$.
  Usa split solo se il prezzo e' vicino a una resistenza/supporto.
- In assenza di motivi precisi, usa l'entrata singola normale.

DCA — INGRESSI PROGRESSIVI:
- Proponi "dca" se la posizione e' in perdita MA il setup originale regge ancora.
- Deve esserci un supporto/resistenza reale vicino al prezzo attuale.
- SCALP: max 1 DCA. MEDIO: max 2 DCA (3 ingressi totali).
- Non fare DCA se il segnale originale e' cambiato o se il prezzo cade in modo sostenuto.
- Con il DCA lo stop non si allarga mai: il codice tiene lo stop attuale se ne proponi uno piu' lontano.

RISCHIO/RENDIMENTO — REGOLA FONDAMENTALE:
- Ogni trade DEVE avere R:R >= 1:2 (guadagno potenziale almeno il doppio del rischio).
- Esempio: margine 150$, SL = rischio 30$ → TP1 DEVE valere almeno 60$ di profitto.
- Con leva 20x su 150$: SL 0.5% = 15$ persi → TP1 a 1% = 30$ guadagnati (R:R 1:2 minimo).
- Non aprire MAI un trade con R:R < 1:2. Se il setup non lo consente, usa "skip".
- R:R ideale per scalp: 1:2.5 o 1:3. Per medio: 1:3 o 1:4.

TAKE PROFIT SCALABILE (usa questa logica per scalp con R:R raggiunto):
- Primo TP (TP1): quando il profitto equivale a 2x il rischio → chiudi 35% (partial_close).
  Il codice mantiene aperto il 65% restante con TP2 piu' lontano (3x o 4x il rischio).
- Usa partial_close_tp2_pct per indicare la percentuale di TP2 sul residuo.
- I cicli successivi rivaluta il residuo: "hold" se trend regge, "close" se invertito.
- Su movimento esplosivo (>4x rischio) puoi chiudere tutto: usa "close" direttamente.
- Esempio concreto: margin=150$, SL=0.4%, TP1=0.8% (chiudi 35%), TP2=1.5% (residuo 65%).

LONG/SHORT RATIO:
- Se il long/short ratio e' > 1.5 (molti piu' long che short) su un asset, considera short.
- Se e' < 0.7 (molti piu' short), considera long (contrarian).
- Ratio neutro 0.8-1.2: segui il segnale tecnico senza aggiustamenti.

GESTIONE POSIZIONI APERTE:
- Ogni ciclo valuti ogni posizione aperta: hold, close, dca, o partial_close.
- "close" se: SL vicino, segnale invertito, TP raggiunto, o migliore opportunita' altrove.
- "hold" se: trend regge, posizione in profitto, setup ancora valido.
- "partial_close" se: primo TP raggiunto ma trend regge ancora.
- "dca" solo se: posizione in perdita E setup regge E supporto reale presente.

REGOLE DURE (il codice le applica comunque):
- Stop loss SEMPRE obbligatorio. Nuove aperture 100-250$, leva >=20x. Posizioni max 10.
- NON forzare trade per raggiungere una quota. Valuta costi netti e rischio in dollari;
  se 20x e' incompatibile con uno stop valido o nessuna occasione supera i costi, usa skip.

APPRENDIMENTO — MEMORIA PERMANENTE:
- STORICO SIMBOLI: win rate e P&L per asset (ultimi 200 trade). Evita simboli con WR < 40%.
- APPUNTI COACHING: errori identificati e pattern ricorrenti. Applicali ogni ciclo.
- Memorizza cosa ha funzionato e cosa no: sei un trader che impara dai propri errori.

RISPOSTA — SOLO JSON:
{"decisions":[
  {"symbol":"BTC","action":"open_long|open_short|open_long_split|open_short_split|hold|close|partial_close|dca|skip",
   "trade_type":"scalp|medio",
   "confidence":0-100,
   "leverage":int,
   "margin_usd":number,
   "stop_loss_pct":number,
   "take_profit_pct":number,
   "partial_close_fraction":number,
   "partial_close_tp2_pct":number,
   "reason":"max 30 parole",
   "dca_sl_pct":number,
   "dca_tp_pct":number,
   "split_retrace_pct":number}
],"note":"max 20 parole"}

Per posizioni aperte: hold, close, partial_close o dca. Per nuovi ingressi: open_long/open_short/open_long_split/open_short_split/skip."""


# ──────────────────────────────────────────────────────────────────────────────
# SYSTEM PROMPT — PORTAFOGLIO BULL
# ──────────────────────────────────────────────────────────────────────────────
SYSTEM_BULL = """Sei il cervello di un trader professionista di futures crypto — PAPER TRADING con $1000 finti.

MISSIONE: gestire il PORTAFOGLIO BULL — massimo 3 posizioni contemporanee, margine fino a $350 per trade.
Operi come un trader di posizione intraday/medio con leva scelta in base al rischio e alla forza del setup.

STRATEGIA PRINCIPALE — POSIZIONI MEDIE (MEDIO):
- MEDIO (trade_type=medio): PRIORITA'. Nuovo ingresso 150-350$, leva >=20x solo se valida e sostenibile.
  TP da 5% in su (puoi tenerlo aperto se il trend continua), SL 1-3%, durata ore-giorni.
  Seleziona solo setup con altissima probabilita': confluence su piu' timeframe, momentum forte, volume.
  Se il trend continua oltre il tuo TP originale → proponi "hold" o aggiorna TP piu' lontano.
- SCALP (trade_type=scalp): secondario. Solo su opportunita' rapide con vantaggio netto.
  Nuovo ingresso 150-350$, leva >=20x se compatibile con stop/strumento; non inseguire i prezzi.

LEVA MASSIMA PER ASSET (applicata automaticamente dal codice):
- BTC, XAU, XAG: max 45x  |  ETH: max 30x  |  Altri: max 25x

SOGLIA MINIMA CONFIDENZA PER APRIRE:
- Asset TIER A (BTC, ETH, XAU, XAG): confidenza >= 60/100
- Asset TIER C (altcoin, tutto il resto): confidenza >= 70/100
- Con max 3 trade devi essere selettivissimo: apri solo se confidenza >= 75 per altcoin, >= 65 per TIER A.

REGOLA CRITICA — MAX 3 POSIZIONI:
- Hai slot per SOLO 3 trade contemporanei. Scegli i migliori setup in assoluto.
- Se hai gia' 3 posizioni aperte, non aprire nuovi trade (skip tutto).
- Meglio aspettare il momento giusto che aprire trade mediocri.

TAKE PROFIT ESTESO (filosofia Bull):
- Il TP minimo accettabile e' 5%. Se il setup non giustifica almeno 5%, usa "skip".
- TP1 suggerito: 5-8%, TP2: 10-15% (o oltre se il trend e' forte).
- Se raggiungi TP1 ma il trend continua: "hold" o "partial_close" lasciando aperto il 60-70%.
- Non chiudere mai una posizione vincente troppo presto — lascia correre il profitto.

RISCHIO/RENDIMENTO:
- R:R minimo 1:2.5. Ideale 1:4 o 1:5 per trade medio.
- Esempio: margin 300$, SL 2% = 120$ rischio → TP deve valere almeno 300$ (5% con leva 20x).
- Non aprire mai con R:R < 1:2. Preferisci 1:3 o meglio.

TAKE PROFIT SCALABILE:
- Usa partial_close al primo TP raggiunto (chiudi 35-40%), mantieni il resto con TP2 piu' lontano.
- Il residuo 60-65% rimane aperto: rivaluta ogni ciclo se trend regge o invertire.

ENTRATA DIVERSIFICATA (opzionale):
- "open_long_split" / "open_short_split": 50% del margine subito, il resto con ordine limite dopo un
  ritracciamento ("split_retrace_pct" in percentuale, 0.3-0.8; se manca usa 0.5). Il margine che
  indichi e' il TOTALE delle due gambe. Scade dopo 12h (medio) e si annulla se chiudi, fai
  partial_close o DCA. Stesso stop per entrambe le gambe.
- PRIMA GAMBA almeno 150$: per uno split reale proponi 300-350$ di margine complessivo.
  Utile vicino a supporto/resistenza con invalidazione verificabile; altrimenti ingresso unico.

DCA — INGRESSI PROGRESSIVI:
- Proponi "dca" se la posizione e' in perdita MA il setup originale regge.
- MEDIO: max 2 DCA (3 ingressi totali). Mai superare 700$ su un singolo asset.
- Ogni DCA deve avere un supporto/resistenza reale vicino al prezzo.
- Con il DCA lo stop non si allarga mai: il codice tiene lo stop attuale se ne proponi uno piu' lontano.

LONG/SHORT RATIO:
- Se il long/short ratio > 1.5 → considera short (molti long rischiano liquidazione).
- Se < 0.7 → considera long (contrarian).

GESTIONE POSIZIONI APERTE:
- "hold" se: trend regge, posizione in profitto, TP non ancora raggiunto.
- "partial_close" se: TP1 raggiunto ma trend continua.
- "close" se: segnale chiaramente invertito, SL vicino, o migliore opportunita'.
- "dca" solo se: setup regge E supporto reale presente.

REGOLE DURE (il codice le applica comunque):
- Stop loss SEMPRE obbligatorio. Nuove aperture 150-350$, leva >=20x. Posizioni max 3.
- NON aumentare automaticamente il rischio di una proposta troppo piccola:
  se stop, leva minima o dimensionamento non sono sostenibili, usa skip e spiega perche'.
- Controlla profitto netto al netto di fee, spread, slippage e funding, non solo ROI lordo.

APPRENDIMENTO:
- STORICO SIMBOLI: win rate e P&L per asset. Evita simboli con WR < 40%.
- APPUNTI COACHING: errori identificati. Applicali ogni ciclo.

RISPOSTA — SOLO JSON:
{"decisions":[
  {"symbol":"BTC","action":"open_long|open_short|open_long_split|open_short_split|hold|close|partial_close|dca|skip",
   "trade_type":"scalp|medio",
   "confidence":0-100,
   "leverage":int,
   "margin_usd":number,
   "stop_loss_pct":number,
   "take_profit_pct":number,
   "partial_close_fraction":number,
   "partial_close_tp2_pct":number,
   "reason":"max 30 parole",
   "dca_sl_pct":number,
   "dca_tp_pct":number,
   "split_retrace_pct":number}
],"note":"max 20 parole"}

Per posizioni aperte: hold, close, partial_close o dca. Per nuovi ingressi: open_long/open_short/open_long_split/open_short_split/skip."""


# ---------------- spesa
def cost_of(usage: dict) -> float:
    return usage.get("input_tokens", 0) * PRICE_IN + usage.get("output_tokens", 0) * PRICE_OUT


def budget_left(state: dict, day: str, cap: float = DAILY_CAP) -> float:
    b = state.setdefault("budget", {})
    if b.get("day") != day:
        b.update(day=day, spent=0.0, calls=0)
    return cap - b["spent"]


def can_call(state: dict, day: str, cap: float = DAILY_CAP) -> bool:
    return bool(os.getenv("ANTHROPIC_API_KEY")) and budget_left(state, day, cap) >= CALL_RESERVE


def record_spend(state: dict, day: str, usage: dict) -> float:
    c = cost_of(usage)
    budget_left(state, day)
    state["budget"]["spent"] += c
    state["budget"]["calls"] += 1
    state["budget"]["total_spent"] = state["budget"].get("total_spent", 0.0) + c
    return c


# ---------------- chiamata API
def call_claude(system: str, user: str, max_tokens: int = 900, timeout: int = 60) -> tuple:
    key = os.getenv("ANTHROPIC_API_KEY", "")
    body = json.dumps({"model": MODEL, "max_tokens": max_tokens, "system": system,
                       "messages": [{"role": "user", "content": user}]}).encode()
    req = urllib.request.Request(API_URL, data=body, headers={
        "x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            d = json.loads(r.read().decode())
    except Exception as exc:
        raise RuntimeError(f"chiamata Claude fallita ({type(exc).__name__})") from None
    text = "".join(b.get("text", "") for b in d.get("content", []) if b.get("type") == "text")
    usage = dict(d.get("usage") or {})
    usage["stop_reason"] = d.get("stop_reason")   # solo per il registro: "max_tokens" = risposta tagliata
    return text, usage


def parse_decisions(text: str) -> dict | None:
    i, j = text.find("{"), text.rfind("}")
    if i < 0 or j <= i:
        return None
    try:
        d = json.loads(text[i:j + 1])
    except ValueError:
        return None
    if not isinstance(d, dict) or not isinstance(d.get("decisions"), list):
        return None
    out = []
    valid_actions = ("open_long", "open_short", "open_long_split", "open_short_split",
                     "hold", "close", "partial_close", "dca", "skip")
    for x in d["decisions"]:
        try:
            act = str(x["action"])
            if act not in valid_actions:
                continue
            sl_pct = float(x.get("stop_loss_pct", 0))
            tp_pct = float(x.get("take_profit_pct", 0))
            out.append({
                "symbol": str(x["symbol"]).upper().split("/")[0],
                "action": act,
                "trade_type": str(x.get("trade_type", "medio")),
                "confidence": int(max(0, min(100, float(x.get("confidence", 0))))),
                "leverage": int(float(x.get("leverage", 3))),
                "margin_usd": float(x.get("margin_usd", 0)),
                "stop_loss_pct": sl_pct,
                "take_profit_pct": tp_pct,
                "rr_ratio": round(tp_pct / sl_pct, 2) if sl_pct > 0 else 0.0,
                "partial_close_fraction": float(x.get("partial_close_fraction", 0.35)),
                "partial_close_tp2_pct": float(x.get("partial_close_tp2_pct", 0)),
                "reason": str(x.get("reason", ""))[:300],
                "dca_sl_pct": float(x.get("dca_sl_pct", 0)),
                "dca_tp_pct": float(x.get("dca_tp_pct", 0)),
                # ritracciamento della seconda gamba: Claude lo scrive in percentuale (0.5 = 0,5%)
                "split_retrace_pct": float(x.get("split_retrace_pct", 0) or 0) / 100.0,
            })
        except (KeyError, TypeError, ValueError):
            continue
    return {"decisions": out, "note": str(d.get("note", ""))[:200]}


def diagnose_reply(text: str) -> str:
    """Perche' una risposta di Claude non e' stata letta da parse_decisions. SOLO per il registro:
    non e' usata per nessuna decisione. Valori: vuota, senza_json, json_troncato, json_non_valido,
    forma_errata, letta (se in realta' si legge)."""
    t = text or ""
    if not t.strip():
        return "vuota"
    i, j = t.find("{"), t.rfind("}")
    if i < 0 or j <= i:
        return "troncato_prima_della_fine" if i >= 0 else "senza_json"
    try:
        d = json.loads(t[i:j + 1])
    except ValueError:
        # apertura senza chiusura corrispondente: la risposta e' stata interrotta a meta'
        return "json_troncato" if t.count("{") > t.count("}") or t.count("[") > t.count("]") else "json_non_valido"
    if not isinstance(d, dict) or not isinstance(d.get("decisions"), list):
        return "forma_errata"
    return "letta"


# ---------------- prompt V2
def build_prompt(snapshot: dict, readings: list, positions: list, headlines: list,
                 lessons: str, ctx: dict | None = None, symbol_stats: str = "", macro_lines: str = "") -> str:
    # tetti veri del portafoglio (passati da cli.account_snapshot); se mancano non si inventa nessuna cifra
    mm, mo = snapshot.get("max_margin"), snapshot.get("max_open")
    margin_txt = f"{snapshot['margin']:.0f}/{mm:.0f}$" if mm is not None else f"{snapshot['margin']:.0f}$"
    open_txt = f"{snapshot['n_open']}/{mo}" if mo is not None else f"{snapshot['n_open']}"
    lines = [
        f"CONTO: capitale {snapshot['equity']:.0f}$, cassa {snapshot['cash']:.0f}$, "
        f"margine in uso {margin_txt}, posizioni {open_txt}, "
        f"P&L oggi {snapshot['day_pnl']:+.1f}$"
        + (f", STOP: {snapshot['halt']}" if snapshot.get("halt") else "")
    ]

    if positions:
        lines.append("POSIZIONI APERTE:")
        for p in positions:
            max_dca = 1 if p.get("trade_type") == "scalp" else 3
            dca_info = f", DCA {p.get('dca_count', 0)}/{max_dca}" if p.get("dca_count", 0) > 0 else ""
            sp = p.get("split_pending")
            if sp:
                dca_info += f", 2a gamba in attesa @{sp['trigger']:.5g} ({sp['margin']:.0f}$)"
            lines.append(
                f"- {p['symbol']} {'LONG' if p['side'] == 1 else 'SHORT'} "
                f"{p.get('trade_type', 'medio').upper()} lev {p['leverage']}x "
                f"margine {p['margin']:.0f}${dca_info} ingresso {p['entry']:.5g} "
                f"ora {p['price']:.5g} P&L {p['pnl']:+.1f}$ stop {p['sl']:.5g} "
                f"da {p['hours']:.1f}h score_lato {p['score_now']} score_opposto {p.get('score_opposite')}. "
                f"TP {p.get('tp')} R_netto {p.get('r_net')} ROI_netto% {p.get('roi_net_pct')} "
                f"ROI_base=iniziale+DCA_non_ridotta_dai_parziali MFE_R_limite {p.get('mfe_price_R_upper_bound')} "
                f"giveback_R_limite {p.get('giveback_price_R_upper_bound')} (estremi barra, non picco netto eseguibile). "
                f"Motivo: {p['reason'][:120]}"
            )
            # contesto di mercato sulla posizione aperta
            if ctx:
                for line in _ctx_lines(ctx, p["symbol"]):
                    lines.append(f"  {line}")

    lines.append("COPPIE ANALIZZATE:")
    for r in readings:
        side_str = "LONG" if r.side == 1 else "SHORT" if r.side == -1 else "-"
        lines.append(
            f"- {r.symbol}: {r.price:.5g}, {side_str} {r.score}/100 "
            f"(L{r.long_score}/S{r.short_score}), tipo={r.trade_type}, "
            f"ATR {r.atr_pct:.2%}, RSI1h {r.facts.get('rsi1h')}, "
            f"trend4h {r.facts.get('ema50_200_4h')}, {r.facts.get('daily_trend', '')}, "
            f"vol x{r.facts.get('vol_ratio', 1):.1f}"
            + (f", pattern={r.pattern}" if r.pattern else "")
            + (f", sl_sug {r.sl_pct:.2%}, tp_sug {r.tp_pct:.2%}")
        )
        if r.seasonal_note:
            lines.append(f"  Stagionalità: {r.seasonal_note}")
        if ctx:
            for line in _ctx_lines(ctx, r.symbol):
                lines.append(f"  {line}")

    if headlines:
        lines.append("NOTIZIE (con sentiment se disponibile): " + " | ".join(headlines[:10]))

    if macro_lines.strip():   # calendario macro: presente solo quando c'e' qualcosa da dire (vedi macro_calendar)
        lines.append(macro_lines.strip())

    if symbol_stats.strip():
        lines.append(symbol_stats.strip())

    if lessons.strip():
        lines.append("APPUNTI ERRORI RICORRENTI (applica queste correzioni):\n" + lessons.strip()[-1500:])

    return "\n".join(lines)


def _ctx_lines(ctx: dict, symbol: str) -> list:
    from desk.market_context import context_lines
    try:
        return context_lines(ctx, symbol)
    except Exception:
        return []


# ---------------- ripiego a sole regole
def rules_decisions(readings: list, positions: list, open_symbols: set, entry_score: int = 70) -> list:
    out = []
    by = {r.symbol: r for r in readings}
    for p in positions:
        r = by.get(p["symbol"])
        if r is None:
            continue
        mine = r.long_score if p["side"] == 1 else r.short_score
        theirs = r.short_score if p["side"] == 1 else r.long_score
        if mine < 35 or theirs >= 60:
            out.append({"symbol": p["symbol"], "action": "close", "trade_type": "medio",
                        "confidence": 0, "leverage": 1, "margin_usd": 0,
                        "stop_loss_pct": 0, "take_profit_pct": 0,
                        "reason": f"segnale sceso a {mine}", "dca_sl_pct": 0, "dca_tp_pct": 0})
    for r in readings:
        if r.symbol in open_symbols or r.side == 0 or r.score < entry_score:
            continue
        frac = min(1.0, max(0.0, (r.score - 60) / 40))
        is_scalp = r.trade_type == "scalp"
        out.append({"symbol": r.symbol,
                    "action": "open_long" if r.side == 1 else "open_short",
                    "trade_type": r.trade_type,
                    "confidence": r.score,
                    # Leva scalp: 15x (score 60) → 45x (score 100), rispettando tier asset.
                    # Leva medio: 5x (score 60) → 25x (score 100).
                    # engine.py applica il cap tier (BTC/XAU/XAG 45x, ETH 30x, altri 25x).
                    "leverage": int(round(15 + frac * 30)) if is_scalp else int(round(5 + frac * 20)),
                    "margin_usd": round(150 + frac * 100, 0) if is_scalp else round(80 + frac * 170, 0),
                    "stop_loss_pct": r.sl_pct,
                    "take_profit_pct": r.tp_pct,
                    "reason": "; ".join(r.why[:3]),
                    "dca_sl_pct": 0, "dca_tp_pct": 0})
    return out


# ---------------- lessons V2: con sezione errori ricorrenti
def update_lessons(d: str, st: dict, day: str, call=call_claude) -> None:
    """Aggiorna lessons.md e la sezione errori ricorrenti. Richiama Claude una volta a sera."""
    if st.get("lessons_day") == day or not can_call(st, day, DAILY_CAP + 0.0):
        return
    if "main" not in st or "closed" not in st.get("main", {}):
        return
    today = [t for t in st["main"]["closed"] if _utc_day(t["close_ms"]) == day]
    if not today:
        return
    st["lessons_day"] = day
    brief = "\n".join(
        f"{t['symbol']} {'L' if t['side'] == 1 else 'S'} {t['leverage']}x "
        f"{t.get('trade_type','?')} conf {t['confidence']} {t['net']:+.2f}$ ({t['why']}): {t['reason'][:90]}"
        for t in today[-15:]
    )
    # leggi errori ricorrenti precedenti
    err_file = os.path.join(d, "errors.md")
    prev_errors = ""
    if os.path.exists(err_file):
        with open(err_file) as f:
            prev_errors = f.read()[-800:]
    system_msg = (
        "Sei un trader senior che fa coaching. Analizza i trade di oggi e:\n"
        "1. Scrivi max 5 appunti brevi su cosa ripetere o evitare (una riga ciascuno).\n"
        "2. Sotto la sezione '## ERRORI RICORRENTI' aggiorna un elenco degli errori "
        "che si ripetono (max 8 voci). Se un errore e' gia' nella lista precedente, "
        "incrementa il contatore. Se e' nuovo, aggiungilo. Se non si e' ripetuto da "
        "piu' di 5 giorni, rimuovilo. Usa formato: '- [N volte] descrizione errore'\n"
        "Niente premesse. Rispondi direttamente."
    )
    user_msg = f"Trade chiusi oggi:\n{brief}\n\nErrori ricorrenti precedenti:\n{prev_errors}"
    try:
        text, usage = call(system_msg, user_msg, 500)
        record_spend(st, day, usage)
        # separa appunti da errori ricorrenti
        if "## ERRORI RICORRENTI" in text:
            parts = text.split("## ERRORI RICORRENTI", 1)
            notes_part = parts[0].strip()
            errors_part = parts[1].strip() if len(parts) > 1 else ""
        else:
            notes_part = text.strip()
            errors_part = ""
        # salva appunti giornalieri
        with open(os.path.join(d, "lessons.md"), "a") as f:
            f.write(f"\n[{day}]\n{notes_part[:600]}\n")
        # aggiorna file errori ricorrenti
        if errors_part:
            with open(err_file, "w") as f:
                f.write(f"# Errori ricorrenti — aggiornato {day}\n{errors_part[:1000]}\n")
    except Exception:
        pass


def _utc_day(ms: int) -> str:
    return time.strftime("%Y-%m-%d", time.gmtime(ms / 1000))


# ---------------- storico trade permanente
def append_trade_history(data_dir: str, trade: dict) -> None:
    """Appende un trade chiuso al log JSONL permanente (sopravvive ai rideploy)."""
    path = os.path.join(data_dir, "trade_history.jsonl")
    os.makedirs(data_dir, exist_ok=True)
    try:
        with open(path, "a") as f:
            f.write(json.dumps(trade, default=str) + "\n")
    except Exception:
        pass


def load_symbol_stats(data_dir: str, last_n: int = 200) -> dict:
    """Legge le ultime N righe del trade_history.jsonl e calcola statistiche per simbolo."""
    path = os.path.join(data_dir, "trade_history.jsonl")
    if not os.path.exists(path):
        return {}
    try:
        with open(path) as f:
            lines = f.readlines()
        trades = []
        for line in lines[-last_n:]:
            try:
                rec = json.loads(line)
            except Exception:
                continue
            if isinstance(rec, dict):   # righe vecchie (liste) di reset passati: si ignorano
                trades.append(rec)
        stats: dict = {}
        for t in trades:
            sym = t.get("symbol", "?")
            if sym not in stats:
                stats[sym] = {"wins": 0, "losses": 0, "total_net": 0.0,
                              "best": 0.0, "worst": 0.0, "trade_types": {}}
            s = stats[sym]
            net = float(t.get("net", 0))
            s["total_net"] += net
            if net >= 0:
                s["wins"] += 1
                s["best"] = max(s["best"], net)
            else:
                s["losses"] += 1
                s["worst"] = min(s["worst"], net)
            tt = t.get("trade_type", "?")
            s["trade_types"][tt] = s["trade_types"].get(tt, 0) + 1
        return stats
    except Exception:
        return {}


def stats_summary(stats: dict, top_n: int = 8) -> str:
    """Genera un riassunto compatto delle statistiche per simbolo, per il prompt."""
    if not stats:
        return ""
    rows = []
    for sym, s in stats.items():
        total = s["wins"] + s["losses"]
        if total == 0:
            continue
        wr = s["wins"] / total * 100
        rows.append((s["total_net"], sym, s, wr, total))
    # ordina per P&L totale decrescente
    rows.sort(key=lambda x: x[0], reverse=True)
    lines = ["STORICO SIMBOLI (ultimi trade):"]
    for _, sym, s, wr, total in rows[:top_n]:
        tt_str = "/".join(f"{k}:{v}" for k, v in s["trade_types"].items())
        lines.append(
            f"- {sym}: {total} trade, WR {wr:.0f}%, netto {s['total_net']:+.1f}$  "
            f"[best {s['best']:+.1f}$ worst {s['worst']:+.1f}$  {tt_str}]"
        )
    return "\n".join(lines)
