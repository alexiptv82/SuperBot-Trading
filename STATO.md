# STATO CORRENTE SuperBot-Trading — 25 ottobre 2026
Fotografia sintetica per ChatGPT Work, chat normale e Claude. Per lo storico precedente consultare i commit di questo file e ARCHIVIO-STATO-PRE-SYNC-2026-10-23.md. Protocollo: SINCRONIZZAZIONE-WORK-CHAT.md.

## Runtime PAPER (NON toccare senza nuova autorizzazione)
- Hawk + Bull in PAPER sul VPS Singapore, codice dichiarato e verificato 297b126ea5f0b26bea281bdcdb330739d9fc2fe2 (versione 297b126). Deploy autorizzato e riuscito: GitHub Actions 40070696611, avvio sequenziale Hawk→Bull, un solo writer per bot; controllo indipendente 40070871034 e riconfermato da Claude (Actions 40217006058, 25/10): processi running, heartbeat fresco, exec_mode=paper e nessun ordine reale.
- Capital Management V1 integrato in rule-pool e INSTALLATO sul VPS ma con DESK_CAPITAL_V1=off, non abilitare senza OK dell'utente. Trading mantiene comportamento pre-abilitazione. Nessun reset portafogli né dati storici.
- Backup pre-deploy cifrato con nuova chiave age V2: superbot-backup-20261024T062811Z.tar.gz.age; prova di decifratura/restore riuscita e dati Hawk/Bull intatti, 43 file verificati in Actions 40010394710 (tentativo 2). Nessuna chiave privata nei file del repository.
- rule-pool è un ramo operativo: il suo HEAD può cambiare per audit/fix senza cambiare l'immagine deployata 297b126. Non toccare Strasburgo/HiTV.

## Fix P1 e P2 in rule-pool — non deployati (in attesa di OK utente)
- **P1 sbias LONG** (commit 635b964, merge 4ec05f4, ChatGPT 25/10): `backend/desk/signals.py` — ridotto peso trend HTF, aggiunto rimbalzo RSI 1h (RSI<35 + mom>0.003 → +10 punti LONG). Revisione Claude: modifica minimale e a basso rischio; monitorare ingressi LONG dopo il prossimo deploy.
- **P2 smart fallback** (commit 5e1ee2a + 017dd07, ChatGPT 25/10): `backend/desk/cli.py` + `brain.py` — distingui "Claude ha risposto e sceglie 0 aperture" da "Claude non disponibile". Se Claude ha risposto: regole solo `only_manage=True` (nessuna nuova apertura). Se Claude non disponibile: fallback completo come prima. Revisione Claude: correzione corretta e importante, risolve incoerenza SHORT spurii.
- **Entrambe le modifiche sono in `rule-pool` HEAD ma i bot girano ancora su 297b126. Deploy richiede OK esplicito.**
- Workflow `claude-write.yml` aggiunto (1dd9004): consente operazioni Git autonome di Claude tramite trigger. Richiede secret `CLAUDE_WRITE_TOKEN` da verificare.

## PROGETTO — FIX B AI PROFIT GUARDIAN V1 (SOLO SHADOW)
- Utente ha autorizzato il 24/10 branch isolato, moduli e test, e pubblicazione di una SPECIFICA sul diario. Esplicitamente **vietati merge su rule-pool, deploy e riavvio Hawk/Bull** finché non arriva un ulteriore OK.
- Branch di lavoro: work/fix-b-profit-guardian; base di partenza rule-pool 91132ec; HEAD finale f212d41.
- Implementati SOLO moduli indipendenti backend/desk/profit_guardian.py e backend/desk/portfolio_alert.py, tre file test e workflow CI no-deploy. CI run 40075723911 SUCCESS: 21 test unitari. Nessuna modifica motore attivo.
- Parametri approvati: watch ROI netto 12%, review 20%; CLOSE_FULL, TAKE_PARTIAL 50%; budget separato 0,10 $/giorno UTC condiviso Hawk+Bull, intervallo minimo 30 minuti per posizione.
- ChatGPT è writer dei componenti Fix B; Claude è revisore incrociato paritario.
- **Specifica vincolante:** FIX-B-PROFIT-GUARDIAN-V1-SPECIFICA.md nel ramo diario. Report: diario/2026-10-24_chatgpt.md.
- **Prossimo passo Fix B:** revisione incrociata con Claude, replay offline, test di convalida, poi OK utente per merge e deploy.

## Altre informazioni operative
- DeepSeek è shadow indipendente: 96 chiamate valide/222 decisioni applied=false (storico 23/10, Action 40072633461).
- Capital Management V1: specifica CAPITAL-MANAGEMENT-V1-SPECIFICA.md; backup/restore V2 certificato; merge e deploy già conclusi. Non confondere con Fix B.
- Vincoli immutabili: nessuna istanza LIVE, nessun doppio processo, preservare DB, trade_history, learning_log, AI memory, vault e journal, non esporre credenziali.

## Claude — collaboratore permanente (25/10)
- Claude (Claude Code, Sonnet 4.6) attivo come collaboratore permanente. Mandato: solo PAPER, controllo VPS via workflow, correzioni su rami separati, nessun deploy/riavvio senza OK.
- Collegamento GitHub→VPS verificato (Actions 40217006058). Revisione Fix P1/P2 completata (25/10).
- Dettagli sessione: diario/2026-10-25_claude.md.

## Riferimenti
- LEGGIMI.md, MANUALE-OPERATIVO.md, SINCRONIZZAZIONE-WORK-CHAT.md.
- FIX-B-PROFIT-GUARDIAN-V1-SPECIFICA.md, diario/2026-10-24_chatgpt.md, diario/2026-10-25_claude.md.
- ARCHIVIO-STATO-PRE-SYNC-2026-10-23.md e cronologia Git del precedente STATO.
