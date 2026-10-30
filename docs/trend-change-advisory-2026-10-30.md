# Sensore di cambio di trend v1 — Brain (30/10/2026)

## Decisione funzionale dell'utente
Riconoscere il prima possibile quando un ribasso potrebbe girarsi al rialzo, e viceversa. Il sensore non e' una strategia di ingresso, non limita o blocca LONG/SHORT e non controlla rischio, stop o capitale. La logica di apertura rimane la stessa in entrambe le direzioni e Brain conserva la propria valutazione AI.

## Codice scritto sul ramo isolato
- `backend/director/trend_advisory.py`: lettore numerico puro, identico a quello del ramo classici. Analizza 40 barre OHLCV chiuse e contigue; usa differenze di log-prezzi per simmetria up/down. `early_upshift` = forza precedente negativa, ultimi tre intervalli positivi; `early_downshift` speculare. Altrimenti `up_continuation`, `down_continuation`, `uncertain`. Stato sempre `advisory_only`, `may_authorize_entry=false`, `may_block_entry=false`. Se ci sono dati mancanti/obsoleti o candele non chiuse, nessuna osservazione. I nomi non implicano che l'inversione sia certa.
- `backend/director/brain_scalp/service.py`: prende i dati 5m pubblici gia' raccolti; legge l'osservazione localmente, senza chiamate API aggiuntive e senza intervenire nell'exchange.
- `backend/director/brain_scalp/supervisor.py`: garantisce che il tick protettivo sia eseguito PRIMA della parte AI. Le osservazioni sono passate come materiale opzionale all'analista, mai a una funzione di ammissione.
- `backend/director/brain_scalp/coordinator.py` e `ai_context.py`: osservazioni con schema/epoca verificati nei candidati gia' ammessi allo scanner. Assenza o errore del sensore non esclude candidati e non provoca fallback ai trade senza AI.
- Il SYSTEM di DeepSeek tratta la possibile inversione come ipotesi, confronta LONG e SHORT, applica gli stessi criteri di costi, invalidazione e rischio; Claude e' solo secondo parere selettivo.

## Limitazioni importanti da non nascondere
1. La lettura su 5m ha latenza di qualche candela: in genere osserva gli ultimi 15 minuti di movimento rispetto a un trend precedente. Non identifica i minimi o massimi futuri e non e' una previsione statisticamente calibrata.
2. Il Brain oggi consulta DeepSeek solo in presenza di candidati scanner. Il lettore **non genera** da solo un nuovo candidato e non apre trade. Lo scanner resta un filtro per setup di ingresso e puo' richiedere un breakout LONG dopo il primo segnale di svolta: requisito da studiare in un laboratorio separato, non aggirare con ordini forzati.
3. Nessun segnale 4h EMA200 o la vecchia P1 vengono usati come veto o requisito dell'advisor. La sperimentazione Claude Regime Reader fallita **non** viene introdotta.
4. Per valutarne il beneficio servono analisi su dati storici con etichette di regime, falsi allarmi, latenza di rilevamento, costi netti e confronto LONG/SHORT fuori campione. Questi test predittivi NON sono ancora eseguiti.

## CI e sicurezza
Run GitHub Actions `41043182817` SUCCESS: Python 3.10/3.11, 33 test pytest mirati e 175 test unitari Brain per versione. Causalita', non-leakage di candele incomplete, simmetria prezzi inversi, schema AI, fallback non bloccante, verifica dossier/protezioni. Nessuna rete, chiave, ordine, modifica allo stato del wallet Brain gia' esistente, nessun merge o deploy.

**Branch:** `work/brain-trend-awareness-20261030`, nato da `work/brain-single-integration-20261030`.
AI: chatgpt
