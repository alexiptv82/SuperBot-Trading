# 31 ottobre 2026 — LONG Lab V6: audit indipendente ChatGPT

**Pacchetto:** SuperBot_Long_Lab_v6.zip, SHA-256 b13cd9733e409d8506caa11ee6d764fd22ecacfd99237159960226c4198a6086. 45 membri ZIP, 44/44 hash del manifesto conformi.

**Esecuzioni verificate offline:** 82/82 test ufficiali PASS; 11/11 test regressivi V4 PASS; 9/9 test avversariali V5 PASS. Le nove anomalie bloccanti V5 (confronto segnali/ledger e candela futura invalida) risultano corrette. Risultati software di laboratorio soltanto, senza mercato reale.

**Nuovi sei test indipendenti negativi:** 6/6 FAIL sulla V6. replay.verify_run restituisce PASS se si modifica 'kind' da synthetic a historical senza cambiare dataset, si svuota 'limitations', si aggiunge PAPER_ELIGIBLE=True al report o a metrics, si aggiunge policy.leverage=50 (non modellata), oppure si elimina 'verdict'. Difetto circoscritto all'integrità/schema esterno del rapporto, non alla curva e al ledger ora ricalcolati. Falsi campi possono presentare in modo scorretto prove sintetiche e limiti economici.

**Compatibilità con Brain reale:** letto backend/director/brain_free/feeds.py e backend/director/brain_scalp/ai_context.py sul ramo work/brain-mtf-packaging-20261031: 120 barre TF lenti di norma, contro 200 richieste LONG, MTF solo riassuntivo; nessun recorder di available_at osservati o binding LONG. Nessun test Bitget OOS genuino, leva/liquidazione e wallet LONG+SHORT congiunto.

**Verdetti:** LAB OFFLINE utilizzabile come base di ricerca con avvertenze; BRAIN_ADVISORY, HAWK_LONG_SHADOW, BULL_LONG_SHADOW = DA_CORREGGERE; PAPER_ELIGIBLE=NO, economicamente INSUFFICIENT_EVIDENCE.

**Consegna in questa chat:** AUDIT_INDIPENDENTE_LONG_LAB_V6_2026-10-31.md, LONG_V6_REGRESSIONI_REPORT_INTEGRITA.py e PROMPT_GROK_PATCH_LONG_V6_1_2026-10-31.md. Prossimo: Grok, proprietario del LONG, può proporre patch minima dei campi/schema di verify_run, test 82+11+9+6 e poi congelare sviluppo software per passare a dati osservati e validazione economica. Nessun merge/deploy/trading, nessuna modifica al codice Brain/SHORT/portafogli, nessun dato sensibile pubblicato. L'ownership di Brain resta ChatGPT per ramo MTF.