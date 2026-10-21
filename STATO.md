# STATO di SuperBot Trading

## 21/10/2026 ~22:00 — Claude: daily_stop 10% + 4 fix integrità replay

**Decisioni utente applicate:**
- `daily_stop` abbassato da 12% a 10% (Hawk + Bull). Commit `9e14a25` su `work/director-claude`. Redeploy in attesa di "via".
- Redeploy `880c4a4` (1d trend su 26 coin, attesa di "via") ancora in coda.

**Ricerca — integrità replay completata:**
Ripresi da b229963 (ChatGPT) e completati i 4 fix aperti: (1) snapshot immutabile + JSON invalidi conteggiati; (2) tolleranza riconciliazione 0.05$ non 0.50$; (3) MFE intrabar dichiarato upper bound; (4) workflow exit code propagato. Commit `701e840` su `work/director-claude`. Test: 184 passed, 44 skipped. Nessun merge in rule-pool, nessun trigger.

**Prossimi passi (sequenza ChatGPT step 3-6):**
3. Copia PAPER verificata con hash (senza dati grezzi nel repo).
4. R per regime (down/flat/up) e lato (long/short) sui trade eseguiti.
5. A/B stagionalità sui punteggi registrati (seasonality_audit.py pronto).
6. Replay economico controllato delle varianti.

## 21/10/2026 17:31 — ChatGPT: preparazione ricerca, nessun deploy

Utente: ChatGPT prosegue il lavoro; Claude interviene quando necessario. Autorizzata
preparazione di analisi e test, non modifiche operative. Raccolti anche i report Kimi
(con rettifiche) e Nemotron: non costituiscono validazioni indipendenti dei dati.

Ramo work/research-integrity, commit b229963, base e7866bf. Nessun merge in rule-pool,
nessun trigger o deploy. work/director-chatgpt e dati bot intatti.
- Nuovo seasonality_audit.py: sola sensibilita dei punteggi registrati con/senza
  bonus, nessuna stima di ordini o P&L; soglia scenario esplicita, versioni ammesse
  solo dopo revisione storica; input hashato, JSON rigoroso, righe duplicate contate,
  conflitti fermano il calcolo, saturazione a 100 con bonus esclusa.
- Limite verificato nel logger: candidate non sono tutto il mercato e cessano
  oltre MAX_BYTES_CANDIDATES. Non dichiarare universo completo.
- pm_exec_replay.py: complete_window richiede copertura continua fino alla barra
  del timestamp di uscita; recente uscita senza barra disponibile viene esclusa.
  Correzione conservativa, non una modifica alle policy del PM.
- Protocollo in docs/research/seasonality-ab-20261021.md: separa sensibilita di
  punteggio, replica storica ed esperimento di portafoglio.
- Test Python 3.11.17: 193 passati, 44 saltati; 3 errori deliberati rilevati (bonus
  ignorato, saturazione invertita, vecchia copertura insufficiente). Nessuna prova
  nuova sul server o sui registri privati; nessun nuovo risultato economico.

Restano: revisione prima di eseguire sui dati veri; ottenere copia PAPER verificata
con hash; verificare le versioni storiche ammesse; completare correzioni input,
riconciliazione, MFE e workflow del replay. Non usare la sola copertura corretta
come validazione finale. Stato operativo del server NON ricontrollato: diario
riporta ancora correzione 880c4a4 in attesa di via, non inferire installazione.

Nota metodologica: analisi per regime/lato non distingue DA SOLA applicazione
errata da effetto di mercato. Il PM resta in ombra. I difetti di copertura possono
alterare i risultati: il loro effetto numerico non e' ancora quantificato.


## Aggiornamento 21/10/2026 11:25 Roma — Claude: valutato report ChatGPT sul replay PM — quadro completo

ChatGPT (commit 69c4fba, run 39565485402, Python 3.11.17, 175 test passati): **giudizio favorevole al replay come strumento di ricerca, non all'attivazione del PM**. Ha identificato 5 difetti tecnici nel codice: (1) copertura candele incompleta (controlla ≥24 barre all'ingresso ma non fino all'uscita); (2) riconciliazione con tolleranza 0,50 $ non 0,01 $, usando fee registrate non ricalcolate; (3) MFE registrato include l'estrema intrabar d'uscita — "ha raggiunto +1R prima di perdere" non e' sempre dimostrato; (4) `set +e` + `echo FINE` incondizionato → job verde anche se il replay fallisce; (5) righe JSON ignorate permissivamente, `:ro` non congela il registro mentre il bot scrive. Nessuno di questi difetti invalida i risultati, ma vanno corretti prima di una validazione conclusiva. Calibrazione: propone confronto appaiato per trade in R netto, raggruppando giorni e trade contemporanei (non indipendenza fittizia). Soglia per il PM: con esiti binari TP/stop, serve p > 74,1% dopo aver raggiunto +1R per giustificare il non-intervento — il massimo gia' raggiunto da solo non basta. Stessa conclusione pratica di DeepSeek e Gemini: ombra in produzione, nessuna attivazione. **Il quadro delle 4 AI e' completo (Perplexity, DeepSeek, Gemini, ChatGPT).** Nessuna modifica ai bot. Dettagli: `diario/2026-10-21_claude.md`.

## Aggiornamento 21/10/2026 11:15 Roma — Claude: sintesi delle analisi AI pronta per ChatGPT

L'utente passa l'analisi comparativa a ChatGPT. Preparata la sintesi (`diario/2026-10-21_sintesi-ai-per-chatgpt_claude.md`): fatti, misure di Claude (stop reali, pareggio al netto dei costi, bonus di stagionalita', errori corretti), valutazione di Perplexity, DeepSeek e Gemini, confronto, otto misure ancora da fare in sola lettura, decisioni che spettano all'utente (redeploy `880c4a4`, gestione del profitto, stagionalita'/leva/soglie, funding carry) e le domande per ChatGPT. Nessuna modifica ai bot.

## Aggiornamento 21/10/2026 11:10 Roma — Claude: valutata la risposta di Gemini al brief

Gemini: (b) nessun vantaggio 70%, (a) 20%, (c) 10%; 3 proposte. Giudizio: meno rigorosa di DeepSeek. Smentita dal brief l'affermazione che i profitti 'si azzerano nei laterali' (controfattuale: +0,16R, 49% vincenti nel piatto); etichetta 'Verificato' errata; la proposta di uscita parziale a +1,5R e' il replay gia' fatto (neutro: +3 $ Hawk, -10 $ Bull come variazione); la proposta di protocollo con quattro basi e' gia' in DeepSeek, con piu' rigore; il modulo AI e' gia' separato. L'accordo tra le AI su (b) non e' indipendente (leggono lo stesso brief). Da misurare: R per regime di mercato e per lato sui trade eseguiti. Nessuna modifica ai bot. Dettagli: `diario/2026-10-21_claude.md`.

## Aggiornamento 21/10/2026 11:15 Roma — Claude: valutata la risposta di DeepSeek al brief

Probabilita' di DeepSeek: 25% idea buona/applicata male, 65% nessun vantaggio (regime), 10% altro; 5 proposte (ablazione del punteggio, leva fissa finche' il punteggio non e' monotono, 'lascia correre' oltre il TP, funding carry, protocollo per il trader AI). Verificato: i denominatori del brief (142 contro 151) non tornavano e il '+0,23R su 142 trade' non e' riproducibile dal registro (124 trade chiusi Hawk, 36 Bull); corretto con le misure nostre (Hawk +0,16R su 121, Bull -0,07R su 30). Chiariti nel brief anche '+226 bp/settimana' (media del book, quasi tutta prezzo del 2021), stop giornaliero 12% (non e' un tetto di perdita), funding simulato (short non pagano ne' ricevono). Registro: i candidati non eseguiti non hanno l'esito (va ricostruito con le candele). Nessuna modifica ai bot. Dettagli: `diario/2026-10-21_claude.md`.

## Aggiornamento 21/10/2026 10:57 Roma — Claude: misurati gli stop reali (sola lettura)

Workflow `desk-stop-fasce` (codice `91c8d21`, CI verde, senza rete, bot non toccati). **Hawk (121 trade):** stop mediano 1,11% (solo 5 trade sotto lo 0,5%); vincenti 45,5% contro pareggio al netto dei costi ~39-41%; R netto medio +0,16 [-0,08/+0,39], non esclude zero; guadagna dalla fascia di stop 1-2% (67 trade, +0,35R), perde sotto lo 0,5% (n=5) e sopra il 2% (n=7). **Bull (30 trade):** stop mediano 0,80%; vincenti 36,7% contro pareggio ~39-43%; R medio -0,07 [-0,51/+0,38]. Quindi l'errore del brief sul pareggio era reale ma per Hawk piccolo; Bull non ha margine. Campioni piccoli: indizi, non prove. Brief per le altre AI aggiornato (Docs, Project, diario). Dettagli in `diario/2026-10-21_claude.md`. Nessuna modifica a strategia o bot.

## Aggiornamento 21/10/2026 10:45 Roma — Claude: correzione al brief (pareggio al netto dei costi)

Valutando la tabella costi/pareggio di Perplexity (numeri ricalcolati: tornano) ho trovato un **mio errore** nel brief per le altre AI: il pareggio del 37-38% era al lordo dei costi. Con 16 bp per giro il pareggio dipende dallo stop: ~55% a stop 0,3%, ~41% a 1%, ~37% a 3,5% (con il TP misurato ~1,72R: ~57% / 43% / 39%). Hawk ha il 45% di vincenti: margine incerto finche' non si misura la distribuzione reale degli stop. Brief corretto (Docs, Project, diario) e rimandato all'utente. Prossimo passo: misura in sola lettura di vincite e R netto per fascia di stop. Nessuna modifica a strategia o bot.

## Aggiornamento 21/10/2026 10:40 Roma — Claude: brief per l'analisi di piu' AI + scoperta del bonus short da stagionalita'

L'utente (10:04) vuole far analizzare il progetto a piu' AI: scritto il brief completo (`diario/2026-10-21_brief-multi-ai_claude.md`, copia nel Project). **Scoperta:** `seasonal.py` dal 7/10 e' in fase "bear market" (mult -1,0) e, con mesi storicamente forti in tabella, da' al punteggio un bonus SHORT fisso (+5 BTC, +4 ETH, +2 altri; +9/+10 BTC/ETH a meta' novembre): contribuisce all'asimmetria short (circa 8 long su 150 aperture). Non misurato l'effetto; nessuna modifica (e' strategia, decide l'utente). Restano: "via" per il redeploy su `880c4a4` e decisione sulla gestione del profitto.

## Aggiornamento 21/10/2026 09:59 Roma — Claude: dati 1d/OI pronti (NON ancora rilasciati), Turbo in ombra, resoconto serale, replay del profitto

Su "implementiamo tutto" dell'utente (08:59). **(1)** Turbo Scalp installato **in ombra** (container `superbot-turbo`, dati `/opt/superbot-turbo-data`, nessun ordine, nessuna chiave di trading). **(2)** Resoconto serale: workflow `desk-report-serale` (sola lettura, trigger `deploy/report-serale.trigger`) + attivita' pianificata "Resoconto serale SuperBot" ogni giorno alle ~20:36 Zurigo. **(3)** Correzione di un mio errore: gli id dei trade ripartono da 1 a ogni azzeramento del conto (`run_no`): i report ora raggruppano per `(run_no, id)`; la conclusione del 20/10 "17 su 58 restituiscono il profitto" e' RITIRATA (le cifre corrette sono nella voce del giorno). **(4)** Trend 1d e dati mancanti **corretti e provati, ma NON rilasciati**: commit `880c4a4ae226815f8686f20c14e5bebdc5bff322` (CI verde, sonda dal vivo ok): trend 1d vero su 26/26 monete (17 rialziste, 9 ribassiste, +15 al lato concorde), open interest in USD 26/26, long/short solo 6 monete (limite di Bitget). **Serve il "via" esplicito dell'utente per il redeploy di Hawk e Bull con questo sha.** **(5)** Gestione del profitto: replay sui trade chiusi veri con candele 15m vere (`deploy/scripts/pm_exec_replay.py`, workflow `desk-replay-profitto`, 175 prove, 20/20 mutazioni uccise, oracolo `PaperAccount`). **Risultato: nessuna regola meccanica testata migliora il totale** (Hawk reale +570 $ su 121 trade; Bull +131 $ su 30): con TP a ~1,7R e stop a -1R la finestra e' stretta, bloccare il profitto taglia piu' vincenti di quanti perdenti salva (17 trade Hawk toccano +1R e finiscono in perdita: -473 $, a pareggio -54 $). L'unica regola neutra: 50% a +1,5R con pareggio sul resto (+3 $ / -10 $). Nella seconda meta' dei trade quasi tutte le regole guadagnano, nella prima perdono: dipende dal regime. **Nessuna attivazione, in attesa della decisione dell'utente** e della revisione indipendente di ChatGPT (messaggio preparato). Dettagli: `diario/2026-10-21_claude.md`.

## Aggiornamento 21/10/2026 09:00 Roma — Claude: check-up aperture (sola lettura)

Dopo il rilascio il mercato e' fermo: 0 monete su 26 sopra soglia (soglie 60 per BTC/ETH/oro/argento, 63 per le altre; nei primi giorni 70). Nessun blocco tecnico; Claude non frena. **Difetto trovato:** il trend 1d "corretto" il 20/10 non si attiva (Bitget restituisce 89 barre giornaliere, ne servono 200); con barre vere +15 punti al lato concorde, bot piu' verso i long. Nessuna modifica fatta; opzioni in `claude/checkup-aperture-trade-2026-10-21.md` e `diario/2026-10-21_claude.md`, in attesa della decisione dell'utente. AI in ombra: 2 cicli, 1 posizione virtuale aperta, spesa 0,004 $.

## Aggiornamento 21/10/2026 08:20 Roma — Claude: punto 1 RILASCIATO e AI in ombra INSTALLATA

Su "via" esplicito dell'utente (08:13): (1) **bot rilasciati su `fa3e220`** (`desk-deploy` VERDE, run 39554172699, per la prima volta dopo la correzione del controllo "una sola istanza"): Hawk e Bull **senza tetto di leva del bot**, **Bull 6 posizioni e 1050 $**, 150-350 $ per trade e opzione A invariati, tutto il resto invariato; paper (`DESK_MODE=paper`, `exec_mode=paper`), un container per bot, battito sano; le posizioni aperte di Hawk sono state conservate dal riavvio; il manifesto del rilascio dovrebbe ora esistere. (2) **AI in ombra DeepSeek installata** (`53111b3`, run 39554436472): container separato `superbot-ai`, conto virtuale, nessun ordine reale, nessuna chiave di trading, dati in `/opt/superbot-ai-data`; primo ciclo completo riuscito (26/26 candele, prima chiamata al modello riuscita, spesa registrata sotto il tetto 0,50 $/giorno e 12 $/mese); container di Hawk, Bull e gli altri verificati identici a prima. Interruttori e report: `deploy/ai-shadow-control.trigger` (`action=report|pause|resume|stop|start`). Turbo Scalp: ancora non installato. Dettagli: `diario/2026-10-21_claude.md`.

## Aggiornamento 21/10/2026 05:20 Roma — Claude: DEPLOY dei bot fatto (b6b9911)

Su OK esplicito dell'utente (04:57) sono stati distribuiti **tutti e 12 i commit di `work/salto-qualita`**: gate A margine minimo Bull 150 $ + guardia NaN/inf, gate B leva massima (Hawk x20, Bull x15), soglia altcoin 63, Bull a 10 posizioni (150-350 $), correzioni motore A-E, trend 1d, soglia tier C 65, prompt allineati. **Hawk e Bull girano su `b6b9911`, PAPER** (`DESK_MODE=paper`, `exec_mode=paper`), online, un solo container per bot; cervello intatto, backup pre-deploy fatto. Turbo Scalp: codice presente, **non installato**. Gate B visto all'opera (Bull ha rifiutato una leva 17x). **Il workflow `desk-deploy` risulta ROSSO** per un probabile difetto del controllo finale "una sola istanza" (conta anche l'app `superbot`, che monta le stesse cartelle): i bot sono sani, il manifesto del rilascio non è stato scritto. Dettagli e cose aperte in `diario/2026-10-21_claude.md`. **Scoperta del 21/10 06:20:** leva e puntata non sono cambiate dall'inizio; il tetto di leva del deploy (opzione B) scarta la maggior parte dei segnali storici (Hawk ~80%, Bull ~96%): decisione dell'utente in attesa (spegnerlo o limitare la leva invece di rifiutare). Il resto di questo file è storico: questo aggiornamento prevale.

## Aggiornamento 20/10/2026 05:18 Roma — audit ChatGPT

Verifica nuova in sola lettura: Hawk run4/Bull run3 PAPER, ciclo15m, una posizione ciascuno, nessun blocco globale; 30 scarti confidenza ciascuno e una guardia liquidazione Hawk. Budget AI nuovamente disponibile. Soglie60/70 invariate dal12/10. Misura candidati con costi: risultati di ricerca incompleti, nessuna modifica di soglia approvata. Dettagli e numeri finali in diario/2026-10-20_chatgpt.md. Review backup:46test passano ma missing last_end_ms/cycles e NaN accettati, correzione proposta non applicata. Nessun deploy, reset, cambio strategia, rischio o PM. Restano aperti vista ombra, backup journal e difetti precedentemente segnalati.

Le sezioni seguenti sono storiche; questo aggiornamento prevale.

**Aggiornato:** 19/10/2026, sera — ChatGPT; esito server disponibile delle 21:39 italiane.
**In corso:** ombra installata da Claude su Hawk run 4 e Bull run 3. ChatGPT ha verificato l'esito salvato delle 21:39 e rilevato problemi di congelamento ROI/ordine ambiguo e validazione heartbeat backup. Dettagli nella voce ChatGPT del 19/10; nessun nuovo deploy.

## Aggiornamento serale autorevole

Ombra gia installata su entrambi; nuove run PAPER da 1000 avviate dall'utente. Nessun passaggio ad attivo autorizzato. ROI 15/5/5/25 autorizzati solo per prova; ATR research-1 non approvati. Bot versione b4709d1 non ridistribuiti. Sidecar sha-ad8d0bddbbda secondo controllo delle 21:39. Vista app e inclusione journal nei backup ancora aperte. La precedente proposta di installazione e reset e superata. Le sezioni storiche sotto descrivono il mattino e non annullano questo aggiornamento.

## In una frase
Il bot di trading su futures Bitget (due portafogli, Hawk e Bull, più un pool di regole) e la sua app girano **tutti su un unico server a Singapore, in modalità paper** (soldi finti). La migrazione da Strasburgo è finita il 19 ottobre. Il live con soldi veri non è attivo e non è in programma finché l'utente non lo decide.

## Che cosa gira e dove (verificato il 19/10 mattina)

| Componente | Stato | Note |
|-----------|-------|------|
| Server Singapore (`51.79.205.82`) | attivo | Ospita tutto. Si è riavviato due volte il 19/10 all'alba (rescue di OVH, non per colpa nostra); i container sono ripartiti da soli |
| App (container `superbot`) | online | `https://superbot-trading.duckdns.org`, HTTPS valido, login con password e impronta digitale. L'utente l'ha provata da telefono: tutto funziona |
| Bot Hawk e Bull | online, **paper** | Cicli ogni 30 minuti; il 19/10 mattina nessun segnale sopra soglia, quindi nessuna posizione aperta: non è un guasto |
| Pool di regole (`superbot-pool`) | online | Runner paper |
| Strasburgo (`51.91.109.45`) | SuperBot fermo | Resta acceso HI-TV (non toccare) e `superbot-staging` (da decidere) |

## Decisioni dell'utente ancora valide (le più recenti)
- Tutto in **paper**; il live si valuta solo dopo il test, con una sua decisione esplicita.
- La **strategia dei bot non cambia** se non la cambia lui. Il cervello (storico, appunti, registro di apprendimento) non si tocca mai.
- 19/10: tutto SuperBot deve essere separato da Strasburgo e stare su Singapore (fatto).
- 19/10: **le chiavi API di Bitget restano in stand-by** finché non si va in live. Sono limitate all'IP di Strasburgo: da Singapore Bitget le rifiuta (errore "Invalid IP"). Quando si andrà in live, l'utente deve aggiungere l'IP `51.79.205.82` alla lista di ciascuna chiave (le due di sola lettura e le due di trading). Fino ad allora la pagina Live dell'app mostra zeri per progetto (in paper non legge il saldo) e va bene così.
- 19/10: l'utente ha lasciato decidere a Claude sui tre workflow di migrazione dei dati → **rimossi** (vedi `diario/2026-10-19_claude.md`).
- 19/10: l'utente vuole che **ChatGPT e Claude possano sostituirsi a vicenda** (scrivere, commit, push, rami, deploy come l'altra AI) e che esista questo diario → creato.

## Cose aperte (in ordine di importanza)
1. **Verificare per intero i nuovi deploy rinforzati** (app: backup verificato, controllo finale di salute, ritorno indietro; bot: backup del cervello). Finora sono stati provati i singoli passi e gli script di backup sul server con dati veri, e il rilascio dell'app con prove su un finto server (ordine reale delle operazioni); un rilascio vero dell'app rinforzato non è ancora stato eseguito (vedi `diario/2026-10-19_claude.md`). Il rilascio dell'app ora si fa solo con `deploy/superbot-sg-deploy.trigger` su `rule-pool` (un merge su `main` non rilascia più). Il deploy dell'app dura pochi secondi di indisponibilità. Il deploy dei bot richiede l'OK esplicito dell'utente.
2. ~~Ponte temporaneo del 18/10~~ — **RITIRATO il 19/10 alle 11:22 UTC** (con l'OK dell'utente, dopo il primo backup esterno verificato): container `superbot-desk-api` fermato e rinominato `superbot-desk-api-retired-20261019` (non cancellato), tolta da `authorized_keys` la sola chiave del tunnel, copia di sicurezza in `/opt/superbot-backups/ponte-20261019-112200`; app e bot invariati. Ritorno indietro: `deploy/sg-bridge.trigger` con `azione=ripristina`. Il container di rollback `superbot-desk-api-retained-…` resta. Da decidere con l'utente, più avanti, se cancellare del tutto i due container vecchi.
3. **Staging a Strasburgo** (`superbot-staging`): decidere se spegnerlo.
4. **Credenziali usate durante la migrazione**: ruotare la chiave SSH di Singapore, il token GitHub e il token DuckDNS (comparsi in chat o in screenshot). Da fare con l'utente.
5. **Repository pubblico**: l'utente deve decidere se renderlo privato. Prima i server hanno bisogno di una chiave di sola lettura per scaricare il codice, altrimenti i deploy si fermano.
6. ~~Backup fuori dal server~~ — **ATTIVO dal 19/10** (primo backup 11:19 UTC, ripristino completo provato): archivi cifrati con age nel repository privato `alexiptv82/superbot-backups`, ogni giorno alle 03:20 UTC (retention 14/8/6). Da controllare ogni tanto con `sg-extbackup` `azione=status` (sola lettura). Dal pomeriggio: verifica con clone nuovo da GitHub, immagini e versioni in esecuzione nel manifesto, ripristino con controlli di coerenza (stato/storico/contabilità). ChatGPT consigliava di ruotare la chiave di recupero (passata dalla chat): **l'utente ha deciso di tenerla** (19/10 14:09, l'ha già salvata). La copia nello spazio di lavoro di Claude è stata cancellata. **La chiave PRIVATA di recupero è dell'utente** (fuori da GitHub e dal server): se la perde, i backup esterni non si aprono. Dettagli in `diario/2026-10-19_claude.md`.
7. **Riallineare `main` e `rule-pool`** (hanno storie diverse: il 19/10 sera circa 50 commit solo su main e oltre 130 solo su rule-pool; misurare con `git rev-list --left-right --count origin/main...origin/rule-pool`) e correggere in `rule-pool` il bug del `Request` mancante in `backend/server.py` (per questo l'app si distribuisce sempre da `main`).
8. **Dati di mercato mancanti**: due endpoint Bitget (open interest, rapporto long/short) rispondono 404, quindi quelle feature sono a zero. Correggerli cambia ciò che vede Claude, quindi serve l'OK dell'utente.
9. **Una ventina di workflow di sola diagnosi** usano ancora ssh senza verifica rigorosa della chiave del server (non mandano segreti di trading).
10. **Prossima fase: "Evoluzione del Cervello Professionale"** — promemoria dell'utente del 19/10 in `SPECIFICA-EVOLUZIONE-CERVELLO.md` (Profit Manager dinamico per Hawk e poi Bull, riconoscimento delle inversioni, cervello come osservatore/consigliere, rischio deterministico, Turbo Scalp in seguito). **Da valutare insieme all'utente e a ChatGPT; nessuna modifica autorizzata.** Il passo richiesto è un piano tecnico in 12 punti (nessun deploy, nessun cambio di strategia, rischio, prompt o slot). Dei 13 passi di implementazione, i primi tre (backup/rollback, snapshot coerente a fine ciclo, merge separato dal deploy) sono in gran parte fatti il 19/10; restano lacune rispetto alla specifica: controllo semantico dello stato (non solo hash), prova di ripristino isolata, verifica di una sola istanza operativa, deploy dei bot su un commit preciso e approvato. Resta da chiarire cosa intende per "20/30%" (Turbo Scalp / scalping).

## Prossimo passo suggerito
Discutere con l'utente e ChatGPT il piano tecnico `PIANO-TECNICO-CERVELLO-PROFESSIONALE.md` (proposta; primo intervento suggerito: replay offline delle correzioni A-D e Profit Manager puro con prove, nessun deploy). Fatto il 19/10 pomeriggio su decisione dell'utente: **deploy di bot e pool agganciati al commit approvato** (non ancora usati da un deploy vero) e **sentinella del backup esterno con avvisi Telegram** (attiva dalla notte del 20/10; prova del 19/10 14:40 partita, arrivo da confermare dall'utente). La chiave di recupero resta quella attuale (decisione dell'utente).

## Dove trovare i dettagli
- Come si lavora: `MANUALE-OPERATIVO.md`.
- Cosa è successo e quando: cartella `diario/` e `STORIA-FINO-AL-19-OTTOBRE.md`.
- Esiti dei controlli sul server: file `deploy/*-output.txt` sul ramo `rule-pool` (i più utili: `superbot-sg-check`, `sg-bots-check`, `sg-hardening-check`).
- Documentazione estesa (rapporti, valutazioni, specifiche): sta nel Project "superbot trading" di Claude. Se serve un documento che non c'è qui, l'utente può passarlo.
