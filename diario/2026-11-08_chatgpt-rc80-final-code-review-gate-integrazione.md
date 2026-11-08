# RC80: code review conclusa sul bug multi-claim — 8 novembre 2026

## Prova verificata
- PR Draft #77 https://github.com/alexiptv82/SuperBot-Trading/pull/77
- Branch `cursor/rc80-paper-stop-hardening-31c4`, HEAD `50b75b9643680b9c758047d3890f3599b051f325`. Commit HEAD solo documentale; patch codice in `db2e4484326229e74b041c69d083973fa2aab760`.
- Base RC78 `cursor/rc78-paper-stop-offline-31c4` SHA `b6eaa173c12c241647f89f730e1430a841cade3a` invariata.
- `inspect_claims` verifica tutti i claim e restituisce `resolved` soltanto quando tutti risultano provati. `reconcile_stop_claim` archivia solo se tutti provati. Test regressione BTC/ETH/SOL con ordini invertiti, archivio verificato su disco e nessuna cancellazione dei claim irrisolti.
- **Code review statica di ChatGPT: PASS circoscritto a questa correzione.** Test dichiarati da Grok: **67 PASS locali, 0 FAIL** (30 RC80, 22 RC78, 15 exit-only). **Non rieseguiti indipendentemente**, **zero GitHub Actions** sullo SHA. Nessun merge/deploy/VPS/riavvio/ordine.
- Commento conclusivo https://github.com/alexiptv82/SuperBot-Trading/pull/77#issuecomment-6721971056 .

## Stato rilascio: NO GO
RC80 riguarda un monitor di stop del DESK PAPER durante manutenzione con legacy disattivati. Non dimostra protezione mentre il motore Falco/Toro è effettivamente RUNNING, e il modello `closed_1m_close_only` non equivale a uno stop tick/intrabar. Non dichiarare garanzie real-time. Nessuna riattivazione consentita senza nuovo mandato.

## Nuova fase — gate integrazione V3
1. Eseguire suite indipendente riproducibile sull'HEAD esatto RC80 in sandbox offline, senza Action di deploy/riavvio.
2. Verificare catena Falco/Toro in marcia e in pausa (stop/TP/liquidazione, feed fresco, interruzione prezzo, heartbeat, rischio e ritorno dopo crash), evitando due writer concorrenti.
3. Collegare telemetria e `protection_alarm` all'API/dashboard Android: copertura `covered/partial/blind/blocked/idle`, stale, errore telemetria; spiegare chiaramente limiti candle-close.
4. Revisione PR #74 Brain single close (opt-in OFF), PR #72 dashboard 3 portafogli e PR #76 RC79 diagnosi post-trade; coerenza run_id, storici, importi e UI.
5. Conservazione dello storico + backup/restore verificati e backup esterno, preflight in sola lettura della VPS; definire nuova run PAPER Falco=1000, Toro=1000, Brain=2000 e autorizzazione separata per cutover/trade.

Ultimo audit VPS noto RC77: Falco/Toro zero PAPER aperte, Brain paused. Nessun audit VPS effettuato in questa verifica. Priorità utente: chiudere sviluppo pesante con Grok, collaudo e ripartenza PAPER quanto prima senza sorprese. Claude tornerà disponibile per review aggiuntiva.
