# Laboratorio Edge — Rapporto Finale
**Data:** 29 ottobre 2026  
**Autore:** Claude Sonnet 4.6  
**Branch:** `work/edge-lab-claude-20261029`  
**Dati:** 540 giorni candele reali Bitget 15m, fine 2026-10-29  
**Durata esecuzione:** 22 minuti 53 secondi  

---

## Risultato sintetico

> **Nessuna delle tre ipotesi ha superato le gate pre-registrate.**  
> Il sistema base13 non ha un vantaggio lordo sufficiente a sopravvivere ai costi reali, né un'architettura che migliori col cap delle posizioni o con un breakout 4h.

---

## Blocco A — Impatto costi

**Ipotesi:** ordini maker (~4 bp/lato) rendono il sistema profittevole?

| Variante | Trade | Netto $ | R medio | G1 (ΔR≥0) | GA1 (netto>0) | GA2 (R>0) |
|----------|-------|---------|---------|-----------|--------------|-----------|
| base_taker (6 bp) | 5.084 | −21.786 | −0,1596 | — baseline — | — | — |
| maker_4bp (4 bp) | 5.176 | −15.855 | −0,1066 | ✅ +0,0530 | ❌ | ❌ |
| maker_3bp (3 bp) | 5.229 | −12.308 | −0,0773 | ✅ +0,0823 | ❌ | ❌ |
| zero_cost (0 bp) | 5.378 | −4.092 | −0,0040 | ✅ +0,1556 | ❌ | ❌ |

**Verdetto:** G1 superata (meno costi = meno perdite, ovvio). GA1 e GA2 **non superate da nessuna variante**.  
Anche con zero costi il sistema perde −4.092$ su 540 giorni (R = −0,004). Il vantaggio lordo non esiste.

**Conclusione chiave:** i costi non sono il problema principale — anche senza commissioni il sistema perde. Il segnale grezzo di base13 non ha un'edge positiva su questo mercato.

---

## Blocco B — Cap concentrazione posizioni

**Ipotesi:** limitare le posizioni aperte nello stesso senso riduce le perdite concentrate?

| Variante | Trade | R medio | Drawdown $ | Bloccate % | G1 (ΔR≥0) | GB1 (dd<90%) | GB3 (blk≤50%) |
|----------|-------|---------|-----------|-----------|-----------|-------------|--------------|
| cap_none (base) | 5.084 | −0,1596 | 23.498 | — | — | — | — |
| cap_5 | 4.265 | −0,1589 | 19.054 | **69%** | ✅ | ✅ | ❌ |
| cap_3 | 3.470 | −0,1617 | 15.562 | **82%** | ❌ | ✅ | ❌ |
| cap_1 | 1.729 | −0,1698 | 7.457 | **95%** | ❌ | ✅ | ❌ |

**Placebo B (8 cap casuali, seed=42):** mediana R ≈ −0,159 — indistinguibile dai cap veri.

**Verdetto:** GB3 **non superata da nessuna variante** — la percentuale di aperture bloccate è enorme (69%–95%). Il cap non seleziona i trade migliori, li elimina quasi tutti indiscriminatamente. Il drawdown scende proporzionalmente ai trade eliminati, non perché migliori la qualità delle operazioni.

**Conclusione chiave:** non c'è concentrazione da correggere — il problema è il segnale, non il numero di posizioni aperte contemporaneamente.

---

## Blocco C — Strategia trend 4h BTC+ETH

**Ipotesi:** un breakout su barre 4h (ATR SL/TP, lookback=20) ha un vantaggio lordo?

| Variante | Trade | R lordo | PF | R OOS | GC1 (R>0) | GC2 (PF>1) | GC3 (Roos>0) |
|----------|-------|---------|----|----|-----------|------------|--------------|
| lordo (0 bp) | 251 | −0,0029 | 0,954 | −0,003 | ❌ | ❌ | ❌ |
| maker (4 bp) | 251 | −0,046 | 0,902 | −0,046 | ❌ | ❌ | ❌ |
| taker (6 bp) | 250 | −0,061 | 0,885 | −0,061 | ❌ | ❌ | ❌ |
| invertito (placebo) | 257 | −0,169 | 0,814 | −0,169 | ❌ | ❌ | ❌ |

**Verdetto:** tutte le gate **non superate**. Nemmeno lordo e senza costi il breakout 4h è positivo (PF=0,954, R=−0,003). Il segnale non funziona su BTC+ETH in questo periodo.

**Nota:** il segnale invertito perde ancora di più (R=−0,169), il che conferma che non c'è alcun segnale direzionale catturabile: né nella direzione originale né in quella opposta.

---

## Confronto con P1 Lab (ripasso)

Il P1 Lab (long-bias) aveva già mostrato R lordo ≈ −0,004. Il Blocco A conferma questo valore con metodo indipendente (zero_cost: R=−0,004, 5.378 trade vs 540 giorni). I due esperimenti sono coerenti — nessun errore sistematico nel codice.

---

## Cosa questo non dice

- **Non dice** che il bot non possa mai essere profittevole — dice che le strategie testate con i parametri attuali non lo sono.
- **Non dice** che i dati siano sbagliati — 5.000+ trade su 540 giorni reali è un campione solido.
- **Non dice** che maker orders non aiutino — aiutano (tagliano le perdite del 28%), ma non bastano da soli.

---

## Prossime ipotesi possibili (solo ricerca — nessun deploy senza OK utente)

Se si vuole continuare la ricerca, le strade ancora non testate sono:

1. **Segnale più selettivo:** ridurre il numero di trade con filtri più severi (confidenza >75%, solo regime S3, ecc.) — qualità sopra quantità.
2. **Gestione del trade:** trailing stop invece di TP fisso su trend forti — catturare le code.
3. **Orari:** escludere le fasce con più rumore (weekend, bassa liquidità asiatica).
4. **Asset class diversa:** materie prime (XAU, XAG) con i quali il sistema lavora diversamente.

Tutte queste sono ipotesi da pre-registrare e testare nello stesso modo — offline, senza toccare i bot.

---

## Stato dei bot

- **Hawk e Bull**: invariati, mai toccati durante questo laboratorio ✅  
- **DESK_MODE**: rimane `paper` ✅  
- **Cervello** (`trade_history.jsonl`, `lessons.md`, ecc.): non modificato ✅  
- **Ramo**: `work/edge-lab-claude-20261029` — mai unito a `rule-pool` ✅

---

*Commit risultati: `da4d68e` — `edge-lab: risultati su candele reali [skip ci]`*
