# SuperBot LONG — audit indipendente di Grok TC02.4 verificato da ChatGPT
Data: 2026-10-31 (ora locale Europa/Roma). Solo audit offline, nessuna modifica operativa.

Audit Grok allegato: SuperBot_Long_Timing_Contract_02_4_Independent_Audit.zip SHA256 f37307c6b6e169032d094314217dd3ba8fa0efe637a17e2d12e5553df3fa6e23. ZIP integro, manifesto 2/2 OK.
Sorgente analizzata: SuperBot_Long_Timing_Contract_02_4.zip SHA256 2abf78ca525592ce77dca1b35c3fe56dbf5ddcbb7f1046edfcc4d4031f65d801, manifesto 18/18.
Runner TC02.4 ripetuto: 163/163 PASS, incluso 21 legacy; baseline V6.1.1 82/82 PASS. Nuovi 25 test Grok 25/25 PASS.

R1 confermato (P1 nel solo harness): _ENTRY_CAPABILITY è importabile e LabLedger._commit_validated_entry accetta un ENTRY preformato con prezzo=-1, quantity=-12 e fee=NaN dopo PENDING valido, senza dimostrazione quote. ID appare filled. SINGLE_AUTHORIZED_ENTRY_PATH forte FAIL, percorso pubblico rigoroso PASS. Non è exploit remoto né un problema motore LONG, e Python private/closure non crea un vero sandbox in presenza di codice ostile nello stesso interprete.
R2 riscontrato indipendentemente (P2, delimitazione del contratto): passando intenzionalmente il medesimo LabLedger a simulate_legacy_synthetic_fill(ledger=...) e poi a simulate_pending_fill(ledger=...), il legacy scrive ENTRY nel ledger condiviso e blocca il successivo strict come ALREADY_TERMINAL. Questo viola isolamento forte se richiesto anche con ledger= esplicito, NON viola la sola promessa documentata di ledger predefiniti separati.

Due nuovi test indipendenti falliscono 2/2 sul pacchetto invariato: TC024_AUDIT_COMPLEMENTARE_REGRESSIONI.py. Rapporto e prove in REPORT_VERIFICA_AUDIT_GROK_TC024_2026-10-31.md, TC024_AUDIT_COMPLEMENTARE_ESITI.txt, prompt PROMPT_GROK_TC024_AUDIT_FOLLOWUP_2026-10-31.md. Pacchetto: PACCHETTO_VERIFICA_AUDIT_GROK_TC024_PER_GROK.zip SHA256 06eb5398d64e5f8d3e7a28b0fb1da1cc5fce7425175d9b6a590168c3377d0fb4.

Verdetto: non congelare ancora in senso forte TC02.4, prima decidere contratto di isolamento legacy e patch mirata del punto ENTRY; non riaprire strategia LONG. REAL_EXECUTION UNVERIFIED, ECONOMIC_EVIDENCE INSUFFICIENT, PAPER_ELIGIBLE NO. Motore V6.1.1, Brain, Falco, Toro, SHORT, wallet, VPS, bot operativi invariati. Nessun merge o trading.