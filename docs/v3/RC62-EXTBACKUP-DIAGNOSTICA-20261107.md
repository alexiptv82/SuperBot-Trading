# SuperBot V3 — diagnosi backup esterno in sola lettura (7 novembre 2026)

Stato: **NO-GO** per deploy/avvio; progetto PAPER. Questo documento non autorizza alcun riavvio, reset, merge, pulizia di storage o modifica del servizio.

## Evidenza di partenza (GitHub Actions, 6 novembre)

- RC #62; audit VPS `42295014067` eseguito 2026-11-06 21:14 UTC: `superbot-extbackup.service` **failed**, `Result=exit-code`, `ExecMainStatus=1`, timer active, status.json presente con errore, ultimo successo **2026-11-02T03:28:45Z**.
- Alert backup `42217335679`: messaggio compatibile sia con **finestra di fine ciclo non verificata** sia con **file indispensabili mancanti**. La stringa non permette di attribuire univocamente la causa.
- L'audit ha rilevato i worker legacy Hawk/Bull fermati, storici 6 e 2 posizioni PAPER rispettivamente, pausa attiva; backup locale con restore temporaneo verificato. Nessuna attestazione di backup cifrato *off-host* recente.
- Il codice storico `deploy/scripts/backup_brain.py` distingue il percorso normale (heartbeat con fine ciclo verificabile) dalla modalità `--bot-stopped`, che è ammessa **solo** dopo verifica che i container siano realmente spenti, heartbeat assente o vecchio (>120 s), file centrali in quiete e file required presenti. Non avviare questa modalità alla cieca; l'unità effettivamente installata potrebbe avvolgere lo script e avere verifiche ulteriori.

## Diagnostica proposta

Il workflow `.github/workflows/v3-rc-extbackup-readonly-diag.yml`, sul ramo di audit dedicato, esegue SOLO:
1. interrogazioni read-only `systemctl show/is-active/is-failed` e `docker inspect`;
2. presenza, tipo e età (non contenuto) dei file richiesti per Hawk/Bull;
3. struttura booleana di `status.json` con categoria di errore filtrata senza mostrare il testo;
4. indicazione se la firma del servizio include *esplicitamente* `--bot-stopped` (non prova che lo script interno lo usi);
5. verdetto dei prerequisiti, **non una riparazione**.

Non stampa unit file, environment, chiavi, token, log grezzi, stato dei trade o contenuti delle posizioni. Non esegue `docker start/stop`, `systemctl start/restart`, scritture, backup o cambio di configurazione.

## Decisione successiva

- Se il controllo dice file obbligatori assenti, NON usare `--first-install` né escludere file: identificare il percorso reale e riparare preservando lo storico.
- Se tutti i prerequisiti `--bot-stopped` risultano soddisfatti, prima verificare **privatamente** la configurazione reale di `external_backup.py`, il percorso off-host e i controlli di cifratura; un singolo flag non garantisce un backup verificato.
- Se qualsiasi container è attivo, heartbeat fresco, scrittura recente o stato non verificabile, non bypassare alcun controllo: classificare il proprietario dello storage e ottenere uno snapshot consistente.
- Solo dopo diagnosi: proporre una correzione separata, un nuovo backup cifrato remoto e **restore isolato con checksum di origine/destinazione**, senza contaminare gli storage legacy. Anche con un backup nuovo, il cutover e la dashboard restano NO-GO fino ai test di integrazione e un OK specifico dell'utente.

**Importante:** il workflow può eseguire un audit SSH read-only tramite la chiave già memorizzata in GitHub Actions; non autorizza nessuna modifica ai servizi della VPS.

## Verifica live in sola lettura — 7 novembre 2026, 08:25–08:28 UTC

- Job riusciti: [prima diagnosi #42355443692](https://github.com/alexiptv82/SuperBot-Trading/actions/runs/42355443692) e [ricognizione wrapper #42355601791](https://github.com/alexiptv82/SuperBot-Trading/actions/runs/42355601791), senza scritture o modifiche dei servizi.
- `superbot-extbackup.service`: stato **failed**, exit-code 1, timer attivo, successo più recente 2 novembre (124 ore prima dell'audit), ultimo tentativo circa 5 ore prima.
- `superbot-desk-hawk`, `superbot-desk-bull`: **exited**; heartbeat assente/fresco? Entrambi **stale >120s**, file centrali stabili da almeno 10s.
- **8 file REQUIRED su 8 PRESENT**: `state_v2.json`, `trade_history.jsonl`, `learning_log.jsonl`, `lessons.md` per Hawk e Bull. Questo controllo verifica presenza e tipo, non la validità semantica di ogni archivio.
- Tutte e quattro le precondizioni base del percorso bot spenti sono soddisfatte: container fermati, heartbeat non recenti, file obbligatori presenti e file centrali quieti.
- Il comando `ExecStart` del servizio NON contiene la stringa `--bot-stopped`; nel solo script Python/Shell osservato sotto `/opt/superbot-extbackup` non compaiono né `backup_brain` né `--bot-stopped`. Il file helper del checkout su VPS, invece, **contiene** il supporto al flag. Questi sono indizi e NON una prova di come il wrapper invochi davvero lo script: non sono stati letti/mostrati i comandi completi o la configurazione privata.
- La categoria dell'ultimo errore rimane **ambigua** (`BOUNDARY_OR_MISSING_FILES_AMBIGUOUS`). Dato che oggi i file risultano presenti, diventa prioritario verificare **quale comando/pipeline il servizio usa realmente** e se tenta di applicare erroneamente il controllo di fine ciclo a bot spenti.

**Decisione:** la modalità a bot fermati è *candidata per un successivo intervento supervisionato*, non è stata attivata e non è stata dichiarata la guarigione del backup. Servono ancora la verifica privata dell'entrypoint effettivo, un backup cifrato off-host verificato e un ripristino isolato. I bot rimangono spenti e la PR #62 resta NO-GO.
