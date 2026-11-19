# Checkpoint verificabile — Smart Profit Guardian: proposta di laboratorio, non approvata

**Data:** 19/11/2026 13:50 Europe/Rome  
**Ambito:** solo documentazione; nessun accesso live VPS e nessuna modifica operativa.

## Novità verificata

Dopo il checkpoint delle 12:47 non risultano nuovi commit, PR o test GitHub. È però disponibile un nuovo rapporto privato di progetto, “SuperBot Smart Profit Guardian Report 2026-11-19”, accompagnato dal prompt di revisione indipendente. I documenti definiscono una direzione di lavoro utile per il futuro Brain unico PAPER, ma **non costituiscono approvazione, implementazione o rilascio**.

## Desiderato / proposto, non implementato

- Obiettivo: proteggere il profitto di sessione e accettare esplicitamente `NO_TRADE`, riduzione delle aperture e pause dopo guadagni rilevanti.
- Leva 20x–50x: possibilità tecnica, mai automatismo o minimo; ogni apertura resta subordinata a stop, volatilità, costi, liquidità e distanza dalla liquidazione.
- Macchina a stati proposta:
  - `NORMAL`: profitto netto di sessione sotto +400 USDT;
  - `SELECTIVE`: da +400 USDT, maggiore selettività;
  - `PROTECTED`: da +500 USDT, stop ordinario alle nuove entrate;
  - `LOCKED/PAUSE`: rischio, giveback o feed incoerente; nessuna nuova entrata.
- Protezione iniziale ipotizzata: conservare circa il 75–80% del picco, cioè giveback 20–25%.
- Le soglie +400/+500 USDT, il giveback, il reset di sessione e il limite di 2–3 rientri per tesi sono **ipotesi da confrontare**, non configurazioni approvate.
- Il PnL realizzato netto deve restare distinto dall’equity mark-to-market; una soglia realizzata non certifica profitto protetto se le posizioni aperte hanno perdita.
- Confrontare reset sessione 00:00 e 08:00 Europe/Rome su dati UTC, senza chiusure forzate al cambio data; HWM, cooldown e limiti globali non devono essere azzerati impropriamente.
- Anti-overtrading: `thesis_id`, conteggio rientri e riconferma oggettiva; evitare inseguimento di trend esausti e SHORT ripetuti sui rimbalzi.
- Varianti di esperimento: baseline; soglie fisse senza eccezioni; eccezioni con budget; soglie dinamiche per equity/volatilità.

## Portafogli PAPER e decisioni

- **Falco:** patrimonio SHORT consultivo/advisory-only; nessuna nuova autorità operativa.
- **Toro:** storico da conservare; nessun reset o modifica.
- **Brain:** storico, journal, memorie e scoreboard da preservare; futuro Brain unico solo dopo prove causali. Il runner storico resta fermo all’ultimo riscontro disponibile; questo checkpoint non verifica lo stato live.
- Arena PAPER e Smart Profit Guardian sono separati: il Guardian non è installato né attivo.
- DeepSeek è candidato possibile al ruolo decisionale e Claude a revisore selettivo; non sono selezioni definitive né autorizzazioni a spendere.

## Riscontri GitHub invariati

- [PR #117](https://github.com/alexiptv82/SuperBot-Trading/pull/117) open/draft, HEAD `6dcdedc36c3aafb4a2bed2a8f7b8edcc74b80482`.
- [PR #118](https://github.com/alexiptv82/SuperBot-Trading/pull/118) open/draft, HEAD `e983d36f7be8d9965ed37283d3d4ca86b658fdab`.
- PR #118 resta prerequisito incompleto per sperimentazioni affidabili: conflitto simbolo/ciclo nel linking feature e attestazione non sufficientemente legata a run/manifest/audit reali.
- RC84 [PR #80](https://github.com/alexiptv82/SuperBot-Trading/pull/80) resta all’ultimo SHA verificato `0e29a73a36f668643da4088178bacb8616a45ac0`.
- Backup esterno branch `work/extbackup-bot-stopped-20261109` a `3dc2116a08058f57fc14b695431f6e3fa1a1ca45`: preparato, non installato.
- Copia cifrata della chiave age sul PC: output PowerShell `ESITO: VERIFICA OK` e chiave pubblica coincidente; **non certifica** presenza, integrità o restore del backup sulla VPS.

## Test e limiti

- Nessun nuovo test GitHub o runtime associato al rapporto Guardian.
- Il rapporto è analisi/proposta. Non prova rendimento, sostenibilità delle soglie, stato dei servizi, qualità dei feed o backup VPS.
- Le conversazioni recenti complete non sono disponibili come trascrizione integrale; sono stati usati soltanto artefatti effettivamente accessibili e riscontri GitHub.
- Test futuri: copie storiche certificate e immutabili, replay causale senza leakage, riconciliazione PnL/fee/funding/equity, gap-liquidazione-slippage, confronto out-of-sample, shadow e PAPER forward.
- Metriche minime: PnL netto, drawdown/tail risk, giveback, expectancy/profit factor, trade post-soglia, perdite da rientro, opportunità perse, LONG/SHORT e regime.

## Blocker e prossimo passo sicuro

1. Correggere i due gap residui di PR #118 con nuovo SHA e test verificabili.
2. Ottenere storici e candele certificati senza cancellare dati non idonei.
3. Ricevere critica indipendente della proposta e decidere esplicitamente politica, soglie, reset e budget delle eccezioni.
4. Solo dopo, preparare design isolato in branch/PR draft; nessuna installazione runtime senza nuova approvazione.
5. Mantenere PAPER, EventJournal, storico e servizi di uscita preservati.

## Azioni di questa esecuzione

- **Fatto:** verifica documentale GitHub e lettura diretta del rapporto/prompt disponibili.
- **Preparato:** questo checkpoint append-only e riallineamento dell’indice.
- **Rilasciato/installato:** nulla.
- **Non approvato:** merge, deploy, GitHub Actions, VPS, restart, reset, ordini, API a pagamento, training o modifica del rischio.
