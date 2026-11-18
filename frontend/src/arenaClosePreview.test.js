import { arenaCloseUiEnabled } from './arenaCloseModel';

test('read-only preview wins over provider close flag, even if accidentally enabled', () => {
  expect(arenaCloseUiEnabled({ REACT_APP_PREVIEW_READONLY: '1',
    REACT_APP_ARENA_MANUAL_CLOSE: '1' })).toBe(false);
  expect(arenaCloseUiEnabled({ REACT_APP_PREVIEW_READONLY: '0',
    REACT_APP_ARENA_MANUAL_CLOSE: '1' })).toBe(true);
  expect(arenaCloseUiEnabled({ REACT_APP_ARENA_MANUAL_CLOSE: '0' })).toBe(false);
});
