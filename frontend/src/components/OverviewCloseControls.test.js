import React from 'react';
import { createRoot } from 'react-dom/client';
import { act } from 'react-dom/test-utils';
import { renderToStaticMarkup } from 'react-dom/server';
import API, { deskAPI, bullAPI } from '../api';
import { closePositionRequest } from './LiveParts';
import { BrainCloseControls, ClassicCloseControls, closeResultMessages } from './OverviewCloseControls';

jest.mock('../api', () => ({ __esModule: true, default: { get: jest.fn(), post: jest.fn() },
  deskAPI: { closeAll: jest.fn() }, bullAPI: { closeAll: jest.fn() } }));
jest.mock('./LiveParts', () => ({ closePositionRequest: jest.fn() }));

const positions = [{ position_id: 'p-001', symbol: 'BTCUSDT', side: 1, entry: '100', stop: '95', leverage: 20,
  unrealized_pnl: '3.4' }];
const find = (parent, label) => Array.from(parent.querySelectorAll('button')).find(el => el.textContent === label);
const click = async button => { await act(async () => { button.dispatchEvent(new MouseEvent('click', { bubbles: true })); }); };

beforeEach(() => { API.post.mockReset(); API.get.mockReset(); closePositionRequest.mockReset();
  deskAPI.closeAll.mockReset(); bullAPI.closeAll.mockReset();
  global.IS_REACT_ACT_ENVIRONMENT = true;
});

function setup(element) {
  const host = document.createElement('div');
  document.body.appendChild(host);
  const root = createRoot(host);
  return { host, root, render: async () => { await act(async () => { root.render(element); }); },
    done: async () => { await act(async () => { root.unmount(); }); host.remove(); } };
}

test('Brain: controls visible for open position, no confirmation on first click', async () => {
  const s = setup(<BrainCloseControls positions={positions} />);
  try {
    await s.render();
    await click(find(s.host, 'Chiudi BTCUSDT'));
    expect(s.host.textContent).toContain('Chiudere BTCUSDT adesso a prezzo di mercato?');
    expect(API.post).not.toHaveBeenCalled();
    await click(find(s.host, 'Annulla'));
    expect(API.post).not.toHaveBeenCalled();
  } finally { await s.done(); }
});

test('Brain: only one POST after confirmation and result polled every 3 seconds', async () => {
  jest.useFakeTimers();
  const now = Date.now();
  API.post.mockResolvedValue({ data: { ok: true, pending: true, ts_ms: now } });
  API.get.mockResolvedValue({ data: { pending: false, result: { request_ts_ms: now, done_ms: now + 5000,
    status: 'done', closed: ['p-001'], failed: [] } } });
  const refresh = jest.fn();
  const s = setup(<BrainCloseControls positions={positions} onRefresh={refresh} />);
  try {
    await s.render();
    await click(find(s.host, 'Chiudi BTCUSDT'));
    await click(find(s.host, 'Chiudi'));
    expect(API.post).toHaveBeenCalledTimes(1);
    expect(API.post).toHaveBeenCalledWith('/api/v3/brain/close', { position_id: 'p-001' });
    expect(s.host.textContent).toContain('Richiesta inviata');
    await act(async () => { jest.advanceTimersByTime(3000); });
    expect(API.get).toHaveBeenCalledWith('/api/v3/brain/close-result');
    expect(s.host.textContent).toContain('BTCUSDT: posizione chiusa.');
    expect(s.host.textContent).not.toContain('p-001');
    expect(refresh).toHaveBeenCalledTimes(1);
  } finally { await s.done(); jest.useRealTimers(); }
});

test('Brain: Chiudi tutte submits only {all:true} after confirmation', async () => {
  API.post.mockResolvedValue({ data: { ok: true, pending: true, ts_ms: Date.now() } });
  const s = setup(<BrainCloseControls positions={positions} />);
  try {
    await s.render();
    await click(find(s.host, 'Chiudi tutte (1)'));
    expect(s.host.textContent).toContain('Chiudere tutte le 1 posizioni');
    expect(API.post).not.toHaveBeenCalled();
    await click(find(s.host, 'Chiudi'));
    expect(API.post).toHaveBeenCalledWith('/api/v3/brain/close', { all: true });
  } finally { await s.done(); }
});

test('Brain: pending request prevents duplicate submissions', async () => {
  API.post.mockResolvedValue({ data: { ok: true, pending: true, ts_ms: Date.now() } });
  const s = setup(<BrainCloseControls positions={positions} />);
  try {
    await s.render(); await click(find(s.host, 'Chiudi BTCUSDT')); await click(find(s.host, 'Chiudi'));
    expect(find(s.host, 'Chiudi BTCUSDT').disabled).toBe(true);
    expect(API.post).toHaveBeenCalledTimes(1);
  } finally { await s.done(); }
});

test('Brain: 60-second timeout is readable and unlocks the button', async () => {
  jest.useFakeTimers();
  API.post.mockResolvedValue({ data: { ok: true, pending: true, ts_ms: Date.now() } });
  API.get.mockResolvedValue({ data: { pending: true, result: null } });
  const s = setup(<BrainCloseControls positions={positions} />);
  try {
    await s.render(); await click(find(s.host, 'Chiudi BTCUSDT')); await click(find(s.host, 'Chiudi'));
    await act(async () => { jest.advanceTimersByTime(60000); });
    expect(s.host.textContent).toContain('Il Brain non risponde');
    expect(find(s.host, 'Chiudi BTCUSDT').disabled).toBe(false);
  } finally { await s.done(); jest.useRealTimers(); }
});

test('Brain: rejection shows a friendly error, no raw code', async () => {
  API.post.mockRejectedValue({ response: { data: { detail: { code: 'richiesta_in_corso' } } } });
  const s = setup(<BrainCloseControls positions={positions} />);
  try {
    await s.render(); await click(find(s.host, 'Chiudi BTCUSDT')); await click(find(s.host, 'Chiudi'));
    expect(s.host.textContent).toContain('Una richiesta di chiusura è già in corso');
    expect(s.host.textContent).not.toContain('richiesta_in_corso');
  } finally { await s.done(); }
});

test.each([
  [{ status: 'done', closed: [], failed: [['p', 'position_already_closed']] }, 'già chiusa'],
  [{ status: 'done', closed: [], failed: [['p', 'price_unavailable']] }, 'prezzo non disponibile'],
  [{ status: 'expired', closed: [], failed: [] }, 'scaduta'],
  [{ status: 'invalid_request', closed: [], failed: [] }, 'non valida'],
])('Brain: plain-language result %j', (result, text) => {
  const msg = closeResultMessages(result).join(' ');
  expect(msg).toContain(text);
  expect(msg).not.toContain('position_already_closed');
  expect(msg).not.toContain('price_unavailable');
});

test('Falco/Toro capability absent: no buttons, fixed explanation', () => {
  const html = renderToStaticMarkup(<ClassicCloseControls portfolio="falco" positions={positions} canClose={false} />);
  expect(html).not.toContain('<button');
  expect(html).toContain('Chiusura manuale non ancora disponibile');
});

test('Falco: use existing closePositionRequest; no POST without confirmation', async () => {
  closePositionRequest.mockResolvedValue({ ok: true, message: 'inviata' });
  const s = setup(<ClassicCloseControls portfolio="falco" positions={positions} canClose />);
  try {
    await s.render();
    await click(find(s.host, 'Chiudi BTCUSDT'));
    expect(closePositionRequest).not.toHaveBeenCalled();
    await click(find(s.host, 'Chiudi'));
    expect(closePositionRequest).toHaveBeenCalledWith('hawk', 'BTCUSDT');
  } finally { await s.done(); }
});

test('Toro: existing closeAll is reused with inline confirmation', async () => {
  bullAPI.closeAll.mockResolvedValue({ data: { ok: true } });
  const s = setup(<ClassicCloseControls portfolio="toro" positions={positions} canClose />);
  try {
    await s.render();
    await click(find(s.host, 'Chiudi tutte (1)'));
    expect(bullAPI.closeAll).not.toHaveBeenCalled();
    await click(find(s.host, 'Chiudi'));
    expect(bullAPI.closeAll).toHaveBeenCalledTimes(1);
  } finally { await s.done(); }
});

test('Brain: pending command persisted before page reload disables close buttons', async () => {
  const s = setup(<BrainCloseControls positions={positions} serverPending />);
  try {
    await s.render();
    expect(find(s.host, 'Chiudi BTCUSDT').disabled).toBe(true);
    expect(s.host.textContent).toContain('Una richiesta di chiusura è già in corso.');
    expect(API.post).not.toHaveBeenCalled();
  } finally { await s.done(); }
});
