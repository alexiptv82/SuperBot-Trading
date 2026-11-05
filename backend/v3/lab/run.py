"""Offline runner. Only read_candles_csv and main perform I/O."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from collections.abc import Sequence
from decimal import Context, Decimal, ROUND_HALF_EVEN, localcontext
from pathlib import Path

from backend.v3.features.indicators import Bar, check_bars
from backend.v3.features.regime import regime_labels
from backend.v3.learning.opportunity import Candle
from backend.v3.detectors.breakout import detect_donchian_breakout
from backend.v3.detectors.reversal import detect_bollinger_macd_reversal
from backend.v3.detectors.trend import detect_ema_cross_adx
from backend.v3.lab.protocol import load_protocol
from backend.v3.lab.controls import shifted_candidate_sets
from backend.v3.lab.evaluate import evaluate_candidates, evaluation_window, evaluation_folds

_CTX = Context(prec=60, rounding=ROUND_HALF_EVEN)
_MS_PER_DAY = 86_400_000
_LIMITS = "ingresso al `close` della barra di segnale, non all'apertura successiva (lo scarto è misurato); nessun funding né slippage separati (il 20 bp li sovrasta); candidati etichettati indipendentemente, non un portafoglio (trade sovrapposti; bootstrap a blocchi di giorni; il drawdown in R è una somma in ordine di chiusura); granularità 15 minuti (tocchi ambigui non risolvibili: si riporta la quota e il limite `target_first`); confronti multipli (6 coppie, confidenza 0,99 approssimata); periodo breve (~540 giorni); la deriva è misurata dal controllo a scorrimento, non eliminata; parametri da manuale, non scelti sui dati, ma i 540 giorni sono stati usati da altri laboratori; solo PAPER."


def split_contiguous(bars, candle_ms):
    if type(candle_ms) is not int or candle_ms < 1 or not isinstance(bars, Sequence):
        raise ValueError('invalid_bars')
    segments = []
    previous = None
    for b in bars:
        if not isinstance(b, Bar) or type(b.open_time_ms) is not int or b.open_time_ms < 0 or b.open_time_ms % candle_ms:
            raise ValueError('invalid_bars')
        if previous is not None and b.open_time_ms <= previous:
            raise ValueError('invalid_bars')
        if previous is None or b.open_time_ms != previous + candle_ms:
            segments.append([])
        segments[-1].append(b)
        previous = b.open_time_ms
    for segment in segments:
        check_bars(segment, candle_ms=candle_ms)
    return segments


def read_candles_csv(path):
    try:
        with Path(path).open(encoding='utf-8', newline='') as f:
            reader = csv.reader(f)
            if next(reader, None) != ['open_time_ms', 'open', 'high', 'low', 'close', 'volume']:
                raise ValueError('invalid_candles_file')
            bars = []
            previous = None
            for row in reader:
                if len(row) != 6 or re.fullmatch(r'\d+', row[0]) is None:
                    raise ValueError('invalid_candles_file')
                t = int(row[0])
                values = [Decimal(s) for s in row[1:]]
                if not all(v.is_finite() for v in values):
                    raise ValueError('invalid_candles_file')
                o, h, l, c, v = values
                if min(o, h, l, c) <= 0 or not l <= o <= h or not l <= c <= h or v < 0 or (previous is not None and t <= previous):
                    raise ValueError('invalid_candles_file')
                bars.append(Bar(t, o, h, l, c, v))
                previous = t
            return bars
    except (ValueError, ArithmeticError, OSError, csv.Error):
        raise ValueError('invalid_candles_file') from None


def run_lab(protocol, bars_by_symbol):
    p = protocol
    try:
        with localcontext(_CTX):
            data, prepared = {}, {}
            for symbol in p.symbols:
                if symbol not in bars_by_symbol:
                    raise ValueError('missing_symbol')
                bars = bars_by_symbol[symbol]
                segments = split_contiguous(bars, p.candle_ms)
                if not bars:
                    raise ValueError('invalid_bars')
                kept = [s for s in segments if len(s) >= p.min_segment_bars]
                regimes = {}
                for s in kept:
                    r = p.regime
                    labels = regime_labels(s, r.atr_n, r.pct_window, r.adx_n, r.params, candle_ms=p.candle_ms)
                    regimes.update((b.open_time_ms, label) for b, label in zip(s, labels))
                candles = tuple(Candle(b.open_time_ms, b.open, b.high, b.low, b.close) for b in bars)
                start, end = evaluation_window(p, candles)
                folds = evaluation_folds(p, start, end)
                data[symbol] = dict(n_bars=len(bars), first_open_ms=bars[0].open_time_ms, last_open_ms=bars[-1].open_time_ms,
                                    n_segments=len(segments), n_kept_segments=len(kept),
                                    n_missing_bars=(bars[-1].open_time_ms - bars[0].open_time_ms) // p.candle_ms + 1 - len(bars),
                                    eval_start_ms=start, eval_end_ms=end, n_folds=len(folds))
                prepared[symbol] = kept, regimes, candles
            results = []
            detectors = {'donchian': detect_donchian_breakout, 'bb_macd': detect_bollinger_macd_reversal, 'ema_cross_adx': detect_ema_cross_adx}
            shift_bars, remainder = divmod(p.controls.min_shift_days * _MS_PER_DAY, p.candle_ms)
            if remainder:
                raise ValueError('invalid_shift')
            for strategy in p.strategies:
                for symbol in p.symbols:
                    kept, regimes, candles = prepared[symbol]
                    cs = tuple(sorted((c for s in kept for c in detectors[strategy.kind](symbol, s, strategy.params, p.risk,
                                                                                      candle_ms=p.candle_ms)), key=lambda c: c.signal_time_ms))
                    nulls = shifted_candidate_sets(symbol, kept, cs, strategy_id=strategy.id, risk=p.risk, candle_ms=p.candle_ms,
                                                   n_shifts=p.controls.n_shifts, min_shift_bars=shift_bars, seed=p.controls.seed)
                    results.append(evaluate_candidates(p, strategy.id, symbol, cs, candles, regimes, nulls))
            return dict(run_id=p.run_id, data=data, results=results,
                        summary=[{k: r[k] for k in ('strategy_id', 'symbol', 'verdict')} for r in results])
    except ArithmeticError:
        raise ValueError('numeric_out_of_range') from None


def render_report_md(result):
    lines = ['# Laboratorio ' + result['run_id'], '',
             'Verdetti: DATI_INSUFFICIENTI (campione insufficiente); NEGATIVO (IC interamente negativo); EVIDENZA_POSITIVA (E1–E4 soddisfatte); POSITIVO_INCONCLUDENTE (media positiva, condizioni incomplete); NULLO (altri casi).', '',
             '| Strategia | Simbolo | Verdetto | n | Netto bp (12) | IC 0,99 | Media R | Max DD R | WF IS / OOS / decadimento / rapporto | Invertita | Rango | 0 bp | 20 bp | Ambigui | Scarto bp |',
             '|---|---|---|---:|---:|---|---:|---:|---|---:|---:|---:|---:|---:|---:|']
    for r in result['results']:
        w, wf = r['whole'], r['walk_forward']
        stress = {Decimal(k): v for k, v in r['stress'].items()}
        row = [r['strategy_id'], r['symbol'], r['verdict'], w['n'], w['mean_net_bp'],
               f"{w['ci_low']} / {w['ci_high']}", w['mean_r'], r['max_dd_r'],
               ' / '.join(str(wf[k]) for k in ('is_mean_net_bp', 'oos_mean_net_bp', 'decay_bp', 'oos_over_is')),
               r['inverted']['cell']['mean_net_bp'], r['shift_control']['rank_pct'],
               stress.get(Decimal('0'), {}).get('mean_net_bp'), stress.get(Decimal('20'), {}).get('mean_net_bp'),
               r['ambiguous']['share'], r['entry_gap']['mean_adverse_gap_bp']]
        lines.append('| ' + ' | '.join('—' if v is None else str(v) for v in row) + ' |')
    explanations = dict(E1='Media e limite basso dell’intervallo devono essere positivi.',
                        E2='Fold, numerosità OOS e tenuta della media OOS rispetto a IS devono rispettare il protocollo.',
                        E3='La media invertita deve essere inferiore a quella osservata e non positiva.',
                        E4='Il rango rispetto ai controlli a scorrimento deve raggiungere la soglia del protocollo.')
    for r in result['results']:
        if r['failed']:
            lines.extend(['', '## ' + r['strategy_id'] + ' / ' + r['symbol'], ''])
            lines.extend('- ' + code + ': ' + explanations[code] for code in r['failed'])
    lines.extend(['', '## Limiti dichiarati', '', _LIMITS, ''])
    return '\n'.join(lines)


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--protocol', required=True)
    parser.add_argument('--data-dir', required=True)
    parser.add_argument('--out-dir', required=True)
    args = parser.parse_args(argv)
    try:
        raw = Path(args.protocol).read_bytes()
        p = load_protocol(json.loads(raw.decode('utf-8')))
        minutes, remainder = divmod(p.candle_ms, 60000)
        if remainder:
            raise ValueError('invalid_candle_ms')
        bars = {s: read_candles_csv(Path(args.data_dir) / f'{s}_{minutes}m.csv') for s in p.symbols}
        result = run_lab(p, bars)
        result['protocol_sha256'] = hashlib.sha256(raw).hexdigest()
        out = Path(args.out_dir)
        out.mkdir(parents=True, exist_ok=True)
        (out / 'lab_report.json').write_text(json.dumps(result, sort_keys=True, indent=2) + '\n', encoding='utf-8')
        (out / 'lab_report.md').write_text(render_report_md(result), encoding='utf-8')
        for row in result['summary']:
            print(row['strategy_id'], row['symbol'], row['verdict'])
        return 0
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
