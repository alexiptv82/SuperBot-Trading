# Checkpoint 18/11/2026, 18:48 Europe/Rome — GARA ARENA 72H AVVIATA; UI NON COLLEGATA

**Tipo:** delta append-only rispetto al checkpoint delle 17:50. Solo documentazione in questa esecuzione; nessun merge, deploy, Action, modifica VPS, reboot, reset, ordine o API a pagamento effettuati da questo checkpoint.

## Novità verificate

1. **Autorizzazione e T0 effettivo.** L'utente ha autorizzato esplicitamente T0 comune e avvio dei runner DeepSeek, Qwen e MiniMax per la gara PAPER di 72 ore, budget AI massimo 18 USD. Screenshot Termius e commento PR #110 attestano T0 `1795021392344`, corrispondente a **18/11/2026 18:03:12.344 Europe/Rome**. Stop di nuove inferenze/aperture previsto per **21/11/2026 18:03:12 Europe/Rome**; le uscite automatiche devono restare attive per eventuali posizioni ancora aperte.
2. **Primo checkpoint operativo alle 18:05.** Da screenshot VPS riportato sulla PR #110:
   - `BLOCCHI=[]`;
   - DeepSeek runner active, exit healthy, 10 eventi, 8 tracce AI, 1 posizione, spesa interna modellata 0,014817 USD;
   - Qwen runner active, exit healthy, 6 eventi, 4 tracce AI, 1 posizione, spesa interna 0,008774 USD;
   - MiniMax runner active, exit healthy, 10 eventi, 7 tracce AI, 2 posizioni, spesa interna 0,008282 USD;
   - totale puntuale: 19 tracce, 26 eventi, 4 posizioni PAPER e 0,031873 USD interni. Non è prova della fatturazione provider né stato live continuo.
3. **Credito DeepSeek.** Uno screenshot recente accessibile mostrava saldo DeepSeek di circa 4,20 USD. È stato ipotizzato un rabbocco di 10 USD, ma non risulta verificato come eseguito. Il limite interno Arena di 6 USD non è hard cap provider e il conto può essere condiviso con Brain storico: monitorare disponibilità senza pubblicare segreti.
4. **App Samsung non aggiornata, gara non persa.** Screenshot Samsung mostra ancora confronto 14 giorni, AI “Non avviato” e dati vuoti, in contrasto con il checkpoint VPS operativo. Il problema è di lettura web/UI, non prova di arresto o perdita delle run.
5. **Diagnosi web conclusiva alle 18:21.** Sul container `superbot`:
   - immagine `superbot:brain-close-ro-candidate-20261115`, restart always, bridge, `127.0.0.1:8002 -> 8001/tcp`;
   - `GET /api/v3/arena = 404`;
   - reader Arena e route non presenti nell'immagine; env Arena read-only/day assenti; nessun mount `/opt/superbot-ai-arena-paper`;
   - build web live ancora “14 giorni”; sorgente PR #110 è “3 giorni”, ma non rilasciata.
   Non bastano refresh o export env: serve una futura candidate image web-only con backend reader/route autenticati e mount Arena read-only, preservando login, WebAuthn/PWA, porte, rete, volumi, mount ed env esistenti.
6. **Cutover web soltanto preparatorio.** È stato definito un incarico per ramo isolato/PR draft, test 401 senza sessione e 200 con sessione, build frontend 3 giorni e rollback. Nessuna candidate, PR dedicata, test o installazione risultano ancora completati in questi riscontri; nessuna autorizzazione al deploy web è implicita nell'autorizzazione T0.

## Stato consolidato per la ripresa

- **Arena PAPER attiva:** DeepSeek/Qwen/MiniMax con T0 comune e tre portafogli separati. Ultima prova puntuale 18:05: tre runner active, tre exit healthy, quattro posizioni PAPER complessive. Non modificare strategie, T0, run, journal o servizi durante la gara.
- **Scadenza:** blocco nuove chiamate/aperture al 21/11/2026 18:03:12 Europe/Rome; uscite restano operative dopo la scadenza se necessario.
- **Falco/Toro/Brain:** Falco e Toro restano spenti/ritirati; preservare storici, SHORT Falco ed EventJournal. Brain storico resta separato/fuori classifica e non va confuso con DeepSeek Arena.
- **App/UI:** i dati Arena non sono visibili nell'app Samsung perché backend web/live bundle non espongono l'Arena. Nessuna evidenza di perdita dei journal; usare riscontri read-only VPS finché un cutover web non è provato e autorizzato.
- **GitHub:** PR #110 resta open/draft a `6a88857ac2ff117bd7711958c63604700f113cb0`; 39/39 mirati e 202/202 Arena riportati PASS. Nessun merge.
- **RC84:** PR #80 resta all'ultimo dato verificato `0e29a73a36f668643da4088178bacb8616a45ac0`.
- **Backup/chiavi:** age PC `ESITO: VERIFICA OK` e chiave pubblica coincidente non certificano il backup VPS. `work/extbackup-bot-stopped-20261109` resta preparato e non installato. Nessun segreto letto o pubblicato.
- **Conversazioni:** accessibili solo estratti recenti, screenshot e commenti GitHub; nessuna trascrizione integrale di chat eliminate né accesso SSH diretto da questo checkpoint.

## Fatto / preparato / rilasciato

- **Fatto su VPS da prova screenshot/commento:** T0 comune, avvio tre runner, prime inferenze/decisioni PAPER, quattro posizioni al controllo 18:05 e uscite sane.
- **Preparato:** diagnosi web completa e mandato tecnico per candidato web-only reversibile in ramo isolato.
- **Rilasciato/attivo:** gara PAPER Arena; nessun LIVE. Il web Arena non è rilasciato.
- **Non approvato/eseguito:** merge PR #110, cutover/recreate container web, nuova immagine, mount Arena nel web, reset, modifica strategie/budget, rabbocco DeepSeek verificato o stop della gara.

## Blocker e prossimo passo

1. Monitorare in sola lettura runner/exit/journal, budget interno e disponibilità provider, senza cambiare la gara; riportare timestamp e fonte per ogni checkpoint.
2. Preparare e testare offline una candidate web-only che riproduca esattamente container/auth/PWA correnti, aggiunga soltanto GET Arena autenticato e mount read-only e abbia rollback automatico. Non deployare senza autorizzazione separata.
3. Finché il cutover non è dimostrato reversibile, preferire readout VPS in sola lettura: non fermare runner/exit e non resettare T0 per correggere l'app.
4. Verificare separatamente eventuale rabbocco DeepSeek e costo provider; non dedurlo dal ledger interno.

## Limiti

Lo stato operativo è una fotografia delle 18:05, non una certificazione continua fino alle 18:48. Il checkpoint documentale non ha accesso SSH live e non ha eseguito operazioni VPS.
