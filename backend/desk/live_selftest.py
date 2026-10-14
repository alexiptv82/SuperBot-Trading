"""
live_selftest.py — Prova del collegamento con Bitget con un importo MINIMO (pochi centesimi di commissioni).

Cosa fa, in ordine (si ferma e ripulisce al primo problema):
  A. solo lettura (nessun soldo): chiavi valide, modalita' posizione, margine, saldo, account senza posizioni,
     tutti i simboli del bot esistono come perpetui su Bitget, minimi di ordine.
  B. con soldi veri ma minimi (margine <= 5$): apre una posizione con stop e take profit, controlla che sia
     ISOLATA con la leva giusta e che stop/TP esistano sull'exchange; poi sposta stop/TP (come dopo un DCA),
     aggiunge contratti, ne riduce meta', chiude tutto, e controlla che l'account torni piatto e senza
     ordini stop rimasti.
  C. pulizia garantita: qualunque cosa succeda, alla fine chiude l'eventuale posizione e annulla gli stop rimasti.

NON tocca i bot, i loro dati, i loro flag. Usa le chiavi di trading SOLO dentro il processo (mai stampate).
Si lancia da un container usa-e-getta (vedi .github/workflows/live-selftest.yml), mai a mano sul server dei bot.

    python -m desk.live_selftest --yes-real-money [--symbol XRP] [--margin 3] [--lev 5]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

from desk import live_connector as lc

STEPS: list = []


def say(msg: str) -> None:
    print(msg, flush=True)


def step(name: str, ok: bool, detail: str = "") -> bool:
    STEPS.append((name, ok, detail))
    say(f"[{'OK ' if ok else 'KO '}] {name}" + (f" — {detail}" if detail else ""))
    return ok


def _plans(conn, ccxt_sym: str) -> list:
    try:
        rows = conn._client.fetch_open_orders(ccxt_sym, None, None, {"stop": True, "planType": "profit_loss"}) or []
    except Exception as e:
        say(f"     (elenco stop non leggibile: {str(e)[:120]})")
        return []
    out = []
    for o in rows:
        info = o.get("info") or {}
        out.append({"id": str(o.get("id")), "tipo": info.get("planType"), "lato": info.get("holdSide"),
                    "trigger": o.get("triggerPrice") or info.get("triggerPrice"), "size": info.get("size")})
    return out


def _cleanup(conn, base: str, ccxt_sym: str) -> None:
    say("--- pulizia ---")
    try:
        snap = conn.snapshot()
        if base in snap:
            ok, d = conn.close(base, snap[base]["side"])
            say(f"chiusura di sicurezza: {'ok' if ok else 'FALLITA ' + str(d)}")
    except Exception as e:
        say(f"pulizia posizione non riuscita: {str(e)[:160]}")
    try:
        for p in _plans(conn, ccxt_sym):
            try:
                conn._client.cancel_order(p["id"], ccxt_sym, {"stop": True, "planType": p["tipo"] or "profit_loss"})
                say(f"annullato stop rimasto {p['id']}")
            except Exception as e:
                say(f"stop {p['id']} non annullato: {str(e)[:100]}")
    except Exception:
        pass


def main(argv=None, conn=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--yes-real-money", action="store_true", help="conferma esplicita: usa soldi veri (importo minimo)")
    ap.add_argument("--symbol", default="XRP")
    ap.add_argument("--margin", type=float, default=3.0)
    ap.add_argument("--lev", type=int, default=5)
    args = ap.parse_args(argv)

    if not args.yes_real_money:
        say("Manca --yes-real-money: nessuna operazione eseguita.")
        return 2
    if args.margin > 5.0 or args.margin <= 0:
        say("Margine non ammesso: il test usa al massimo 5$.")
        return 2
    if conn is None:
        if not lc.IS_LIVE:
            say("DESK_MODE non e' 'live': nessuna operazione eseguita.")
            return 2
        os.makedirs(os.getenv("DESK_DATA_DIR", "/tmp/selftest"), exist_ok=True)
        conn = lc.LiveConnector(data_dir=os.getenv("DESK_DATA_DIR", "/tmp/selftest"))

    base, ccxt_sym = args.symbol.upper(), lc._symbol_ccxt(args.symbol.upper())
    client = conn._client
    t0 = time.time()
    say(f"=== PROVA COLLEGAMENTO BITGET — simbolo {base}, margine {args.margin}$ x{args.lev} ===")

    # ---------------- A. sola lettura ----------------
    try:
        client.load_markets()
        step("A1 mercati caricati", True, f"{len(client.markets)} mercati")
    except Exception as e:
        step("A1 mercati caricati", False, str(e)[:160])
        return 1
    try:
        bal = client.fetch_balance({"type": "swap"})
        usdt = (bal.get("USDT") or {})
        step("A2 chiave valida e saldo futures letto", True,
             f"USDT liberi={usdt.get('free')} totali={usdt.get('total')}")
    except Exception as e:
        step("A2 chiave valida e saldo futures letto", False, str(e)[:200])
        return 1
    try:
        snap = conn.snapshot()
        if not step("A3 account senza posizioni aperte", not snap, ", ".join(sorted(snap)) or "nessuna"):
            say("Interrompo: l'account ha gia' posizioni. Il test parte solo su account piatto.")
            return 1
    except lc.LiveError as e:
        step("A3 account senza posizioni aperte", False, str(e)[:160])
        return 1
    try:
        cfg = conn._symbol_config(ccxt_sym)
        step("A4 impostazioni account letti", cfg["pos_mode"] in (lc.ONE_WAY, lc.HEDGE),
             f"posizioni={cfg['pos_mode']} margine={cfg['margin_mode']} leve(long/short)={cfg['long_lev']}/{cfg['short_lev']}")
    except lc.LiveError as e:
        step("A4 impostazioni account letti", False, str(e)[:160])
        return 1
    try:   # tutti i simboli del bot devono esistere come perpetui attivi
        sys.argv = sys.argv[:1]     # cli legge --portfolio dagli argomenti: qui non deve vedere i nostri
        from desk.cli import SYMBOLS
        missing = []
        for s in SYMBOLS:
            try:
                m = client.market(lc._symbol_ccxt(s))
                if not m.get("swap") or m.get("active") is False:
                    missing.append(s)
            except Exception:
                missing.append(s)
        step("A5 simboli del bot presenti come perpetui su Bitget", not missing,
             "tutti" if not missing else "MANCANO: " + ", ".join(missing))
    except Exception as e:
        step("A5 simboli del bot presenti come perpetui su Bitget", False, f"non verificabile: {str(e)[:120]}")

    # ---------------- B. con importo minimo ----------------
    side = 1
    try:
        m = client.market(ccxt_sym)
        px = float(client.fetch_ticker(ccxt_sym)["last"])
        qty = conn._round_qty(ccxt_sym, args.margin * args.lev / px)
        min_cost = float(((m.get("limits") or {}).get("cost") or {}).get("min") or 5.0)
        if qty * px < min_cost * 1.05:
            say(f"Importo troppo piccolo per il minimo del contratto ({qty*px:.2f}$ < {min_cost}$): alzo la quantita'")
            qty = conn._round_qty(ccxt_sym, min_cost * 1.2 / px)
        cost_now = qty * px / args.lev
        if cost_now > 5.0:
            step("B0 importo del test entro 5$ di margine", False, f"servirebbero {cost_now:.2f}$: scegli un simbolo meno costoso")
            return 1
        step("B0 importo del test", True, f"qty={qty} prezzo={px} valore={qty*px:.2f}$ margine~{cost_now:.2f}$")
    except Exception as e:
        step("B0 importo del test", False, str(e)[:160])
        return 1

    sl, tp = round(px * 0.93, 8), round(px * 1.07, 8)
    try:
        ok, detail = conn.open(base, side, qty, args.lev, sl=sl, tp=tp, ref_price=px)
        if not step("B1 apertura con stop e take profit nello stesso ordine", ok, str(detail)[:200]):
            return 1
        pos = conn.snapshot().get(base)
        step("B2 posizione ISOLATA, lato e leva giusti",
             bool(pos) and pos["margin_mode"] == "isolated" and pos["side"] == side and pos["leverage"] == args.lev,
             json.dumps({k: pos[k] for k in ("side", "qty", "entry", "leverage", "margin_mode")}) if pos else "assente")
        plans = _plans(conn, ccxt_sym)
        kinds = sorted(p["tipo"] or "?" for p in plans)
        step("B3 stop e take profit presenti sull'exchange", len(plans) >= 2, f"{plans}")
        fill = conn.last_fill
        say(f"     esito reale: prezzo medio={fill.get('avg')} quantita'={fill.get('filled')} commissione={fill.get('fee')}")

        ok, detail = conn.set_protection(base, side, round(px * 0.92, 8), round(px * 1.08, 8))
        plans2 = _plans(conn, ccxt_sym)
        step("B4 spostamento stop/TP (come dopo un DCA)", ok, f"{detail[:100]} | ora: {plans2}")

        ok, detail = conn.add(base, side, qty, args.lev, sl=round(px * 0.92, 8), tp=round(px * 1.08, 8), ref_price=px)
        pos2 = conn.snapshot().get(base)
        step("B5 aggiunta di contratti (DCA / seconda gamba)",
             ok and bool(pos2) and pos2["qty"] > pos["qty"] * 1.5, f"{str(detail)[:80]} qty ora={pos2['qty'] if pos2 else None}")
        step("B5b la posizione resta isolata dopo l'aggiunta", bool(pos2) and pos2["margin_mode"] == "isolated")

        ok, detail = conn.reduce(base, side, 0.5)
        pos3 = conn.snapshot().get(base)
        step("B6 riduzione al 50% (TP parziale)",
             ok and bool(pos3) and pos2 is not None and pos3["qty"] < pos2["qty"] * 0.6,
             f"{str(detail)[:80]} qty ora={pos3['qty'] if pos3 else None}")

        ok, detail = conn.close(base, side)
        flat = base not in conn.snapshot()
        step("B7 chiusura completa", ok and flat, str(detail)[:120])
        left = _plans(conn, ccxt_sym)
        step("B8 nessuno stop rimasto dopo la chiusura", not left, f"{left}" if left else "pulito")
    except Exception as e:
        step("B* errore imprevisto", False, f"{type(e).__name__}: {str(e)[:200]}")
    finally:
        _cleanup(conn, base, ccxt_sym)   # C. pulizia garantita

    try:
        bal2 = client.fetch_balance({"type": "swap"})
        usdt2 = (bal2.get("USDT") or {})
        say(f"saldo finale USDT totali={usdt2.get('total')} (costo del test = differenza con quello iniziale)")
    except Exception:
        pass

    bad = [n for n, ok, _ in STEPS if not ok]
    say("=" * 60)
    say(f"RISULTATO: {'TUTTO OK' if not bad else 'NON OK -> ' + '; '.join(bad)}  ({time.time()-t0:.0f}s)")
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
