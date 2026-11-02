# SuperBot V3 — 2026-11-02 F0 access gate + local operator CLI

## Autorizzazione e limiti
Utente «ok perfetto procedi». Continuato lo sviluppo isolato su `work/v3-foundations-event-risk-20261102`, PR #29 DRAFT. Nessun contatto con la VPS, SSH, API exchange, modifica ai dati reali, reset, merge, deploy o riavvio di Falco/Toro/Brain. Non descrivere lo stato corrente dei worker come verificato oggi da questo checkpoint.

## Riscontri GitHub
- PR #29 aperta, DRAFT, mai integrata.
- F0 CI finale https://github.com/alexiptv82/SuperBot-Trading/actions/runs/41512040185 **96 test PASS Python 3.10 e 96 test PASS Python 3.11**. Test su fixture sintetiche.
- Audit statico mirato dei workflow presenti sul ramo rileva altri accessi `root@Singapore` in `sg-extbackup-watch.yml` (sentinella), `v3-vps-inventory.yml` e `v3-stop-paper-workers.yml`; NON disattivati per evitare rotture a monitoraggio/maintenance. Il vecchio workflow pericoloso V3 root era stato rimosso dal ramo. Chiave SSH root ancora da ruotare/restringere: non si può considerare messa in sicurezza dal solo diff.
- Nessuna possibilità diretta di SSH con privilegi minimi verificata via connector.

## Nuovo codice
- `backend/v3/f0_cli.py` ha comandi `observe-brain`, `capture-brain`, `verify-brain`, `observe-classic`, `verify-classic`, usando soltanto filesystem locale e moduli V3; mai crea workflow SSH o legge segreti. Per il ripristino richiede prova esterna separata e rifiuta witness dentro directory ripristinata.
- `backend/tests/test_v3_f0_cli.py`: prove interfaccia CLI indipendente per Brain e Falco/Toro, witness falso/mancante/portafoglio sbagliato, fail closed senza log di dati sorgente.
- `backend/v3/f0_classic_certificate.py`: witness completo dei dati contabili già inclusi più **`lessons.md` obbligatorio** e **`errors.md` facoltativo ma con presenza/assenza autenticata**. La memoria didattica resta preservata, non ancora importata.
- Test F0 su perdita/alterazione `lessons.md` aggiunti. Il verificatore Brain certifica solo `brain.sqlite3` e non altri file di apprendimento eventualmente adiacenti.
- Runbook aggiornato: `docs/v3/f0-backup-certification-runbook.md`.
- Procedura accesso minimo: `docs/v3/f0-operator-access-gate-20261102.md`, prevede account OS separato senza sudo o Docker, ACL limitate, sorgente fermata autenticata, destinazione backup separata, witness indipendente e copia cifrata fuori host. Nessun account nuovo o credenziale creata realmente.

## NO-GO residuo
1. Stato attuale servizi e percorsi autoritativi non ricontrollati via accesso segregato.
2. Non eseguita cattura reale Brain con backup SQLite API e controllo WAL/COUNT/MAX(seq) della fonte; precedente conteggio di 8447 da backup non è attestazione WAL-completa.
3. Non presente un archivio post-stop cifrato fuori VPS ripristinato e validato su macchina separata.
4. Lezioni classici coperte dai test ma gli archivi reali non hanno ancora superato i nuovi gate F0; tutti gli altri file Brain fuori SQLite ancora da inventariare.
5. Nessun import persistente di eventi né saldi in V3; capitale nuovo PAPER 1000/1000/1000 NON assegnato.
6. Accessi legacy root/chiavi e altri workflow necessitano di piano graduale di rotazione per non rompere backup e sentinelle.

## Prossima azione fattibile
Un operatore autorizzato prepara identità OS F0 a permessi minimi senza riutilizzare SSH root via Actions, raccoglie i witness sul database fermo, trasferisce copia cifrata su host esterno e produce evidenza di restore; solo allora eseguire verifiche e discutere GO con Claude/Grok. L'utente deve approvare la configurazione delle credenziali prima delle modifiche operative.
