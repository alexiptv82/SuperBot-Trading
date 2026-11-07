# RC80 — Revisione indipendente ChatGPT, 7 novembre 2026

**Esito: REQUEST CHANGES / NO-GO ATTIVAZIONE.** Non è un audit VPS.

## Oggetto e conferme
- PR Draft #77: https://github.com/alexiptv82/SuperBot-Trading/pull/77
- HEAD verificato `9dedf5dc9ea0586e854afc59ebc050f9574f62c0`; base PR #75 `b6eaa173c12c241647f89f730e1430a841cade3a`. 6 file diff, PR #74/#76 separate.
- 56 PASS **dichiarati locali** nella PR, nessuna GitHub Actions per il commit. Qui verifica statica GitHub + riproduzione isolata Linux del controllo lock percorso vs possesso reale; non è una certificazione e2e.
- Nessun merge, deploy, contatto VPS, riavvio, reset o ordini da ChatGPT durante la review.

## Rilievi e istruzioni
Commento completo pubblicato: https://github.com/alexiptv82/SuperBot-Trading/pull/77#issuecomment-6713923063

1. **P0 lock:** `_fd_is_writer_lock` confronta soltanto path del file descriptor, non controlla che tenga davvero `flock(LOCK_EX)`. Riproduzione: secondo FD non lockato sullo stesso path passa il controllo path ma fallisce su acquisizione reale. Test negativo multiprocesso e ownership concreta.
2. **P0 identità:** `_history_has_close` e `inspect_claims` confrontano `symbol,id` senza `open_ms,run_id`; vecchio close con ID riusato in run successiva può causare falsa riconciliazione oppure stop bloccato. Non equiparare close parziale a terminale. Persistire e verificare identità forte e learning journal.
3. **P1 dato prezzo:** `classify_candle` accetta anche candela 1m ancora in formazione (apertura 5 secondi fa), pur definendola finita. Wick oltre stop ma close rientrato non fa uscire: è monitor stop *close-only* non protezione tick/intrabar. Definire modello PAP​ER esplicito, evidenziare limiti e testare.
4. **P1 stato:** perdita scrittura `paper_stop_health.json` soppressa; assente collaudo UI/allarme per partial/blind/blocked. Fail-visible non ancora certificato.

## Prossimo passo
Lasciare PR #77 Draft e RC78 OFF; Grok può effettuare correzione nel proprio branch con commit aggiuntivo e test mirati; ChatGPT controlla gli SHA aggiornati, poi possibile revisione Claude. Nessun merge, deploy o riavvio senza autorizzazione dedicata. Protezione 450 USDT, PAPER, storici e strategie invariati. Ultimo audit VPS noto RC77 Falco/Toro 0 aperte, Brain pausa, backup locale/restore PASS, off-host non certificato.
