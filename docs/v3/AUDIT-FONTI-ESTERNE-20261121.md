# Audit esplorativo: registri pubblici di altri sistemi di trading AI (21/11/2026)

**Metodo:** lettura di README, schemi, licenze ed elenchi dei file tramite l'API di GitHub. Nessun dataset scaricato, nessun codice di terzi eseguito, nessuna API a pagamento. I contenuti di terzi sono trattati come dati non attestati.
**Vincoli:** nessun dato esterno entra nel training o nel runtime; nessuna modifica a strategie, parametri o runtime; nessuna nuova linea di sviluppo senza approvazione.

## Sintesi
Nessuna delle quattro fonti offre **operazioni crypto perpetual per singolo trade con il contesto di mercato al momento della decisione**, che è l'unica cosa che amplierebbe davvero la memoria del Brain. Il valore è **metodologico**: ipotesi già misurate su popolazioni grandi, da verificare sui **nostri** dati attestati. Come dati, le nostre run Brain V3 e Arena (circa 4.900 eventi con catena di hash verificata) superano già tutte le fonti in qualità e pertinenza.

## Valutazione per fonte
| | sunshinfight/nof1-arena-data | Dixter999/nof1-tracker | qrak/LLM_trader | ProjectDXAI/continuous-record |
|---|---|---|---|---|
| Che cos'è | SQLite di ~5 MB raccolto dall'API di nof1 Alpha Arena (8 LLM, Hyperliquid) | **solo uno scraper** (Playwright + PostgreSQL): nel repository non ci sono dati | agente LLM PAPER con memoria vettoriale; registro congelato | articolo (arXiv 2609.05663) + dati aggregati delle figure |
| Tipo di operazioni | reali o simulate secondo nof1 (non verificabile); **trade per singola operazione solo della Stagione 1.5 = azioni USA** (NVDA, TSLA…) | — | PAPER su testnet, **commissioni zero** | flotta Hyperliquid: PAPER a prezzi reali + piccolo libro reale |
| N. operazioni utilizzabili | ~400 trade (non crypto); crypto della Stagione 1 solo come **aggregati** per run (32) e curva oraria del patrimonio | 0 | 20 chiusi (17 contati), 174 cicli | **0 righe per posizione** (solo aggregati; 3 casi anonimizzati su Hugging Face) |
| Contesto alla decisione | 100 conversazioni (prompt + ragionamento), della Stagione 1.5 (azioni) | — | prompt e memoria pubblicati sul sito; nel repository c'è `cycles.jsonl` (53 kB) | no |
| Prezzi / ora / leva / stop / commissioni / esito | sì nei trade (azioni); stop solo come testo (`invalidation_condition`) | — | presumibilmente nel DB; commissioni assenti | solo statistiche |
| Ricostruibile senza informazioni future | parziale e solo per le azioni; per le crypto no | — | sì in principio (candele 4h BTC), ma 20 trade | no |
| NO_TRADE | solo conteggi `num_hold_signals` negli aggregati | — | "segnali rifiutati" in memoria (non nel registro congelato) | aggregati di replay |
| Provenienza e affidabilità | dati di nof1, **non attestabili**; nota dell'autore: alcuni campi a volte già moltiplicati | — | snapshot con manifest SHA-256 (buona pratica), ma sorgente privata | articolo con metodologia e ritrattazioni dichiarate |
| Licenza | MIT per lo script; **diritti sui dati di nof1 non dichiarati** | MIT (codice); lo scraping del sito richiede di rispettarne i termini | MIT | CC BY 4.0 (testo, figure); dataset con le loro licenze |
| Compatibilità con Bitget USDT-M | bassa: Hyperliquid, prompt diversi; le crypto non sono per trade | — | spot/testnet BTC/USDC 4h, nessuna leva né funding | Hyperliquid perps: metodologicamente vicina |
| Utilità rispetto alla nostra memoria | bassa come dati | nulla | bassa come dati, **alta come architettura** | **alta come ipotesi** da verificare |

**Fonti realmente utilizzabili come DATI per Brain Unico: nessuna.** La meno lontana è nof1, ma i trade per singola operazione sono di azioni e non c'è alcuna attestazione.

## Cosa vale la pena imparare, senza importare dati
Ogni punto si verifica come **analisi controfattuale pre-registrata sui nostri journal attestati**, senza modificare il runtime e senza promozioni automatiche.

1. **Profitto raggiunto e poi restituito** (DXRG): il 43 % delle posizioni tocca +300 bp e metà chiude in perdita; un bracket fisso batte le uscite discrezionali. Collegamento: punto 6 (uscite). Misurare MFE, MAE e cattura sulle nostre run (i campi `mfe_r`/`mae_r` esistono già nei classici, che però non sono certificati: utilizzabili solo come confronto descrittivo) prima di proporre varianti di uscita.
2. **Leva cieca alla volatilità** (DXRG): la leva mediana è uguale in ogni fascia di volatilità e le liquidazioni sono concentrate. Collegamento: punto 5 (profilo di rischio). Misurare la distanza dallo stop e dalla liquidazione per fascia di ATR nelle nostre decisioni.
3. **Coerenza delle scelte** (DXRG): stessi scenari ripetuti, tasso di ripensamento dal 35 % a oltre il 90 % secondo il modello. Collegamento: la memoria decisionale. Misurare la stabilità delle decisioni su snapshot identici tra le run Arena; è un buon indicatore per scegliere il modello.
4. **Elementi del prompt che guidano gli ingressi** (DXRG: una classifica mostrata nel prompt determina il 46 % degli ingressi). Collegamento: snapshot v2. Verificare se qualche campo del nostro prompt domina gli ingressi.
5. **Memoria e riflessione controllate** (qrak):
   - recupero dei soli trade più simili e di poche regole;
   - "rapporto di sorpresa" per ridurre il peso di regole poco attendibili;
   - **controllo deterministico delle affermazioni del modello**: la forza del trend dichiarata viene confrontata con l'ADX calcolato e sovrascritta;
   - memoria dei segnali rifiutati, l'equivalente dei nostri NO_TRADE.

   Collegamento: potrebbe diventare uno strato di **consultazione in sola lettura** sopra EventJournal, mai una sorgente di training. Il controllo delle affermazioni è il punto più concreto e meno rischioso.
6. **Disciplina dei numeri pubblici** (qrak `claims.json`, DXRG con le ritrattazioni): coincide con la nostra regola "snapshot congelato + manifest SHA-256 + nessun numero non riproducibile".

## Proposta minima (solo se approvata)
- **Fase A, senza codice nel runtime:** un rapporto offline sulle nostre run attestate, cioè Brain V3 e le 3 Arena, con le misure 1–4. Strumento in `ops/brain-unico/analysis/`, sola lettura, nessuna rete.
- **Fase B, opzionale:** una "memoria esterna" separata, contenente **solo le ipotesi** e le citazioni, cioè fonte, licenza e numero riportato, in un file statico versionato; nessuna riga di trade esterna. Il Dataset Builder non la legge. `SOURCES` resta invariato.
- **Esclusi:** importare trade o conversazioni di nof1 (licenza dei dati non chiara, azioni, nessuna attestazione); eseguire scraper o il codice di qrak; scaricare il pacchetto DXRG, che non contiene righe per posizione.

Costo stimato della Fase A: piccolo e dopo la RC. Non rallenta backup, RC e completamento di Brain Unico.
