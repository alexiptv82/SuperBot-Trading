# Chat normale — passaggio da Work, 30 ottobre 2026 (Europe/Rome)

## Presa in carico isolata
L'utente ha riportato l'ultimo messaggio di Work: Work ha registrato il mandato ma **non ha ancora implementato** la revisione periodica delle posizioni; Work e' temporaneamente indisponibile per limite di utilizzo. L'utente chiede di continuare in questa chat e conferma che gli archivi di ripresa sono in GitHub e Library.

Chat normale ha riletto LEGGIMI, SINCRONIZZAZIONE-WORK-CHAT, MANUALE-OPERATIVO, STATO e checkpoint Library, verificando GitHub. Branch Work dichiarato work/brain-position-review-20261030 **non pubblicato** al momento del controllo; possibili modifiche locali Work NON toccate. Per evitare sovrascritture, nuovo owner temporaneo chat normale **solo** sul ramo distinto `work/brain-position-review-chat-20261030`, base `895b34a64058b1321ba5ad372e8de435f3e7fec0`. Quando Work torna, deve rileggere questo checkpoint e confrontare le proprie modifiche locali prima di qualunque integrazione.

Prima fase mirata: valutazione periodica autonoma delle posizioni aperte anche a scanner vuoto, con AI in worker, verifica posizione/versione/prezzo/scadenza, riserva budget condivisa, output **consultivo** e audit idempotente. Non attribuire alla prima fase la capacita' di eseguire una chiusura AI: la gestione attiva richiede transazione PAPER distinta con guardrail, prove di resilienza e contratto con l'app. Non alterare classici, wallet o storico; test di regressione e CI prima di qualunque merge.

Permessi: preparazione e test offline gia' autorizzati; **nessun merge, deploy, reset, API pagata, accesso VPS, ordini o apertura di seconda istanza** autorizzato in questo passaggio. PAPER permanente.

## Checkpoint verificato — 30/10 ~20:56 Europe/Rome
Ramo `work/brain-position-review-chat-20261030`, HEAD `f825a62a5592f95693378435421f8c8ddc1fc5e4` (base `895b34a64058b1321ba5ad372e8de435f3e7fec0`).
**Preparato OFFLINE**:
- `backend/director/brain_scalp/position_review.py`: snapshot per posizione PAPER, prezzo recente, id, controllo fingerprint esposizione, scadenza, limite di movimento del mark, idempotenza journal; DeepSeek analisi non bloccante, Claude revisore facoltativo quando propone un'azione. Sola raccomandazione HOLD/SUGGEST_CLOSE/SUGGEST_TIGHTEN; `automatic_actions=0`.
- `supervisor.py`: dopo il tick protettivo parte revisione AI anche con zero candidati, un worker unico condiviso con analisi d'ingresso, budget e deadline invariati. In presenza di entrambe le opportunita' conserva l'ingresso iniziale e alterna i tipi di analisi; AI guasta/scaduta non ammette azioni.
- `backend/tests/test_brain_position_review_chat.py`: 7 test nuovi per no-candidates, duplicate, prezzo/versione scaduti, output invalido, revisore selettivo, non-block protezione, fairness entry/review. Nessuna modifica ai moduli classici/live/engine/scanner.

**Test CI verificati**: run `41119121131` SUCCESS Python 3.10 e 3.11; **50 PASS +21 subtest PASS per interprete** (test nuovi e regressioni selezionate); gate Git confirms desk, brain_free, frontend, deploy, engine e scanner invariati. Prima CI `41119004859` aveva 1 regressione nel test di precedenza ingressi, corretta a `f8284b31...`, poi ampliati test e superata CI sul nuovo HEAD. Nessun skip test usato per coprire la regressione.
Link CI: https://github.com/alexiptv82/SuperBot-Trading/actions/runs/41119121131

**Rilasciato**: NULLA. Nessun merge/deploy/riavvio/VPS/API pagata/reset/ordine o wallet alterato; git branch isolato. La sola consultazione AI sulle posizioni non e' ancora chiusura/stop automatico. Restano integrazione reale delle decisioni PAPER con test atomici e guardrail, feed API pubblico, collaudo end-to-end, budget/mandato, PWA, backup/restore e approvazione separata; non dichiarare Brain completo.

## Prosecuzione autorizzata: motore decisioni PAPER su ramo distinto
Utente: «ok procedi» per fase successiva dopo revisione periodica CI verde.
Owner: Chat normale. Nuovo ramo `work/brain-position-execution-chat-20261030`, base `f825a62a5592f95693378435421f8c8ddc1fc5e4`; Work locale resta intatto. Obiettivo: collegare l'output `SUGGEST_CLOSE`/`SUGGEST_TIGHTEN` a transazioni PAPER **solo dopo controllo e revisione selettiva**, con opt-in esplicito di configurazione, atomicità SQLite, stop mai allargato, prezzo e ID posizione freschi, idempotenza, e test Python 3.10/3.11. Default: **OFF**, nessuna chiusura AI attiva sui servizi.
Vincoli immutati: niente merge/deploy, VPS, avvio istanze o credenziali API; tutti gli storici append-only.
