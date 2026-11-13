# 2026-11-13 — Toro funding LONG: pre-registrazione verificabile, NO RUN

**Fonte originale:** rapporto Claude `TORO-LONG-nuova-ipotesi-rapporto-Claude-2026-11-13.md`, sezioni D-F.  
**PRE-REG COMMIT (già creato prima di ogni nuovo backtest):** `429bdd7382ef03a4f1617ee6174ed35d7e44f7a2`  
**File canonico immutabile:** `docs/v3/TORO-FUNDING-LONG-PREREG-20261113.md` nel ramo `work/toro-funding-prereg-20261113`.  
**PR Draft:** #97. **Precedente V1:** PR #96, Step 0′ V1 esito NO-GO, NON deploy.  
**Stato:** nessun run/test della nuova ipotesi, nessun deploy/merge, Brain PAPER invariato, Falco SHORT/Toro non riattivati.

## Precisazioni richieste prima di lanciare
- **Nessun filtro R:R** nel segnale funding; la specifica prevede **solo stop distante 0,8–2,5 ATR**.
- **24h** orizzonte **PRIMARIO**, **8h** secondario.
- Benchmark espliciti: **(1) LONG random stesso asset/mese, (2) LONG random con funding negativo senza trigger, (3) stesso trigger SENZA funding**. 1.000 randomizzazioni ciascuno, confronto per matching temporale e costi; benchmark (3) confuta il valore aggiunto del funding.
- **Salvare ogni trade** (segnale, timestamp as-of settlement, prezzi, funding, MFE/MAE, costi, durata, giorno/episodio, capitale e hash delle fonti). Riportare **segnali per mese**, compresi mesi senza trade.
- **Cinque simboli riservati per nome:** `ADAUSDT`, `AVAXUSDT`, `BCHUSDT`, `DOGEUSDT`, `DOTUSDT`. Regola meccanica: primo cinque in ordine alfabetico tra pannello 15 pre-fissato, escludendo i 5 osservati nella V1; non sostituirli mai a posteriori. Per ogni mese utilizzarli solo quando soddisfano davvero la selezione top15 per volume 30gg e storia >=365gg, con dati storici (nessun survivorship).
- Sei soglie GO Claude **immutate**: >=150 trade e 60 giorni-evento; lordo medio 24h funding incluso >=25pb e IC95% basso >10pb; positivo separatamente in validazione e test; >95° percentile di ciascuno dei tre benchmark; nessun mese >30% del risultato e positivo escludendo il 5% dei migliori trade; positivo in tutti i cinque holdout.
- **Gate dati funding Binance vs Bitget** proposto e pre-registrato: almeno 70% coincidenza aggregata degli episodi Binance negativi+estremi con Bitget, >=60% per simbolo, almeno 10 episodi e >=90% coverage temporale; se manca o fallisce, **nessun GO sul proxy Binance**. Solo diagnostica comparativa RETROSPETTIVA sulla sovrapposizione disponibile: NON usare percentili 90d stimati sul futuro per i segnali causali.
- Binance funding storico è **proxy**, NON funding pagato su Bitget. API Bitget funding pubblico ultimi 90gg, insufficienti per percentile rolling dei precedenti 90gg sull'intera overlap senza dati aggiuntivi. GO storico proxy richiede convalida separata (8 settimane shadow real funding Bitget, poi PAPER).
- **Rischio suggerito in futuro** 12 USDT/trade, 24 USDT aggregati; NON applicare alla configurazione operativa durante il Passo 0′.
- **NO-GO:** stop a questa linea di LONG rules-only, nessun ritocco parametri sul medesimo OOS.

## Gate ancora aperti prima del primo test P
1. Con un comando READ-ONLY sulla VPS verificare `step0_SOLUSDT_result.json`: `report.windows["4"].avg_net` e `avg_gross`, poiché log +0.000257 ma tabella manuale mostra un segno negativo.
2. Verificare se sia possibile ricostruire top15 30gg storici e funding storico con provenienza e timestamp, distinti per Binance e Bitget, senza lookahead.
3. Controllare che il commit prereg `429bdd7...` sia disponibile nel repository PR#97 **prima** di qualunque risultato/esperimento nuovo.
4. Nessuna modifica ai processi, al capitale o alle strategie Falco/Brain. Nessun merge/deploy.

**Nota:** soglia coincidenza 70/60/10/90 è una scelta di progettazione registrata preventivamente su richiesta dell'utente; NON era una soglia numerica fornita da Claude. Il pannello 15 è una scelta di pre-selezione, non un'asserzione che sia realmente il top15 storico.
