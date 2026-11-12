# SuperBot RC84 — Fase 3, configurazione sperimentale SHORT_ONLY Falco

**Stato:** ramo di lavoro isolato; **NON** distribuito; nessun merge, riavvio o cambio delle pause PAPER.
**Base immutabile:** `dc98413ee555c7f0aefeeca8a5367b41ba370c92` (Fasi 2/2B/2C hardening).
**Obiettivo futuro autorizzabile solo dopo verifica:** Falco scalp SHORT_ONLY, Toro Claude medio LONG/SHORT, Brain AI autonoma.

## Interruttore reversibile di Falco (PAPER soltanto)

Configurazione proposta: `DESK_HAWK_ENTRY_MODE=SHORT_ONLY`. Senza variabile, default `BOTH`:
conserva la politica del candidato congelato. Variabile sconosciuta -> `SHORT_ONLY` per impedire che
un refuso abiliti ingressi LONG. La configurazione **non viene attivata** in alcuna unità systemd in questa fase.
Nessun cambiamento al comportamento LIVE: la nuova verifica direzionale è applicata solo nel percorso PAPER
dei classici `hawk`.

Il motore rifiuta `open_long` e `open_long_split` di Falco da tutte le origini ordinarie
(`rules`, `claude`) senza inventare un segnale SHORT alternativo.
Preserva `open_short` e `open_short_split` scalping, i filtri 4H, pausa, claim, limiti e cooldown.
Gli ingressi LONG rifiutati producono evento `candidate` con stato `falco_short_only`,
prezzo/feature al tempo del segnale, e conteggio heartbeat `hawk_short_only_long_candidates`.
Non vengono iscritti come trade eseguiti o outcome positivi/negativi.

## Posizioni LONG residue e gestione dell'esposizione

- LONG già aperti: stop, TP, chiusura manuale/AI e registrazioni **restano disponibili**.
- Una seconda gamba LONG split ancora pendente viene annullata **prima** che
  `apply_paper_protective_exits` passi a `PaperAccount.on_bar`, altrimenti potrebbe
  incrementare il LONG senza attraversare il nuovo gate.
- Un DCA su una LONG residua non è consentito con SHORT_ONLY attivo, perché
  incrementerebbe l'esposizione LONG. Non viene chiusa forzatamente alcuna posizione.
- I DCA di posizioni SHORT e le uscite rimangono secondo la policy esistente.
- Annullamenti split sono salvati nello stato PAPER prima della scansione delle barre.
  Gli eventi di annullamento continuano a usare il normale percorso di flush.
- `long_s25.step` resta separato per gestire posizioni storiche. Nuovi ingressi
  S25 su Falco sono **sempre spenti** dalla politica RC84, indipendentemente
  dall'interruttore SHORT_ONLY. Nuovi S25 Toro rimangono spenti di default e
  richiederebbero un opt-in separato, che **non è autorizzato** per questo esperimento.

## Cosa NON viene cambiato

- Toro: Claude medio LONG/SHORT, rules entries disabilitati come nella RC84.
- Brain: codice, servizi, AI, NO_TRADE e mandato invariati.
- Rischio, equity floor 450, capitali, leve, SL/TP, funding, strategie, dashboard, unità VPS invariati.
- Nessun lock globale sullo stesso simbolo tra bot: la correlazione resta da **misurare**
  anziché vietare indiscriminatamente trade indipendenti.

## Collaudo (Claude, 12/11/2026) — prove ESEGUITE localmente, nessuna GitHub Actions
**Esito: PASS tecnico** sul ramo `work/rc84-phase3-falco-short-only-20261112` (non è una release).

Revisione del codice (`cli.py`): l'interruttore agisce solo in PAPER e solo su Falco; tutti i percorsi d'ingresso LONG sono coperti
(regole e Claude `open_long`/`open_long_split` → candidati `falco_short_only`; DCA su LONG residuo bloccato; seconda gamba LONG
pendente annullata prima di `on_bar`; il monitor degli stop non esegue mai seconde gambe; S25 su Falco sempre spento). Nessun LONG
viene trasformato in SHORT. `brain.py`, `engine.py`, `long_s25.py`, `signals.py` e tutto `backend/v3` (Brain) sono identici al
congelato `dc98413`.

**Correzione applicata (unica, minima):** il contatore `hawk_short_only_long_dca_blocked` era cumulativo per tutta la vita del
processo, mentre gli altri `hawk_short_only_*` sono per ciclo; la prova originale (`>= 1`) poteva quindi passare grazie a cicli
precedenti. Ora si azzera a ogni ciclo di Falco e la prova verifica `== 1`; inoltre la posizione della prova è resa davvero idonea al
DCA (medio, prezzo sfavorevole), così il blocco SHORT_ONLY è l'**unico** motivo per cui il DCA non avviene (controllo in BOTH:
lo stesso DCA avviene).

Prove aggiunte nel collaudo (`backend/tests/test_desk_rc84_phase3_collaudo.py`, 12, ciclo vero): Claude `open_long` e
`open_long_split` rifiutati e registrati come candidati; Claude `open_short_split` ammesso; nessuno SHORT forzato con sole proposte
LONG e trend ribassista; LONG residua chiusa da stop, da take profit, da chiusura parziale e da chiusura decisa; controllo BOTH (DCA
LONG e seconda gamba LONG restano); DCA SHORT ammesso in SHORT_ONLY; Toro bidirezionale con l'interruttore di Falco impostato; S25 mai
su Falco anche con `DESK_S25_TORO_ENTRY_APPROVED=1` nell'ambiente.

| Esecuzione | Congelato `dc98413` | Fase 3 collaudata |
|---|---|---|
| Prove Fase 3 (originali 12 + collaudo 12) | — | **24/24** |
| Suite `backend/tests`, Python 3.13 (esclusi i 2 moduli SQLAlchemy) | 7.039 ok, 1 fallito (ambiente) | **7.063 ok, 1 fallito** (lo stesso: `test_v3_rc84_import_paths`, SQLAlchemy 2.0.28 + Python 3.13) |
| Moduli SQLAlchemy, Python 3.11 | 49/49 | **49/49** |
| Replay 42 percorsi (default `BOTH`) | base | **identico** |

## Prove iniziali (ora eseguite: 12/12)

File `backend/tests/test_desk_rc84_phase3_short_only.py`:
- blocco ingressi `open_long` e `open_long_split` (origini Rules/Claude);
- `open_short` autorizzato, gestione non bloccata;
- default BOTH, ritorno reversibile, refusi fail-closed;
- Toro Claude medio non alterato; Rules Toro rifiutato;
- ciclo PAPER vero con `candidate` LONG rifiutato e feature;
- ciclo SHORT PAPER valido; ciclo LONG ripristinato in BOTH;
- LONG split residuo annullato prima degli stop;
- DCA di LONG residuo bloccato senza chiusura forzata.

Eseguite nel collaudo con esito positivo (vedi sopra), insieme a RC82/RC84, Fasi 2/2B/2C/hardening, suite completa e replay.

## Gate da soddisfare prima di qualsiasi unpause

1. Esecuzione e revisione indipendente dei test Fase 3, nessun regress su exit/claim/pause.
2. Verificare `DESK_S25_TORO_ENTRY_APPROVED` **non attivo** nella configurazione futura.
3. Decidere regola TP/R:R, guardrail rischio che alza margin/leverage e protezione equity 450;
   sono ancora `POLICY_SHADOW`, non controlli runtime allineati.
4. Verificare dati Bitget e comportamento reale dei filtri 4H; calendario XAU/XAG nel dubbio UNKNOWN.
5. Preparare backup/rollback, preflight PAPER, aggiunta opt-in unit Falco separata e check pause in VPS;
   niente modifica runtime finché non autorizzata.
6. Collaudo Brain su percorso dedicato, con NO_TRADE valido e senza trade forzati.
