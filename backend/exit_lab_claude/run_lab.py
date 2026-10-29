#!/usr/bin/env python3
"""Esegue il laboratorio di uscite/entrate sulle entrate REALI dei classici e scrive il rapporto.

Uso:
  python run_lab.py --entries data/real_entries.csv --cache cache --out results     # candele vere (CI)
  python run_lab.py --entries data/real_entries.csv --synthetic --out /tmp/synth    # solo verifica dell'impianto
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

import lab_sim as ls
from lab_sim import HORIZON_MS, HOUR_MS, SLIP, Trade

PHASE = {("hawk", 2): "golden", ("bull", 1): "golden", ("hawk", 3): "crisi", ("bull", 2): "crisi"}
PHASES = ["golden", "crisi", "dopo"]
TTL = {"hawk": 3 * HOUR_MS, "bull": 12 * HOUR_MS}      # SPLIT_TTL_MS del motore: scalp 3h (Hawk), medio 12h (Bull)
GATE_AGREE, GATE_NET = 0.85, 0.10                     # soglie del gate di fedelta', fissate PRIMA di vedere i dati
COVERAGE_MIN = 0.95


# ------------------------------------------------------------------ dati
def load_trades(path: str):
    df = pd.read_csv(path)
    need = ["entry_fill", "entry_sl", "entry_tp", "entry_margin", "leverage"]
    skipped = int(df[need].isna().any(axis=1).sum())
    df = df.dropna(subset=need)
    df = df[df.side.isin([1, -1])]
    out, rdiff = [], []
    for r in df.itertuples():
        side, fill = int(r.side), float(r.entry_fill)
        d_sl = abs(fill - float(r.entry_sl)) / fill
        d_tp = abs(float(r.entry_tp) - fill) / fill
        lev, margin = int(r.leverage), float(r.entry_margin)
        if pd.notna(r.entry_r_dist) and float(r.entry_r_dist) > 0:
            rdiff.append(abs(d_sl - float(r.entry_r_dist)) / float(r.entry_r_dist))
        out.append(Trade(
            key=f"{r.bot}-{int(r.run_no)}-{int(r.id)}", bot=str(r.bot), run_no=int(r.run_no), symbol=str(r.symbol),
            side=side, t0=int(r.open_ms), price=fill / (1 + side * SLIP), fill0=fill, d_sl=d_sl, d_tp=d_tp, lev=lev,
            margin=margin, notional=margin * lev, risk_usd=margin * lev * d_sl,
            phase=PHASE.get((str(r.bot), int(r.run_no)), "dopo"), real_net=float(r.net),
            real_kind=str(r.exit_kind), parts=int(r.parts)))
    out.sort(key=lambda t: t.t0)
    return out, skipped, (float(np.max(rdiff)) if rdiff else float("nan"))


def synth_slice(tr: Trade, dt: int, seed: int, drift: float = 0.0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    n = int(HORIZON_MS // dt) + 8
    t = (tr.t0 // dt) * dt - 2 * dt + np.arange(n) * dt
    sig = 0.0007 * np.sqrt(dt / 60_000)
    cl = tr.price * np.exp(np.cumsum(rng.normal(0, sig, n) + tr.side * drift * dt / 60_000))
    op = np.concatenate([[tr.price], cl[:-1]])
    hi = np.maximum(op, cl) * (1 + np.abs(rng.normal(0, sig / 2, n)))
    lo = np.minimum(op, cl) * (1 - np.abs(rng.normal(0, sig / 2, n)))
    return np.column_stack([t, op, hi, lo, cl]).astype(float)


def slice_real(c: np.ndarray, tr: Trade, dt: int):
    if len(c) == 0:
        return None, 0.0
    lo = int(np.searchsorted(c[:, 0], tr.t0 - 2 * dt, "left"))
    hi = int(np.searchsorted(c[:, 0], tr.t0 + HORIZON_MS + 2 * dt, "right"))
    s = c[lo:hi]
    cov = float(((s[:, 0] >= tr.t0) & (s[:, 0] < tr.t0 + HORIZON_MS)).sum()) / (HORIZON_MS / dt)
    return s, cov


# ------------------------------------------------------------------ varianti
def build_variants():
    v = []
    for slm in (1.0, 1.5, 2.0):
        for tpm in (0.5, 0.75, 1.0, 1.5):
            for sizing in ("S", "R"):
                if slm == 1.0 and sizing == "R":
                    continue                       # identico a S
                v.append(("exit", f"uscite SL x{slm} TP x{tpm} [{sizing}]", dict(sl=slm, tp=tpm, sizing=sizing)))
    for pull in (0.3, 0.5, 0.75):
        for slm in (1.5, 2.0):
            for tpm in (0.75, 1.0):
                for sizing in ("S", "R"):
                    v.append(("scala", f"2 gambe pull x{pull} SL x{slm} TP x{tpm} [{sizing}]",
                              dict(pull=pull, sl=slm, tp=tpm, sizing=sizing)))
    for mode in ("limit", "bounce"):
        for w in (30, 60, 180):
            for p in (0.3, 0.5):
                v.append(("rimbalzo", f"entrata {mode} finestra {w}m ritracc. x{p}", dict(mode=mode, w=w, p=p)))
    return v


def run_variant(fam, p, c, tr):
    if fam == "exit":
        r = ls.run_exit_variant(c, tr, p["sl"], p["tp"])
        return r, r.net / tr.risk_usd * (r.scale if p["sizing"] == "R" else 1.0)
    if fam == "scala":
        r = ls.run_scalein_variant(c, tr, p["pull"], p["sl"], p["tp"], p["sizing"], TTL[tr.bot])
        return r, r.net / tr.risk_usd
    r = ls.run_pullback_variant(c, tr, p["mode"], p["w"] * 60_000, p["p"])
    return r, (r.net / tr.risk_usd if r.kind != "NOFILL" else 0.0)


# ------------------------------------------------------------------ statistica
def max_dd(R):
    cum = np.cumsum(R)
    return float((np.maximum.accumulate(np.maximum(cum, 0)) - cum).max()) if len(R) else 0.0


def top3_share(R):
    pos = np.sort(R[R > 0])[::-1]
    return float(pos[:3].sum() / pos.sum()) if pos.sum() > 0 else float("nan")


def boot_diff(diff, cl, mask, B=2000, seed=7):
    d, k = diff[mask], cl[mask]
    u, inv = np.unique(k, return_inverse=True)
    if len(u) < 3:
        return (float("nan"), float("nan"))
    sums, cnt = np.bincount(inv, weights=d), np.bincount(inv)
    idx = np.random.default_rng(seed).integers(0, len(u), size=(B, len(u)))
    m = sums[idx].sum(1) / cnt[idx].sum(1)
    return float(np.percentile(m, 2.5)), float(np.percentile(m, 97.5))


def boot_ratio_diff(Rv, ex, Rb, cl, B=2000, seed=7):
    """IC95 di  media(Rv sui trade ESEGUITI) - media(Rb su TUTTI i segnali), ricampionando blocchi di 12 ore."""
    u, inv = np.unique(cl, return_inverse=True)
    if len(u) < 3:
        return (float("nan"), float("nan"))
    sv = np.bincount(inv, weights=np.where(ex, Rv, 0.0))
    cv = np.bincount(inv, weights=ex.astype(float))
    sb = np.bincount(inv, weights=Rb)
    cb = np.bincount(inv).astype(float)
    idx = np.random.default_rng(seed).integers(0, len(u), size=(B, len(u)))
    den_v = cv[idx].sum(1)
    ok = den_v > 0
    m = sv[idx].sum(1)[ok] / den_v[ok] - sb[idx].sum(1)[ok] / cb[idx].sum(1)[ok]
    return float(np.percentile(m, 2.5)), float(np.percentile(m, 97.5))


def f(x, d=3):
    return "n/d" if x is None or (isinstance(x, float) and np.isnan(x)) else f"{x:.{d}f}"


# ------------------------------------------------------------------ main
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--entries", required=True)
    ap.add_argument("--cache")
    ap.add_argument("--synthetic", action="store_true")
    ap.add_argument("--drift", type=float, default=0.0,
                    help="solo sintetico: deriva per minuto a favore del lato del segnale (controllo positivo)")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)

    trades, skipped, rdist_err = load_trades(a.entries)
    meta = {"granularity": "1m", "sha256": "sintetico"}
    cache = {}
    if not a.synthetic:
        meta = json.loads((Path(a.cache) / "meta.json").read_text())
        cache = {p.stem: np.load(p) for p in Path(a.cache).glob("*.npy")}
    dt = {"1m": 60_000, "5m": 300_000}[meta["granularity"]]

    kept, slices, no_cov = [], [], 0
    for i, tr in enumerate(trades):
        if a.synthetic:
            s, cov = synth_slice(tr, dt, i, a.drift), 1.0
        else:
            s, cov = slice_real(cache.get(tr.symbol, np.zeros((0, 5))), tr, dt)
        if s is None or cov < COVERAGE_MIN:
            no_cov += 1
            continue
        kept.append(tr)
        slices.append(s)
    trades = kept
    n = len(trades)
    if n == 0:
        print("ERRORE: nessuna entrata con copertura candele sufficiente", file=sys.stderr)
        return 2
    ph = np.array([t.phase for t in trades])
    risk = np.array([t.risk_usd for t in trades])
    cl_id = np.array([t.t0 // (12 * HOUR_MS) for t in trades])
    side_arr = np.array([t.side for t in trades])

    # baseline, placebo (lato opposto), rimbalzo dopo lo stop
    base_res = [ls.run_exit_variant(c, t, 1.0, 1.0) for t, c in zip(trades, slices)]
    flip_res = [ls.run_exit_variant(c, t, 1.0, 1.0, flip=True) for t, c in zip(trades, slices)]
    base_R = np.array([r.net for r in base_res]) / risk
    flip_R = np.array([r.net for r in flip_res]) / risk
    rev = [ls.reversal_after_stop(c, t, r) for t, c, r in zip(trades, slices, base_res)]

    # gate di fedelta'
    sub = [i for i, t in enumerate(trades) if t.real_kind in ("SL", "TP") and t.parts == 1]
    agree = float(np.mean([base_res[i].kind == trades[i].real_kind for i in sub])) if sub else float("nan")
    sim_net = float(sum(base_res[i].net for i in sub))
    real_net = float(sum(trades[i].real_net for i in sub))
    scale_abs = float(sum(abs(trades[i].real_net) for i in sub)) or 1.0
    net_gap = abs(sim_net - real_net) / scale_abs
    gate_ok = bool(sub) and agree >= GATE_AGREE and net_gap <= GATE_NET and not a.synthetic
    conf = Counter((trades[i].real_kind, base_res[i].kind) for i in sub)

    # varianti
    variants = build_variants()
    rows, per = [], {}
    base_idx = next(i for i, (fam, nm, p) in enumerate(variants) if nm == "uscite SL x1.0 TP x1.0 [S]")
    for fam, name, p in variants:
        R = np.zeros(n)
        ex = np.ones(n, bool)
        kinds, nodata = [], 0
        for i, (t, c) in enumerate(zip(trades, slices)):
            r, val = run_variant(fam, p, c, t)
            if r.kind == "NODATA":
                nodata += 1
                ex[i] = False
                val = 0.0
            elif r.kind == "NOFILL":
                ex[i] = False
            R[i] = val
            kinds.append(r.kind)
        per[name] = (fam, R, ex, Counter(kinds), nodata)
    baseR = per["uscite SL x1.0 TP x1.0 [S]"][1]

    for fam, name, p in variants:
        _, R, ex, kinds, nodata = per[name]
        diff = R - baseR
        # famiglia 'rimbalzo' - DUE trappole, entrambe verificate con candele sintetiche SENZA vantaggio:
        #  (a) per segnale, un trade saltato vale 0 invece di -costi: "fare meno" sembra meglio;
        #  (b) sui soli segnali eseguiti, variante vs base sugli STESSI segnali: quelli in cui il prezzo ritraccia
        #      contro sono per costruzione quelli in cui l'entrata immediata parte male (~ -p R), quindi la
        #      variante vince di ~ +p R anche senza alcun vantaggio reale.
        # Il confronto che regge: R medio per trade ESEGUITO della variante contro R medio di TUTTI i segnali del base.
        if fam == "rimbalzo":
            lo, hi = boot_ratio_diff(R, ex, baseR, cl_id)
            delta = float(R[ex].mean() - baseR.mean()) if ex.any() else float("nan")
            phase_diff = {q: (float(R[ex & (ph == q)].mean() - baseR[ph == q].mean()) if (ex & (ph == q)).any()
                              else float("nan")) for q in PHASES}
        else:
            lo, hi = boot_diff(diff, cl_id, np.ones(n, bool))
            delta = float(diff.mean())
            phase_diff = {q: float(diff[ph == q].mean()) for q in PHASES}
        phase_mean = {q: float(R[ph == q].mean()) for q in PHASES}
        missed_base = float(baseR[~ex].mean()) if (fam == "rimbalzo" and (~ex).any()) else float("nan")
        te = R[ex]
        row = dict(
            famiglia=fam, variante=name, n_eseguite=int(ex.sum()), n_segnali=n,
            R_medio=float(R.mean()), diff_vs_base=delta, base_mancati=missed_base, ci_lo=lo, ci_hi=hi,
            golden=phase_mean["golden"], crisi=phase_mean["crisi"], dopo=phase_mean["dopo"],
            d_golden=phase_diff["golden"], d_crisi=phase_diff["crisi"], d_dopo=phase_diff["dopo"],
            win=float((te > 0).mean()) if len(te) else float("nan"),
            peggior_R=float(te.min()) if len(te) else float("nan"),
            maxDD_R=max_dd(R), top3=top3_share(R), usd=float((R * risk).sum()),
            sl=kinds.get("SL", 0), tp=kinds.get("TP", 0), tempo=kinds.get("TIME", 0), liq=kinds.get("LIQ", 0),
            nofill=kinds.get("NOFILL", 0), nodata=nodata)
        c1 = row["R_medio"] > 0
        c2 = (not np.isnan(lo)) and lo > 0
        c3 = sum(row[f"d_{q}"] > 0 for q in PHASES) >= 2
        c4 = (not np.isnan(row["top3"])) and row["top3"] < 0.5
        row["candidata"] = bool(c1 and c2 and c3 and c4 and name != "uscite SL x1.0 TP x1.0 [S]")
        rows.append(row)
    vdf = pd.DataFrame(rows)
    vdf.to_csv(out / "variants.csv", index=False)

    # dettaglio per trade (baseline e placebo)
    pd.DataFrame([dict(key=t.key, bot=t.bot, run=t.run_no, fase=t.phase, simbolo=t.symbol, lato=t.side,
                       reale_uscita=t.real_kind, reale_net=t.real_net, sim_uscita=b.kind, sim_net=b.net,
                       sim_R=b.net / t.risk_usd, flip_uscita=fl.kind, flip_R=fl.net / t.risk_usd, dopo_stop=rv,
                       mfe_R=b.mfe_r, mae_R=b.mae_r)
                  for t, b, fl, rv in zip(trades, base_res, flip_res, rev)]).to_csv(out / "per_trade_baseline.csv", index=False)

    # ------------------------------------------------------------- rapporto
    L = []
    L.append("# Laboratorio uscite/entrate classici (Claude) - RAPPORTO\n")
    if a.synthetic:
        L.append("> **ESECUZIONE SINTETICA: serve solo a verificare l'impianto. I numeri NON hanno alcun significato di mercato.**\n")
    L.append("Solo PAPER, solo offline, nessun dato di produzione toccato. Le entrate sono le "
             f"{n} REALI degli archivi dei classici; si simulano solo le uscite (e, nella famiglia 'rimbalzo', il momento d'ingresso).\n")
    L.append(f"- Candele: granularita' **{meta['granularity']}**, SHA256 dati `{meta['sha256']}`")
    L.append(f"- Entrate usate: **{n}** (escluse {skipped} senza dati d'ingresso, {no_cov} senza copertura candele >= {COVERAGE_MIN:.0%})")
    L.append(f"- Lato: **{int((side_arr == -1).sum())} SHORT, {int((side_arr == 1).sum())} LONG**. "
             "Con cosi' pochi LONG questo test NON dice nulla sui LONG.")
    L.append(f"- Scarto massimo tra distanza stop ricalcolata e `entry_r_dist` dell'archivio: {f(rdist_err * 100, 2)}%\n")

    L.append("## 1. Gate di fedelta' (fissato prima di vedere i risultati)\n")
    L.append(f"Sul sottoinsieme semplice (uscita reale SL o TP, nessuna chiusura parziale): n = {len(sub)}.\n")
    L.append(f"- Concordanza del tipo di uscita sim/reale: **{f(agree * 100, 1)}%** (soglia >= {GATE_AGREE:.0%})")
    L.append(f"- Differenza di P&L netto aggregato: **{f(net_gap * 100, 1)}%** della somma dei |net| reali (soglia <= {GATE_NET:.0%}); "
             f"sim {f(sim_net, 1)} USD vs reale {f(real_net, 1)} USD")
    L.append(f"- **Esito: {'PASSATO' if gate_ok else 'NON PASSATO'}**" +
             (" (esecuzione sintetica: non valutabile)" if a.synthetic else ""))
    if not gate_ok and not a.synthetic:
        L.append("  - Con gate non passato i risultati sotto sono **solo indicativi**: non bastano per decidere.")
    L.append("\nMatrice reale -> simulato (conteggi):\n")
    L.append("| reale \\ sim | " + " | ".join(["SL", "TP", "TIME", "LIQ"]) + " |")
    L.append("|---|---:|---:|---:|---:|")
    for rk in ("SL", "TP"):
        L.append(f"| {rk} | " + " | ".join(str(conf.get((rk, sk), 0)) for sk in ("SL", "TP", "TIME", "LIQ")) + " |")

    L.append("\n## 2. Le entrate hanno un vantaggio direzionale? (placebo: stesse entrate, lato opposto)\n")
    L.append("| fase | n | R medio reale-lato | R medio lato-opposto | quota TP lato reale | quota TP lato opposto |")
    L.append("|---|---:|---:|---:|---:|---:|")
    for q in PHASES + ["tutte"]:
        m = np.ones(n, bool) if q == "tutte" else ph == q
        idx = np.where(m)[0]
        if not len(idx):
            continue
        tpb = np.mean([base_res[i].kind == "TP" for i in idx])
        tpf = np.mean([flip_res[i].kind == "TP" for i in idx])
        L.append(f"| {q} | {len(idx)} | {f(base_R[m].mean())} | {f(flip_R[m].mean())} | {f(tpb * 100, 1)}% | {f(tpf * 100, 1)}% |")
    L.append("\nSe il lato opposto rende quanto (o piu') del lato reale in una fase, in quella fase le entrate non "
             "mostravano vantaggio direzionale e nessuna regola di uscita puo' crearlo.\n")

    L.append("## 3. Dopo uno stop dell'originale, il prezzo andava dove previsto? (la tua tesi)\n")
    L.append("Per ogni stop della variante base: nelle 6 ore successive il prezzo tocca prima il TP originale "
             "('TP_first': uno stop piu' largo avrebbe salvato il trade) o prima uno stop a 2x ('STOP2_first': "
             "avrebbe perso di piu')?\n")
    L.append("| fase | stop base | TP_first | STOP2_first | neither |")
    L.append("|---|---:|---:|---:|---:|")
    for q in PHASES + ["tutte"]:
        idx = [i for i in range(n) if (q == "tutte" or ph[i] == q) and base_res[i].kind == "SL"]
        cnt = Counter(rev[i] for i in idx)
        L.append(f"| {q} | {len(idx)} | {cnt.get('TP_first', 0)} | {cnt.get('STOP2_first', 0)} | {cnt.get('neither', 0)} |")
    L.append("")

    L.append("## 4. Confronto varianti (tutte sulle stesse entrate, costi inclusi)\n")
    L.append("R = guadagno in multipli della perdita pianificata allo stop (1R). `[S]` = stesso nozionale dell'originale "
             "(il rischio cresce con lo stop largo); `[R]` = nozionale ridotto in modo che la perdita allo stop resti 1R. "
             "R medio e' PER SEGNALE (le entrate non eseguite contano 0). Delta = differenza dal base, con intervallo al 95% "
             "(bootstrap a blocchi di 12 ore, approssimato e probabilmente ottimista). Per 'rimbalzo' il delta e' "
             "R medio per trade ESEGUITO della variante meno R medio di TUTTI i segnali del base (il confronto sugli stessi "
             "segnali sarebbe distorto: dove il prezzo ritraccia contro, l'entrata immediata parte male per costruzione, "
             "circa -p R, anche senza alcun vantaggio reale); 'base su mancati' e' il risultato medio che la base avrebbe "
             "avuto sui segnali saltati. Le varianti [R] "
             "con stop largo riducono il nozionale e quindi il peso dei costi per 1R: un delta positivo con R medio negativo "
             "NON e' un vantaggio, e' solo trading piu' piccolo in un contesto in perdita.\n")
    for fam, title in (("exit", "Solo uscite"), ("scala", "Due gambe (stop largo fissato all'inizio)"),
                       ("rimbalzo", "Entrata su ritracciamento/rimbalzo")):
        L.append(f"### {title}\n")
        extra = fam == "rimbalzo"
        L.append("| variante | eseguite | R medio | delta [IC95] | golden | crisi | dopo | win% | peggior R | maxDD R | USD |"
                 + (" base su mancati |" if extra else "") + " cand. |")
        L.append("|---|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|" + ("---:|" if extra else "") + ":--:|")
        for r in sorted([x for x in rows if x["famiglia"] == fam], key=lambda x: -x["R_medio"]):
            L.append(f"| {r['variante']} | {r['n_eseguite']} | {f(r['R_medio'])} | {f(r['diff_vs_base'])} [{f(r['ci_lo'])}, {f(r['ci_hi'])}] "
                     f"| {f(r['golden'])} | {f(r['crisi'])} | {f(r['dopo'])} | {f(r['win'] * 100, 0)}% | {f(r['peggior_R'], 2)} "
                     f"| {f(r['maxDD_R'], 1)} | {f(r['usd'], 0)} |" + (f" {f(r['base_mancati'])} |" if extra else "")
                     + f" {'SI' if r['candidata'] else ''} |")
        L.append("")

    cand = [r for r in rows if r["candidata"]]
    L.append("## 5. Candidate secondo la regola fissata in anticipo\n")
    L.append("Una variante e' candidata solo se: (1) R medio per segnale > 0 dopo costi; (2) estremo inferiore dell'IC95 del "
             "delta vs base > 0 (per 'rimbalzo': per trade eseguito contro tutti i segnali del base); (3) delta > 0 in almeno 2 fasi su 3; "
             "(4) i 3 migliori trade pesano < 50% dei guadagni.\n")
    if cand:
        for r in cand:
            L.append(f"- **{r['variante']}**: R medio {f(r['R_medio'])}, delta {f(r['diff_vs_base'])} [{f(r['ci_lo'])}, {f(r['ci_hi'])}]")
        L.append(f"\nAttenzione: sono state provate {len(variants)} varianti; per puro caso, a livello 95%, se ne aspettano "
                 f"~{len(variants) * 0.05:.0f} che sembrano buone. Una candidata va riconfermata su dati nuovi prima di qualsiasi uso.")
    else:
        L.append("Nessuna variante soddisfa la regola.")
    L.append("\n## 6. Limiti\n")
    L.append("- Solo entrate SHORT in pratica; periodo 12-26/10 e mercato specifico; campione piccolo e correlato tra simboli.")
    L.append("- Le uscite reali includevano chiusure decise da AI/regole, parziali e talvolta seconde gambe: qui sono sostituite da "
             "SL/TP/tempo (24h). Il gate di fedelta' misura quanto questo e' accettabile.")
    L.append("- Nella stessa candela: liquidazione > stop > TP (caso peggiore). Stop a gap eseguito all'apertura.")
    L.append("- Seconda gamba: TP ricalcolato sul prezzo medio, TTL 3h (Hawk) / 12h (Bull) come il motore; ipotesi non verificabile sui dati.")
    L.append("- Nessun effetto di mercato delle proprie operazioni, nessun limite di slot o di cassa tra posizioni contemporanee.")
    (out / "report.md").write_text("\n".join(L) + "\n")
    (out / "summary.json").write_text(json.dumps(dict(
        n=n, skipped=skipped, no_cov=no_cov, granularity=meta["granularity"], sha256=meta["sha256"],
        gate=dict(n=len(sub), agree=agree, net_gap=net_gap, passed=gate_ok), candidates=[r["variante"] for r in cand]),
        indent=1, default=float))
    print("\n".join(L[:30]))
    print(f"\n[ok] rapporto in {out / 'report.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
