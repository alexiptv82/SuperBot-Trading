# SuperBot V3 — runbook PR #65: chiusura PAPER legacy dall'app (7 novembre 2026)

**Stato: DRAFT / NON INSTALLATO / NO-GO operativo.** Questa documentazione non autorizza il deploy, l'avvio dei worker o la chiusura di trade. Non si tocca la PR #62, i mandati Brain o le nuove run V3.

## Perché serve

Alla verifica del 6/11, i contenitori legacy erano fermati con **6 posizioni PAPER Falco e 2 Toro**. Il vecchio worker non consuma le richieste dell'app, quindi il pulsante può restare senza effetto. La PR #64 impedisce comandi ritardati a bot spenti; la PR #65 aggiunge un consumer di **sole chiusure**, separato dall'algoritmo, che non apre posizioni e non consulta Claude.

## Verifiche necessarie prima di una futura attivazione (richiede OK espresso)

1. **Nessuna posizione LIVE.** Confermare DESK_MODE=paper nel processo, nella configurazione e nell'interfaccia. Il nuovo worker rifiuta qualsiasi modalità diversa.
2. **Inventario immutabile.** Registrare il numero/ID delle posizioni legacy e gli SHA di `state_v2.json`, `trade_history.jsonl`, `learning_log.jsonl`, `lessons.md` per Falco/Toro. Non spostare né azzerare lo storico; non usare vecchie directory per la nuova run.
3. **Snapshot locale fresco e ripristino isolato.** Creare snapshot fuori dalla directory dati per ciascun portafoglio (quattro file essenziali almeno, più archivio completo/SQLite se presenti); validare la copia con hash e prova di restore temporaneo. Il worker rifiuta l'avvio se uno dei quattro file essenziali non è *byte-identico* allo snapshot; per riavviarlo dopo una chiusura occorre uno snapshot aggiornato.
4. **Unico writer.** Dimostrare via `docker inspect` che `superbot-desk-hawk` e `superbot-desk-bull` sono stopped e hanno **RestartPolicy=no** prima di avviare i servizi exit-only, e ad ogni tick. Se non sono così, STOP. La modifica di restart policy è un'operazione VPS distinta, da autorizzare.
5. **Pausa e richieste arretrate.** `pause.flag` presente e nessun `reset.flag`, `reset.flag.work`, `close_position.flag` o `close_position.flag.work` preesistente. Qualsiasi flag presente richiede riconciliazione manuale, **mai cancellazione automatica**.
6. **Web mount e autenticazione.** La nuova web app deve montare le directory storiche corrette in modalità PAPER, essere aggiornata alla PR che integra la lettura di `exit_only_heartbeat.json`, e preservare l'accesso autenticato. Prima delle nuove run, controllare sul telefono la vista Falco/Toro/Brain, i prezzi e la distinzione “solo chiusure PAPER”.
7. **Test su dati copiati.** Eseguire prove di una singola chiusura, chiusura totale, prezzo non disponibile, doppio clic, restart, processo concorrente e PnL con commissioni/slippage, usando esclusivamente uno storage sandbox.
8. **Autorizzazione alla chiusura.** L'utente decide i trade da chiudere nell'app: clic singola/tutte + conferma. Non chiudere per default le otto posizioni. Verificare `closed_by=utente`, `manual_learning` e il PnL NETTO nel registro, poi mantenere il vecchio storico separato.

## Comando tecnico di riferimento (NON eseguire senza tutti i gate)

L'applicazione Python viene eseguita in un processo supervisionato separato. Esempio illustrativo per **Falco**:

```bash
DESK_MODE=paper DESK_PORTFOLIO=hawk DESK_DATA_DIR=/opt/superbot-desk-data/hawk \
PYTHONPATH=/opt/superbot-v3-rc65-src/backend \
python3 -m desk.exit_only --portfolio hawk \
  --data-dir /opt/superbot-desk-data/hawk \
  --snapshot-dir /opt/superbot-backups/rc65-new-hawk-snapshot \
  --start-paper-exit-only
```

Il percorso del checkout e dello snapshot è un esempio, non una risorsa già presente sulla VPS. Usare una configurazione PINNED a uno SHA dopo verifica. Per Toro sostituire `bull` e la directory. **Non** richiamare `desk.cli --once`, `loop_step`, `process_flags`, avvio dei vecchi container o il comando di reset: quei percorsi potrebbero eseguire la logica di trading e non sono necessari.

## Contratto tecnico

- `exit_only_heartbeat.json`: pubblica `ready=true` soltanto finché la verifica di fermo/pausa è soddisfatta; la web accetta il segnale solo se recente (meno di 12 s), PAPER e portafoglio corretto.
- File-comando singola/tutte con scadenza di 10 minuti e claim atomico in `.work`; richieste sovrapposte vengono rifiutate. Un `.work` rimasto richiede riconciliazione prima del riavvio, mai esecuzione cieca.
- Prezzo da candela pubblica Bitget Futures 1 minuto fresca (entro 120 s), mai da cache di giorni precedenti. Senza prezzo valido la posizione resta aperta, segnalando errore.
- Il motore contabile è quello storico: `PaperAccount.close` (fee, slippage, funding), `closed_by=utente`, `manual_learning=profit_protection_example` per netto positivo; un esempio non diventa automaticamente una strategia convalidata.
- **Nessuna chiamata a `run_cycle`, Claude, scanner, DCA, nuove aperture o reset.** Se il worker o il comando si interrompono a metà, usare prima snapshot e riconciliazione manuale di conto/storico; non ripetere automaticamente un comando.

## Fuori dal perimetro di questa PR

Non viene installato il servizio systemd, non si aggiorna Docker, non si pubblica la web app e **non si chiude alcuna posizione**. Le nuove run restano separate: Falco/Toro 1.000 USDT PAPER ciascuno, Brain 2.000 USDT PAPER con politica di rischio approvata nella RC. Il backup esterno cifrato resta raccomandato; per l'esperimento PAPER può essere differito solo con decisione documentata e rischio residuo accettato, mai saltando lo snapshot locale precedente.
