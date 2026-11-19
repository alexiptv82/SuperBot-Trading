# Claude — Verifica indipendente PR #121 (fail-closed prezzi nel freno giornaliero)

**Data:** 19/11/2026 · **Autore:** Claude Code · **Natura:** solo test su copia isolata del repository (worktree nel laboratorio, utente non-root). Nessun runner, container, API, journal reale, Actions, merge o deploy.

## Checkout

- HEAD PR #121: `454020a192b037675fd06f43a41abfcdf0236a5f` ✅ (confermata)
- Base: `work/brain-exit-observability-20261113` @ `33a0de73a9903ba1ff76326aa4cb7c688a1e4aca` ✅ (merge-base coincide)
- Diff: solo `backend/v3/runner/daily_loss.py` e `backend/v3/runner/test_daily_loss_mark_failclosed.py`
- Ambiente: Python 3.12.3; pytest 9.2.0, fastapi e httpx in un venv temporaneo fuori dal repo; HOME temporanea; proxy HTTP verso porta chiusa (nessun provider raggiungibile).

## Esiti

| # | Verifica | Esito |
|---|---|---|
| 1 | HEAD e baseline | PASS |
| 2 | `python3 -m unittest backend.v3.runner.test_daily_loss_mark_failclosed -v` | **8/8 PASS** |
| 2b | Gli stessi 8 test contro il `daily_loss.py` della baseline | 11 fallimenti (con sottocasi), 4 pass attesi: i test rilevano il ritorno al vecchio comportamento |
| 3 | 28 moduli di test V3 pertinenti (daily loss, runner, wiring, post-AI, open_serial, exit service/worker, close fence, RC) con pytest | HEAD: 1110 pass, **7 fail**, 1 skip. Base: 1104 pass, 5 fail |
| 4 | `last_minute_close` reale (fetch sostituito) con candela vecchia o assente → `DailyLossGuard` reale → `Runner.tick` | PASS: `halted:daily_loss_check_failed`, nessun ciclo d'apertura, monitor uscite eseguito; `recheck` (percorso post-AI) solleva → `post_ai_guard` nega |
| 5 | Persistenza del latch HALT | Rischio residuo confermato (sotto) |

## FAIL bloccante per la PR

Due test esistenti in `backend/tests/test_v3_runner_daily_loss.py` codificano il **vecchio** comportamento fail-open e falliscono con la PR:

- `test_missing_or_invalid_price_counts_only_the_realized_part` (riga 182)
- `test_one_missing_price_does_not_hide_the_loss_of_another_position` (riga 192)

È il cambiamento voluto, ma la PR non li aggiorna: la suite risulterebbe rossa. Vanno riscritti per attendere `daily_loss_price_unavailable` / `daily_loss_price_invalid` (il secondo può verificare che il primo prezzo mancante interrompa il calcolo senza esito parziale).

I 5 fallimenti di `test_v3_rc84_import_paths.py` sono **preesistenti** (identici sulla base): import di `desk.signals` da `backend/desk/cli.py` con PYTHONPATH assoluto da directory estranea. Non dipendono dalla PR.

## Punto 5 — persistenza di `daily_loss.json` (rischio residuo, non introdotto dalla PR)

Riprodotto con test sintetici:

1. **Scrittura fallita + riavvio:** HALT raggiunto con directory non scrivibile → in memoria resta HALT e `recheck` nega correttamente (`daily_loss_latch_not_persisted`). Ma dopo un riavvio nello stesso giorno, con la perdita rientrata sotto il 50 %, il livello torna **`ok`**: il latch è perso e le aperture riprendono.
2. **File di stato corrotto:** `_load` lo tratta come stato vuoto → dopo il riavvio, con perdita rientrata, livello **`ok`**. Fail-open.

Impatto: il blocco "agganciato fino a mezzanotte UTC" non è garantito attraverso un riavvio se il file manca, è corrotto o non è stato scritto.

Correzione proposta (non applicata, serve autorizzazione):
- `_load`: file presente ma illeggibile o invalido ⇒ considerare `halt_latched=True` per il giorno corrente (fail-closed) e segnalarlo nel battito; file assente ⇒ ammesso solo se il journal non mostra perdite di oggi ≥ soglia (oppure ricalcolo del massimo della perdita del giorno dal journal).
- Test: (a) directory non scrivibile + riavvio ⇒ resta `halt`; (b) file corrotto ⇒ `halt` fino a mezzanotte UTC; (c) giorno nuovo ⇒ reset normale.

## Note

- Il prezzo "Decimal valido ma vecchio" segnalato nella PR è coperto nel percorso reale: `last_minute_close` solleva `stale_minute_bar` se l'ultima candela non è quella del minuto appena chiuso, e la PR lo converte in `daily_loss_price_unavailable`. Resta scoperto solo un `price_of` diverso da `last_minute_close`.
- Anche la chiusura manuale usa `last_minute_close`: con feed fermo è rifiutata (comportamento preesistente, non della PR). Stop ed exit service non dipendono dal freno giornaliero.
- Lo script di verifica empirica è rimasto fuori dal repository (scratchpad); può essere convertito in test della PR su richiesta.

**Verdetto:** fix corretto nel merito; **NO-GO al merge finché i due test legacy non sono aggiornati**. Rischio del latch da trattare in un commit separato.
