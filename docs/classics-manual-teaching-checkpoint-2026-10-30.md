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

## AGGIORNAMENTO VALIDATO — 30/10: 16 test storici corretti senza regressioni

La verifica A/B isolata e' stata eseguita sullo stesso Python 3.10/3.11 contro l'esatto commit originale `rule-pool` `fed2e3fd32ff162d22b045b4a8e5f0524e88a9b7`. Risultati finali run `41037349600` **SUCCESS**: originale **76/95 superati, 19 falliti**; ramo `work/classics-manual-teaching-20261030` **92/95 superati, 3 falliti**, **nessuna nuova regressione**. Altri **11 test mirati superati** su entrambi gli interpreti.

Correzioni nuove, ancora **solo offline**:
- DCA: lo stop LONG non puo' scendere e lo stop SHORT non puo' salire; no aumento della perdita consentita per allargamento SL. Prezzi invaldi e liquidazione incompatibile sono rifiutati prima di modificare il wallet.
- Aperture, DCA e chiusure parziali: prezzi take-profit negativi, non numerici o non finiti vengono esclusi.
- Reset: `trade_history.jsonl`, `lessons.md`, `errors.md` e `learning_log.jsonl` restano intatti, anche se una vecchia richiesta contiene `clear_lessons=true`. La run viene anche archiviata. La copia del record del trade ora include `run_no` e capitale iniziale, senza mutare il record del motore.
- Chiusura singola: `close_position.flag` con lista esplicita di simboli e timestamp massimo 120s, senza inventare prezzi; il conto PAPER viene salvato, poi nasce l'evento didattico; `closed_by=utente` nel trade, heartbeat espone disponibilita'. La singola chiusura e' stata collaudata con evento didattico pending e nessuna lezione automatica. **Non e' una chiamata Bitget privata** e nessun Telegram listener e' stato avviato.
- Ruolo AI classici: nuova configurazione `DESK_CLASSICS_AI_MODE=rules_only` salta completamente Claude e continua a calcolare decisioni con regole meccaniche; `scheduled` mantiene il vecchio comportamento finche' non si imposta esplicitamente il nuovo modo. Valori ignoti non autorizzano nuove chiamate a Claude.
- Gli **unici 3 fallimenti** rimasti chiedono maggior numero di token per Claude e diagnostica del vecchio percorso Claude. Sono preesistenti, non implicano che si debbano aumentare le chiamate del provider. Prima del deploy, separare o aggiornare i test della configurazione storica secondo la politica classici rules-only richiesta dall'utente.

**Non rilasciato**: nessun merge `rule-pool`, deploy, reset del conto, aggiornamento VPS, consumo AI reale, o mutazione di storia. Necessari revisione compatibilita' PWA e test operativi di end-to-end, backup/restore e approvazione separata.

---

