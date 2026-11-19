# Checkpoint verificabile — Cloud temporaneo, Arena preservata, P0 latch e PR #123

**Data:** 19/11/2026 18:45 Europe/Rome  
**Ambito:** consolidamento documentale; nessuna azione operativa.

## Novità verificate dopo il checkpoint delle 17:46

### Decisione temporanea su responsabilità e collaborazione

- L'utente ha deciso che, **temporaneamente e fino a nuova indicazione**, Claude/Cloud sarà l'operatore principale per completare SuperBot.
- ChatGPT resta consulente: analizza i report ricevuti, prepara risposte o prompt e mantiene il checkpoint verificabile. Non è un passaggio definitivo.
- L'accesso VPS di Claude resta una capacità dichiarata dall'utente. Non è stato verificato qui alcun login, privilegio, servizio o stato live e non autorizza automaticamente operazioni.
- Il mandato di questo checkpoint resta documentale: nessun merge, deploy, accesso/modifica VPS, restart, reset, ordine, training, API a pagamento o GitHub Actions.

### Dati Arena: preservare integralmente, non promuovere automaticamente

- Decisione utente: conservare integralmente i dati dell'Arena anche se i risultati sono molto negativi.
- Prestazioni scarse non sono motivo per cancellare EventJournal, decisioni, trade, scoreboard, feature o metadati: sono evidenza utile anche di failure mode.
- Conservazione non equivale ad ammissione al training. Prima di usare record Arena nel Brain Unico servono provenienza, completezza, legame causale, qualità e attestazione; record dubbi restano esclusi/non eleggibili.
- Qualunque conclusione anticipata dell'Arena, stop delle aperture o gestione di posizioni richiede backup/checkpoint coerente e consenso operativo separato. Nessuna azione Arena è stata eseguita qui.

### PR #121 — fail-closed prezzi e test legacy

- [PR #121](https://github.com/alexiptv82/SuperBot-Trading/pull/121) resta open/draft, non mergiata; HEAD aggiornata a `5b7403aa333b43d801ca7e28825ea4707f6847b4`, base `work/brain-exit-observability-20261113`.
- Claude ha verificato su worktree isolato la HEAD precedente `454020a…`: 8/8 nuovi test PASS; suite pertinente 1110 PASS, 7 FAIL, 1 skip. Cinque fail `test_v3_rc84_import_paths` risultano preesistenti sulla base; due fail erano test legacy incompatibili col nuovo fail-closed.
- Il commit `5b7403a…` aggiorna soltanto due aspettative legacy in `backend/tests/test_v3_runner_daily_loss.py`; non modifica runtime, RiskManager, soglie, leva o capitale.
- I test aggiornati sulla nuova HEAD **non risultano ancora rieseguiti sul checkout completo**. Non dichiarare PASS totale; 0 workflow run e 0 status GitHub.
- Uscite/ExitService restano da mantenere indipendenti dal blocco delle nuove aperture.

### Issue #124 — P0 persistenza latch daily-loss

- Nuova [Issue #124](https://github.com/alexiptv82/SuperBot-Trading/issues/124), open: **P0 / NO-GO a nuovi deploy Brain Unico** finché il latch HALT non sopravvive in modo verificabile a file corrotto, scrittura fallita e riavvio.
- Difetto riprodotto in laboratorio: se `daily_loss.json` non viene scritto o si corrompe, il blocco può perdersi dopo restart e nuove aperture possono riabilitarsi se il PnL è risalito sotto soglia.
- La soluzione deve distinguere primo avvio fidato da perdita di stato dopo attività, restare idempotente per run/giorno UTC, bloccare solo nuove aperture in caso di incertezza e mantenere ExitService/chiusure autonomi.
- Soglie 35% WARN, 50% HALT e floor equity 450 USDT non vanno cambiate. Nessuna correzione o test operativo eseguiti in questo checkpoint.

### PR #123 — laboratorio SHADOW costi LLM (lacuna recuperata)

- [PR #123](https://github.com/alexiptv82/SuperBot-Trading/pull/123) open/draft, non mergiata: branch `cursor/brain-llm-cost-lab-20261119-31c4`, HEAD `c51c7520b35640518baea217404da9657702d4f5`, base `work/brain-exit-observability-20261113`.
- È stata creata alle 17:25:53 Europe/Rome, quindi prima del checkpoint delle 17:46, ma non era stata inclusa: questa è una lacuna importante ora recuperata.
- Prepara un laboratorio offline/shadow con tre ID fissi: `deepseek-flash`, `google/gemini-2.5-flash`, `groq/llama-3.3-70b`; niente `auto:smart`, fallback, ordini o scrittura nel journal operativo.
- Il corpo PR riferisce 13 test locali PASS, nessuna chiamata provider. 0 workflow run e 0 status GitHub; risultato non replicato in questa esecuzione.
- Raccomandazione della PR: non integrare ora; DeepSeek resta decisore. Il candidato Gemini può essere valutato solo come shadow; il listino zero di Groq non misura la qualità.
- PR #120 resta separata e non allineata alla policy consolidata. Il lavoro Grok/Cursor è preparazione da confrontare, non approvazione o installazione.

## Stato consolidato dei tre portafogli PAPER

- **Falco:** storico e logica SHORT preservati; per Brain Unico solo advisor non bloccante. Nessuna modifica live verificata.
- **Toro:** storico preservato come archivio/benchmark; nessun reset autorizzato o eseguito.
- **Brain:** Brain Unico resta l'obiettivo prioritario. Brain storico/Arena, EventJournal, memorie, scoreboard, decisioni, trade e posizioni sono da preservare integralmente. PR #114–#123 sono preparazioni draft, non una release installata.
- **Configurazione desiderata LLM:** DeepSeek primario; advisor shadow opzionali con 1–2 modelli/provider/versioni fissati, senza auto-routing libero o fallback silenzioso.
- **Implementato/preparato:** PR #120 propone ancora router gratuito primario + fallback DeepSeek; PR #123 propone laboratorio fisso e inert/shadow. Nessuna delle due è approvata o operativa.

## Riferimenti invariati e sicurezza

- PR #122 resta open/draft @ `513448e57747f381e11ce23ab09788d6a41e6cb0`; test SQLite isolati non equivalgono a suite completa, adapter non collegato ai runner e snapshot non eleggibili al training.
- RC84 PR #80: ultimo SHA verificato `0e29a73a36f668643da4088178bacb8616a45ac0`.
- Backup esterno `work/extbackup-bot-stopped-20261109` @ `3dc2116a08058f57fc14b695431f6e3fa1a1ca45`: preparato, non installato e non certificato sulla VPS.
- Copia cifrata age sul PC: PowerShell `ESITO: VERIFICA OK` e chiave pubblica coincidente; prova della copia locale, non del backup/restore VPS.
- Nessun segreto letto o pubblicato. Nessuna trascrizione integrale di chat eliminata e nessuno stato live VPS assunto.

## Blocker e prossime attività

1. Claude/Cloud, come operatore temporaneo scelto dall'utente, deve lavorare soltanto entro autorizzazioni esplicite e riferire SHA, comandi, ambiente e risultati.
2. Rieseguire offline i due test legacy e la suite pertinente sulla PR #121 HEAD `5b7403a…`; non confondere i 5 fail baseline con PASS totale.
3. Progettare una PR draft separata per Issue #124 e dimostrare persistenza cross-restart, file corrotto/assente, I/O failure, mezzanotte UTC, idempotenza e sidecar vivo.
4. Confrontare PR #120 e #123 con la policy LLM desiderata; nessuna integrazione prima di review, privacy/costi, modelli fissati e collaudo shadow.
5. Preservare integralmente Arena e storici; nessun dato Arena nel training finché non verificato e attestato.
6. Nessun merge/deploy/Action/VPS/restart/reset/ordine/API a pagamento senza consenso separato.

## Istruzioni di ripresa

Leggere prima `STATO.md`, questo checkpoint, PR #121/#122/#123 e Issue #124. Considerare Cloud operatore principale solo temporaneamente; ChatGPT consulente e custode del checkpoint. Distinguere sempre fra dichiarato, preparato, verificato offline, approvato e installato. PAPER soltanto; storici ed EventJournal intatti.
