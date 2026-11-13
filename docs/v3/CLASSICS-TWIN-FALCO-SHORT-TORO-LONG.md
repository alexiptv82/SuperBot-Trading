# SuperBot — Falco SHORT / Toro LONG: coppia di portafogli gemelli (PAPER)

**Stato:** esperimento reversibile su ramo isolato, **NON collaudato** e **NON attivato**.
**Base sicura:** Phase3 `f8332c92cc2bc4edee3ea7363f71f15a0a37a816` (Falco SHORT_ONLY, PR #92).
**Fallimento separato:** PR #93 `c8e8992` (LONG Mirror 15m) resta **FAIL** e **non viene importata né incorporata** qui.
**Versione su VPS:** invariata, i tre bot PAPER rimangono in pausa; nessun deploy, merge, reset, LIVE.

## Direttiva utente

Voglio due classici gemelli in capitali, slot, margine, leva, rischio e regole:
- **Falco:** solo nuovi SHORT, strategia SHORT originale intatta, `DESK_HAWK_ENTRY_MODE=SHORT_ONLY` (facoltativo, Fase3).
- **Toro:** solo nuovi LONG, ma **stessi indicatori 1h/4h, score, cooldown, SL/TP e sizing Falco**, senza inventare un algoritmo LONG a 15 minuti. PAPER `DESK_BULL_TWIN_MODE=LONG_ONLY` (facoltativo).
- **Brain:** indipendente, nessun cambiamento.

Le due direzioni NON sono una copertura perfetta e non devono fare hedge forzato. Uno o entrambi possono scegliere NO_TRADE.

## Parametri gemelli (solo quando Toro Twin è attivo)

| Parametro | Falco | Toro Twin |
|---|---:|---:|
| Capitale iniziale PAPER | 1000 USDT | 1000 USDT |
| Slot massimi | 10 | 10 |
| Margine massimo per trade | 100 USDT | 100 USDT |
| Margine totale massimo | 1000 USDT | 1000 USDT |
| Equity kill threshold | 450 USDT | 450 USDT |
| Stop giornaliero | 12% | 12% |
| Guardrail min/forzato margine | 50/60 USDT | 50/60 USDT |
| Guardrail min/forzato leva | 10x/15x | 10x/15x |
| Orizzonte forzato dal guardrail | scalp | scalp |

La leva resta soggetta ai tetti originali del motore (BTC/XAU/XAG 45x, ETH 30x, alt 25x). Nessuna nuova impostazione 20–50x. Stesso max di 100 non significa dieci aperture a 100 USDT: cassa, commissioni, rischio e pausa possono impedirle.

## Strategia condivisa, ingressi separati

**Si riusa il medesimo codice esistente:** `signals.read_symbol` e `brain.rules_decisions` non sono modificati.
Il segnale `r.side` dipende dal confronto tra `long_score` e `short_score`.
- Falco SHORT_ONLY nega nuovi `open_long` / `open_long_split`.
- Toro LONG_ONLY nega nuovi `open_short` / `open_short_split`.
- Toro Twin autorizza nuovi LONG `scalp` da `claude` e `rules`, mentre Toro legacy accetta come prima `medio` da `claude`; la fonte non viene sintetizzata in LONG da un SHORT escluso.
- Il prompt Toro Twin riutilizza integralmente `SYSTEM_HAWK` come base e aggiunge il vincolo di orientamento LONG e capienza; `SYSTEM_BULL` storico resta intatto e valido in modalità OFF.
- Non viene modificato il motore SHORT, ma **`cli.py` cambia** per aggiungere selezione Toro e filtri: non dichiarare byte-identica l'intera CLI; confrontare esplicitamente gli output SHORT di Falco su input identici rispetto a Fase3.
- I dati, equity, learning e storico di Toro restano propri, non condividono state o file con Falco.

## Interruttore e comportamento di sicurezza

- Assenza di `DESK_BULL_TWIN_MODE` o `OFF`: Toro si comporta esattamente come prima (3 slot/350/medio/Claude).
- `LONG_ONLY`: Toro PAPER Gemello 10 slot/100, soltanto nuovi LONG scalp.
- Valore sconosciuto (anche refuso): `BLOCK_NEW` — vieta entrambe le direzioni di nuove aperture e tutti i DCA, annulla split pending, preserva gestione delle uscite.
- `DESK_MODE=live`: Twin OFF anche se la variabile è impostata; nessuna nuova funzionalità LIVE.
- SHORT Toro preesistenti: SL, TP, chiusure/partial_close permessi; nuove seconde gambe SHORT annullate prima della scansione stop; DCA SHORT bloccati. LONG già aperti restano normalmente gestibili.
- `DESK_S25_TORO_ENTRY_APPROVED=1` NON può autorizzare nuove S25 se Twin != OFF; la gestione delle uscite S25 legacy rimane.
- Lo stato `candidate` documenta i rifiuti per direzione, orizzonte o configurazione errata; nessun trade viene inventato.

## Test scritti ma NON eseguiti

`backend/tests/test_classics_twin_long_only.py` — config PAPER/LIVE, cap/guardrails, modalità legacy,
allow/block LONG/SHORT da AI e rules, splits, DCA legacy, S25, NO_TRADE e cicli del bot.
Test S25 legacy in `backend/tests/test_desk_rc84_phase2.py` allineato al requisito aggiuntivo Twin OFF.

**Obbligatorio prima di qualsiasi release:** pytest Phase2/2B/2C, RC82/RC84, Fase3; prova SHORT-by-SHORT
sullo stesso feed vs `f8332c9`, e ritorno OFF; verifica claim e pause, nuovi LONG no trade
su trend 4H UNKNOWN, liquidazioni, saldo, logging, slippage, commisioni, memory, S25.

## Rischio e risultati pregressi: nessuna promessa

Backtest reale 2025–2026 della PR #93 ha dato **FAIL** sulla variante LONG 15m e anche
`LONG originale 1h` nella sua simulazione (media netta ~−0,164% nello studio, ~−0,289% in valutazione),
nonostante questo sia un test di riferimento differente dal runner Toro Twin con AI.
**Copiare capitali, slot e parametri non crea un vantaggio LONG.** Quindi la modalità Twin
**non è pronta per una ripartenza**, nemmeno PAPER, prima di nuovo backtest con le regole correnti e benchmark reali.

La soglia `kill_equity=450` **blocca aperture**, non garantisce matematicamente che un gap o posizioni
già aperte non facciano scendere l'equity sotto 450: audit risk preventivo ancora aperto.
L'operatività con 10 posizioni correlate merita una verifica di esposizione aggregata prima dell'unpause.

## Prossime attività autorizzabili (non automatiche)

1. Claude Opus esegue test locali e corregge solo regressioni dimostrate sul nuovo ramo, senza cambiare SHORT.
2. Grok verifica indipendentemente direzione, uscite legacy, NO_TRADE, S25 e assenza bypass.
3. Backtest su dati reali conservando le stesse regole, includendo costi e scenari di rischio aggregato.
4. Nessuna modifica a servizi o VPS finché non siano superati i gate rischio e accordata autorizzazione esplicita per la distribuzione PAPER.

**Questa PR è soltanto il candidato configurabile. Non eseguire merge/deploy/unpause/reset.**
