# AI Arena — Accesso al socket di chiusura dal container web (17 novembre 2026)

**Ramo di sviluppo**, non distribuito. Questo documento riguarda solo il bridge di chiusura manuale PAPER creato nella PR #102, non il trading LIVE.

## Problema e soluzione opt-in

La versione della PR #102 avvia il bridge host come root con parent `/run/superbot-arena-close` permessi `0700` e socket `0600`. Un backend web eseguito con UID non-root in un altro container non può attraversare il parent né connettersi al socket; una chiamata in UI risulterebbe `arena_bridge_unavailable`. I test con stesso UID non dimostrano il collegamento host-container.

Questa patch mantiene la modalità di default root-only (`parent 0700`, socket `0600`), e aggiunge **solo sul bridge host** un flag opzionale:

```
V3_ARENA_CLOSE_GROUP_GID=<GID numerico di un gruppo dedicato>
```

Con flag impostato, il bridge **richiede**:
- directory `/run/superbot-arena-close` reale, non symlink, proprietario `root`, gruppo GID dedicato e modo **0710** (`rwx--x---`);
- il socket è creato da root, poi impostato `root:GID` modo **0660** (`rw-rw----`);
- il processo web deve avere il GID nel proprio elenco di gruppi supplementari **effettivo nel namespace del container** e deve vedere il socket tramite un mount puntuale;
- nessun permesso `0777`/world e nessuna necessità di eseguire il web come root.

Il GID **non è scelto dal codice** e il programma non crea gruppi, non modifica la directory e non avvia servizi. Se il flag è scorretto o la directory non ha ownership/permessi attesi, il bridge rifiuta l'avvio.

## Checklist operativa prima dell'installazione (solo lettura fino ad autorizzazione)

1. Identificare l'utente effettivo del backend nel container (`id -u; id -G`) e i gruppi/GID disponibili sull'host; controllare eventuale user-namespace remapping. Non presupporre che un GID host abbia lo stesso numero nel container.
2. Dopo autorizzazione e prima dell'abilitazione manual close, un amministratore prepara **fuori dal repository** il gruppo dedicato e la directory root:GID modo 0710. Un gruppo esistente condiviso con altri servizi non va riutilizzato.
3. Montare soltanto il path necessario nel container e aggiungere il GID al processo web. Mantenere i journal in sola lettura lato web e il socket host separato dal bridge storico.
4. Avviare il servizio bridge esclusivamente in PAPER e con l'opzione GID impostata dall'amministratore; verificare `stat -c '%a %u %g %n'` della directory e del socket.
5. **Smoke test usando l'UID/GID del vero processo web**, dentro il container: creare un socket AF_UNIX e chiamare `connect('/run/superbot-arena-close/arena.sock')`. Il solo successo della connessione dimostra trasporto/permessi, **non** l'abilitazione della chiusura manuale né la salute dei servizi uscite. Eseguire poi test di richiesta su una posizione PAPER sintetica con exit-worker e journal, mai sul Brain storico.
6. In caso di errore: lasciare `V3_ARENA_ALLOW_MANUAL_CLOSE` disabilitato. NON allargare i permessi, NON eseguire web come root, NON inoltrare a `/api/v3/brain/close`.

## Test

`python -m pytest -q backend/v3/arena/test_socket_access_policy.py` — nuovo test puro di default root-only, validazione GID, ownership e permessi di directory/socket, rifiuto symlink. **Non ancora eseguito su VPS o nel container di produzione.**

Non sono stati effettuati deploy, spese AI, attivazioni di runner o modifiche ai classici. La PR #102 può mantenere le sue modifiche originali mentre questo fix viene revisionato a parte.
