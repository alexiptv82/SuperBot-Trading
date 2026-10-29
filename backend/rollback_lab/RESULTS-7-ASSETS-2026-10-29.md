# Esperimento A/B sul primo campione Bitget — 29 ottobre 2026

**Tipo:** simulazione PAPER offline, NON un replay fedele dell'esecuzione storica. Eseguito con GitHub Actions **40821658014** (SUCCESS) su candele pubbliche Bitget. Nessuna connessione VPS, ordine, chiave exchange, merge o deploy. Artefatti JSON/log conservati nel workflow.

## Mandato e input

- Periodo: 12 ottobre 2026 00:00 UTC fino al 29 ottobre 2026 00:00 UTC; 17 giorni.
- Mercati effettivamente caricati: BTC, ETH, SOL, ADA, DOGE, BNB, XRP.
- Feed identico per Hawk e Bull; checksum SHA256 su array 15m, 4h, 1d: `3a0b3b232509f6e7d441045449647955f025a4c4f5fb65ded7e64f80374dc5ab`.
- Motore entry 'old': `signals.py` effettivo di a0afc63 (12/10), stagionalità storica, max 1000 barre 15m, nessun 4h nativo/1d; scorer genera lato, score, livelli. Motore entry 'modern': `signals.py` del runtime dc16e01 con 4h e 1d nativi e configurazione attuale. Nelle due varianti si usa la medesima routine di decisione regole (non i prompt AI storici): confronto SCORER+INPUT, non esecuzione integrale 12/10 contro attuale.
- Esecuzione OHLC 'old': `PaperAccount` di a0afc63; 'modern': `PaperAccount` dc16e01. Config fissata da run storiche, start1000 USD, Hawk massimo100/trade e10 slot, Bull350/trade e3slot, daily stop12%, kill equity450, soglia A/B60/C70, costi del motore. Scelte ogni 2 barre15m (30min); senza Claude, DeepSeek, DCA, split, macro e intrabar tick.
- Le quattro varianti condividono gli stessi prezzi; identica impronta dati per entrambi i portafogli. Test con reset di capitale iniziale UNA volta all'inizio dei 17 giorni, **NON un nuovo conto ogni finestra di calendario**. Periodi sono raggruppamenti *per data di chiusura*, con effetto dell'esposizione precedente.

## Risultati complessivi simulati

| Portfolio | Scoring e mercato | Motore OHLC | Posizioni chiuse | Netto USD | Win rate | Max drawdown simulato |
| --- | --- | --- | ---:| ---:| ---:| ---: |
| Hawk | vecchio | vecchio | 115 | -443.70 | 36% | 891 |
| Hawk | vecchio | moderno | 115 | -443.70 | 36% | 891 |
| Hawk | moderno | vecchio | 14 | -10.00 | 43% | 100 |
| Hawk | moderno | moderno | 14 | -10.00 | 43% | 100 |
| Bull | vecchio | vecchio | 69 | -585.40 | 33% | 1001 |
| Bull | vecchio | moderno | 69 | -585.40 | 33% | 1001 |
| Bull | moderno | vecchio | 14 | -20.40 | 43% | 183 |
| Bull | moderno | moderno | 14 | -20.40 | 43% | 183 |

*L'identità dei risultati fra i due motori OHLC in questo campione significa soltanto che nei casi simulati le differenze di exit non hanno influito sulle operazioni completate. NON prova equivalenza delle funzioni di uscita in produzione.*

### Effetto direzione e attività
- Hawk 12/10: 115/115 posizioni SHORT, netto -443.70. Hawk moderno: 11 LONG con -78 USD e 3 SHORT con +68 USD.
- Bull 12/10: 69/69 SHORT, netto -585.40. Bull moderno: 11 LONG con -148 USD e 3 SHORT con +127 USD.
- Il vecchio comportamento apre molto di più ma perde; quello moderno apre poco e chiude comunque negativo in questo campione. **Non scegliere un rollback dal solo saldo totale.**

### Finestra per data di chiusura, conto continuo
| UTC | Hawk OLD | Hawk modern | Bull OLD | Bull modern |
|---|---:|---:|---:|---:|
| 12–16 ottobre | +25.83 | +42.08 | -136.61 | +74.04 |
| 16–20 ottobre | -214.08 | -62.57 | -107.12 | -109.24 |
| 20–25 ottobre | -68.23 | +24.22 | -112.75 | +40.44 |
| 25–29 ottobre | -187.20 | -13.76 | -228.90 | -25.60 |

## Validazione mancante e decisioni
1. Le golden REALI 12–16 ottobre su intero universo e con AI/posizioni registrate hanno guadagnato Hawk +1090.61 (76 posizioni) e Bull +770.75 (17 posizioni). La simulazione limitata a7 mercati non ricostruisce affatto quegli esiti, soprattutto Bull: non usare come replica fedele.
2. Lo scorer originale era identico anche al primo crollo del 16/10; il problema NON è spiegato da un file `signals.py` cambiato.
3. Il bot attuale usa il nuovo contesto4h/1d: le condizioni di disponibilità dati influenzano il numero di aperture; 7 simboli non rappresentano tutte le altcoin che contribuivano alle golden. Un test sull'intero universo è avviato separatamente.
4. **Priorità:** validare il replay contro reali posizioni, tempi, costi e fonti di decisione. Poi run per finestra indipendente con nuovi conti virtuali, diverse volatilità, sensibilità ingressi15m vs30m e ai costi. Soltanto allora investigare filtri regime/momentum, non imporre aumento leve.
5. Nessun deploy classici e nessun cambiamento ai portafogli, journal, vault, Brain o app. Per passaggio operativo: backup/restore e OK separato.

AI: chatgpt (chat normale)
