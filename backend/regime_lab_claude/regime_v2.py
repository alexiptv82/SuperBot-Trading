"""Lettore di regime v2 (Claude, 30/10/2026) - PROPOSTA NON VALIDATA, non collegata a nessun bot.

Idea: separare tre cose che il regime attuale mescola.
  1. DIREZIONE (contesto K sul movimento ampio, presente D sul movimento in corso, svolta dD);
  2. QUALITA' del movimento (ER: rettilineo = 1, a scatti = 0): uno short in un ribasso a scatti non e' uno short in un ribasso pulito;
  3. VOLATILITA' anomala (VR): in SHOCK nessuna direzione e' affidabile.
Nessuno stato e' un veto: il modulo produce informazioni (stato, classe per lato) che il decisore usa come vuole.

Proprieta' garantite dai test (tests/test_regime_v2.py):
  - SPECCHIO ESATTO: invertire il segno del prezzo scambia SU/GIU' e LONG/SHORT, nulla d'altro (le feature direzionali sono dispari,
    ER e VR pari). Il trattamento dei due lati e' simmetrico per costruzione.
  - CAUSALITA': una barra futura non cambia nessun valore gia' calcolato; si usano solo barre complete e chiuse.
  - MEMORIA FINITA: batch (laboratorio) e vivo (ultime N barre) danno lo stesso stato; niente stato nascosto da persistere.
  - DATI MANCANTI: buchi nelle barre azzerano l'avviamento; qualunque componente mancante -> stato NA, mai un valore inventato.

Solo numpy. I valori sono ipotesi iniziali NON ottimizzate (vedi PREREGISTRAZIONE.md)."""
from __future__ import annotations

import hashlib
import json
import warnings
from dataclasses import asdict, dataclass

import numpy as np

SCHEMA_VERSION = "2.0"
TF_MS = {"1m": 60_000, "5m": 300_000, "15m": 900_000, "1h": 3_600_000, "4h": 14_400_000}

# ---- stati (codici interi) ----------------------------------------------------------------------------------------
(NA, SHOCK, DOWN_CLEAN, DOWN_CHOP, TURNING_UP, RANGE, TURNING_DOWN, UP_CHOP, UP_CLEAN,
 EMERGING_DOWN, EMERGING_UP) = range(11)
STATE_NAMES = ["NA", "SHOCK", "DOWN_CLEAN", "DOWN_CHOP", "TURNING_UP", "RANGE", "TURNING_DOWN", "UP_CHOP", "UP_CLEAN",
               "EMERGING_DOWN", "EMERGING_UP"]
# specchio: SU <-> GIU' (RANGE, SHOCK, NA restano se stessi)
MIRROR = np.array([NA, SHOCK, UP_CLEAN, UP_CHOP, TURNING_DOWN, RANGE, TURNING_UP, DOWN_CHOP, DOWN_CLEAN,
                   EMERGING_UP, EMERGING_DOWN], dtype=np.int8)

ALIGNED, NEUTRAL, OPPOSED = 1, 0, -1
CLASS_NAMES = {ALIGNED: "ALIGNED", NEUTRAL: "NEUTRAL", OPPOSED: "OPPOSED"}
LONG, SHORT = 1, -1
# classi per il lato SHORT; per il LONG si usa lo specchio dello stato (side_class)
_SHORT_ALIGNED = {DOWN_CLEAN, EMERGING_DOWN}
_SHORT_OPPOSED = {UP_CLEAN, UP_CHOP, EMERGING_UP, TURNING_UP}

# direzione grezza per il confronto con un'EMA: -1 se lo stato e' di discesa o svolta al ribasso, +1 salita/svolta al rialzo
DIR_OF_STATE = np.zeros(11, dtype=np.int8)
for _s in (DOWN_CLEAN, DOWN_CHOP, TURNING_DOWN, EMERGING_DOWN):
    DIR_OF_STATE[_s] = -1
for _s in (UP_CLEAN, UP_CHOP, TURNING_UP, EMERGING_UP):
    DIR_OF_STATE[_s] = 1


@dataclass(frozen=True)
class Profile:
    """Quali timeframe e quanto pesano. `validated` resta False finche' un laboratorio con i dati giusti e l'utente non lo dicono."""
    name: str
    base_tf: str
    d_weights: tuple          # ((tf, peso), ...) il presente
    k_weights: tuple          # il movimento ampio
    er_tf: str                # timeframe su cui si misura la qualita' del movimento
    vr_w: int                 # barre base per la media di riferimento della volatilita'
    dd_lag: int               # barre base per la variazione di D
    validated: bool = False


CLASSIC15 = Profile("classic15", "15m", (("15m", 0.60), ("1h", 0.40)), (("4h", 1.0),), "1h", vr_w=288, dd_lag=4)
SCALP1M = Profile("scalp1m", "1m", (("1m", 0.65), ("5m", 0.35)),
                  (("15m", 0.50), ("1h", 0.30), ("4h", 0.20)), "5m", vr_w=1440, dd_lag=3)


@dataclass(frozen=True)
class Params:
    atr_n: int = 14
    m_n: int = 3
    m_k: float = 2.0
    sw_n: int = 6
    q_n: int = 3
    er_n: int = 24
    w_m: float = 0.35
    w_b: float = 0.20
    w_s: float = 0.15
    w_q: float = 0.10
    w_x: float = 0.20
    k_thr: float = 0.25
    d_thr: float = 0.20
    dd_thr: float = 0.30
    er_thr: float = 0.30
    emerge_d: float = 0.35
    vr_shock: float = 2.5
    lookback_cap: int = 96     # oltre queste barre di instabilita' continua lo stato e' RANGE
    confirm_n: int = 2         # chiusure consecutive uguali per cambiare stato (v2.0: 2)
    warmup: int = 32           # barre consecutive minime per timeframe
    eps: float = 1e-12


def config_hash(profile: Profile, p: Params) -> str:
    d = asdict(p)
    if d.get("confirm_n") == 2:
        del d["confirm_n"]            # compatibilita': l'hash della v2.0 (prima che il campo esistesse) non cambia
    return hashlib.sha256(json.dumps([asdict(profile), d], sort_keys=True).encode()).hexdigest()[:12]


# ---- aggregazione -------------------------------------------------------------------------------------------------
def aggregate(ts, o, h, l, c, v, base_ms: int, tf_ms: int) -> dict:
    """Barre base (aperture `ts` crescenti, uniche) -> barre `tf_ms` COMPLETE: tutte le barre base presenti e contigue."""
    ts = np.asarray(ts, dtype=np.int64)
    close_base = ts + base_ms
    if tf_ms == base_ms:
        return dict(ts=ts, close_ms=close_base, o=np.asarray(o, float), h=np.asarray(h, float),
                    l=np.asarray(l, float), c=np.asarray(c, float), v=np.asarray(v, float))
    ratio = tf_ms // base_ms
    if tf_ms % base_ms or len(ts) == 0:
        return dict(ts=ts[:0], close_ms=ts[:0], o=np.empty(0), h=np.empty(0), l=np.empty(0), c=np.empty(0), v=np.empty(0))
    b = ts // tf_ms
    start = np.flatnonzero(np.r_[True, b[1:] != b[:-1]])
    end = np.r_[start[1:], len(ts)]
    ok = ((end - start) == ratio) & ((ts[end - 1] - ts[start]) == (ratio - 1) * base_ms)
    o_, h_, l_, c_, v_ = (np.asarray(x, float) for x in (o, h, l, c, v))
    t_open = b[start] * tf_ms
    return dict(ts=t_open[ok], close_ms=t_open[ok] + tf_ms, o=o_[start][ok], h=np.maximum.reduceat(h_, start)[ok],
                l=np.minimum.reduceat(l_, start)[ok], c=c_[end - 1][ok], v=np.add.reduceat(v_, start)[ok])


# ---- feature per timeframe ----------------------------------------------------------------------------------------
def _roll_sum(x, n):
    out = np.full(len(x), np.nan)
    if len(x) >= n:
        cs = np.cumsum(np.concatenate(([0.0], x)))
        out[n - 1:] = cs[n:] - cs[:-n]
    return out


def _shift(x, k):
    """x[t-k] (NaN davanti)."""
    out = np.full(len(x), np.nan)
    if k < len(x):
        out[k:] = x[:len(x) - k]
    return out


def _roll_ext(x, n, fn):
    """fn(x[i..i+n-1]) assegnato a i+n-1 (finestra che termina in t, comprende t)."""
    out = np.full(len(x), np.nan)
    if len(x) >= n:
        w = np.lib.stride_tricks.sliding_window_view(x, n)
        out[n - 1:] = fn(w, axis=1)
    return out


def true_range(h, l, c):
    pc = np.concatenate(([c[0]], c[:-1]))
    return np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))


def _gap_mask(ts, tf_ms, need):
    """True dove le ultime `need` barre sono contigue (un buco azzera l'avviamento)."""
    n = len(ts)
    if n == 0:
        return np.zeros(0, bool)
    gap = np.r_[True, np.diff(ts) != tf_ms]
    last = np.maximum.accumulate(np.where(gap, np.arange(n), -1))
    return (np.arange(n) - last) >= need


def features(o, h, l, c, ts, tf_ms, p: Params) -> dict:
    """Feature su barre chiuse e contigue di un timeframe. NaN dove l'avviamento non basta. Direzionali dispari, ER pari."""
    o, h, l, c = (np.asarray(x, float) for x in (o, h, l, c))
    n = len(c)
    nan = np.full(n, np.nan)
    if n == 0:
        return dict(F=nan, ER=nan, A=nan)
    tr = true_range(h, l, c)
    A = _roll_sum(tr, p.atr_n) / p.atr_n
    den = np.maximum(A, p.eps)
    M = np.clip((c - _shift(c, p.m_n)) / (p.m_k * den), -1, 1)
    rng = h - l
    B = _roll_sum(c - o, 3) / np.maximum(_roll_sum(rng, 3), p.eps)
    hi_prev = _shift(_roll_ext(h, p.sw_n, np.max), 1)      # massimo delle sw_n barre PRECEDENTI (esclusa la corrente)
    lo_prev = _shift(_roll_ext(l, p.sw_n, np.min), 1)
    with np.errstate(invalid="ignore"):
        S = np.where(c > hi_prev, 1.0, np.where(c < lo_prev, -1.0, 0.0))
    S = np.where(np.isnan(hi_prev) | np.isnan(lo_prev), np.nan, S)
    q_i = np.where(rng > 0, (2 * c - h - l) / np.where(rng > 0, rng, 1.0), 0.0)
    Q = _roll_sum(q_i, p.q_n) / p.q_n
    w = p.sw_n                                           # struttura: finestra recente [t-w+1..t] contro precedente [t-2w+1..t-w]
    minl_r = _roll_ext(l, w, np.min)
    maxh_r = _roll_ext(h, w, np.max)
    minl_p, maxh_p = _shift(minl_r, w), _shift(maxh_r, w)
    SU = np.clip((minl_r - minl_p) / (2 * den), -1, 1)   # minimi che salgono = rialzista
    SD = np.clip((maxh_p - maxh_r) / (2 * den), -1, 1)   # massimi che scendono = ribassista
    X = np.clip((SU - SD) / 2, -1, 1)
    F = p.w_m * M + p.w_b * B + p.w_s * S + p.w_q * Q + p.w_x * X
    # qualita' del movimento
    dc = np.abs(np.diff(c, prepend=c[0]))
    path = _roll_sum(dc, p.er_n)
    net = np.abs(c - _shift(c, p.er_n))
    ER = np.where(path > 0, net / np.where(path > 0, path, 1.0), 0.0)
    ER = np.where(np.isnan(net) | np.isnan(path), np.nan, ER)
    valid = _gap_mask(ts, tf_ms, p.warmup)
    F = np.where(valid, F, np.nan)
    ER = np.where(valid, ER, np.nan)
    A = np.where(valid, A, np.nan)
    return dict(F=F, ER=ER, A=A)


def _on_base(close_base, agg, arr, tf_ms):
    """Valore dell'ultima barra `tf` chiusa a ciascuna chiusura base, NaN se mancante o scaduta (piu' vecchia di un periodo)."""
    n = len(close_base)
    if len(agg["close_ms"]) == 0:
        return np.full(n, np.nan)
    j = np.searchsorted(agg["close_ms"], close_base, side="right") - 1
    out = np.where(j >= 0, arr[np.clip(j, 0, None)], np.nan)
    age = close_base - agg["close_ms"][np.clip(j, 0, None)]
    return np.where((j >= 0) & (age < tf_ms), out, np.nan)


def volatility_ratio(ts, h, l, c, base_ms, p: Params, vr_w: int):
    """A_base / media di A_base sulle `vr_w` barre PRECEDENTI (conteggio completo richiesto)."""
    n = len(c)
    tr = true_range(np.asarray(h, float), np.asarray(l, float), np.asarray(c, float))
    A = _roll_sum(tr, p.atr_n) / p.atr_n
    A = np.where(_gap_mask(ts, base_ms, p.warmup), A, np.nan)
    ok = ~np.isnan(A)
    cs = np.cumsum(np.concatenate(([0.0], np.where(ok, A, 0.0))))
    cc = np.cumsum(np.concatenate(([0], ok.astype(int))))
    vr = np.full(n, np.nan)
    if n > vr_w:
        t = np.arange(vr_w, n)                                   # finestra [t-vr_w .. t-1]
        s = cs[t] - cs[t - vr_w]
        cnt = cc[t] - cc[t - vr_w]
        mean_prev = s / vr_w
        good = (cnt == vr_w) & ok[t]
        vr[t] = np.where(good, A[t] / np.maximum(mean_prev, p.eps), np.nan)      # prezzo piatto: 0/eps = 0 (calmo), mai NaN
    return vr


# ---- stati --------------------------------------------------------------------------------------------------------
def classify(K, D, dD, ER, VR, p: Params):
    """Stato grezzo per barra. Qualunque componente mancante -> NA."""
    K, D, dD, ER, VR = (np.asarray(x, float) for x in (K, D, dD, ER, VR))
    n = len(K)
    ok = ~(np.isnan(K) | np.isnan(D) | np.isnan(dD) | np.isnan(ER) | np.isnan(VR))
    r = np.full(n, RANGE, dtype=np.int8)
    with np.errstate(invalid="ignore"):
        kd = np.where(K <= -p.k_thr, -1, np.where(K >= p.k_thr, 1, 0))
        clean = ER >= p.er_thr
        m = kd == -1
        t_up = (D >= p.d_thr) | (dD >= p.dd_thr)
        r[m & t_up] = TURNING_UP
        r[m & ~t_up & clean] = DOWN_CLEAN
        r[m & ~t_up & ~clean] = DOWN_CHOP
        m = kd == 1
        t_dn = (D <= -p.d_thr) | (dD <= -p.dd_thr)
        r[m & t_dn] = TURNING_DOWN
        r[m & ~t_dn & clean] = UP_CLEAN
        r[m & ~t_dn & ~clean] = UP_CHOP
        m = kd == 0
        em = clean & (np.abs(D) >= p.emerge_d)
        r[m & em & (D > 0)] = EMERGING_UP
        r[m & em & (D < 0)] = EMERGING_DOWN
        r[VR >= p.vr_shock] = SHOCK
    r[~ok] = NA
    return r


def confirm(raw, p: Params):
    """Isteresi SENZA STATO: lo stato e' l'ultimo valore grezzo comparso su `confirm_n` chiusure consecutive, SENZA attraversare dati
    mancanti. SHOCK e NA valgono subito (nessuna attesa, nessun ponte sopra un buco). Dipende solo dalle ultime `lookback_cap`
    barre: batch e vivo coincidono."""
    raw = np.asarray(raw, dtype=np.int8)
    n = len(raw)
    if n == 0:
        return raw.copy()
    idx = np.arange(n)
    chg = np.r_[True, raw[1:] != raw[:-1]]
    run_start = np.maximum.accumulate(np.where(chg, idx, 0))
    eq = (idx - run_start + 1) >= p.confirm_n                                        # serie uguale lunga almeno confirm_n
    last = np.maximum.accumulate(np.where(eq, idx, -1))
    na_at = np.maximum.accumulate(np.where(raw == NA, idx, -1))
    state = raw[np.clip(last, 0, None)].astype(np.int8)
    state = np.where((last < 0) | (last <= na_at), NA, state).astype(np.int8)       # nessuna serie dopo l'ultimo NA
    state = np.where((state != NA) & ((idx - last) > p.lookback_cap), RANGE, state).astype(np.int8)
    state = np.where(raw == SHOCK, SHOCK, state).astype(np.int8)
    state = np.where(raw == NA, NA, state).astype(np.int8)
    return state


def side_class(state, side: int):
    """ALIGNED / NEUTRAL / OPPOSED di uno stato per un lato (LONG=+1, SHORT=-1). Specchio per costruzione."""
    s = np.asarray(state)
    if side == LONG:
        s = MIRROR[s]                  # il LONG e' lo SHORT dello stato specchiato
    out = np.zeros(s.shape, dtype=np.int8)
    out[np.isin(s, list(_SHORT_ALIGNED))] = ALIGNED
    out[np.isin(s, list(_SHORT_OPPOSED))] = OPPOSED
    return out


def combine_classes(a, b):
    """Combinata: ALIGNED solo se entrambe ALIGNED; OPPOSED se almeno una OPPOSED; altrimenti NEUTRAL."""
    a, b = np.asarray(a), np.asarray(b)
    out = np.zeros(a.shape, dtype=np.int8)
    out[(a == ALIGNED) & (b == ALIGNED)] = ALIGNED
    out[(a == OPPOSED) | (b == OPPOSED)] = OPPOSED
    return out


# ---- serie per simbolo e mercato -----------------------------------------------------------------------------------
def compute_series(base: dict, profile: Profile = CLASSIC15, p: Params = Params()) -> dict:
    """`base`: ts (apertura, ms), o, h, l, c, v delle barre base CHIUSE. Ritorna le serie sulla griglia delle barre base."""
    base_ms = TF_MS[profile.base_tf]
    ts = np.asarray(base["ts"], dtype=np.int64)
    n = len(ts)
    close_base = ts + base_ms
    if n == 0:
        e = np.empty(0)
        return dict(ts=ts, close_ms=close_base, D=e, K=e, dD=e, ER=e, VR=e, raw=np.empty(0, np.int8),
                    state=np.empty(0, np.int8), F={})
    need_tfs = {tf for tf, _ in profile.d_weights} | {tf for tf, _ in profile.k_weights} | {profile.er_tf}
    onb, aggs = {}, {}
    for tf in need_tfs:
        agg = aggregate(ts, base["o"], base["h"], base["l"], base["c"], base["v"], base_ms, TF_MS[tf])
        aggs[tf] = agg
        f = features(agg["o"], agg["h"], agg["l"], agg["c"], agg["ts"], TF_MS[tf], p)
        onb[tf] = (_on_base(close_base, agg, f["F"], TF_MS[tf]), _on_base(close_base, agg, f["ER"], TF_MS[tf]))
    D = sum(w * onb[tf][0] for tf, w in profile.d_weights) if n else np.empty(0)
    K = sum(w * onb[tf][0] for tf, w in profile.k_weights) if n else np.empty(0)
    ER = onb[profile.er_tf][1] if n else np.empty(0)
    dD = D - _shift(D, profile.dd_lag)
    VR = volatility_ratio(ts, base["h"], base["l"], base["c"], base_ms, p, profile.vr_w)
    raw = classify(K, D, dD, ER, VR, p)
    return dict(ts=ts, close_ms=close_base, D=D, K=K, dD=dD, ER=ER, VR=VR, raw=raw, state=confirm(raw, p),
                F={tf: onb[tf][0] for tf in need_tfs})


def market_series(results: dict, master_close_ms, profile: Profile = CLASSIC15, p: Params = Params(),
                  exclude=("XAU", "XAG"), min_symbols: int = 5, breadth_thr: float = 0.15) -> dict:
    """Stessa macchina sulle MEDIANE di K, D, ER, VR dei simboli (cripto: esclusi oro e argento) sulla griglia master.
    Ritorna anche l'ampiezza (quota di simboli con D sotto/sopra la soglia): informativa, non entra negli stati."""
    master = np.asarray(master_close_ms, dtype=np.int64)
    names = [s for s in results if s not in exclude]
    n = len(master)
    mats = {k: np.full((len(names), n), np.nan) for k in ("K", "D", "ER", "VR")}
    for i, s in enumerate(names):
        r = results[s]
        pos = np.searchsorted(master, r["close_ms"])
        hit = (pos < n) & (master[np.clip(pos, 0, n - 1)] == r["close_ms"])
        for k in mats:
            mats[k][i, pos[hit]] = r[k][hit]
    with np.errstate(all="ignore"), warnings.catch_warnings():
        warnings.simplefilter("ignore")
        cnt = np.sum(~np.isnan(mats["D"]), axis=0)
        med = {k: np.where(cnt >= min_symbols, np.nanmedian(mats[k], axis=0), np.nan) for k in mats}
        dn = np.where(cnt >= min_symbols, np.nansum(mats["D"] < -breadth_thr, axis=0) / np.maximum(cnt, 1), np.nan)
        up = np.where(cnt >= min_symbols, np.nansum(mats["D"] > breadth_thr, axis=0) / np.maximum(cnt, 1), np.nan)
    dD = med["D"] - _shift(med["D"], profile.dd_lag)
    raw = classify(med["K"], med["D"], dD, med["ER"], med["VR"], p)
    return dict(close_ms=master, D=med["D"], K=med["K"], dD=dD, ER=med["ER"], VR=med["VR"], raw=raw,
                state=confirm(raw, p), breadth_dn=dn, breadth_up=up, n_symbols=cnt)


# ---- uso vivo ------------------------------------------------------------------------------------------------------
def _evidence(state, D, K, ER, dD, VR, p: Params):
    ev = []
    if not np.isnan(K):
        ev.append("CONTEXT_DOWN" if K <= -p.k_thr else "CONTEXT_UP" if K >= p.k_thr else "CONTEXT_FLAT")
    if not np.isnan(D):
        ev.append("FAST_DOWN" if D <= -p.d_thr else "FAST_UP" if D >= p.d_thr else "FAST_FLAT")
    if not np.isnan(ER):
        ev.append("CLEAN_MOVE" if ER >= p.er_thr else "CHOPPY_MOVE")
    if not np.isnan(dD) and abs(dD) >= p.dd_thr:
        ev.append("MOMENTUM_SHIFT_UP" if dD > 0 else "MOMENTUM_SHIFT_DOWN")
    if not np.isnan(VR) and VR >= p.vr_shock:
        ev.append("VOL_SHOCK")
    return ev


def snapshot(series: dict, profile: Profile = CLASSIC15, p: Params = Params(), symbol: str = "", market: dict | None = None,
             i: int = -1) -> dict:
    """Contratto dati per il decisore. Nessuna probabilita': `quality` misura la disponibilita' dei dati, non il successo."""
    st = int(series["state"][i])
    degraded = st == NA
    cls = {"LONG": int(side_class(st, LONG)), "SHORT": int(side_class(st, SHORT))}
    f = lambda x: None if np.isnan(x) else round(float(x), 4)   # noqa: E731
    D, K, ER, dD, VR = (series[k][i] for k in ("D", "K", "ER", "dD", "VR"))
    out = {"schema_version": SCHEMA_VERSION, "symbol": symbol, "as_of_close_ms": int(series["close_ms"][i]),
           "profile": profile.name, "profile_validated": profile.validated,
           "quality": "degraded" if degraded else "ok", "state": STATE_NAMES[st],
           "direction_score": f(D), "context_score": f(K), "delta": f(dD), "efficiency": f(ER), "vol_ratio": f(VR),
           "preferred_side": "NONE" if (np.isnan(D) or abs(D) <= 0.15) else ("LONG" if D > 0 else "SHORT"),
           "side_class": {k: CLASS_NAMES[v] for k, v in cls.items()},
           "evidence": _evidence(st, D, K, ER, dD, VR, p), "fallback_reason": "warmup_or_gap" if degraded else None,
           "config_hash": config_hash(profile, p)}
    if market is not None:
        mst = int(market["state"][i])
        out["market"] = {"state": STATE_NAMES[mst], "context_score": f(market["K"][i]), "direction_score": f(market["D"][i]),
                         "breadth_down": f(market["breadth_dn"][i]), "breadth_up": f(market["breadth_up"][i]),
                         "side_class": {"LONG": CLASS_NAMES[int(side_class(mst, LONG))],
                                        "SHORT": CLASS_NAMES[int(side_class(mst, SHORT))]}}
    return out


def degraded_snapshot(symbol: str, reason: str, profile: Profile = CLASSIC15, p: Params = Params()) -> dict:
    """Risposta di sicurezza: nessuna preferenza, nessun veto, il percorso precedente decide."""
    return {"schema_version": SCHEMA_VERSION, "symbol": symbol, "as_of_close_ms": None, "profile": profile.name,
            "profile_validated": profile.validated, "quality": "degraded", "state": "NA", "direction_score": None,
            "context_score": None, "delta": None, "efficiency": None, "vol_ratio": None, "preferred_side": "NONE",
            "side_class": {"LONG": "NEUTRAL", "SHORT": "NEUTRAL"}, "evidence": [], "fallback_reason": reason,
            "config_hash": config_hash(profile, p)}


def read_regime(candles: dict, symbol: str, now_ms: int, profile: Profile = CLASSIC15, p: Params = Params(),
                max_age_bars: int = 2) -> dict:
    """Uso vivo: `candles` = ts, o, h, l, c, v delle barre base (servono >= 1000 barre 15m, o 1m per scalp1m). Non solleva mai:
    qualunque errore o dato vecchio -> snapshot degradato neutro. Scarta le barre non ancora chiuse a `now_ms`."""
    try:
        base_ms = TF_MS[profile.base_tf]
        ts = np.asarray(candles["ts"], dtype=np.int64)
        keep = ts + base_ms <= now_ms
        if keep.sum() < profile.vr_w + 3 * p.warmup:
            return degraded_snapshot(symbol, "insufficient_bars", profile, p)
        base = {k: np.asarray(candles[k], float)[keep] for k in ("o", "h", "l", "c", "v")}
        base["ts"] = ts[keep]
        if now_ms - (base["ts"][-1] + base_ms) > max_age_bars * base_ms:
            return degraded_snapshot(symbol, "stale_data", profile, p)
        return snapshot(compute_series(base, profile, p), profile, p, symbol)
    except Exception as e:      # noqa: BLE001 - il lettore non deve mai fermare il bot
        return degraded_snapshot(symbol, f"exception:{type(e).__name__}", profile, p)


PROMPT_INSTRUCTION = (
    "Il regime e' informazione di contesto, non un permesso ne' un divieto. Leggi insieme: contesto ampio (context_score), "
    "movimento in corso (direction_score), qualita' del movimento (efficiency: alta = rettilineo, bassa = a scatti) e volatilita' "
    "(vol_ratio). Un candidato nel verso del regime con movimento pulito ha piu' evidenza di uno in regime a scatti, in svolta o in "
    "SHOCK; un candidato contro un movimento pulito richiede evidenze specifiche e recenti, che devi esplicitare. Non chiedere "
    "concordanza fra tutti i timeframe. Valuta i candidati idonei di entrambe le direzioni; non creare un trade per rispettare una "
    "quota LONG/SHORT; non trasformare RANGE, SHOCK o quality=degraded in un divieto generale. Se profile_validated=false trattalo "
    "come ipotesi non verificata. Conserva tutti i controlli di rischio. Motiva NO_TRADE con il controllo o l'assenza di setup effettivi.")
