# RC84 — Fase 1: analisi quantitativa LONG/SHORT (come eseguirla e come leggerla)

**Stato:** strumento di **sola lettura**, provato solo su dati sintetici. **Nessun risultato reale è contenuto in questo documento**: i
numeri veri escono solo eseguendo il comando sotto sulla VPS. Nessuna modifica a `signals.py`, `cli.py`, motore, rischio, pause o bot.

## 1. Il comando (Termius, VPS Singapore, utente root)
Scarica lo script dal commit indicato nel rapporto di consegna, ne controlla l'impronta e lo esegue; non serve nessuna credenziale
(il repository è pubblico) e lo script non apre la rete:
```sh
D=$(mktemp -d) && curl -fsSL -o "$D/audit.py" https://raw.githubusercontent.com/alexiptv82/SuperBot-Trading/<COMMIT>/deploy/scripts/audit_long_short.py && echo "<SHA256>  $D/audit.py" | sha256sum -c - && python3 -I "$D/audit.py" --vps /opt/superbot-desk-data | tee "$D/rapporto.txt"; echo "rapporto salvato in $D/rapporto.txt"
```
`<COMMIT>` e `<SHA256>` sono nel rapporto di consegna (l'impronta dello script è anche in fondo a questo documento). Se `sha256sum -c`
non stampa `OK`, **non** si esegue nulla. Il rapporto contiene solo dati PAPER (simboli, orari, importi PAPER, motivi), nessuna chiave.

**Cosa fa sulla VPS:** per `hawk` (Falco) e `bull` (Toro) copia `trade_history.jsonl`, `learning_log.jsonl`, `state_v2.json` e gli
storici archiviati dai reset (`archive/*/trade_history.jsonl`) in una cartella temporanea privata (0700) **fuori** dai dati, aprendo gli
originali solo in lettura; la copia è ripetuta finché nessun file cambia durante il giro (i worker di uscita possono scrivere anche coi
bot in pausa). Analizza le copie e le cancella alla fine. La riga `copia COERENTE` lo conferma; `NON COERENTE` = ripetere il comando.
Con `--keep-copies /root/audit-copie-AAAAMMGG` (cartella nuova) le copie restano per altre analisi.

## 2. Come sono ricostruiti i trade
* **Chiave di un trade = (simbolo, id, ora di apertura).** L'id del motore riparte da 1 a ogni reset, quindi da solo non basta; la
  sezione *Integrità* conta gli id riusati.
* **Reset:** dopo un reset lo storico corrente viene spostato in `archive/<data>/`: lo script legge anche quelli e indica l'origine.
* **Parziali:** le chiusure parziali si sommano nel loro trade (P&L e R sono additivi); il trade è *chiuso* solo con la riga finale.
* **Aperti:** da `state_v2.json`; la *stima aperta* usa l'ultimo prezzo salvato nello stato ed è solo indicativa.
* **Collegamento al learning:** l'evento `open` di `learning_log.jsonl` con la stessa chiave dà run, prezzo, SL, TP, 1R in dollari, leva,
  margine e le **feature d'ingresso** (contesto del desk, oppure le grandezze S25). *Integrità* conta i trade senza evento open e le
  chiusure dello storico assenti nel learning: se non sono zero, quei trade hanno meno informazioni, non sono sbagliati.
* **Periodo:** dal `--since` (predefinito 11/11 00:00 UTC). **Rilascio RC84: 12/11/2026 12:37 Europe/Rome = 11:37 UTC** (`--cutoff`).

## 3. Le sezioni del rapporto
| Sezione | Che cosa risponde |
|---|---|
| Integrità | i registri sono completi e collegabili? righe rotte, duplicate, id riusati, run presenti |
| Riepilogo | portafoglio × lato × strategia (Claude/Rules/S25) sui trade **aperti** nel periodo: è il confronto con i numeri dell'operatore |
| Report principale | per **ora di apertura**: prima/dopo RC84 × portafoglio × lato × strategia × orizzonte. È quello che attribuisce un trade alla versione che l'ha deciso |
| Report secondario | per **ora di chiusura**: utile per i conti giornalieri; un trade aperto prima e chiuso dopo RC84 cambia sezione tra i due report |
| Contesto all'ingresso | esito dei trade per trend 4h/1h/1d (come li calcola il codice), RSI e presenza del funding, per lato |
| Diagnostica S25 | per ogni S25: segnale, ingresso, piano, costi, esito, duplicati tra portafogli, contesto del desk più vicino |
| Posizioni aperte | ciò che manca per chiudere i conti |

Colonne: `n` chiusi, `ap` aperti, `win%`, `PF` profit factor (inf = nessuna perdita), `netto$` realizzato dopo commissioni, slippage e
funding, `ex-fund$` lo stesso **senza** il funding, `R` media in multipli del rischio pianificato, `MAE`/`MFE` medi in R, `ore` durata
media, `leva`, `SL%` distanza dello stop, `R:R` pianificato **rispetto al prezzo eseguito**, `costR` commissioni + funding in R.

## 4. Come leggere i punti chiave
* **LONG contro SHORT, a parità di strategia.** Il confronto onesto è *Rules SHORT* contro *Rules LONG* e *S25 LONG* contro le altre
  strategie LONG, non "tutti i LONG" contro "tutti gli SHORT": se i LONG del periodo sono quasi solo S25, il confronto LONG/SHORT misura
  S25 contro le regole, non la direzione.
* **Funding:** nel PAPER è addebitato **solo ai LONG** (`engine.py`). La differenza `ex-fund$ − netto$` è quanto pesa; se è piccola
  rispetto alle perdite, il funding non è la causa.
* **S25 — la soglia di pareggio.** S25 ha stop e target simmetrici (1,5 ATR, R:R 1:1 sul prezzo) e nessun filtro di trend. Con R:R 1:1
  un sistema guadagna solo se vince **più della metà** delle volte, e un po' di più per i costi: la diagnostica stampa per ogni trade
  `costi = x R → pareggio con win rate y%` (con il motore PAPER, nei dati sintetici, ~0,08–0,10 R → 54–55%). Inoltre il R:R rispetto al
  prezzo **eseguito** è già sotto 1 per lo slippage. Tre perdite su tre per portafoglio non bastano a misurare la probabilità, ma con
  questa geometria anche un segnale "neutro" perde nel tempo; un segnale che entra contro il trend 4h/1d perde più spesso.
* **S25 — perché è entrato.** Per ogni trade: la candela di segnale (EMA9 che passa sopra il VWAP giornaliero), di quanti bp, il
  trigger, quanti minuti dopo e quanti ATR sopra il trigger è entrato (limite 0,5). Se tutte le condizioni risultano rispettate, la
  perdita non è un errore di esecuzione ma un limite della regola. **Contesto del desk più vicino:** S25 non registra il trend; lo script
  cerca nel learning la riga più vicina (±2 ore, stesso simbolo, qualunque portafoglio) con il punteggio del desk e ne mostra trend 4h/1h/1d,
  RSI, ROC 24h e punteggi long/short, con lo scarto in minuti. Se il trend 4h del desk era "giu" all'ingresso, S25 ha comprato un
  rimbalzo dentro un ribasso. Attenzione: il "trend 4h" del desk è quello del codice (EMA50 contro EMA61, audit del 12/11, E1).
* **Duplicati:** "stessa apertura S25 anche su Toro/Falco" = lo stesso segnale ha aperto su entrambi i portafogli (era l'11/11, prima
  della correzione delle 21:36): la perdita va contata una volta come *segnale* e due volte come *denaro*.
* **MAE/MFE:** un MFE vicino a 0 su uno stop dice che il trade non è mai andato a favore (ingresso sbagliato); un MFE alto con esito
  stop dice che il mercato era a favore e poi è girato (gestione/uscita). Sono in R rispetto al primo prezzo d'ingresso.
* **Campione:** con pochi trade per gruppo, win rate e PF sono **descrittivi**, non statistiche: non vanno usati per scegliere
  parametri. Servono per decidere che cosa verificare sul banco storico.

## 5. Che cosa NON fa
Non ricostruisce gli indicatori dalle candele storiche (non ci sono nei registri); non legge Brain V3; non tocca bot, pause, configurazioni
o dati; non invia nulla in rete. Lo stato di mercato "vero" (EMA200 4h piena, 1d, funding/OI storici) all'ingresso di ogni LONG perdente
richiede le candele del periodo: è il passo successivo, sul banco storico, prima di qualunque modifica alla strategia LONG.

## 6. Prove
`deploy/scripts/test_audit_long_short.py` (13 prove): registri prodotti dal **motore PAPER vero** (`PaperAccount.open/close/partial_close`)
con lo schema esatto di storico e learning; reset con id riusato e storico archiviato; parziale + finale; posizione aperta; riga troncata e
riga duplicata; S25 duplicati tra portafogli con contesto del desk; trade a cavallo del rilascio (cambia sezione tra i due report);
cutoff verificato con `zoneinfo` (12:37 Europe/Rome = 11:37 UTC); copia coerente, ripetuta se un file cambia, dichiarata non coerente se
continua a cambiare; nessuna scrittura nei dati (contenuto e date di ogni file identici), copie mai dentro i dati, cartella temporanea
cancellata; script senza moduli di rete e con un solo punto di scrittura (le copie).

## 7. Impronta dello script
`sha256(deploy/scripts/audit_long_short.py) = 0769bc1a19f48988d5385f557fd7ac216c7ffecad916fd39d1236aeb050d3926`
