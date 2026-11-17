import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import API from '../api';
import ArenaCloseControls from './ArenaCloseControls';
import { arenaErrorText, newRequestId, statusText, validNote } from '../arenaCloseModel';

jest.mock('../api', () => ({ __esModule: true, default: { get: jest.fn(), post: jest.fn() } }));

const POS = [{ position_id: 'pos-1', symbol: 'BTCUSDT', side: 1 }, { position_id: 'pos-2', symbol: 'ETHUSDT', side: -1 }];

async function mount(props) {
  const node = document.createElement('div');
  document.body.appendChild(node);
  const root = createRoot(node);
  const render = async p => act(async () => {
    root.render(<ArenaCloseControls provider="qwen" positions={POS} ready annotations={[]}
      onRefresh={() => {}} renderPosition={t => <span>{t.symbol}</span>} {...p}/>);
  });
  await render(props);
  return { node, render, dispose: async () => { await act(async () => root.unmount()); node.remove(); } };
}
const button = (node, text) => Array.from(node.querySelectorAll('button')).find(b => b.textContent.trim() === text);

beforeEach(() => { global.IS_REACT_ACT_ENVIRONMENT = true; jest.useFakeTimers(); });
afterEach(() => { jest.useRealTimers(); API.get.mockReset(); API.post.mockReset(); });

test('model helpers: request id format, notes, terminal texts never guessed', () => {
  const id = newRequestId();
  expect(id).toMatch(/^[A-Za-z0-9-]{16,64}$/);
  expect(newRequestId()).not.toBe(id);
  expect(validNote('')).toBe(true);
  expect(validNote('ok')).toBe(true);
  expect(validNote('a\nb')).toBe(false);
  expect(validNote('x'.repeat(281))).toBe(false);
  expect(statusText({ status: 'closed' })).toContain('confermata');
  expect(statusText({ status: 'failed', code: 'price_unavailable' })).toContain('resta aperta');
  expect(statusText({ status: 'unconfirmed', code: 'exit_service_did_not_confirm' })).toContain('non risulta chiusa');
  expect(statusText({ status: 'closed_by_other_exit', exit_reason: 'stop' })).toContain('stop');
  expect(arenaErrorText({ response: { data: { detail: { code: 'exit_service_not_ready' } } } })).toContain('non è pronto');
  expect(arenaErrorText(new Error('x'))).toContain('Nessuna operazione presunta');
});

test('nothing is closable when the exit service of this AI is not ready', async () => {
  const { node, dispose } = await mount({ ready: false });
  try {
    expect(button(node, 'Chiudi BTCUSDT').disabled).toBe(true);
    expect(node.textContent).toContain('servizio di uscita PAPER di questa AI non è attivo');
    expect(node.textContent).not.toContain('Chiudi tutte');
  } finally { await dispose(); }
});

test('confirm -> dedicated provider route -> journal confirmation -> one reason, never brain/close', async () => {
  let refreshed = 0;
  API.post.mockImplementation((url, body) => {
    if (url === '/api/v3/arena/qwen/close') {
      return Promise.resolve({ data: { ok: true, status: 'pending', terminal: false, request_id: body.request_id } });
    }
    if (/^\/api\/v3\/arena\/qwen\/close\/arena-[0-9a-f]{24}\/annotation$/.test(url)) {
      return Promise.resolve({ data: { ok: true, annotation: { reason: body.reason, note: body.note ?? null } } });
    }
    throw new Error('UNEXPECTED_' + url);
  });
  API.get.mockResolvedValue({ data: { ok: true, status: 'closed', terminal: true, close_event_id: 'e1' } });
  const { node, render, dispose } = await mount({ onRefresh: () => { refreshed += 1; } });
  try {
    await act(async () => button(node, 'Chiudi BTCUSDT').click());
    expect(node.querySelector('[role="dialog"]')).not.toBeNull();
    expect(API.post).not.toHaveBeenCalled();                  // nessuna chiamata senza conferma
    await act(async () => button(node, 'Conferma chiusura').click());
    const [url, body] = API.post.mock.calls[0];
    expect(url).toBe('/api/v3/arena/qwen/close');
    expect(Object.keys(body).sort()).toEqual(['position_id', 'request_id']);
    expect(body.position_id).toBe('pos-1');
    expect(node.textContent).toContain('in attesa della conferma');
    expect(node.textContent).not.toContain('Perché hai chiuso');  // nessun motivo prima della conferma
    await act(async () => { jest.advanceTimersByTime(3100); });
    expect(API.get).toHaveBeenCalledWith(`/api/v3/arena/qwen/close/${body.request_id}`);
    expect(node.textContent).toContain('Chiusura PAPER confermata dal journal');
    expect(refreshed).toBe(1);
    // la posizione sparisce dalle aperte dopo l'aggiornamento: l'esito e il motivo restano visibili
    await render({ positions: [POS[1]], onRefresh: () => {} });
    expect(node.textContent).toContain('BTCUSDT');
    const save = button(node, 'Registra motivazione');
    expect(save.disabled).toBe(true);                         // nessun motivo preselezionato o dedotto
    const radio = node.querySelector('input[value="loss_reduction"]');
    await act(async () => radio.click());
    await act(async () => save.click());
    expect(API.post.mock.calls[1][0]).toBe(`/api/v3/arena/qwen/close/${body.request_id}/annotation`);
    expect(API.post.mock.calls[1][1]).toEqual({ reason: 'loss_reduction' });
    expect(node.textContent).toContain('Motivazione registrata');
    expect(API.post.mock.calls.every(([u]) => !u.includes('/brain/close'))).toBe(true);
  } finally { await dispose(); }
});

test('failed close shows the reason and offers no annotation', async () => {
  API.post.mockResolvedValue({ data: { ok: true, status: 'pending', terminal: false } });
  API.get.mockResolvedValue({ data: { ok: true, status: 'failed', terminal: true, code: 'price_unavailable' } });
  const { node, dispose } = await mount();
  try {
    await act(async () => button(node, 'Chiudi ETHUSDT').click());
    await act(async () => button(node, 'Conferma chiusura').click());
    await act(async () => { jest.advanceTimersByTime(3100); });
    expect(node.textContent).toContain('Prezzo non disponibile');
    expect(node.textContent).not.toContain('Perché hai chiuso');
  } finally { await dispose(); }
});

test('server refusal is shown and nothing is presumed closed', async () => {
  API.post.mockRejectedValue({ response: { status: 409, data: { detail: { code: 'request_in_progress' } } } });
  const { node, dispose } = await mount();
  try {
    await act(async () => button(node, 'Chiudi BTCUSDT').click());
    await act(async () => button(node, 'Conferma chiusura').click());
    expect(node.textContent).toContain('Una chiusura è già in corso');
    expect(node.textContent).not.toContain('confermata');
  } finally { await dispose(); }
});
