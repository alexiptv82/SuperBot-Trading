# 11 novembre 2026 — Brain V3 in Performance e Impostazioni PUBBLICATO sulla dashboard RC84

**RILASCIO COMPLETATO e VERIFICATO** su VPS Singapore da [GitHub Actions run 42990499079](https://github.com/alexiptv82/SuperBot-Trading/actions/runs/42990499079), status completed/conclusion success, job 130421924975. Pubblicazione verificata dai log verso le 08:54 UTC / 09:54 Europe/Rome del 2026-11-11. Autorizzazione utente: «ok ottimo lavoro, andiamo avanti!» dopo conferma PR Draft #81 e indicazione esplicita del passo successivo (test API e rilascio frontend+backend con rollback).

## Modifica funzionale realmente online

1. **Performance:** selettore Falco / Toro / **Brain**. Per Brain, pannello con Diario, Statistiche e Run Brain V3 indipendente dai classici, derivato da API journal run-scoped e overview. No mescolamento del vecchio Brain Free; P&L realizzato e statistiche con avviso se dataset parziale; nessun falso drawdown.
2. **Impostazioni:** nuova sezione **🧠 Brain** con stato, capitale/equity, posizioni, budget DeepSeek, limiti leva/rischio e profilo della run. **Sola lettura**, nessun reset, avvio o cambio parametro attraverso questa UI.
3. Backend nuovo: **GET /api/v3/brain/config**, autenticato, Cache-Control no-store, espose solo campi whitelist di configurazione non segreta della run Brain. Frontend React e backend Docker **dallo stesso commit pinned** `d0c832620e9b237ce97305029bab5150d3f77489`.
4. PR #81 rimane **DRAFT non mergiata**: https://github.com/alexiptv82/SuperBot-Trading/pull/81. Rilascio effettuato da commit tecnico isolato; non confondere merge GitHub e pubblicazione web. Staging nuovo `/opt/superbot-v3-brain-ui-stage`; Docker nuovo `superbot` immagine `superbot:brain-ui-20261111`, frontend web `/opt/superbot-web/build`.

## Esiti reali GitHub Actions

- **Backend test mirati:** `6 passed, 1 warning` (test whitelist config e regressione paginazione Brain).
- **Frontend:** 2 suite, **9 test PASS**; `Compiled successfully`, build React ottimizzata.
- Controllo SHA codice sorgente e SHA bundle statico: `RC84_BRAIN_UI_STAGED_PINNED_SOURCE=PASS`, `RC84_BRAIN_UI_ASSET_HASH_MATCH=PASS`.
- Preflight su VPS (due volte) `RC84_BRAIN_UI_PREFLIGHT=PASS`, `RC84_BRAIN_UI_THREE_PAPER_RUNS_PAUSED=True`, `RC84_BRAIN_UI_PUBLIC_SITE_CURRENTLY_SAFE=True`.
- Asset staged `RC84_BRAIN_UI_CANDIDATE_ASSET_STAGED=PASS`; backup autenticazione SQLite `RC84_BRAIN_UI_AUTH_BACKUP_CHECK=PASS`; backend Docker `RC84_BRAIN_UI_IMAGE_BUILT=PASS`.
- Nuova API protetta (401 senza login), /api/health=200 e richieste mutanti 423 `RC84_BRAIN_UI_NEW_API_AUTHENTICATED_GATE=PASS`.
- Esito finale `RC84_BRAIN_UI_PUBLIC_RELEASE=PASS`, `RC84_BRAIN_UI_OLD_RC84_RETAINED_FOR_ROLLBACK=True`, `RC84_BRAIN_UI_RC73_BACKUP_UNTOUCHED=True`, `RC84_BRAIN_UI_NO_PAPER_TRADE_OR_PROVIDER_CALLS=True`.

## Rollback e vincoli operativi

- Container precedente RC84 conservato fermo come `superbot-rc84-before-brain-ui`, frontend precedente RC84 `/opt/superbot-web/build.rc84-before-brain-ui`. Originale rollback RC73 già conservato come `superbot-rc84-previous` e `/opt/superbot-web/build.rc84-previous`. **Non eliminare né rinominare senza piano di cleanup separato.**
- I tre nuovi wallet Falco 1.000 USDT PAPER / Toro 1.000 USDT PAPER / Brain 2.000 USDT PAPER sono rimasti **PAUSED**; Brain `mandate.approved=false`. Nessun trade, nessun riavvio strategie, nessun cambio storico. La nuova app è soltanto consultiva finché i gate di comando sono disabilitati.
- **Gap ancora aperto:** Claude e DeepSeek delle nuove unità non ancora collegate ai file secret protetti; presenza vecchie chiavi non certifica credito/validità. Non rimuovere pause o approvare Brain finché provisioning e consenso non siano completati.
- Prova tecnica della API 401 senza sessione è fatta; l'utente deve confermare nel browser già autenticato che Brain appare in **Performance** e **Impostazioni**. Su dispositivi con asset memorizzati nella cache fare un refresh completo o riaprire l'app.
- Esecuzione su GitHub Actions: **un singolo workflow di rilascio**, senza suite massive; preservare quota minuti fino al 1 dicembre.

**Prossimo obiettivo:** conferma visiva dell'utente, poi configurazione AI sicura senza esporre chiavi e, solo con autorizzazione, sblocco trading simulato.
