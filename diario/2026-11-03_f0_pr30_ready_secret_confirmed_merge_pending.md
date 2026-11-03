# SuperBot F0 — 2026-11-03 — PR #30 pronta per revisione, merge in attesa

L'utente conferma di aver creato direttamente nel repository GitHub il secret `SUPERBOT_F0_SSH_PRIVATE_KEY` associato alla chiave SSH dedicata. **Non è stata verificata né visualizzata la chiave privata**; è corretto non trasmetterla nella chat. Da screenshot precedenti: account `superbot-f0` e fixed command installati su VPS, successiva conferma utente di installazione della chiave pubblica.

**Verifica GitHub:** PR #30 `https://github.com/alexiptv82/SuperBot-Trading/pull/30` (ramo `work/f0-restricted-remote-diagnostics-20261103`) aggiornata da DRAFT a `ready for review`. PR ancora aperta, **NON mergiata**, GitHub indica mergeable. 8 test di unità e controlli bash PASS al run #41576404958.

**Non eseguito:** nessun merge, workflow SSH remoto, connessione, accesso a database, modifica VPS, reset dei portafogli, avvio bot, import storico o deploy V3. I contenuti GitHub Actions Secrets non sono leggibili dal connettore, pertanto presenza e correttezza del secret sono solo conferma dell'utente.

**Gate successivo:** richiedere autorizzazione esplicita per merge della **sola PR #30**, senza PR #29. Solo dopo il merge sul ramo predefinito, eseguire il workflow `SuperBot F0 - restricted VPS status` in modalità manuale e leggere i log. Verificare forced-command, assenza shell privilegiata, ed eventuali errori di autenticazione prima di farlo operare regolarmente. L'account diagnostico è solo per metadati e non per backup o modifiche operative. Backup off-host Brain ancora NON certificato.
