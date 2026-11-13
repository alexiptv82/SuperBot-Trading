# Brain V3 PAPER — RC84 hotfix dati Bitget, stato 13/11/2026

**PRIORITÀ:** primo avvio del solo Brain PAPER senza modificare classici. **STATO: TEST IN CORSO, NON DISTRIBUITO.**

## Stato della VPS certificato dai due screenshot Termius

- Stage SHA esatto: `0e29a73a36f668643da4088178bacb8616a45ac0`; dirty_count=0.
- Brain paused=1; `superbot-v3-paper-brain-runner` active; `superbot-v3-paper-brain-exit` active/healthy al primo preflight; journal integrity/chain OK.
- Mandato Brain `approved=true`, run_id e policy_hash validi; capitale 2.000 USDT, leva operativa 20–50x, cap DeepSeek 0,75 USD/giorno.
- **DeepSeek realmente provato su VPS**: `deepseek-flash`, thinking high, max_tokens=6000, HTTP200, finish_reason=stop, JSON `{kind:NO_TRADE}` accettato, 1,3 s, 126 token. Prompt diagnostico, non verifica ancora analisi con candele/OPEN.
- Prima diagnostica completa `regole_contratti_ok=6/8`: BTC ed ETH mancanti; SOL `data_unavailable` prima di qualsiasi chiamata AI.

## Causa e correzione

Un backport **solo sui due moduli dati V3**, partendo dallo SHA operativo (non aggiornamento indiscriminato dei 72 commit successivi):
1. `backend/v3/runner/contracts.py`: leggere maxLever pubblicato fino a 200 anziché 125, senza innalzare il max_leverage 50x di RiskPolicy. SHA blob Git `8ffc7f6ec3fe832b30fc70fbc1f41ef319b6f452`.
2. `backend/v3/lab_tools/fetch_candles.py`: endTime allineato e paginazione overlap, no lookahead né interpolazione; blob Git `150aec1d3427af926bd02a074bac4212615c4cdb`. Codice identico alla correzione già contenuta in `ab7e0b7`.
3. `backend/tests/test_brain_market_hotfix_rc84.py`: 4 test, blob Git `bd32e412533bd1c848da322fe6994a4d4d896808`.
4. `deploy/scripts/v3-brain-hotfix-test-offline-20261113.sh`: test isolati in /tmp, offline e opzionale Bitget pubblico `--with-market`. Utilizza SHA pinning Git e rifiuta di procedere se lo stage VPS non è lo SHA esatto o è dirty; NON modifica servizi, portafogli o database.

**Controllo statico GitHub:** l'unico diff dalla versione installata riguarda i 4 file sopra. Blob invariati per `backend/desk/cli.py`, `signals.py`, `brain.py`, `engine.py`, `backend/v3/runner/runner.py`, `wiring.py`, `exit_worker.py`. Il driver del feed è condiviso tra runner ed exit service Brain, quindi **la distribuzione richiederà un piano prudente di riavvio entrambi in pausa**; con posizioni aperte, serve blocco alla distribuzione.

## Test realmente eseguiti da ChatGPT in ambiente locale separato

- `4/4` test del comportamento delle due funzioni corrette, ricostruite dai sorgenti GitHub, **PASS**.
- `256/256` combinazioni aggiuntive di bordi temporali/1m/15m/1H/4H, pagine inclusive/esclusive, con e senza buchi — **PASS**.
- Limite: la prova locale non è una checkout del repository; non dimostra il funzionamento dei file completi in produzione né della suite intera.

**Prossimo gate preparato ma NON eseguito sulla VPS:** eseguire `deploy/scripts/v3-brain-hotfix-test-offline-20261113.sh --with-market` dal commit immutabile della branch. Il comando scarica tre file esatti in `/tmp`, verifica hash e prova **4/4 test originali più 256 casi aggiuntivi**. Con `--with-market` accede **solo agli endpoint pubblici Bitget** per BTC/ETH/SOL e le candele 15m/1H/4H, senza DeepSeek, ordini o modifica dati. Senza `--with-market` è offline. Aspettare output completo e qualsiasi FAIL prima di dichiarare pronto.

## Piano di approvazione separato (NON eseguito)

1. Dopo PASS del test con file esatti e prova Bitget, verificare in sola lettura zero posizioni Brain aperte, journal/backup, integrità, versioning e single exit owner. Se ci sono posizioni aperte, NON riavviare sidecar senza piano di protezione attivo.
2. Fare backup verificabile di file stage, journal+WAL/SHM, budget, heartbeat, env referenziati (NON copiare/mostrare segreti in log), unit metadata. Verificare ripristino su dati sintetici.
3. Solo con OK esplicito utente: sostituire atomicamente i due moduli dati del solo stage RC84, senza modificare `backend/desk/*`, Brain policy/mandate/AI, né web e senza GitHub Actions. Predisporre rollback del doppio file e stato precedente.
4. Riavviare in maniera coordinata **solo servizi Brain in PAPER paused**, verificare uscita healthy, mandato approved e feed su tutti i mercati; non rimuovere mai pause automaticamente.
5. Richiedere ulteriore consenso per togliere esclusivamente `pause.flag` Brain; monitorare prima risposta AI con contesto reale, rifiuti da risk guard, eventuali NO_TRADE (leciti), commissioni, leve e stop. Un NO_TRADE non va convertito artificialmente in OPEN.
6. In caso di failure: bloccare nuove aperture ripristinando pausa Brain; preservare funzione uscite, rollback se necessario e no reset dei journal.

**PER ORA nessun merge, deploy, unpause, reset, LIVE, GitHub Actions o modifica VPS.**
