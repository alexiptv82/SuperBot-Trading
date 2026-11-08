# SuperBot V3 RC80 — Verifica HEAD 9bdb82, 8 novembre 2026

**PR:** https://github.com/alexiptv82/SuperBot-Trading/pull/77 `cursor/rc80-paper-stop-hardening-31c4`, head verificato `9bdb82cef48bc22df399ac2a5ac9b8481ad9305b`, base RC78 `b6eaa173c12c241647f89f730e1430a841cade3a`. Draft, non merged/deployed.

**Confermato sul codice:** `terminal_closure_status` rifiuta terminali contrastanti in uno o entrambi i registri anche se è presente una coppia valida; ammette copie identiche e ignora partial. Test `test_conflicting_terminal_closes_are_not_a_unique_proof` copre ordine, learning/history, entrambi, duplicate e parziali. 66 PASS dichiarati nei test locali dell'autore (29+22+15), non CI GitHub né nuova esecuzione indipendente. Nessun workflow run associato al commit.

## P0 regressione nell'ultimo diff
`inspect_claims()` restituisce `resolved` **dentro** `for claim in claims` al primo claim con `status=="unique"` e non in fondo al loop. Il file `paper_stop_protect.work` contiene più claims quando uno stesso tick protegge più trade; dopo crash del batch, se BTC è risolta e ETH resta aperta/non verificata, il file viene archiviato al primo claim BTC. L'ordine delle entries cambia il verdetto. **Questo è rilievo bloccante per la riconciliazione batch**, non una richiesta di rifare RC80. Review GitHub https://github.com/alexiptv82/SuperBot-Trading/pull/77#issuecomment-6721423727 contiene patch/test richiesti.

**Gate:** accumulare verdetto su tutti i claims, `resolved` solo se tutti provati; test 2+ claims con uno irrisolto e invertendo ordine. No merge/deploy/riavvio/ordine/VPS. No cambi strategie, rischio o formulazione economica.

**Dopo:** esecuzione indipendente CI/test sul SHA completo, test integrati di health indicator e allarme UI, policy esplicita close-only 1m (wick non fill), check Brain manual-close PR74, dashboard PR72, backup esterno, pianificazione cutover PAPER con portafogli 1000/1000/2000 e memoria conservata. Ultimo audit VPS resta RC77 Falco/Toro 0 posizioni PAPER, Brain paused.
