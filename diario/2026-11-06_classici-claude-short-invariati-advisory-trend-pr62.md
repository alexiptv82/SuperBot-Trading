# SuperBot V3 — Falco/Toro preservati, segnale cambio trend consultivo Claude (PR #62)

**Data:** 2026-11-06, 21:08 Europe/Rome ca. **Modalità PAPER / sola PR #62 draft.**

## Direttiva confermata
Falco e Toro **devono consultare Claude come nella versione precedente**. Non diventano solo meccanici; si conserva integralmente la logica SHORT che l'utente ritiene efficace, i limiti e le condizioni di rischio e il fallback regole. **Le uniche due migliorie autorizzate sono LONG S25 e segnale di cambio trend** per assistere Claude e scegliere più adeguatamente LONG/SHORT rispetto al regime, senza forzare quote di LONG o negare SHORT.

## Verifiche sul commit del ramo
Commit **`f46b267d3ead008816383a2c1da513c5ff03307f`** in `work/v3-release-candidate-gpt6-20261106`, PR #62 (draft). `backend/desk/cli.py` è **byte-identico** a prima e mantiene `call_claude`, `parse_decisions`, scheduling/budget, e fallback `rules_decisions` quando non ci sono decisioni. I SYSTEM_HAWK e SYSTEM_BULL non sono modificati.

- **Nuovo** `backend/desk/trend_change.py`: dati chiusi/contigui, `UP_CROSS`/`DOWN_CROSS` su incrocio EMA20/EMA50 dell'ultima candela completa 1h, `NONE` o `UNKNOWN` in caso di dati insufficienti, stale o sporchi. Solo osservazione. EMA50/200 4h nativa soltanto con >=200 barre valide, altrimenti bias `UNKNOWN` (non presentato come verifica).
- `backend/desk/signals.py`: **solo** estensione `Reading.facts` con `trend_change`, `trend_change_h4`, `trend_change_asof_ms`. Punteggi LONG/SHORT, `side`, SL, TP, timing e strategie SHORT **invariati**.
- `backend/desk/brain.py`: **solo** arricchimento del prompt di Claude col segnale e timestamp, marcato `[solo consultivo: non forzare LONG/SHORT]`. Nessuna istruzione di sistema o funzione `rules_decisions` modificata.
- `backend/desk/long_s25.py`: strategia LONG S25 già presente, ancora **OFF per default**; per avviarla nelle nuove run PAPER serve `DESK_LONG_S25=1` dopo gli altri gate. Le posizioni S25 sono gestite da stop/TP/tempo secondo il modulo dedicato, senza alterare le posizioni classiche.
- La fonte dei classici chiede fino a 1000 candele 15m per ciclo: sono circa 62 candele 4h. Il nuovo bias EMA200 4h sarà quindi normalmente non disponibile. Il prompt conserva comunque il trend4h e giornaliero originale; non si inventa un EMA200 nativo.

## Test e gate
- Test `backend/tests/test_desk_trend_change_advisory.py` **15 PASS** localmente (dati sintetici) su entrambi i versi di crossover, candela non chiusa, gap, stale, pattern invalidi, contesto 4h e assenza di effetti su `side/score/sl/tp`.
- `.github/workflows/v3-dashboard-ci.yml` classic-rc esteso per compilarli e lanciare il test nuovo assieme a `test_desk.py` e `test_long_s25.py`. La CI GitHub del commit f46b267 **era in esecuzione alla registrazione**; non dichiarare conclusa fino a esito verificato.
- Il test locale `test_desk.py` sull'archivio base può restare bloccato nei test legati a rete; l'esecuzione integrale va validata in CI, non inventare PASS.

## Sicurezza rilascio
**Nessun merge, deploy, VPS touch, riavvio, reset o sblocco delle run**. Falco e Toro storici preservati (6 e 2 posizioni PAPER ancora aperte all'ultimo audit) e Brain mantiene indipendenza e rischio 12%/55%. Solo sviluppo sulla PR #62.

## Artefatti in Library
- `/SuperBot-Trading/SuperBot-V3-Falco-Toro-Claude-Trend-Advisory-PAPER-2026-11-06.zip` SHA256 `a8c3462a1c0302744a316004d122dd1850c454e98624f8345a2d789b6553743c`.
- `/SuperBot-Trading/RAPPORTO_FALCO_TORO_CLAUDE_LONG_TREND_2026-11-06.md` SHA256 `a6798e5a2d3ba82111f5e247975f2fa575cb66e372974a1c93b64ba4c353cac4`.