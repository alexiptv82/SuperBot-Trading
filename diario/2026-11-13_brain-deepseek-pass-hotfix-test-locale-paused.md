# Checkpoint verificabile — DeepSeek reale PASS; hotfix dati Brain testato solo localmente

**Data:** 13/11/2026 13:45 Europe/Rome  
**Ambito:** sola documentazione; trading esclusivamente PAPER; nessun deploy, unpause o ordine eseguito da questo checkpoint.

## Sintesi per la ripresa

Dopo il checkpoint delle 12:47 sono stati chiusi due dubbi importanti:

1. lo stage VPS Brain installato è stato identificato come `0e29a73a36f668643da4088178bacb8616a45ac0`, pulito;
2. una vera chiamata DeepSeek dalla VPS ha risposto correttamente `NO_TRADE`.

Restano però bloccanti i dati mercato sullo SHA installato: parser contratti vecchio e paginazione candele. È stato preparato e testato localmente un backport Brain-only, ma **non è stato distribuito né provato sui file completi in VPS**. Brain resta PAUSED.

## Fatto e verificato

Fonte principale: [Issue #95](https://github.com/alexiptv82/SuperBot-Trading/issues/95), commenti:
- [DeepSeek reale e hotfix minimo](https://github.com/alexiptv82/SuperBot-Trading/issues/95#issuecomment-6852270511);
- [collaudo locale e gate VPS](https://github.com/alexiptv82/SuperBot-Trading/issues/95#issuecomment-6853187851).

I riscontri VPS derivano da screenshot/output Termius forniti dall'utente e registrati nell'Issue; questa esecuzione non ha effettuato accesso SSH autonomo.

### VPS / DeepSeek

- Stage installato: `0e29a73a36f668643da4088178bacb8616a45ac0`; `dirty_count=0`.
- Parser installato: limite metadata `maxLever<=125`, incompatibile con BTC/ETH pubblicati a 150.
- Brain: `paused=1`; runner e exit attivi; exit healthy nel preflight precedente; journal integrity/chain OK.
- Modello: `deepseek-flash`, thinking enabled/high, max_tokens 6000; chiave presente verificata solo come booleano.
- Chiamata reale: HTTP 200, 1,3 s, `finish_reason=stop`, JSON valido, `kind=NO_TRADE`, risposta accettata; 93 prompt + 33 completion = 126 token.
- La prova certifica accesso provider, modello e formato diagnostico. **Non certifica** analisi su candele reali, reasoning complesso, proposal OPEN, passaggio risk o apertura PAPER.
- I blocker precedenti restano: BTC/ETH `no_market_rules`; SOL `data_unavailable` prima della chiamata AI.

## Hotfix Brain-only preparato

Branch `work/brain-rc84-market-data-hotfix-20261113`, base esatta dello stage VPS `0e29a73…`, HEAD verificato [`5113e10a57f7db2461f1259151af593569c34850`](https://github.com/alexiptv82/SuperBot-Trading/commit/5113e10a57f7db2461f1259151af593569c34850).

Confronto GitHub base→HEAD: 7 commit, **5 file**:

1. `backend/v3/runner/contracts.py`: accetta metadata Bitget fino a 200; RiskPolicy Brain resta 20–50×.
2. `backend/v3/lab_tools/fetch_candles.py`: confini allineati e overlap delle finestre; niente lookahead o interpolazione.
3. `backend/tests/test_brain_market_hotfix_rc84.py`: 4 regressioni offline.
4. `deploy/scripts/v3-brain-hotfix-test-offline-20261113.sh`: test in `/tmp`, opzionale Bitget pubblico `--with-market`.
5. `docs/v3/BRAIN-RC84-BITGET-HOTFIX-HANDOFF-20261113.md`: runbook, gate e rollback.

Il codice funzionale iniziale è nel commit [`4fd28ad7e4d00d3db9d15c510dbedf700ce24719`](https://github.com/alexiptv82/SuperBot-Trading/commit/4fd28ad7e4d00d3db9d15c510dbedf700ce24719).

Nessuna modifica verificata a `backend/desk/*`, runner/wiring/exit-worker Brain, API, UI, policy, mandato, unità o dati. Non distribuire l'intero `ab7e0b7`: rispetto allo stage installato contiene 72 commit e modifiche anche ai classici.

## Test con fonte e limiti

Riportati nell'Issue e nel runbook, eseguiti da ChatGPT in ambiente locale separato:

- 4/4 casi delle funzioni hotfix: PASS;
- 256/256 casi aggiuntivi su 1m/15m/1H/4H, boundary inclusivi/esclusivi e gap: PASS.

Limite obbligatorio: le funzioni sono state ricostruite dai sorgenti GitHub; **non è stata eseguita la suite completa del repository**, né è stata certificata la compatibilità dei file completi con la VPS.

Lo script pinned per i file esatti e Bitget pubblico è preparato ma **non ancora eseguito sulla VPS**. Può generare traffico verso API pubbliche Bitget, ma non usa chiavi, DeepSeek o ordini e non dovrebbe modificare run, journal, budget, pausa o servizi.

## Portafogli PAPER e decisioni

- **Brain:** priorità corrente; capitale desiderato/verificato nella config 2.000 USDT, floor 450, leva 20–50×, 8 simboli, cap DeepSeek 0,75 USD/giorno. Provider PASS diagnostico; dati mercato ancora NO-GO. Resta PAUSED.
- **Falco:** strategia SHORT originale congelata e intatta; nessuna modifica autorizzata.
- **Toro:** LONG/Twin sospeso; PR #93 FAIL e PR #94 PASS tecnico/NO-GO strategico restano evidenza, non rilascio.
- `NO_TRADE` è valido e non va convertito artificialmente in OPEN.

## Eseguito / preparato / rilasciato

- **Eseguito:** smoke DeepSeek reale sulla VPS; identificazione SHA; confronto GitHub; test locali 4+256; documentazione.
- **Preparato:** hotfix Brain-only, script di verifica file esatti/Bitget pubblico, runbook e rollback.
- **Rilasciato:** nulla.
- **Non eseguito/non approvato:** test VPS hotfix, deploy dei due moduli, restart servizi, rimozione pausa, ciclo Brain E2E con dati reali, proposal OPEN, ordine PAPER, merge o GitHub Actions.

## Backup e chiavi

- Backup esterno `work/extbackup-bot-stopped-20261109`: preparato, non installato.
- Copia cifrata della chiave age sul PC: PowerShell `ESITO: VERIFICA OK` e chiave pubblica coincidente; non certifica backup o restore sulla VPS.
- RC84 PR #80 resta riferimento storico.
- Nessuna chiave privata, passphrase, token o dettaglio d'accesso è riportato.

## Blocker e prossimo passo

1. Eseguire, solo come gate diagnostico separato, lo script pinned dei file esatti con prova Bitget pubblica; attendere output completo e trattare ogni FAIL come bloccante.
2. Verificare in sola lettura: zero posizioni Brain aperte, journal/backup/integrità, stage SHA pulito e owner uscite unico.
3. Solo con autorizzazione esplicita futura: backup+rollback e deploy atomico dei **due soli moduli dati** nello stage Brain, mantenendo Brain in pausa e senza toccare Falco/Toro.
4. Dopo deploy autorizzato: restart coordinato solo runner+exit Brain in PAPER paused e test feed.
5. L'unpause Brain richiede una seconda autorizzazione distinta e prova E2E su dati reali; nessun trade forzato.
6. Preservare storici ed EventJournal; nessun reset.

## Limite conversazioni

Sono stati usati soltanto i contenuti recenti effettivamente accessibili e i riscontri GitHub. Non esiste accesso garantito a chat eliminate o trascrizioni integrali. Nessuno stato live VPS successivo ai riscontri dell'Issue è stato assunto.
