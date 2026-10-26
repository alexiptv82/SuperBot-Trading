import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { createRoot } from 'react-dom/client';
import { act } from 'react-dom/test-utils';
import BrainDashboard, { BrainCards } from './BrainDashboard';
import { brainAPI } from '../api';

jest.mock('../api', () => ({ brainAPI: { getStatus: jest.fn() } }));

const sample = {
  status: 'ok', portfolio: { equity: 1035, cash: 800, margin_in_use: 200, pnl: 35, pnl_pct: 3.5, cycles: 5 },
  positions: [{ symbol: 'BTC', side: 'LONG', entry: 100, margin: 100, leverage: 20, notional_entry: 2000, floating_margin_roi_pct: 20, floating_pnl: 20 }],
  trades: [{ symbol: 'ETH', side: 'SHORT', pnl: 3, reason: 'take_profit', closed_ms: 100, partial: true }],
  stats: { closed_trades: 1, win_rate_pct: 100, average_pnl: 3 },
  daily_stop: { stopped: true, used_limit_pct: 100, drawdown_pct: 20 },
  reasoning: { bull_scenario: '<script>UNSAFE_MODEL_TEXT</script>', bear_scenario: 'Breakdown', verdict: 'Hold' },
  system: { health: 'unknown', sha: null, uptime_seconds: null },
};

test('six observation cards, native values and escaped model text', () => {
  const html = renderToStaticMarkup(<BrainCards data={sample} />);
  expect((html.match(/<section/g) || []).length).toBe(6);
  expect(html).toContain('$1035.00');
  expect(html).toContain('SHORT');
  expect(html).toContain('Chiusura parziale');
  expect(html).toContain('Raggiunto');
  expect(html).toContain('&lt;script&gt;UNSAFE_MODEL_TEXT&lt;/script&gt;');
  expect(html).not.toContain('<script>');
  expect(html).not.toMatch(/<button|<form|onClick/);
});

test('empty and unavailable states are distinct, metrics never show fabricated zero', () => {
  const unavailable = renderToStaticMarkup(<BrainCards data={null} />);
  expect(unavailable).toContain('Posizioni non disponibili');
  expect(unavailable).not.toContain('$0.00');
  const empty = renderToStaticMarkup(<BrainCards data={{ status: 'ok' }} />);
  expect(empty).toContain('Nessuna posizione aperta');
  expect(empty).toContain('unknown');
  expect(empty).toContain('Non disponibile');
  expect(empty).not.toContain('1f2edeb6');
});

test('only GET polling, no overlap, abort and timer cleanup on unmount', async () => {
  jest.useFakeTimers();
  global.IS_REACT_ACT_ENVIRONMENT = true;
  let resolve;
  brainAPI.getStatus.mockReturnValue(new Promise(done => { resolve = done; }));
  const host = document.createElement('div');
  const root = createRoot(host);
  await act(async () => { root.render(<BrainDashboard />); });
  expect(brainAPI.getStatus).toHaveBeenCalledTimes(1);
  await act(async () => { jest.advanceTimersByTime(60000); });
  expect(brainAPI.getStatus).toHaveBeenCalledTimes(1);
  await act(async () => { resolve({ data: sample }); });
  expect(host.textContent).toContain('$1035.00');
  const signal = brainAPI.getStatus.mock.calls[0][0];
  await act(async () => { root.unmount(); });
  expect(signal.aborted).toBe(true);
  expect(jest.getTimerCount()).toBe(0);
  jest.useRealTimers();
  brainAPI.getStatus.mockReset();
});

test('network failure clears previous data and announces unavailable', async () => {
  jest.useFakeTimers();
  global.IS_REACT_ACT_ENVIRONMENT = true;
  brainAPI.getStatus.mockResolvedValueOnce({ data: sample }).mockRejectedValueOnce(new Error('offline'));
  const host = document.createElement('div');
  const root = createRoot(host);
  await act(async () => { root.render(<BrainDashboard />); });
  expect(host.textContent).toContain('$1035.00');
  await act(async () => { jest.advanceTimersByTime(30000); });
  expect(host.textContent).not.toContain('$1035.00');
  expect(host.textContent).toContain('Brain non disponibile');
  await act(async () => { root.unmount(); });
  jest.useRealTimers();
  brainAPI.getStatus.mockReset();
});


test('positions show actual leverage, committed margin, exposure and gross margin ROI', () => {
  const html = renderToStaticMarkup(<BrainCards data={sample} />);
  expect(html).toContain('Margine totale impegnato');
  expect(html).toContain('$200.00');
  expect(html).toContain('Margine impegnato');
  expect(html).toContain('$100.00');
  expect(html).toContain('Leva effettiva');
  expect(html).toContain('20×');
  expect(html).toContain('Valore posizione (entry)');
  expect(html).toContain('$2000.00');
  expect(html).toContain('Rendimento lordo sul margine');
  expect(html).toContain('20.00%');
  expect(html).toContain('commissioni e funding non detratti');
});

test('older API fields remain unavailable rather than zero or guessed leverage', () => {
  const html = renderToStaticMarkup(<BrainCards data={{ status: 'ok', positions: [
    { symbol: 'BTC', side: 'LONG', entry: 100, floating_pnl: 1 },
  ] }} />);
  expect(html).toContain('Margine impegnato');
  expect(html).toContain('Leva effettiva');
  expect(html).not.toContain('0×');
  expect(html).not.toContain('1×');
  expect(html).not.toContain('NaN');
  expect(html).not.toContain('$0.00');
});

test('negative floating returns render clearly and fractional saved leverage is preserved', () => {
  const data = { ...sample, positions: [{ symbol: 'SOL', side: 'SHORT', margin: 25,
    leverage: 2.5, notional_entry: 62.5, entry: 100, floating_pnl: -1, floating_margin_roi_pct: -4 }] };
  const html = renderToStaticMarkup(<BrainCards data={data} />);
  expect(html).toContain('$25.00');
  expect(html).toContain('2.5×');
  expect(html).toContain('$-1.00');
  expect(html).toContain('-4.00%');
  expect(html).not.toMatch(/<button|<form|onClick/);
});
