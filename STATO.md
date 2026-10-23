# STATO CORRENTE SuperBot-Trading — 23 ottobre 2026
**Fonte comune Work / chat normale / Claude:** branch `diario`, `SINCRONIZZAZIONE-WORK-CHAT.md`. Leggere anche `LEGGIMI.md`, `MANUALE-OPERATIVO.md`, ultimi diario e l'handoff tecnico specifico. Questa pagina è una fotografia attuale, non uno storico.

## Ambiente operativo
- Hawk e Bull: esclusivamente **PAPER**, runtime **`code_version=f87f2d6`** (SHA completo `f87f2d63c5849b177dbd33ee43c5be05ca58c8ed`), confermato 23/10/2026 con controllo indipendente GitHub Actions **39922740438** dopo il deploy isolato Fix A run **39922453846**.
- VPS Singapore; una sola istanza per bot. Ultimo rilascio verificato: Fix A soltanto. Default stop operativo attuale **12%**, non ancora 20%. Risorse e stati live da ricontrollare prima di future operazioni.
- Salvaguardia: backup cervello del deploy `bots-20261023-080755-deploy`; rollback immagine `superbot-desk:rollback-20261023-080755`. Non cancellare memoria, trade, lessons o DB.
- `rule-pool` è ramo operativo con storia diversa da `main` (app); SHA `rule-pool` **non coincide necessariamente con il codice dei container**. Non eseguire deploy ordinario di `rule-pool` supponendo sia identico a f87f2d6.
- Credenziali, importi reali Bitget e chiavi **mai** nel repo pubblico. Non toccare Strasburgo / HI-TV.

## Decisioni recenti dell'utente: Capital Management V1
**Design e parametri confermati; implementazione e deploy NON autorizzati.**
- Stop giornaliero futuro: **20%** del budget operativo di inizio giornata; protezione assoluta $450 invariata.
- Ogni bot ha vault virtuale indipendente; a **00:00 UTC** trasferire eccedenza sopra $1000 se effettivamente coperta da liquidità realizzata; altrimenti `pending` fino a chiusura posizioni, senza forzare chiusure e senza recupero automatico dal vault sotto $1000.
- Prelievo dal vault al portafoglio **soltanto manuale** con autenticazione/registro/idempotenza, mai automaticamente. In futura live nessuna movimentazione Bitget automatica.
- Sizer: Hawk **10%**, Bull **25%** del budget operativo giornaliero; max slot **10/6**; protezioni PAPER e rischio esistenti fino a nuovo deploy autorizzato.
- L'utente ha riconfermato 10%/25%, 00:00 UTC, pending e protezione 450 e autorizzato la progettazione tecnica. **Piano dettagliato pubblicato:** `CAPITAL-MANAGEMENT-V1-SPECIFICA.md`; handoff: `CAPITAL-MANAGEMENT-V1-HANDOFF.md`. Nessun codice o deploy autorizzato.
- Da esplicitare prima di codice: (A) tetto complessivo incluso DCA/split, (B) versamento manuale neutrale rispetto a stop/sizer fino al nuovo UTC, (C) equity temporaneamente >1000 con posizioni aperte e pending. Raccomandazioni scritte nel handoff; evitare di trattarle come deploy approvato.
- La discussione separata sul pulsante "Azzera budget AI" è stata diagnosticata read-only: bot riceve ed esegue reset; messaggio `stop giornaliero raggiunto` deriva da rischio trading, indipendente dal budget API. Non è stata applicata alcuna fix al reset.

## IN_CORSO — prenotazione componente (un autore alla volta)
- **Capital Manager / Vault Manager / Position Sizer / Dashboard:** Work ha completato la specifica tecnica per review. Nessun autore ha iniziato implementazione; prossimo passo review e decisione A/B/C, poi eventuale OK separato al codice. Chat normale/Claude possono revisionare; nessuna modifica concorrente allo stesso componente.
- **Ramo futuro proposto** `work/capital-management-v1` dalla baseline runtime `f87f2d63c5849b177dbd33ee43c5be05ca58c8ed`; non ancora creato.
- Prima di iniziare un componente, assegnare qui autore corrente (Work/chat/Claude), file, branch e SHA. L'altro non modifica lo stesso componente in contemporanea; eventualmente fa sola lettura/review.
- Nessun deploy autorizzato. Nessun aggiornamento a code_version autorizzato.

## PASSAGGIO Work / chat normale
- Chat normale ha creato e pubblicato **solo documentazione** sul ramo `diario`: `SINCRONIZZAZIONE-WORK-CHAT.md`, `CAPITAL-MANAGEMENT-V1-HANDOFF.md`, questa fotografia e cronologia 23/10. Nessuna modifica ai bot.
- **Presa in carico Work (23/10):** letti LEGGIMI, STATO, protocollo di sincronizzazione, handoff Capital Management e ultime voci del diario al checkpoint `b1baf5552194aebdb59c92b776edccbca359a3e4`. Confermata la ripresa della sola progettazione; nessun autore di codice prenotato e nessuna implementazione avviata. Restano aperti i punti A/B/C del handoff; codice e deploy richiedono le rispettive autorizzazioni.
- **Aggiornamento non continuo:** lo stato diventa visibile all'altra chat solo dopo il commit sul diario e una sua successiva lettura. Le chat inattive non si scambiano messaggi automaticamente.

## Riferimenti
- Regole inviolabili: `LEGGIMI.md`; prassi GitHub/SSH/backup: `MANUALE-OPERATIVO.md`.
- Cronologia per giorno/autore: `diario/YYYY-MM-DD_*.md`.
- Storico della vecchia pagina STATO: `ARCHIVIO-STATO-PRE-SYNC-2026-10-23.md`.
