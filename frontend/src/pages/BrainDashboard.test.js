import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { createRoot } from 'react-dom/client';
import { act } from 'react-dom/test-utils';
import BrainDashboard, { BrainCards } from './BrainDashboard';
import { brainAPI } from '../api';

jest.mock('../api', () => ({ brainAPI: { getStatus: jest.fn() } }));

const sample = {
  status: 'ok', portfolio: { equity: 1035, cash: 800, pnl: 35, pnl_pct: 3.5, cycles: 5 },
  positions: [{ symbol: 'BTC', side: 'LONG', entry: 100, floating_pnl: 20 }],
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
  expect(brainAPI.getStatus).toHaveBeenCalledTimes(1); // pending call cannot overlap
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
