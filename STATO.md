# STATO CORRENTE SuperBot-Trading — 24 ottobre 2026
Fotografia sintetica per ChatGPT Work, chat normale e Claude. Per lo storico precedente consultare i commit di questo file e ARCHIVIO-STATO-PRE-SYNC-2026-10-23.md. Protocollo: SINCRONIZZAZIONE-WORK-CHAT.md.

## Runtime PAPER (NON toccare senza nuova autorizzazione)
- Hawk + Bull in PAPER sul VPS Singapore, codice dichiarato e verificato 297b126ea5f0b26bea281bdcdb330739d9fc2fe2 (versione 297b126). Deploy autorizzato e riuscito: GitHub Actions 40070696611, avvio sequenziale Hawk→Bull, un solo writer per bot; controllo indipendente 40070871034: processi running, heartbeat fresco, exec_mode=paper e nessun ordine reale.
- Capital Management V1 integrato in rule-pool e INSTALLATO sul VPS ma con DESK_CAPITAL_V1=off, non abilitare senza OK dell'utente. Trading mantiene comportamento pre-abilitazione. Nessun reset portafogli né dati storici.
- Backup pre-deploy cifrato con nuova chiave age V2: superbot-backup-20261024T062811Z.tar.gz.age; prova di decifratura/restore riuscita e dati Hawk/Bull intatti, 43 file verificati in Actions 40010394710 (tentativo 2), comprese posizioni aperte al momento del snapshot, più backup locale e immagine rollback del deploy. Nessuna chiave privata nei file del repository.
- rule-pool è un ramo operativo di codice e workflow: il suo HEAD può cambiare per audit/test senza cambiare l'immagine deployata 297b126. main/altre app sono entità separate. Non toccare Strasburgo/HiTV.

## NUOVO PROGETTO — FIX B AI PROFIT GUARDIAN V1 (SOLO SHADOW)
- Utente ha autorizzato il 24/10 branch isolato, moduli e test, e pubblicazione di una SPECIFICA sul diario. Esplicitamente **vietati merge su rule-pool, deploy e riavvio Hawk/Bull** finché non arriva un ulteriore OK.
- Branch di lavoro: work/fix-b-profit-guardian; base di partenza rule-pool 91132ec230200f921d08674b0508163eab4d6e7d; HEAD finale del lavoro f212d4140adae4c48f8657aa7ceb0e481ac585d8.
- Implementati SOLO moduli indipendenti backend/desk/profit_guardian.py e backend/desk/portfolio_alert.py, tre file test e workflow CI no-deploy. Pipeline CI run 40075723911 SUCCESS: 21 test unitari offline, py_compile e isolamento import. Nessuna chiamata AI reale/runner/esecuzione, nessuna modifica motore attivo. ChatGPT è writer dei componenti Fix B; Claude è revisore incrociato paritario e non deve scrivere contemporaneamente negli stessi file senza accordo.
- Parametri approvati: watch ROI netto 12%, review 20%; CLOSE_FULL, TAKE_PARTIAL 50% (stop residuo valido o intera operazione rifiutata), HOLD_TP; budget separato 0,10 $/giorno UTC condiviso Hawk+Bull, intervallo minimo 30 minuti per posizione; prompt Claude Fix B dedicato con ROI/MFE/distanza TP in R.
- Portfolio Trend Alert: SHORT aperte + BTC/ETH, 3+ inversioni simultanee su barre 1h chiuse EMA20/50 + RSI + volume -> rivalutazione Claude priorità massima, anche ROI sotto 20%, senza chiusure automatiche. In cooldown si registra subito e si differisce la revisione alla prima scadenza.
- Tre corsie comparative da registrare per evento: candidato Claude operativo NON eseguito; seconda proposta Claude shadow; output DeepSeek già esistente, applied=false, indipendente e mai co-decisore. Se i dati DeepSeek non sono comparabili, lo si dichiara, mai inventare. I moduli consentono registrazione append-only in directory separata, senza scrittura bot/DeepSeek.
- **Specifica vincolante:** FIX-B-PROFIT-GUARDIAN-V1-SPECIFICA.md nel ramo diario. Handoff e report del giorno: diario/2026-10-24_chatgpt.md.

## Altre informazioni operative
- DeepSeek è shadow indipendente e non cambia in questo progetto; resoconto storico 23/10: 96 chiamate valide/222 decisioni applied=false, comparazione con Hawk/Bull in sola lettura (Action 40072633461).
- Capital Management V1: specifica originale CAPITAL-MANAGEMENT-V1-SPECIFICA.md; backup/restore V2 certificato; merge e deploy già conclusi in precedenza. Non confondere con Fix B.
- Vincoli immutabili: nessuna istanza LIVE, nessun doppio processo, preservare DB, trade_history, learning_log, AI memory, vault e journal, non esporre credenziali, backup verificato e rollback prima di ogni intervento.
- Prossimo passo Fix B: revisione incrociata con Claude, replay offline, test di convalida con dati reali, poi richiedere esplicito OK per merge e successivo deploy. **Nessuna attivazione permessa ora.**

## Riferimenti
- LEGGIMI.md, MANUALE-OPERATIVO.md, SINCRONIZZAZIONE-WORK-CHAT.md.
- FIX-B-PROFIT-GUARDIAN-V1-SPECIFICA.md e diario/2026-10-24_chatgpt.md.
- ARCHIVIO-STATO-PRE-SYNC-2026-10-23.md e cronologia Git del precedente STATO.
