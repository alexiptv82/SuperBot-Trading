# Checkpoint verificabile — 14/11/2026 00:51 Europe/Rome

## Esito sintetico

Novità verificata dopo il checkpoint delle 23:51: il test isolato della patch Brain P0 è stato corretto ed eseguito con **192/192 test PASS in 4,92 s**. L'output dichiara sorgenti pinned e sintassi verificate, stage invariato, pausa preservata e servizio uscite non modificato. La patch resta **non installata**. È stato inoltre preparato un installer guarded con default read-only/check-only, ma non esiste prova accessibile che sia stato eseguito, né in modalità check né apply.

## Fonti e limiti

- GitHub: ramo `diario`, `STATO.md`, ramo `work/brain-exit-observability-20261113`, commit e PR recenti.
- Conversazioni recenti effettivamente accessibili e screenshot Termius forniti dall'utente.
- Nessuna trascrizione integrale delle chat perse e nessun accesso SSH indipendente in questo checkpoint.
- Gli output VPS sono prove puntuali mostrate negli screenshot, non attestazione di stato continuativo o controllo live eseguito qui.
- Library `ULTIMO-STATO-SUPERBOT.md` v97 letta prima dell'aggiornamento.

## Brain — sequenza verificata

### Primo tentativo bloccato

- Screenshot delle 23:47: blob sorgenti e sintassi PASS, ma esecuzione interrotta con `No module named pytest`.
- Il blocco non è un fallimento della logica P0; non produce però alcun PASS di regressione.

### Test isolato completato

- Screenshot delle 00:33 sul commit pinned [`4efd1a31051dd023480d4d9a327016ae9a6f9a0e`](https://github.com/alexiptv82/SuperBot-Trading/commit/4efd1a31051dd023480d4d9a327016ae9a6f9a0e):
  - `SOURCE_BLOBS=PASS`;
  - `SYNTAX=PASS`;
  - pytest 8.4.2 installato esclusivamente in area temporanea;
  - **192 passed in 4.92s**;
  - `RESULT=PASS synthetic_and_regression_only=1 stage_unchanged=1 pause_preserved=1 exit_service_untouched=1`.
- La suite comprende gli otto casi dedicati feed/uscite più regressioni selezionate su monitor, servizio uscite, worker, post-AI guard e chiusura manuale.
- Prova valida per comportamento sintetico e regressioni isolate; non prova installazione, performance economica, edge, fill reali o funzionamento continuativo della VPS.

### Baseline e hotfix preservabili

- Screenshot delle 00:36: checksum SHA-256 identici fra le due copie operative controllate per `monitor.py`, `feed.py`, `contracts.py` e `fetch_candles.py`.
- Il controllo consente di fissare una baseline comune e mostra che gli hotfix precedenti su contratti/candele sono presenti in entrambe le copie.
- È un confronto read-only dei quattro file, non prova di installazione della nuova patch.

## GitHub — preparato, non installato

- Ramo corrente: `work/brain-exit-observability-20261113`.
- Nuovo HEAD verificato: [`1bbdd6e217d230ecbefd96b2207d7dc26a2a1004`](https://github.com/alexiptv82/SuperBot-Trading/commit/1bbdd6e217d230ecbefd96b2207d7dc26a2a1004).
- Differenza rispetto a `4efd1a3…`: un solo nuovo file, installer guarded PAPER-only con hash pinning, verifica pausa/servizi/journal/zero posizioni, backup e rollback.
- Il comportamento predefinito è check-only; l'applicazione richiede opzione esplicita e autorizzazione separata.
- **Non verificato come eseguito:** nessun output `PRECHECK=PASS` o `RESULT=CHECK_ONLY` accessibile.
- **Non applicato:** nessun backup d'installazione creato, nessun file operativo sostituito, nessun restart e nessun heartbeat post-installazione.
- Nessuna nuova PR trovata; nessun merge o GitHub Action.

## Fatto / preparato / rilasciato

- **Fatto:** Brain mantenuto in pausa; test isolato 192/192 PASS; confronto checksum dei quattro file uguale fra le due copie.
- **Preparato:** patch P0 su `monitor.py`/`feed.py`; installer guarded al commit `1bbdd6e…`.
- **Rilasciato/installato:** nulla.
- **Non approvato:** modalità apply, restart, unpause, modifica rischi, riattivazione Falco/Toro.

## Stato desiderato versus implementato

- **Desiderato:** feed uscite fail-closed con posizione aperta e copertura 1m vuota/incompleta; rifiuto di prezzo 1m obsoleto; pausa preservata durante verifica e installazione.
- **Dimostrato offline/isolato:** 192 test PASS sul candidato pinned.
- **Implementato nel runtime:** no; le copie controllate mostrano ancora la baseline precedente comune. La patch candidata non risulta installata.
- **Rischi/configurazioni:** nessuna variazione verificata a capitale, leva, size, stop, TP, budget AI o Guardian.
- L'audit economico/affidabilità Brain precedente resta NO-GO alla certificazione; i test P0 non dimostrano edge.

## Tre portafogli PAPER

- **Brain:** nuove aperture in pausa; ultimo controllo noto runner/exit attivi. Patch P0 testata isolatamente ma non installata.
- **Falco:** congelato, nessuna riattivazione verificata.
- **Toro:** sospeso; PR #99 resta NO-GO strategico e non è stata promossa.

## Backup, chiavi e riferimenti

- Verifica PC copia cifrata age: PowerShell `ESITO: VERIFICA OK` e chiave pubblica coincidente; non certifica backup o restore VPS.
- `work/extbackup-bot-stopped-20261109`: preparato, non installato.
- RC84 [PR #80](https://github.com/alexiptv82/SuperBot-Trading/pull/80) resta riferimento storico; non autorizza installazione.
- Solo PAPER; storici ed EventJournal preservati. Nessun segreto o dettaglio d'accesso registrato.

## Blocker e prossimo passo

1. Eseguire, solo con autorizzazione operativa separata, la modalità **check-only** del commit `1bbdd6e…`; conservare output completo `JOURNAL=OK`, zero posizioni, candidate syntax/hash e `RESULT=CHECK_ONLY no_stage_changes=1 no_restart=1`.
2. Non usare `--apply` senza nuovo consenso esplicito.
3. Prima di un'eventuale applicazione: review del diff, conferma zero posizioni, backup/rollback e pin esatto.
4. Dopo un'eventuale installazione separatamente autorizzata: attestare checksum candidati, pausa ancora presente, servizi attivi, heartbeat e scenari feed vuoto→degraded/feed completo→healthy.
5. Non dedurre redditività o riattivare portafogli dai soli test sintetici.

## Vincoli invariati

Solo documentazione in questo checkpoint. Nessun merge, deploy, GitHub Actions, VPS, reboot, restart, reset, ordine, wallet o API a pagamento. Trading esclusivamente PAPER; storici ed EventJournal preservati.
