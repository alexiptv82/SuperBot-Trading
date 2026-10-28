# Brain Scalp dual — sviluppo offline e revisione Claude

28 ottobre 2026. Opzione B: archiviare il Brain originale, poi sostituirne l'operatività con Brain Hawk e Brain Bull. Questo ramo di sviluppo NON effettua l'archiviazione, non si collega al VPS e non modifica Hawk/Bull classici. Base: e0021488b47e8b245954a708b139bc4785a4b644 (Brain Free V2). Non fare merge automatici verso rule-pool: il ramo storico è divergente.

## Codice completato
- Wallet Hawk 10 slot e Bull 3 slot, ciascuno 1.000 USD PAPER nuovi, database SQLite, writer lock, identificativo di conto e budget rischio separati. Questi nuovi saldi non rappresentano una cancellazione delle perdite precedenti.
- Config di laboratorio: margini Hawk 100–250, Bull 150–350; budget margine 950 per wallet; rischio stimato a stop 50 USD per trade / 150 USD aggregati, stop giornaliero 20%, kill equity 450. Questi nuovi limiti devono essere revisionati prima dell'attivazione.
- Scanner breakout long/short con candele 1m/5m chiuse e controlli su volumi, freschezza e continuità; shortlist e motivazione per ogni simbolo. Bounce e altri setup non sono ancora integrati.
- Piani AI con direzione, trigger, expiry, stop, target, margine, leva, durata, protezione netto e invalidazione. Direzione incoerente con la shortlist, timestamp scaduti e contraddizioni sono rifiutati.
- Esecuzione condizionale PAPER ogni tick usando il motore fisico di Brain Free V2 per precisione Bitget, fee/slippage, liquidazione, stop/target; protezioni e uscite su prezzi osservati. Slot e margine prenotati dai piani pendenti. Due wallet autonomi e una sola shortlist condivisa.
- Test su Python 3.10/3.11 in workflow isolato; nessuna chiave, deploy, modifica ai classici o al Brain originale.

## BLOCCANTI al deploy
1. Worker H24 collegato al feed Bitget (WS/REST), universo di mercato filtrato, riconnessione e dati mancanti, senza duplicare il writer.
2. Chiamate DeepSeek con prompt compatto, budget reserve/settle crash-safe per wallet e totale, metrica consumo/latenza; nessuna analisi completa di 26 monete ad ogni ciclo.
3. Replay causale per trend/range/alta volatilità, test intrabar/gap e casi avversariali su long e short, confronto net expectancy/drawdown/costi/frequenza.
4. Setup bounce/retest/momentum; misurazione ragioni di skip, non apertura artificiale per occupare slot.
5. Dashboard read-only in ramo separato work/brain-scalp-dual-app-20261028 basato su main, prima del deploy configurare mount RO dei due SQLite con test di accesso. Nessun cambio alla app già distribuita.
6. Ritiro Brain originale: status VPS read-only, completare in sicurezza eventuali posizioni, backup/restore SQLite e outbox/log/versioni/memoria, saldo finale originale in archivio, fermare una sola istanza originale, mai farla coesistere attiva coi due nuovi.
7. Nuova autorizzazione operativa e postflight PAPER prima del rilascio.

## Review indipendente Claude
Verificare calcolo del rischio su stop+fee/funding, limitazioni dell'uso degli slot, expiry dei piani dopo restart, roll-over UTC, gap/stop-prima e stop senza aumento di rischio, short speculare, lock SQLite e varianti di stato, confronto sulle prime run Hawk/Bull. Lavorare su rami/file diversi da questo modulo e condividere checkpoint sul ramo diario. Non confondere PASS di test unitari con certificazione di redditività o prontezza al deploy.

AI: chatgpt (chat normale)
