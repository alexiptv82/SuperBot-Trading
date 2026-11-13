# SuperBot — Falco SHORT / Toro LONG: coppia di portafogli gemelli (PAPER)

**Stato:** esperimento reversibile su ramo isolato, collaudato tecnicamente il 13/11/2026 (vedi in fondo), **NON attivato**.
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

## Test (eseguiti nel collaudo del 13/11/2026, vedi in fondo)

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

## Collaudo del 13 novembre 2026 (Claude, sul commit `4025db3`)

**Verdetto tecnico: PASS** (correttezza dell'implementazione). **Verdetto strategico: i risultati NON giustificano un
collaudo PAPER di Toro gemello LONG**; la configurazione resta un candidato tecnico, interruttore OFF, PR in Draft.

### 1. Falco SHORT invariato: confronto di comportamento, non solo di impronte

Il vero `cli.run_cycle` di `f8332c9` e di questo ramo è stato eseguito, in processi separati, sullo **stesso flusso di
candele reali Bitget USDT-FUTURES** (BTC, ETH, SOL; 15m e 4H native; 22/05/2025 → 13/11/2026; un ciclo ogni 30 minuti;
26.000 cicli circa) con `deploy/scripts/replay_classics_twin_real.py`. Confronto con
`deploy/scripts/compare_classics_twin_replays.py` (risultato in `docs/v3/classics-twin-collaudo/confronto-replay.json`):

| Configurazione | Chiusure | Esito |
|---|---|---|
| Falco SHORT_ONLY, sole regole | 351 | identico |
| Falco SHORT_ONLY, percorso Claude (decisioni pseudo-casuali deterministiche) | 312 | identico |
| Falco BOTH, sole regole | 255 | identico |
| Falco BOTH, percorso Claude | 276 | identico |
| Falco SHORT_ONLY con `DESK_BULL_TWIN_MODE=LONG_ONLY` nell'ambiente | 312 | identico |
| Falco SHORT_ONLY, periodo B, dopo la correzione di questo collaudo | 98 | identico |
| Toro OFF esplicito / variabile assente vs Toro di `f8332c9` | 392 | identico |

"Identico" vuol dire: stessi segnali e aperture (simbolo, lato, istante, prezzo, leva, margine, stop, TP, motivazione),
stesse chiusure (prezzo, motivo, PnL, commissioni), stessi candidati rifiutati, stesse posizioni finali e stessa
cassa. L'unico campo escluso è `logged_ms`, l'orario di sistema in cui la riga viene scritta.

### 2. Toro gemello: requisiti

| # | Requisito | Esito | Prova |
|---|---|---|---|
| 1–3 | 1.000 USDT, 10 posizioni, 100 USDT per operazione | OK | `Limits` identici a Falco; margine 300 proposto → 100 |
| 4 | Stessi guardrail e limiti di Falco | OK | 30$/5× → 60$/15× scalp come Falco |
| 5 | LONG da Claude e regole | OK | ciclo vero, entrambe le fonti |
| 6 | Nuovi SHORT sempre rifiutati | OK | `open_short`/`open_short_split`, Claude e regole; replay: 0 SHORT in 26.000 cicli |
| 7 | NO_TRADE | OK | risposta vuota di Claude non sostituita da LONG delle regole; trend 4h UNKNOWN blocca |
| 8 | Nessuna trasformazione SHORT → LONG | OK | risposta di Claude con soli SHORT: nulla si apre, le regole non subentrano |
| 9 | Uscite SHORT preesistenti | OK | stop, TP, chiusura parziale e chiusura decisa |
| 10 | DCA e seconde gambe SHORT bloccati | OK | DCA SHORT bloccato, DCA LONG ammesso; seconda gamba SHORT annullata, LONG mantenuta |
| 11 | S25 disabilitata | OK | ciclo vero: con OFF e autorizzazione S25 apre (controllo), con LONG_ONLY no |
| 12 | Ritorno con OFF | OK | ciclo vero e replay reale identico a `f8332c9` |
| — | Valore non valido | OK | BLOCK_NEW: nessun nuovo ingresso, DCA o seconda gamba; uscite consentite; replay reale: 0 aperture |

I test nuovi (`backend/tests/test_classics_twin_collaudo.py`, 13) falliscono se si tolgono il blocco DCA, il vincolo
S25, il tetto di 100 USDT o l'annullamento delle seconde gambe (prova a mutazione eseguita).

### 3. Difetto trovato e corretto

`policy_shadow_violations` (solo registro, nessun effetto sulle decisioni) applicava al gemello il contratto del
vecchio prompt Toro (TP ≥ 5%, confidenza 65/75), mentre il prompt gemello è quello di Falco: una proposta valida
risultava "violazione". Ora il contratto Toro vale solo con OFF; il comportamento di Falco e di Toro OFF non cambia.
Test: `test_shadow_audit_uses_the_falco_contract_in_twin_and_the_toro_contract_when_off`.

### 4. Protezione del capitale (replay reale, sole regole)

La protezione dei 450 USDT ferma le nuove aperture come previsto; nessuna apertura dopo la soglia. Nel replay del
gemello con percorso Claude pseudo-casuale si sono verificate 2 liquidazioni (SOL 25×, ETH 26×; le leve vengono dalle
decisioni; il motore applica i tetti per asset): la soglia 450 blocca le aperture, non limita la perdita delle posizioni
già aperte.

### 5. Risultato strategico su dati reali (sole regole, nessun Claude reale)

| Replay (1.000 USDT iniziali) | Operazioni | PnL netto | Profit factor | Lordo prima dei costi | Commissioni | 450 raggiunto |
|---|---|---|---|---|---|---|
| Toro gemello LONG, 22/05/2025 → | 229 | −556,9 | 0,83 | +25,4 | 543,5 | 10/09/2025 |
| Toro gemello LONG, periodo B (15/02/2026 →) | 112 | −551,9 | 0,61 | −280,5 | 254,1 | 15/07/2026 |
| Falco SHORT_ONLY, 22/05/2025 → | 351 | −576,6 | 0,91 | +261,2 | 837,8 | 19/02/2026 |
| Falco SHORT_ONLY, periodo B | 98 | −602,4 | 0,63 | −378,3 | 224,1 | 02/04/2026 |

Su tre mercati e con le sole regole, **entrambi i gemelli consumano il capitale fino alla protezione**. Il LONG del
gemello ha un risultato lordo vicino a zero nel primo periodo e negativo nel secondo; le commissioni a leva ~20× lo
rendono pesantemente negativo. Coerente con il backtest della PR #93 (LONG originale 1h negativo).

Limiti dichiarati: tre mercati invece dei 30 del runner; nessun Claude reale (le sue decisioni non sono riproducibili);
contesto, notizie e funding esterni disattivati; cicli a cadenza fissa di 30 minuti. Questi limiti valgono anche per
Falco: il replay non dice che lo SHORT di produzione perda, dice che le **regole** da sole non bastano su questi mercati.

### 6. Conclusione

- Correttezza tecnica: **PASS**.
- Protezione del capitale: la soglia 450 funziona come blocco delle aperture; liquidazioni possibili a leva alta.
- Risultato strategico: **non giustifica** un collaudo PAPER di Toro gemello LONG. Lasciare `DESK_BULL_TWIN_MODE` non
  impostato (OFF). Nessun merge, deploy, unpause o reset.
