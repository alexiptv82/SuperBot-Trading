# Brain PAPER — rilascio web-only della correzione Chiudi trade (15/11/2026)

**Stato:** procedura preparata, **non eseguita** sulla VPS. Nessun merge, GitHub Action, riavvio dei servizi di trading o ordine eseguito da questa modifica.

## Evidenze reali

- Audit VPS: le tre unit `superbot-v3-paper-brain-runner`, `superbot-v3-paper-brain-exit` e `superbot-v3-paper-single-close-bridge` sono attive, il socket bridge esiste, la cartella Brain e' montata `ro`.
- `lock_O_RDWR=ERRORE_EROFS`, `lock_O_RDONLY=apribile lease_tenuto_dal_servizio=1`, `uscite_sane_viste_dal_web=False`, `chiusura_brain_consentita_vista_dal_web=False`.
- Preflight del 15/11 15:56 UTC: `/api/health=200`; target `exit_service.py` nello stage e' pulito; quattro altri file locali modificati e da preservare.
- Preparazione del 15/11 17:07 Europe/Rome: immagine candidata `superbot:brain-close-ro-candidate-20261115` (ID sha256:`bb914acdb7d02b55f6c51a27351fa98f69503d5632826af67758e1c11d501366`), test import Python isolato senza rete PASS, web corrente intatto.

## Strategia di rilascio

`deploy/scripts/brain-close-ro-publish-20261115.py` espone `--preflight` e `--publish`:

1. Impone image SHA pinned per web originale e candidato, esamina porte/mounts/env/policy PAPER e le identita' PID delle unita'.
2. Ricrea **soltanto** il container `superbot` da un'immagine derivata dall'immagine in uso; passa tutti gli stessi volumi e variabili d'ambiente tramite un file privato temporaneo in `/run`, da eliminare a fine rilascio.
3. Rinomina e conserva l'originale `superbot-before-brain-close-ro-20261115` fermo e senza restart automatico. Non altera i file dello stage VPS.
4. Esegue controlli di salute, endpoint non autenticati protetti, readiness `_brain_single_close_ready=True`, identita' PID delle tre unita', identita' dei volumi e env invariati.
5. Su fallimento, elimina il nuovo container e tenta il ripristino del web precedente; in caso di recupero incompleto stampa chiaramente l'esigenza di controllo manuale.

### Esecuzione prevista (solo da operatore VPS)

Scaricare il file dalla revisione esatta, validare `python3 -m py_compile`, eseguire `--preflight` in sola lettura, quindi `--publish` solo dopo autorizzazione consapevole del breve riavvio della dashboard web.

Nessun cambio di leva, stop, posizioni, sospensione/riavvio servizi Brain, Falco o Toro. `--publish` comporta una breve interruzione della sola dashboard web. **Non avviare altre operazioni Docker simultaneamente.**

### Ripristino

In caso di errori durante il cutover, il codice tenta il rollback automaticamente. Dopo un successo, il vecchio container rimane fermo sotto `superbot-before-brain-close-ro-20261115`, per ripristino manuale se necessario. Non cancellarlo senza collaudo utente.

## Limiti

- Lo script di pubblicazione e' stato revisionato staticamente ma **non ancora eseguito** sulla VPS; nessun test CI avviato per non consumare minuti GitHub.
- Il file `frontend/src/components/OverviewCloseControls.js` del ramo Fable contiene anche miglioramenti dell'interfaccia, ma questa immagine candidata modifica **solo il backend**: la priorita' e' abilitare il pulsante che gia' esiste.
- Se il container e' cambiato rispetto agli ID verificati, il preflight deve rifiutare la sostituzione.
