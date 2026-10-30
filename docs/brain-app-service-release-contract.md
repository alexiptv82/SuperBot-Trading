# Brain e app: contratto di rilascio PAPER

Questo documento prepara la distribuzione; non abilita servizi né inizializza conti.
Il conto e i limiti devono provenire da un mandato completo approvato, mai dalle fixture.

## File condivisi

| Servizio Brain | App | Accesso richiesto |
|---|---|---|
| BRAIN_SINGLE_SNAPSHOT_PATH | BRAIN_SCALP_SNAPSHOT_PATH | Brain scrive atomicamente; app legge |
| conto unico schema 2 | BRAIN_SCALP_LAYOUT=single | Identità brain-scalp-single-paper |
| BRAIN_OPERATOR_REVIEWS_PATH | BRAIN_OPERATOR_REVIEWS_PATH | Stesso JSON pubblicato; app sola lettura |
| BRAIN_OPERATOR_INBOX_PATH | BRAIN_OPERATOR_INBOX_PATH | Stesso SQLite separato dal wallet, API accoda e owner consuma |
| BRAIN_SINGLE_DATA_DIR | Nessun mount scrivibile del wallet necessario | Un solo owner del conto |

I percorsi interni ai container possono essere diversi ma devono riferirsi agli
stessi file host. Il JSON usa sostituzione atomica: condividere la directory,
non un bind mount del solo file che potrebbe restare legato al vecchio inode.
SQLite inbox richiede una directory scrivibile condivisa e compatibile con
locking SQLite, separata dai JSON pubblici e dal wallet.

L'app richiede BRAIN_OPERATOR_ALLOWED_ORIGIN esattamente uguale all'origine
HTTPS della PWA. POST autenticata con header X-Brain-Operator; la ricevuta
pending indica accodamento, confirmed indica elaborazione dell'owner.
Il JSON review scade dopo 120 secondi; una conferma in coda dopo 120 secondi
non viene eseguita. Processing/needs_reconciliation non vengono ritentati.

## Analisi AI e osservazioni

DeepSeek primario e revisore Claude richiedono configurazione esplicita,
modello Claude e chiave accoppiati, prezzi token e budget. La configurazione
non dimostra la disponibilità o il credito dei provider.
Le conferme vengono consumate dopo supervisor.step; gli esempi vengono
ricaricati nello stesso tick e sono disponibili all'analisi del tick successivo.
Il recovery periodico li rilegge anche senza riavvio. Nessuna chiamata AI extra.

## Sequenza da certificare prima del rilascio

1. Fissare mandato conto, budget/provider/modelli, percorsi e proprietari file.
2. Verificare backup e restore in ambiente isolato, senza sovrascrivere storici.
3. Collaudare il servizio con feed pubblico e configurazione definitiva.
4. Verificare snapshot fresco, conferma yes/no e receipt dall'app autenticata.
5. Preparare versioni esatte e rollback; ottenere OK separato al rilascio.

Una nuova sessione PAPER non cancella o fonde i conti precedenti.
Gli avvisi strutturali restano consultivi; la loro abilitazione deve essere
esplicita nel pacchetto e non cambia punteggi o obbliga aperture.
