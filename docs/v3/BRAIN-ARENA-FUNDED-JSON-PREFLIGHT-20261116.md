# Brain AI Arena — verifica finanziamento e schema completo JSON (16/11/2026)

**Utente:** segnala ricarica OpenRouter **10 USD** effettuata oggi. Trattare come **dichiarazione**, non come saldo verificato dal sistema: nessuna management key e nessuna richiesta al conto utente. Il nuovo saldo deve risultare nel workspace/account che fattura le due chiavi. L'eventuale `HTTP_402` richiedera' verifica del workspace e del saldo, senza tentare addebiti ripetuti.

## Importante: soldi nell'account vs limiti delle chiavi

- Le chiavi `SuperBot-Qwen` e `SuperBot-MiniMax` sulla VPS sono state validate con limiti **2 USD per chiave** in data 16 novembre. La ricarica di 10 USD **non innalza automaticamente** questi limiti.
- Per ora preservare 2 USD per chiave, **auto-top-up spento**. Non raddoppiare né aggiornare i limiti delle API senza approvazione esplicita del piano di 14 giorni.
- OpenRouter documenta che la verifica del totale dei crediti via `GET /api/v1/credits` richiede una **management key**. Il nostro codice non legge né genera questa chiave; preferire la schermata Credits personale/workspace.
- Il test sotto usa al massimo **due chiamate a pagamento**, una per modello, e non ripete automaticamente chiamate fallite. Richiede 0,10 USD residui **del limite della singola chiave** prima di ogni POST. Nessuna garanzia di costo esatto per richiesta: è il limite API da 2 USD a fornire il tetto separato.

## Script isolato e risultati attesi

`deploy/scripts/arena-funded-schema-preflight-20261116.py`:
- `--selftest`: verifica **offline**, senza accesso ai segreti o rete, output `ARENA_SCHEMA SELFTEST=PASS_OFFLINE` solo dopo esecuzione effettiva.
- `--probe`: legge due chiavi dal file root-only esistente; controlla `GET /api/v1/key` e invia **una richiesta per modello** con un contesto **sintetico, senza candele o conti reali**; ragionamento disabilitato **soltanto per diagnosticare il formato** e `json_schema` rigido a otto campi come `ArenaL5Analyst`.
- Il risultato valido è `NO_TRADE` con tutti gli otto campi di tipo corretto e `finish_reason=stop`. La decisione non viene mai salvata o eseguita: nessuna apertura, nessuna chiusura, nessuna modifica a VPS services, journal, saldo PAPER o strategia Falco SHORT.
- Non vengono stampate chiavi, prompt, risposte dell'AI o eventuali error body da provider. Nei log compaiono solo metadati, token contati, esito e limite key.
- Un modello che non risponde allo schema viene marcato fallito, **nessun fallback automatico** verso l'altro.

## Requisiti prima dei runner AI Arena

1. Confermare superamento schema per entrambi, poi test dell'analista con dati di mercato realistici **offline** e successivamente eventualmente API reali su budget limitato.
2. Verificare formalmente test Python dei nuovi moduli Arena e regressioni del vecchio Brain, in checkout isolata e senza GitHub Actions finché i minuti sono preziosi.
3. Solo dopo, collegare due nuovi runner PAPER con tre journal, wallet e exit-worker distinti, capitale 2.000 USDT ciascuno e T0 condiviso. **Nessun runner è stato avviato.**
4. Preservare Falco SHORT: archivio del codice su GitHub già creato, ma backup integrale e verifica exit-worker/posizioni VPS ancora da eseguire prima della sua pausa.
5. L'universo più ampio **23 crypto + oro + argento** rimane su ramo di ricerca: prima dell'attivazione servono ranking e categorie affidabili, reali contratti Bitget, feed chiusi, compatibilità leva e percorso uscite per asset usciti dalla classifica.
6. Solo dopo il campione indipendente considerare i consulenti selettivi in shadow, mai come voto automatico sui trade.

**Stato al momento del commit:** script GitHub pronto. Nessuna richiesta API effettuata da questo intervento. Nessun nuovo costo provocato da ChatGPT, né test eseguito sulla VPS. Nessun merge/deploy.
