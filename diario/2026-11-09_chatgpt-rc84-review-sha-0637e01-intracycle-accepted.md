# SuperBot V3 — ChatGPT RC84 review: fix esposizioni intra-ciclo accettato (09/11/2026)

## Verifiche repository
- [PR #80](https://github.com/alexiptv82/SuperBot-Trading/pull/80) **DRAFT**, HEAD `0637e01b2b41a4c89fdbe7473bdc867ee5c58860`, base RC82 PR #79 `1e64684b9d813aad1ca1c7d344872333e451fd05`. Non mergeata, non distribuita.
- Commit codice+test `cd6436fc87bbc78b759afd190e78bcf401b824f2`; ultimo commit solo handoff `docs/v3/RC84-P1-TELEGRAM-CLAUDE-HANDOFF-20261108.md`.
- File modificati dalla revisione `8b486f1`: `backend/desk/cli.py`, `backend/desk/long_s25.py`, `backend/tests/test_v3_rc84_claim_integration.py`, nuovo `backend/tests/test_v3_rc84_same_cycle_exposure.py`, `backend/tests/test_v3_rc84_telegram_durable_close.py`, handoff. Nessuna strategia/risk/AI/Brain/dashboard alterata.
- [Commento di code review e valutazione ChatGPT](https://github.com/alexiptv82/SuperBot-Trading/pull/80#issuecomment-6739399948).

## Review specifica: PASS sul fix intra-ciclo
L'exposure guard precedente controllava solo i claims all'inizio ciclo; una close/partial non protettiva poteva essere seguita da apertura/DCA o ingresso S25 prima della prova contabile. Nuova `_settle_claims_now` salva conto con claim e prova history+learning subito dopo ogni close/partial, senza bloccare le sequenze sane. Se il claim permane, `claim_block` filtra le successive azioni non-management; S25 riceve callback `entries_blocked` aggiornata e non apre mentre i claims sono pending; seconde gambe pendenti cancellate prima del secondo controllo protettivo. Stop/TP/liquidazione e chiusure consentite restano attivi. I test comprendono same-cycle close(A)+open(B), partial(A)+DCA(A), S25 time-close+open, percorso sane, partial pending+terminale e stop. La patch resta isolata dal LIVE.

**Decisione della revisione codice: fix accettato.** Non significa RC84 pronta al deploy o garanzia di corretto funzionamento sulla VPS.

## Evidenza test e limiti
Claude riferisce nuovi 11 test (6 fail senza patch), backend esteso **6.801 PASS / 32 FAIL / 3 xfail**, 0 nuovi FAIL rispetto a `8b486f1`; Jest **109/109 PASS**, build React **success**. Test eseguiti sulla sandbox Claude con rete rifiutata e dati sintetici, non rieseguiti da ChatGPT; nessun workflow GitHub associato allo SHA. Dei 32 FAIL: 20 fixture Brain, 1 desk_view, 1 live_view, 1 test S25 hash fissato, 9 test_superbot server live. Due test esclusi per mancanza di sqlalchemy: test_auth_flow e test_profiles_engine. **NON dichiarare full-suite verde.**

## Gate ora prioritari — readiness integrata, non altri refactoring
1. Collaudo su combinazione di commit pinned delle PR #74, #77, #78, #79, #80, confrontando dipendenze e sequenza release, senza deploy.
2. Classificazione/isolamento o risoluzione documentata dei 32 FAIL backend e dei due test esclusi; eseguire suite offline riproducibile e CI.
3. Dashboard web autenticata + Android: 3 portafogli, posizione/prezzo/PNL/leva, pulsanti manual-close PAPER, allarmi stop RUNNING separati da RC80, claim pending/conflict visibili con parole corrette e operazioni potenzialmente bloccate.
4. Brain RC83: exit-worker effettivo non verificato su VPS, flag `--legacy-exits-disabled` non spegne da solo writer legacy; serve single owner handoff comprovato.
5. Falco/Toro stop periodici OHLC 15m ogni 15/30m, **non** tick-by-tick, wick ingresso non riprodotto: rischio operativo da accettare prima di ripartenza.
6. Backup off-host + restore, preflight VPS in sola lettura con OK specifico, nuovi portafogli PAPER Falco/Toro 1000 USDT e Brain 2000 USDT preservando storico, release/dipendenze e riavvio solo con OK utente.

**No merge, deploy, VPS, restart, reset, ordini effettuati. PR #80 resta DRAFT.**


## Controllo di ascendenza GitHub (solo lettura)
Il confronto dei commit dimostra che l'HEAD PR #80 `0637e01b...` **discende già** da:
- PR #74 Brain manual close `91214f9064ee2fba478a5c4fcdf5efc3f21a707b` (compare: ahead 59, behind 0);
- PR #77 RC80 `50b75b9643680b9c758047d3890f3599b051f325` (ahead 41, behind 0);
- PR #78 RC81 `29eb75750625a8819cd2db71dc2459d164c3199c` (ahead 27, behind 0);
- PR #79 RC82 `1e64684b9d813aad1ca1c7d344872333e451fd05` (base diretta PR #80).
Quindi non serve ricopiare la PR #74 dentro RC84: è un antenato nella storia Git. **Questo non certifica la catena di deploy né Brain exit-worker single-owner.** Tutte le PR consultate risultano Draft e non mergeate, gli effettivi gate di release restano da verificare.
