# Checkpoint verificabile — PR #119 e gate del PAPER definitivo

**Data:** 19/11/2026 14:45 Europe/Rome  
**Ambito:** documentazione e verifica GitHub/Library; nessuna azione operativa.

## Novità verificate dopo il checkpoint delle 13:50

1. È stata aperta la [PR #119](https://github.com/alexiptv82/SuperBot-Trading/pull/119), draft e non mergiata, sul branch `claude/brain-unico-profit-guardian-20261119`, HEAD `cec2b872e3f546b3e03a2323d29c7b855c5f3237`, base `main` `a1e9722a1a9af32ee045ebf61d7e43858c9a1d5e`.
2. Il ramo `diario` contiene la revisione Claude dello Smart Profit Guardian, commit `e10d6294cb5b6e59e3af80b5e3e495d5481f0868`.
3. Decisione utente accessibile del 19/11/2026: il prossimo PAPER del Brain unico dovrà essere un **unico collaudo finale, completo e integrato**, con tutte le funzionalità e sicurezze concordate; non va avviata un’altra prova parziale con componenti mancanti o cause note di pause/stop.
4. Il rapporto Smart Profit Guardian disponibile in Library ribadisce che +400/+500 USDT sono soglie sperimentali e non target quotidiani né configurazioni approvate.

## PR #119 — fatto, preparato, non rilasciato

La PR aggiunge soltanto:

- `docs/v3/BRAIN-UNICO-SMART-PROFIT-GUARDIAN-PROPOSTA-20261119.md`: critica, architettura, politiche di profit lock, ordine dei gate, anti-reingresso, reset e piano E0–E5;
- `ops/brain-unico/guardian/sim_policies.py`: simulatore sintetico Python standard library, senza rete o dati reali.

**Preparato/proposto:**

- floor mobile sul picco di equity mark-to-market come budget di rischio, invece di usare +400/+500 come unico meccanismo;
- limite di perdita di sessione e drawdown globale prioritari;
- `thesis_id`, cooldown e limite/riduzione dei reingressi;
- leva come risultato di invalidazione → stop → rischio monetario/costi → nozionale → leva minima ammissibile;
- sessione 08:00 Europe/Rome come ipotesi di sicurezza da confrontare con 00:00;
- nessuna eccezione nella prima versione;
- prima E0 su copie certificate, poi test sintetici/replay/shadow/PAPER.

**Non implementato/non approvato:**

- nessun Guardian nel runtime, nessun gate vincolante, nessuna nuova configurazione rischio;
- nessun dato reale o VPS letto;
- nessun merge, deploy, root/SSH, servizio, restart, reset, trade o API a pagamento;
- nessun modello addestrato.

## Prova sintetica e suoi limiti

Fonte: documento e simulatore della PR #119.

- Esecuzione dichiarata: 40.000 sessioni sintetiche, circa 6 occasioni/sessione, esiti indipendenti +2R/−1R e costo fisso; `R=85,71 USDT` ereditato come ipotesi Arena, non approvato per Brain unico.
- Risultato illustrativo: i profit lock non migliorano il 5° percentile delle sessioni peggiori; il limite di perdita di sessione sintetico lo porta da circa −429 a −257 USDT.
- Se l’edge resta costante, fermarsi dopo il profitto riduce leggermente la media; il Guardian può aumentarla solo se i trade/reingressi successivi hanno EV peggiore.
- A margine 400 e leva 50×, con costi ipotetici, stop teorico circa 0,25%, costi circa 42% di R e win rate di pareggio 57,5% con TP a 2×. Le ipotesi sui costi devono essere verificate.
- Mancano posizioni simultanee, correlazione, gap, funding, slippage reale, mark-to-market intratrade, ordini pendenti e tracce VPS. I risultati non provano edge, rendimento futuro o protezione garantita.
- Sulla HEAD risultano **0 check run e 0 status**; nessuna CI GitHub certifica il simulatore.

## Gate del prossimo PAPER definitivo

“Definitivo” significa collaudo unico di una release candidate completa, non promessa di assenza assoluta di difetti. Prima dell’avvio devono essere integrati e verificati insieme almeno:

- DeepSeek decisore LONG/SHORT/NO_TRADE e Falco SHORT solo consulenza;
- memoria/apprendimento causale verificabile, Dataset Builder e provenienza dati;
- gestione posizione completa: sizing, leva dinamica, stop, target, costi, rischio aggregato e correlazione;
- equity protection, limite perdita, Guardian e anti-reingresso;
- ExitService indipendente dall’AI, single-owner, chiusura manuale, recovery e idempotenza del journal;
- app Samsung con Brain unico completo, posizioni/PnL/stato Guardian e chiusura manuale;
- notifiche Telegram post-commit per apertura/chiusura/errori rilevanti;
- backup/restore e continuità di storici, memorie, scoreboard ed EventJournal;
- test offline, replay causale, shadow e preflight PAPER con criteri pre-registrati.

La richiesta “niente pause/stop” va intesa come **nessuna pausa involontaria dovuta a moduli mancanti, integrazioni incomplete o servizi non sani**. Un `LOCKED` deterministico che blocca soltanto nuove aperture per rischio/feed è una funzione di sicurezza richiesta; non deve fermare ExitService, monitoraggio o chiusure.

## Stato consolidato dei tre portafogli

- **Falco:** storico PAPER e logica SHORT da preservare; advisory-only per il Brain unico.
- **Toro:** storico PAPER da preservare; nessun reset.
- **Brain storico:** ultimo riscontro disponibile lo dà fermo; journal, memorie, scoreboard, trade e posizioni storiche sono fonti da conservare, non prova di apprendimento. Nessuna verifica live VPS in questo checkpoint.
- Arena PAPER resta separata e non deve dettare automaticamente i limiti del Brain unico.

## PR, SHA, backup e chiavi

- PR #117 open/draft, invariata a `6dcdedc36c3aafb4a2bed2a8f7b8edcc74b80482`.
- PR #118 open/draft, invariata a `e983d36f7be8d9965ed37283d3d4ca86b658fdab`; restano i due gap su conflitto simbolo/ciclo e attestazione legata a run/manifest/audit.
- PR #119 open/draft a `cec2b872e3f546b3e03a2323d29c7b855c5f3237`.
- RC84 PR #80 resta all’ultimo SHA verificato `0e29a73a36f668643da4088178bacb8616a45ac0`.
- Backup esterno `work/extbackup-bot-stopped-20261109` a `3dc2116a08058f57fc14b695431f6e3fa1a1ca45`: preparato, non installato.
- Copia cifrata age sul PC: PowerShell `ESITO: VERIFICA OK` e chiave pubblica coincidente; non certifica backup o restore sulla VPS.

## Blocker e prossimo passo

1. Chiudere con nuovo SHA e test i due gap residui PR #118.
2. Definire una checklist di completezza/accettazione del Brain unico e una matrice di tracciabilità requisito → implementazione → test → evidenza.
3. Misurare E0 su copie certificate con consenso separato: EV post-profitto, reingressi, giveback e costo opportunità.
4. Correggere i limiti della simulazione prima di trasformare PR #119 in gate operativo.
5. Integrare tutti i moduli su un’unica release candidate e avviare il PAPER finale solo dopo preflight documentato e consenso separato.

## Azioni di questa esecuzione

- **Fatto:** verifica PR/SHA/check/status, lettura del nuovo rapporto e recupero della decisione utente accessibile.
- **Preparato:** checkpoint e aggiornamento dell’indice.
- **Rilasciato/installato:** nulla.
- **Vincoli preservati:** PAPER soltanto; storici ed EventJournal intatti.
