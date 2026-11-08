# SuperBot V3 — RC80 terza revisione indipendente, 8 novembre 2026

**PR #77 HEAD controllato:** `34a4abe6ac80b5d65bfc12fbfdbe40d131124b4d`, branch `cursor/rc80-paper-stop-hardening-31c4` Draft, base `cursor/rc78-paper-stop-offline-31c4` @ `b6eaa173c12c241647f89f730e1430a841cade3a`. Nessun merge, deploy, VPS, reset, startup.

## Stato tecnico
- **P0-E storico + learning:** `find_same_closure` accoppia `close_ms`, `why`, `net`, `gross`, `fees`, `exit` presenti, e ignora fill parziali. Correzione presente.
- **P0-F restart:** `assess_restart` read-only verifica append-only di logs, prova delle posizioni scomparse e invariabilità di `lessons.md`; `publish_recovery_snapshot` produce checkpoint separati nella cartella sorella del backup originale. Non ripristina sopra i file correnti e non riscrive il backup storico. Test scritto con due posizioni BTC/ETH, BTC chiusa e ETH protetta dopo restart, learning mancante rifiutato. Correzione presente.
- **Test:** PR dichiara 65 PASS locali, GitHub Actions sul commit: nessuna esecuzione associata; non rieseguiti indipendentemente da ChatGPT in questa verifica. Questi dati non certificano l'attivazione.

## Un caso limite di consistenza da coprire prima della certificazione
`find_same_closure` considera validi una coppia di righe identiche anche se uno dei due log contiene **un'ulteriore chiusura terminale contraddittoria** per la stessa posizione. Test necessario: history con terminali close_ms 2000 e 3000, learning solo 2000; spec deve rifiutare l'ambiguità `unproven/mismatch`. Controllare il reciproco e i duplicati. Commento GitHub https://github.com/alexiptv82/SuperBot-Trading/pull/77#issuecomment-6720918518 .

## Rimane per l'avvio
Dashboard V3 non integra ancora allarmi effettivi `protection_alarm`, modello `closed_1m_close_only` non esegue stop su wick intrabar, backup off-host non certificato, Brain single-close PR #74 offline, nuova run 1000/1000/2000 e snapshot iniziali dedicati, test di integrazione e collaudo su VPS con OK separato. Nessun rischio o strategia modificata. **RC80 rimane DRAFT e OFF**.
