# Brain AI Arena — un solo input 25 mercati per tre AI (16/11/2026)

## Risultato VPS confermato
Screenshot dell'utente ore 19:45: `ARENA_APPLY RESULT=PRIVATE_CACHE_UPDATED_WITH_BACKUP_NO_DEPLOY`; 75 GET Bitget pubbliche su 25 mercati, 25 rebase sul timeframe 1m, copia privata del vecchio cache, zero ordini e zero chiamate AI. Nuovo SHA cache `fba771b33ad1935614df124d74c357b63d66694f47193abb65ed514c77ed4bdd`. Hash precedente conservato nel backup; NON è il nuovo hash. I dati aggiornati sono una fotografia storica (`updated_asof_ms=1794854670091`), non un feed live.

## Fase nuova
Branch `work/arena-three-ai-common-packet-20261116` basato sul ramo recovery; file isolati:
- `backend/v3/arena/comparison_packet.py`: prende il vero compact Brain dei 25 mercati e ne codifica i 18 indicatori PER timeframe in 25 righe/3 timeframe; non altera i valori. Le colonne sono in un ordine fisso descritto nel payload. Il prompt per DeepSeek, Qwen e MiniMax è **identico parola per parola** e il market bytes/hash sono identici. Limite 24 KB per evitare il vincolo 25.000 caratteri per messaggio del trasporto OpenRouter attuale.
- Il modello può rispondere SOLO con `action=NO_TRADE` oppure `action=CANDIDATE`, un simbolo dei 25, side LONG/SHORT, confidence e motivo codificato. Il parser rifiuta OPEN, leva, ordini, campi estranei, simboli non inclusi, risultati non validi. CANDIDATE è informazione di ricerca, non un permesso di trading.
- `backend/v3/arena/test_comparison_packet.py`: **12 test nuovi scritti, non ancora eseguiti sulla VPS**: parità completa dei tre input, equivalenza dei 18 indicatori tra origine e rappresentazione compatta, limite del payload, integrità, NO_TRADE, rifiuto segnali non autorizzati/extra/rischiosi.
- `deploy/scripts/arena-three-ai-common-packet-audit-20261116.py`: `--audit <SHA della cache>`, legge solo la cache privata persistente, confronta il digest, calcola indicatori reali, produce i digest per le tre AI; non stampa il payload, non usa credenziali, non fa chiamate AI, non scrive file, non apre posizioni. Il documento è **sempre storico**, anche quando completo.

## Gate sperimentale
1. Eseguire `python3 -m unittest -q backend.v3.arena.test_comparison_packet`, poi lo script `--audit` sulla VPS.
2. Il primo confronto **pagato** richiederà un trasporto comparativo separato che supporti questo schema research (5 campi), con credenziali DeepSeek preesistenti e Qwen/MiniMax root-only, una chiamata per modello, controllo di budget, permesso esplicito, nessun retry. L'attuale trasporto `openrouter_transport` accetta il contratto operativo a 8 campi, e quindi NON può essere usato direttamente per questo schema a 5 campi. Evitare di aggirare le verifiche.
3. Anche se il modello sceglie un candidato, il confronto verrà registrato in ombra e non genera trade. Per 14 giorni PAPER servono poi motore rischio deterministico per ciascun portafoglio, storici separati, servizi uscite e interfaccia.

## Custodia progetto
Nessuna modifica su branch operativo, runner, portafogli, posizioni, servizi, GitHub Actions, API keys. Falco SHORT preservato, Toro accantonato, Brain DeepSeek ancora unico attivo. La presenza di 25 simboli è provvisoria per trading; oro e argento sono inclusi nel pacchetto ricerca. I 14 giorni e i tre portafogli da 2.000 USDT NON sono avviati.
