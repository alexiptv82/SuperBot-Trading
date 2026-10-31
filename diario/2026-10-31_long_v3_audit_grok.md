# LONG Lab V3 — revisione indipendente, 31 ottobre 2026

Utente ha comunicato disponibilita' di Grok come collaboratore con connessione GitHub. Non risulta alcuna modifica o incarico gia' eseguito da Grok; ruolo proposto: audit/correzioni LONG su ramo separato, senza toccare il ramo Brain gestito dalla chat principale.

Pacchetto verificato offline: SuperBot_Long_Lab_v3.zip SHA256 3f3a6655f2b745d04baab86578c391bc29c6cd6f67ba820d65f1aa7260a447ce; 29/29 hash del manifesto conformi. 77/77 test originali PASS. Fix V2 relativi a bool non validi, availability unknown, quote non finite e NO_TRADE confermati.

**BLOCCHI RIPRODOTTI in test avversariali indipendenti:**
1. adapters/brain_adapter.py/adapt_context usa brain_payload.get('short_open', short_open). Se il wallet owner fornisce short_open=True e il payload contiene short_open=False, l'adapter restituisce False. Il payload puo' dunque scavalcare un SHORT autorevole; errore di trust boundary.
2. superbot_long_lab/replay.py/verify_run accetta modifiche equity_curve[3], [5], [120] += 0.10 USDT, mantenendo 'software_checks=PASS' e dataset inalterato. Controlla in modo speciale soltanto i primi 2 punti interni anziche' ricostruire per ciascun timestamp.
3. verify_run accetta max_drawdown dichiarato maggiorato di 0.04 (quattro punti percentuali), per via di una tolleranza assoluta ~0.05 contro la curva close-path.
4. observed_availability e' indicizzata solo da close_ms, non da simbolo/timeframe; potenziale collisione fra serie storiche distinte.

**LIMITE DI INTEGRAZIONE CONFERMATO via GitHub:** backend/director/brain_free/feeds.py sul ramo work/brain-mtf-packaging-20261031 legge generalmente 120 barre TF lenti, contro 200 richieste dal LONG. ai_context.py contiene closed_multitimeframe riassuntivo, non le 200 barre con availability osservata. Servono recorder/backfill e contratto consultivo non bloccante. Nessun OOS autentico, leverage/liquidazioni o LONG+SHORT congiunto.

Verdetti: BRAIN_ADVISORY=DA_CORREGGERE; HAWK_LONG_SHADOW=DA_CORREGGERE; BULL_LONG_SHADOW=DA_CORREGGERE; PAPER_ELIGIBLE=NO.

Artefatti creati in chat e da consegnare a Grok: AUDIT_LONG_LAB_V3_GROK_2026-10-31.md, PROMPT_GROK_SUPERBOT_LONG_V4_2026-10-31.md, long_v3_independent_repros.py. Sono file locali di questa conversazione, non disponibili automaticamente sul repo; allegarli insieme allo ZIP V3. Se Grok accetta il compito, usare ramo isolato, registrare ownership in STATO.md prima di scrivere e lasciare intatto Brain principale.

Nessun merge, deploy, servizio, VPS, trading, portafoglio, commit sul codice del Brain o modifica agli SHORT. Diario aggiornato solo per sincronizzare i collaboratori.
