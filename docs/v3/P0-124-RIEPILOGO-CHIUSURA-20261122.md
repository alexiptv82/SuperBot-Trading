# Issue #124 (P0): riepilogo per la chiusura (22/11/2026)

**Stato:** correzione completa **integrata e pubblicata** nell'integrazione `integration/brain-unico-20261119` @ `5f110379`, gate completo verde (V3 5418, builder 158, Jest 153).
**La chiusura dell'Issue spetta al proprietario.**

## Cosa è stato corretto
| Commit | Correzione |
|---|---|
| `ddd13084` | lo stato su disco registra la continuità dei controlli; file mancante, corrotto, del giorno prima, in formato vecchio o con minuti saltati → la giornata si ricostruisce da journal e candele 1m; se la ricostruzione è impossibile → blocco `unverified` |
| `a1777291` | nessuna finestra di tolleranza: dopo **ogni** riavvio si ricostruisce sempre |
| `7169558c` | **concorrenza:** sezione critica con lock; chi scrive rilegge il disco e **adotta** un blocco `loss` dello stesso giorno, solo in aggiunta |
| `0f71d0be` | lock **non bloccante** con tentativi limitati: se il lock non è acquisibile lo stato non viene scritto e l'apertura è negata in pochi secondi |
| `5f110379` | unione nell'integrazione; conserva il pre-collaudo (`e8804ac9`) |

## Prove
- **Scenario dell'Issue** (blocco alle 10:01 con scrittura fallita, poi recupero e riavvio): baseline → **riapre**; codice attuale → **bloccato**.
- **Due processi del sistema operativo concorrenti:** prima della correzione il secondo processo **apriva**; ora resta bloccato e il file conserva `loss`.
- **Lock tenuto da un altro processo:** con il lock bloccante non negava; ora nega in pochi secondi.
- **Test:**
  - `backend/v3/runner/test_daily_loss_latch_p0.py`: 46 casi;
  - `backend/tests/test_v3_runner_daily_loss.py`.

  Tutti i criteri 1–8 sono collegati ai test in `P0-124-VERIFICA-CRITERI-20261122.md`.

## Limiti dichiarati (fail-closed, non riaprono)
- Senza candele 1m dopo un riavvio, il blocco `unverified` resta finché la ricostruzione non riesce (nuovo tentativo ogni 5 minuti) o fino a mezzanotte UTC.
- Due runner sulla stessa run sono comunque **non supportati**. La protezione impedisce che uno cancelli il blocco dell'altro; l'installazione prevede un solo runner.
- Nuovo file `.daily_loss.lock` nella cartella della run: vuoto, permessi 0600.

## Testo proposto per la chiusura (da pubblicare SOLO su decisione del proprietario)
> Chiusa con `5f110379` (integrazione Brain Unico): ricostruzione obbligatoria dopo ogni riavvio (`ddd13084`, `a1777291`), concorrenza tra processi (`7169558c`), lock non bloccante (`0f71d0be`). Criteri 1–8 verificati, con evidenze in `docs/v3/P0-124-VERIFICA-CRITERI-20261122.md`; gate completo verde (V3 5418). Nessun deploy eseguito.
