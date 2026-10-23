# Protocollo di sincronizzazione — ChatGPT Work e chat normale
Ultima definizione: 2026-10-23 · responsabile del protocollo: ChatGPT · fonte comune: GitHub `alexiptv82/SuperBot-Trading` ramo `diario`.

## Scopo e limite reale
Le due chat NON condividono automaticamente il contesto istantaneo e NON si scambiano messaggi quando sono inattive. Questo ramo GitHub è il **punto di verità condiviso aggiornato a checkpoint**, non uno streaming automatico. La sincronizzazione diventa disponibile all'altra chat al successivo accesso al repository. Non promettere aggiornamento continuo o di aver letto l'altra chat direttamente. Un fatto trovato nel server/repository live prevale su annotazioni obsolete.

## Procedura obbligatoria, identica per Work e chat normale
1. **All'inizio di ogni sessione e prima di ogni intervento** connesso a SuperBot: aprire su `diario` `LEGGIMI.md`, `STATO.md`, `MANUALE-OPERATIVO.md`, `SINCRONIZZAZIONE-WORK-CHAT.md`, `CAPITAL-MANAGEMENT-V1-HANDOFF.md` se pertinente, e le ultime voci datate di `diario/`. Leggere anche i commit/branch correnti pertinenti prima di considerare `STATO.md` esaustivo.
2. **Prima di lavorare su codice**: registrare nella sezione `IN_CORSO` di `STATO.md` componente, chat proprietaria per questa fase, ramo, commit base e obiettivo; l'altra chat opera da revisore (sola lettura) sullo stesso componente fino al passaggio di mano. Se proprietà già dichiarata e attiva, non scrivere sugli stessi file senza coordinarsi con l'utente.
3. **Ogni volta che l'utente approva, rifiuta o modifica un vincolo**, scrivere immediatamente decisione, ambito e autorizzazioni effettive in `STATO.md` e in `diario/YYYY-MM-DD_chatgpt.md` (Work e normale: indicare nella voce quale delle due). Un OK per progettazione NON autorizza implementazione o deploy.
4. **Dopo ogni commit, test, controllo VPS, blocco o rilascio** aggiornare checkpoint GitHub (SHA completo, ramo, risultato test, run ID, `code_version` runtime SOLO se verificata) e `STATO.md` con prossimo passo, chi deve fare cosa, e gli eventuali blocchi. Scrivere prima e dopo operazioni ad effetto, se mai autorizzate.
5. **Quando si passa da Work alla chat normale o viceversa**, chi lascia scrive `PASSAGGIO` con commit esatto, stato e istruzione successiva; chi entra rilegge prima di agire. Se la sessione che lascia si interrompe prima di scrivere, la nuova legge i commit e verifica lo stato senza inferire che il lavoro sia completato.
6. **Mai sovrascrivere aggiornamenti altrui**: leggere il blob SHA più recente e usare update condizionale; in caso di conflitto, rileggere e integrare. Non riscrivere storia / non force-push. Le due chat possono lavorare parallelamente SOLO su componenti e branch non sovrapposti; evitare aggiornamenti paralleli dello stesso `STATO.md`.
7. **Diario è pubblico**: mai credenziali, chiavi, dati del conto Bitget live, PII, log non filtrati, token, host key privata. Link e riferimenti a commit, run e branch sono consentiti.
8. **In caso di divergenza** fra diario, code_version e ambiente, fermarsi e misurare in sola lettura prima di suggerire modifiche.

## Invarianti permanenti
- Hawk e Bull restano strettamente PAPER. Nessun deploy senza OK esplicito riferito a quello specifico rilascio; non inferire autorizzazione dall'OK dato ad analisi, progetto, test o preparazione branch.
- Versione in esecuzione verificata il 23/10: `f87f2d6` su entrambi i bot. NON cambiare ramo operativo `rule-pool` o codice distribuito finché non autorizzato.
- Preservare memoria del Cervello AI, storico trade e DB, volumi del VPS Singapore; backup verificati e rollback prima di future attività ad effetto. Non creare doppie istanze; non toccare servizi HI-TV.
- Preparazioni Capital/Vault/Sizer/UI esclusivamente su ramo `work/*` separato; per l'app tenere distinti `main` e `rule-pool`. Non fare merge accidentali tra storie diverse.

## Ambiti di collaborazione
Work e chat normale hanno **uguale autonomia e responsabilità**, ma un solo autore attivo per file/componente. Suggerimento operativo (non vincolo permanente): Work sviluppa un modulo su branch dedicato, chat normale revisiona e verifica; oppure viceversa. Ogni cambiamento di ruolo va annotato in `STATO.md`. Claude, se coinvolto, usa il medesimo protocollo e la stessa riserva di proprietà.

## Stato di sincronizzazione
Aggiornamento garantito SOLO se una chat ha pubblicato il checkpoint GitHub e l'altra lo ha letto. Non esiste un ponte nascosto tra le due conversazioni né polling continuativo.

## Messaggio di avvio riutilizzabile
«Siamo in SuperBot-Trading. Prima di qualunque attività leggi dal repo GitHub `alexiptv82/SuperBot-Trading`, ramo `diario`: `LEGGIMI.md`, `STATO.md`, `MANUALE-OPERATIVO.md`, `SINCRONIZZAZIONE-WORK-CHAT.md`, `CAPITAL-MANAGEMENT-V1-HANDOFF.md` e ultime voci del diario. Applica il protocollo di checkpoint e proprietà del componente. Verifica che Hawk e Bull siano PAPER e baseline `f87f2d6`; non modificare né deployare senza mio OK esplicito. Per il progetto gestione capitale vale la specifica handoff. Dammi una sintesi breve dello stato e prosegui nella fase da me indicata, scrivendo le novità su `diario`.»
