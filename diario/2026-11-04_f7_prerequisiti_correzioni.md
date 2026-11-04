# 04/11 (mattina) — Correzioni a F6, hardening test F2, prerequisiti F7

**AI:** Claude Sonnet 5.5 (coordinatore)
**Branch:** `work/v3-f6-dashboard-20261104` (PR #39 DRAFT, commit `303be9a`) · `work/v3-test-hardening-20261104` (PR #40 DRAFT, commit `09104af`)

---

## 1. Errore mio in F6 — corretto

La dashboard F6 leggeva eventi `brain_step`, nome inventato. `BrainEngine` scrive `brain_decision`. Su un journal reale mostrava sempre 0 decisioni; i 25 test passavano perché usavano eventi costruiti a mano con lo stesso nome sbagliato.

Corretto in `303be9a`: la dashboard riconosce `brain_decision`; nuovi test contro i produttori veri (`BrainEngine` ed `execute_paper`).

## 2. Test F2 che passavano per il motivo sbagliato (PR #40)

Misura con un plugin pytest su `BrainEngine.step`: 14 test non passavano `run_id`, il motore rispondeva `NO_TRADE('invalid_input')` subito e il controllo dichiarato dal test (pausa, NaN, floor 450, parametri, errori analista/reviewer) non veniva mai raggiunto.

Prova di mutazione (engine.py temporaneo, ripristinato identico): togliendo il controllo chiavi obbligatorie / NaN / floor 450, i 20 test vecchi passavano tutti; i nuovi ne falliscono 3, 3 e 1. Il motore risulta corretto in tutti i casi esaminati.

Impatto sul "215/215 PASS" del diario di stamattina: il numero era vero ma sovrastimava la copertura di sicurezza. Ora 245 PASS.

**Aperto:** ~27 test finiscono a `policy_not_authorized` (in gran parte di proposito); 3-4 potrebbero non esercitare ciò che dicono (es. `test_untrusted_sources_not_persisted`). Da rivedere — proposta: ChatGPT, audit indipendente.

## 3. F7 — perché non parte subito

Tre buchi verificati nel codice: (A) nessun modulo scrive `paper_close`, quindi nessuna posizione si chiude; (B) nessun legame decisione→posizione (id = hash, payload senza simbolo/prezzi, `paper_open` senza id decisione); (C) i soli trade eseguiti sono pochi, servono opportunità etichettate.

Piano e brief per Grok: Project Claude, `claude/piano-f7-prerequisiti-brief-grok-2026-11-04.md`. Ordine: P1 chiusura PAPER (Claude) → P2 legame decisione/posizione (Grok engine + Claude executor) → P3 `TradeOutcome` (Claude) → P4 moduli F7 (Grok).

## Status gate

- ⛔ Nessun merge/deploy · DESK_MODE=paper invariato · Hawk/Bull non toccati · cervello intatto
- ✅ Nessuna modifica a codice di produzione in questa sessione (solo test e dashboard offline)
- Prossimo: P1 (F5b, esecutore di chiusura PAPER)
