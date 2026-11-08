# RC84 — ChatGPT review Claude, UI fix, outstanding Telegram P1 (8 novembre 2026)

## Fonti verificabili
- PR #80 Draft https://github.com/alexiptv82/SuperBot-Trading/pull/80, branch `cursor/rc84-running-stop-health-telegram-20261108` base PR #79 RC82 `1e64684b9d813aad1ca1c7d344872333e451fd05`. Claude ha collaudato lo SHA `05935707b651de3e89fb35509ec708ad901ed282`.
- Report Claude https://github.com/alexiptv82/SuperBot-Trading/blob/ccr-999de027-0stnyt/claude/rc84-collaudo-claude-20261108.md, copia `diario/2026-11-08_claude-rc84-collaudo-indipendente.md` e handoff/scratchpad, nessun commit di codice della PR da Claude.
- **Evidenza riferita nel report (test locali VM):** backend mirati 120/120 PASS, suite backend V3 4887/4887 PASS **esclusi** test_auth_flow.py e test_profiles_engine.py per sqlalchemy assente, test_desk.py 84/84 PASS usando HTTPS_PROXY locale con rifiuto rapido; Jest completo 107/108 (fallimento singolo per 'Non è' vs 'non è'), build React produzione PASS.
- Nessuna CI GitHub, browser autenticato, verifica VPS, ordine o deploy. Limite test_desk: migliaia richieste pubbliche Bitget da fixture non hermetiche.

## Difetto P1 — azione da implementare
Claude ha riprodotto tre casi di Telegram che annuncia erroneamente 'CHIUSO':
- `backend/desk/cli.py` close regole/Claude, quando `save_state` fallisce;
- stesso close regole/Claude, quando `append_trade_history` non scrive (nessuno storico);
- single manual `Chiudi posizione` quando `save_state` fallisce.
Altri percorsi condividono ordine sbagliato **per sola ispezione, senza prova**: partial_close in `cli.py`, S25 `long_s25.py`. La patch RC84 precedente correggeva solo le uscite protettive stop/TP/liquidazione.
**Requisito:** notifica informativa *solo dopo* prova coerente history+learning + commit stato per tutte le chiusure PAPER, inclusi partial (identità fill parziale!) e S25; test per ogni percorso; niente notifica se persistenza fallisce. Telegram down non deve rollbackare wallet. Conservare strategie, dati, formule e LIVE. Esito review Github https://github.com/alexiptv82/SuperBot-Trading/pull/80#issuecomment-6727105023.

## Due correzioni frontend GIÀ pubblicate da ChatGPT (senza attestare nuovo PASS)
- Commit `c69481c11a3429bb325b520d5472baea6c492706` su `frontend/src/components/ClassicStopNotice.js`: `health=null` o scope sconosciuto usa avviso neutro «Dati di protezione non disponibili», non modello RC80 a 1m erroneo, non promette stop certificati.
- Commit `bfe5ab9bd13005a37dc39918a33d9f8cac8c3adc` su `frontend/src/pages/ClassicStopNotice.test.js`: asserzione case-insensitive e test null/undefined/unknown.
- I test di Claude (107/108) sono riferiti solo al commit precedente; **frontend sul nuovo HEAD non ancora ri-eseguito**.

## Coordinamento per prossimi passi
- Un solo proprietario backend: delegare a Claude **Sonnet 5.5** la correzione P1 limitata e test su PR #80, **senza modificare il frontend** e senza aggiornare STATO.md (gestito dal coordinatore), oppure Grok se Claude non disponibile. Claude conosce la sonda ed è il più adatto.
- ChatGPT verifica i nuovi commit/risultati e può far rieseguire a Claude Opus un audit indipendente oppure chiedere a Grok test riproduttivi, se bisogno.
- PR #80 resta Draft, NO MERGE/DEPLOY/RIAVVIO/RESET/VPS. Gate ulteriori: collaudo browser autentico/Android, protezione periodica classici 15-30min non continua, Brain exit-worker con handover single-owner certificato, backup off-host/restore, preflight VPS read-only autorizzato e nuovo run 1000/1000/2000 PAPER solo dopo OK.
- Nessun reset o storico cancellato. Cleanup di worktree temporanei Claude non va eseguito con `git branch -D` senza verifica della loro utilità; non è requisito release RC84.
