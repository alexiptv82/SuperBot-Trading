# Falco / Toro — insegnamento da chiusura manuale (ramo isolato, 30/10/2026)

## Stato esatto

- Sviluppo solo su `work/classics-manual-teaching-20261030` (base `rule-pool` codice 13/10). Nessun deploy, merge, reset, modifica al runtime VPS.
- `backend/desk/manual_teaching_bridge.py` e `backend/director/manual_teaching.py`: trasforma in evento di insegnamento esclusivamente un record `acc.close` con `why='chiusura manuale'` e portafoglio identificato. Richiede conferma che il conto sia stato gia' salvato e che la posizione non risulti piu' aperta.
- `backend/desk/cli.py`: nel percorso gia' esistente `reset.flag` (= chiudi tutto PAPER), la richiesta didattica viene registrata **dopo** `save_state`. Nessun cambiamento a stop/soglie/aperture/leva e nessun comando nuovo attivato.
- `/insegna_si` / `/insegna_no` sono logica offline con gruppo, TTL 2h e log append-only; nessun receiver Telegram installato. Non nascono automaticamente regole di profitto. La chiusura singola resta disabilitata sulla baseline del 13/10.
- Limite importante: una chiusura **Bitget esterna** non fa sparire una posizione dal PAPER di Falco/Toro. Nessun teaching e' prodotto solo dalla scomparsa di una posizione reale.
- In caso di guasto del registro didattico, la chiusura PAPER gia' avvenuta non viene annullata e il bot non si blocca. Per garantire consegna esattamente una volta servira' un outbox nello stesso writer o un recupero con riconciliazione verificata (non si deduce automaticamente dal solo JSONL).

## CI

- GitHub Actions `41034727528`: SUCCESS Python3.10/3.11 sulla nuova funzione, **4 test nuovi per versione** e guardia immutabilita' Brain/frontend/deploy.
- La suite `backend/tests/test_desk.py` completa e' stata eseguita **come controllo informativo non bloccante**: 76 pass, **19 fail** su entrambe le versioni Python. Vi sono test che richiedono funzionalita' delle versioni successive (close-position, reset non distruttivo, ecc.) non presenti nella baseline 13/10. **Non e' certificata** l'intera suite storica; non cambiare alla cieca il codice congelato per rendere verde ogni test. Un confronto A/B della suite su un checkout immutato della stessa baseline e' consigliabile per attribuire ciascun fail.
- La modifica di insegnamento non include e non autorizza strategia nuova per i classici, che restano accantonati su decisione dell'utente.

## Prossimo gate

- Collega un unico consumer Telegram autorizzato, di sola lettura fino a conferma del bot/posizione, senza duplicare reader esistenti.
- Solo dopo un nuovo collaudo offline e un backup+restore, decidi se integrare il ramo nei classici. Richiede OK separato al merge e al deploy.

AI: chatgpt (chat normale)
