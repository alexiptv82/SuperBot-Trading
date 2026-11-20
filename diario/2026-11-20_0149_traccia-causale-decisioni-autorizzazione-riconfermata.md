# Checkpoint verificabile SuperBot — 20/11/2026 01:49 Europe/Rome

**Tipo:** delta consolidato rispetto al checkpoint 19/11/2026 21:48.  
**Ambito:** documentazione e verifica; trading esclusivamente PAPER.

## Esito sintetico

Sono confermate due novità successive al checkpoint precedente:

1. Il proprietario ha riconfermato l'autorizzazione temporanea e revocabile a sviluppare e integrare **solo** in `integration/brain-unico-20261119`, con test prima/dopo, zero regressioni, documentazione e rollback. Restano esclusi `main`, rami operativi, deploy, VPS/servizi, restart, reset, parametri attivi, nuove spese API e LIVE. La riconferma è registrata nel commit documentale `04871e8d879a71a3d402076bb21b2fa78adee329`.
2. Il ramo laboratorio è avanzato da `dd414831ef329ab1bc34d517dffffb85731af5bc` a `a5a920401e0259c63a316ceb6eea573b4a12ac8a`: ogni decisione Brain, comprese le NO_TRADE, riceve uno snapshot v2 dopo la decisione e prima di un'eventuale apertura. Il commit documentale `0084250007143cfb99f0cefeffe94469155c000e` registra evidenze e test riferiti.

Nessun deploy o stato live VPS è stato verificato in questa esecuzione.

## Obiettivo e tre portafogli PAPER

- Obiettivo: Brain Unico PAPER con memoria/eventi preservati, decisioni tracciabili, rischio fail-closed e confronto LLM isolato; nessun passaggio LIVE implicito.
- **Falco:** storico e logica SHORT preservati; consulente non bloccante del Brain. Nessun reset o parametro operativo nuovo attestato.
- **Toro:** storico preservato come archivio/benchmark; nessun reset o parametro operativo nuovo attestato.
- **Brain:** capitale di riferimento PAPER 2.000 USDT; laboratorio isolato ora @ `a5a92040…`. Brain Unico non risulta deployato. Arena, EventJournal, memorie, decisioni, trade, posizioni, NO_TRADE e scoreboard vanno conservati integralmente.

## Configurazione e rischio — desiderato vs implementato

- Desiderato: DeepSeek decisore principale; advisor economici fissi in shadow/non bloccanti; niente auto-routing o fallback silenzioso. PR #120 resta non conforme e non integrata; PR #123 resta laboratorio shadow.
- Desiderato: scalp intraday, leva 20–50× e rischio 1–1,5% compatibili solo con sizing/margine risk-first. Il conflitto resta pretendere insieme margine fisso elevato, leva alta, stop largo e basso rischio monetario.
- Implementato/attuale documentato: soglie 35% WARN, 50% HALT e hard floor 450 USDT invariati. Nessuna leva, size, stop, soglia o capitale runtime modificati.
- Snapshot v2 di `a5a92040…`: `inputs_verified=false`, `eligible_for_training=false`; ammessi alla catena causale ma esclusi dal training finché non validati indipendentemente.

## Traccia causale Brain @ a5a92040

Il commit collega il ciclo reale a una traccia obbligatoria:

- ordine journal: decisione → snapshot → eventuale `paper_open`;
- feature soltanto da candele chiuse entro l'istante decisionale;
- NO_TRADE, rifiuti rischio e AI indisponibile inclusi;
- snapshot deterministici/idempotenti; ambiguità non indovinate;
- fallimento di traccia esplicito; una OPEN approvata viene bloccata con `open_blocked_untraced`;
- copertura misurabile dal solo journal;
- RiskManager ed ExitService restano indipendenti.

Limite documentato: una finestra di circa 120 secondi con evento sidecar concorrente può far rifiutare lo snapshot; l'effetto dichiarato è fail-closed (nessuna apertura nel giro), da misurare nel collaudo PAPER.

## Test e fonte

Risultati **riferiti dal commit/diario Claude**, verificati come documentazione Git ma non rieseguiti qui e non attribuiti a GitHub Actions o VPS:

- suite V3 `5121 → 5147`, 1 skipped, 0 falliti;
- Dataset Builder 134 OK;
- mutazioni 10/10;
- 26 test aggiunti per causalità, candele chiuse, NO_TRADE, idempotenza, fallimenti, copertura, indipendenza rischio/uscite ed esclusione training;
- rollback documentato: commit singolo reversibile.

P0 #124 resta open. La correzione precedente `a177729107231199f802f38e5592ab6e5373ea48`, integrata via `cc35f532…`, rimane il riferimento contro il fail-open di riavvio; nessun nuovo cambiamento P0 rilevato.

## Branch, PR e SHA verificati

- `diario` prima di questo checkpoint: `0084250007143cfb99f0cefeffe94469155c000e`.
- `integration/brain-unico-20261119`: `a5a920401e0259c63a316ceb6eea573b4a12ac8a`.
- PR #80 RC84: open/draft @ `0e29a73a36f668643da4088178bacb8616a45ac0`.
- PR #120: open/draft @ `f4f745788e4514d01dc11e11402eb689a2ec7c74`, non integrata.
- PR #121: open/draft @ `5b7403aa333b43d801ca7e28825ea4707f6847b4`.
- PR #122: open/draft @ `513448e57747f381e11ce23ab09788d6a41e6cb0`.
- PR #123: open/draft @ `c51c7520b35640518baea217404da9657702d4f5`; contenuto integrato solo nel ramo laboratorio.
- Issue #124: open.
- Extbackup: `work/extbackup-bot-stopped-20261109` @ `3dc2116a08058f57fc14b695431f6e3fa1a1ca45`.

## Servizi, backup e chiavi

- Nessun controllo live VPS svolto qui; non inferire servizi attivi, installazioni o deploy.
- Extbackup resta **preparato sul ramo ma non certificato come installato o funzionante end-to-end**. Un timer precedentemente riferito è informazione non verificata in questa esecuzione; versione, contenuto, cifratura, copia off-host e restore restano da provare.
- Copia cifrata della chiave age sul PC: output PowerShell `ESITO: VERIFICA OK`; chiave pubblica derivata coincidente. È prova locale della copia cifrata, **non** certificazione del backup o restore VPS.
- Nessuna chiave privata, passphrase, token o segreto letto o pubblicato.

## Eseguito, preparato, non approvato

- **Eseguito e verificato come Git:** riconferma documentale autorizzazione; commit laboratorio `a5a92040…`; aggiornamento diario `0084250…`.
- **Preparato/laboratorio, non operativo:** traccia causale decisioni, snapshot v2 non verificati per training, laboratorio LLM #123, studio rischio v2.
- **Non approvato/non eseguito:** merge su `main` o rami operativi, deploy, Actions, modifiche VPS/servizi, restart, reboot, reset, ordini, provider/chiavi, API a pagamento, training reale, restore, conclusione Arena e LIVE.

## Blocker, prossime attività e istruzioni di ripresa

1. Validare indipendentemente le feature degli snapshot ricalcolandole da copie attestate delle candele; fino ad allora restano escluse dal training.
2. Review indipendente di `a5a92040…` e replica offline dei test, compreso il caso concorrente oltre 120 secondi.
3. Mantenere P0 #124 open fino alla chiusura formale e alla validazione prevista; nessun deploy.
4. Proseguire con anti-reingresso tramite `thesis_id` persistente ed etichette esiti solo nel ramo autorizzato e con i gate registrati.
5. Riprendere da `STATO.md`, `AUTORIZZAZIONI.md`, `diario/2026-11-20_claude-traccia-decisioni.md`, registro integrazione e questo checkpoint.
6. Distinguere sempre: verificato Git, test riferito, test replicato, Actions, VPS, preparato, integrato in laboratorio, installato, deployato e live.

Questo checkpoint non ha modificato codice operativo, servizi o trading; conserva integralmente storico e EventJournal.
