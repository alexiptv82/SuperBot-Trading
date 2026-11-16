# Falco SHORT — conservazione prima di AI Arena (16 novembre 2026)

**Vincolo esplicito dell'utente:** Falco ha una strategia SHORT valida da preservare. Toro puo' essere temporaneamente accantonato, ma **non cancellato**. Per dedicare l'interfaccia e l'attivita' a Brain AI Arena non si deve alterare, riscrivere, resettare o perdere Falco.

## Primo livello: ancoraggio GitHub effettuato

- Riferimento storico verificato: ramo `rule-pool` al commit **`fed2e3fd32ff162d22b045b4a8e5f0524e88a9b7`**.
- Creato ramo dedicato **`archive/falco-short-before-ai-arena-20261116`** da quell'esatto commit.
- Questo protegge un riferimento del **codice GitHub** pre-Arena, non costituisce da solo un backup dei dati PAPER, ne' prova che l'installazione VPS Falco corrisponda a quel commit.
- Rami storici gia' citati dalla documentazione precedente: `backup/classici-2026-10-27`, `backup/rule-pool-2026-10-27`. Evitare modifiche arbitrarie a questi archivi.

## Secondo livello: runtime Falco da verificare prima di fermare le aperture

Il repository RC84 indica i seguenti identificativi come **candidati** (NON riautenticati dal runtime corrente):
- Falco V3: unita' `superbot-v3-paper-falco.service`, directory `/opt/superbot-v3-paper-runs/classic-hawk-paper20261111`, `portfolio_id=hawk`.
- Falco classico/desk: `/opt/superbot-desk-data/hawk`, container storico `superbot-desk-hawk`.

**Non presumere che siano tutti contemporaneamente operativi.** Serve una verifica read-only su VPS per identificare con certezza quale codice, strategia SHORT, configurazione, risk policy e quali dati stiano utilizzando i servizi realmente attivi.

Prima di qualsiasi pausa operativa:
1. Registrare commit e image digest realmente installati, la revisione della strategia e i relativi parametri SHORT/leve/SL/TP. Il solo SHA su GitHub non certifica questo.
2. Verificare stato e posizioni aperte, heartbeat del servizio uscite, pause e protezioni del rischio. Non fermare le uscite e non chiudere posizioni in automatico.
3. Effettuare backup **consistente** e verificato del journal V3 `journal.db` (backup ufficiale SQLite, include contenuto WAL), dei file di stato/configurazione non segreti e della storia classica/diario dove applicabile. Salvare data, percorso, SHA-256 e prova di ripristino SQLite; non copiare API keys nei report.
4. Riutilizzare, quando applicabile al classico desk, `deploy/scripts/backup_brain.py` che gia' implementa una copia verificata delle memorie `state_v2.json`, `trade_history.jsonl`, `learning_log.jsonl`, `lessons.md`. **Non applicare automaticamente lo script classico al journal V3** senza audit delle directory e delle condizioni.
5. Preservare gli eventuali commit locali o file modificati sulla VPS con un backup a parte; non eseguire `git reset --hard`, `docker rm -v`, pulizie aggressive o reset di capitale.
6. **Solo dopo il backup verificato**, mettere eventualmente in pausa le **nuove aperture** di Falco e Toro, mantenendo attivi i servizi di gestione delle uscite per le posizioni non chiuse. Non attribuire il cambio di schermata UI a una pausa dei servizi.
7. La UI AI Arena nasconde i classici nella barra ma li mantiene in archivio e recuperabili. Terminata la competizione, Falco deve poter essere riabilitato senza nuova strategia e senza perdere memoria o cronologia.

**Stato verificato oggi:** creato ramo GitHub di archivio; nessuna pausa, nessun backup dati VPS, nessun cambio a Falco o Toro effettuato da questa attività. I dati VPS e l'effettivo commit operativo richiedono il controllo sulla macchina.

## Ordine dei lavori

- Fase A: completare le tre istanze Brain PAPER isolate, confrontare Qwen/MiniMax/DeepSeek con capitale iniziale equivalente e T0 comune.
- Fase B: dopo confronto, selezionare eventualmente la principale per merito misurato, non per fama o numero di parametri.
- Fase C: provare collaborazione fra AI **solo come consiglio in shadow**, con chiamate limitate e log del valore marginale di ogni parere; valutare poi se autorizzare uso operativo PAPER.
- **Falco resta una strategia preservata**, indipendente dalla scelta della migliore AI.
