# STATO di SuperBot Trading

**Aggiornato:** lunedì 19 ottobre 2026, ~14:45 (ora di Roma) — da Claude.
**In corso:** ChatGPT su `backend/desk/profit/`, test e replay offline, dal 19/10/2026 15:15 (Europe/Zurich). Autorizzazione utente in chat: fase 1 pura, ramo `work/profit-manager` da `rule-pool`; nessun aggancio, deploy o modifica dei bot. (Chi comincia a lavorare su un componente scrive qui sotto: "In corso: <chi> su <componente> dalle <ora>", e lo toglie a fine lavoro.)

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
