# RC82 — Seconda revisione indipendente ChatGPT (8 novembre 2026)

**PR Draft #79:** https://github.com/alexiptv82/SuperBot-Trading/pull/79, branch `cursor/rc82-active-paper-stops-31c4`, HEAD `bccfddfb98e6ee0213962951879426fc61ef6f13`. Commit di codice `dfc705974396b826bfee42e34571d2aa7583e7ab`, base RC81 `29eb75750625a8819cd2db71dc2459d164c3199c` invariata. No merge, deploy, VPS, riavvii, reset, ordini.

## Report indipendente ricevuto e verifica statica
L'utente ha fornito `RAPPORTO-RC82-P0.md` e `HANDOFF-RC82-P0.md`, basati su esecuzioni Grok nella VM sviluppo, non CI GitHub. Test dichiarati: 17 RC82 PASS, 84 desk PASS, 67 exit-only/RC78/RC80 PASS con 7 warning deprecazione. SHA HEAD verificato GitHub. Nessuna run GitHub Actions relativa. Il test su `test_desk.py` ha impiegato 565 s in VM, perciò non è stato ripetuto da ChatGPT.

Sono implementate le correzioni richieste nella review precedente:
- `_prove_protective_close` rilegge storico e learning con `(symbol,id,open_ms,close_ms,why,net)` e run_no nel learning; non salva conto se manca una prova di chiusura; recupera lato incompleto; preserva frammenti JSONL e non riscrive la prova già presente.
- `operational_prices` fornisce prezzi solo da OHLC validi e non futuri a nuove aperture/DCA; stop storico su barre valide resta applicabile; nessun cambio strategie/Claude/rischio.
- Il codice del nuovo HEAD è uguale al commit `dfc705...` più aggiornamento documentale.

## Gate release RC82 ancora aperti
Commento completo ChatGPT https://github.com/alexiptv82/SuperBot-Trading/pull/79#issuecomment-6724909518 .

**P0-A vecchia candela ancora operativa:** se ultima barra valida BTC = 6 ore prima (o se ultima invalida e si ripiega a un vecchio close), `operational_prices` restituisce comunque prezzo per `open/dca`. `stop_feed` può segnalare stale contemporaneamente. Per l'apertura/aumento di rischio PAPER occorre quote freshness e controllo latest non degradato; mantenere chiusure protettive su barre storiche provate. Test open/DCA stale/future fallback no; current good yes; stop su historical breach yes.

**P0-B secondo passaggio dopo DCA e fallimento parziale dei registri:** dopo una modifica DCA in memoria, la seconda `apply_paper_protective_exits` può scrivere history su posizione post-DCA, ma non learning, e non salvare stato; su disco resta pre-DCA. Al retry la chiusura potrebbe avere `net` diverso e quindi non corrispondere alla chiave provata di quella già scritta, dando terminali incompatibili per la stessa posizione o posizione fantasma. Test mirato con learning write failure nel secondo passaggio dopo DCA e recovery; fail-closed su terminali contraddittori, nessuna distruzione registri. Test precedente RC82 copriva solo first-pass close.

Questi due gate sono **release blockers** e non equivalgono a un invito a riscrivere RC82. Correzione soltanto nel ramo RC82, test/rapporti prima di nuovo review. Nessun merge/deploy autorizzato.

## Gate di integrazione distinto dopo RC82
- Il loop attivo Falco/Toro verifica OHLC 15m ogni 900s (scalp/draining) o 1800s (altro), più durata fetch/ciclo; non è stop in tempo reale.
- Il wick sulla candela d'ingresso non è valutato, per evitare una cronologia sconosciuta.
- `stop_feed.alarm` del runner RUNNING non viene mostrato in dashboard RC81, che osserva il sidecar manutenzione. Occorre RC83/indicatore run-specific distinto. Brain deve mantenere la propria telemetria di rischio/exit-service.
- Non certificati: browser autenticato/mobile, backup off-host e prova restore, cutover/nuova run 1000/1000/2000 con storici preservati. Tutto PAPER.

**Ultimo audit VPS verificato nel diario:** RC77 Falco/Toro senza posizioni aperte, Brain paused. Non ricertificato su VPS oggi, nessuna operazione VPS compiuta da ChatGPT durante RC82.
