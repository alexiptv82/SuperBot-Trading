# Reset e ripartenza PAPER di Falco Evoluto e Brain Scalp (23/11/2026)

Autorizzazione del proprietario (23/11): reset reale dei due portafogli PAPER e riattivazione, solo PAPER.
Codice: commit `364edd3e` (ramo `claude/limiti-paper-20261123`), `deploy/falco-evoluto/reset/`.

## Nuovi portafogli
| | Falco Evoluto | Brain Scalp |
|---|---|---|
| Capitale iniziale | 1.000 | 2.000 |
| Avviso / stop giornaliero | 6 % / **12 %** | 15 % / **25 %** |
| Guardian, perdita di sessione | 12 % | 25 % |
| Floor assoluto di equity | 800 (invariato) | **1.400** (era 1.600) |
| Guardian, blocco per drawdown globale | 20 % (invariato) | **30 %** (era 20 %) |
| Guardian, rischio dimezzato | 10 % | 10 % |
| Rischio per trade / aperto, leva | 4 % / 10 %, 15–45× | 4 % / 10 %, 15–45× |
| Protezione dei profitti | attiva (8 %, 75 %) | attiva (8 %, 75 %) |

Primo blocco reale dal capitale pieno: Falco a 880 (−12 %), Scalp a 1.500 (−25 %); anche dopo +20 % lo stop giornaliero
resta il primo blocco. Floor e blocco globale restano come sicurezza sotto lo stop (Scalp 1.400 = −30 %).
Dopo una giornata a −10 % il floor arriva prima dello stop (Falco −11,1 %, Scalp −22,2 %).

**Mandati:** mandati nuovi, uno per run, legati alla politica di rischio della run nuova (Scalp ha un'impronta nuova
perché il floor cambia). Approvati dall'attivazione standard (`80-paper.sh attiva`) con il nome di chi aveva
approvato i mandati precedenti; la procedura verifica che il mandato sia valido per la configurazione nuova.

## Cosa fa la procedura (`reset_paper.py --esegui`, root)
1. Preflight senza modifiche: impronte del pacchetto installato (come `superbot-ops`), codice installato unico,
   Brain RC1 in pausa, unità attive, web in esecuzione, configurazioni nuove con impronte bloccate e stop utilizzabile,
   journal attuali integri (copia in sola lettura), nome di chi approva, spazio su disco, chiave AI.
2. Pausa delle nuove aperture nelle run attuali; attesa che il giro in corso finisca.
3. Chiusura delle posizioni PAPER ancora aperte dal canale manuale ufficiale (servizio uscite della run, prezzo
   dell'ultimo minuto), verifica nel journal, contabilità finale.
4. Arresto di runner e uscite delle run attuali (nessuna sovrapposizione con i nuovi).
5. Archivio integrale: il contenuto di ogni run viene SPOSTATO in `/opt/superbot-v3-paper-runs/.archivio/reset-<data>/`
   con l'impronta di ogni file (verificata dopo lo spostamento), il journal ricontrollato e `RISULTATI.json`.
   Journal, budget, memoria del freno, mandato, configurazione, posizioni e risultati restano tutti lì, per l'audit
   dell'8,2 % e per lo studio successivo.
6. Run nuove preparate dal codice installato (`prepare_paper_run`): capitale pieno, journal nuovo con il solo evento
   di preparazione, in pausa, mandato da approvare. Stesse cartelle e stessi run_id: web, bridge, unità systemd,
   interfaccia e `superbot-ops` non cambiano.
7. Avvio di uscite (attesa «sane») e runner.
8. Sonda nel container web vero: solo i due portafogli, capitale pieno, 0 chiusure, nessuna posizione, nessun dato
   precedente al reset, stop della configurazione nuova, «chiudi tutte» rifiutata, chiusura singola instradata alla
   SUA run.
9. Attivazione PAPER (`80-paper.sh attiva`), attesa di RUNNING, seconda sonda.

Blocchi: prima dell'archivio la procedura si ferma con le run attuali intatte e in pausa; durante archivio,
preparazione, avvio o prima sonda torna da sola alle run precedenti (in pausa, impronte verificate); dopo, lascia le
run nuove in pausa e indica il blocco. Rollback manuale: `reset_paper.py --rollback <TIMBRO>` (le run nuove scartate
sono conservate in `.archivio/reset-<TIMBRO>-run-nuove-scartate`).

## Verifiche prima della consegna
`test_reset.py` (6 test): procedura completa in cartelle finte con run vere preparate dal codice, posizione aperta
chiusa dal canale manuale vero, dashboard letta da `compare_view` vero; blocco prima dell'archivio; rollback automatico;
attivazione fallita. Deploy `falco-evoluto` 58 test.
