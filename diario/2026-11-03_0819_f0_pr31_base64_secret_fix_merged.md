# SuperBot F0 — PR #31 approvata e mergiata il 2026-11-03

Utente ha risposto `ok✅` alla richiesta esplicita di merge della sola PR #31. Verificati PR #31 head `01d57af47a900796d30ba2d38cbffc4cb1e8b26d` e CI #41583708908 con esito SUCCESS per lo stesso SHA.

Con `mcp__GitHub__merge_pull_request` in modalità `squash`, usando `expected_head_sha`, PR #31 unita su `main`. GitHub conferma `merged:true`, commit `fb38267433235780e5f22a335837139cf5ec4211`. Seconda verifica GitHub: PR #31 closed/merged, PR #29 SuperBot V3 ancora aperta DRAFT e NON mergiata. Il file workflow `.github/workflows/f0-restricted-status.yml` su `main` riconosce `F0B64:`.

Correzione abilita `SUPERBOT_F0_SSH_PRIVATE_KEY` in forma **F0B64:<base64 di una chiave privata OpenSSH>` all'interno del secret GitHub. Il valore è altamente riservato anche se Base64, da trasferire **soltanto** da terminale fidato direttamente al secret Actions GitHub. Non riportarlo in chat, log condivisi, commit o screenshot. Con la nuova coppia chiavi generata sul server il passo successivo è eseguire `printf 'F0B64:'; base64 -w0 /root/superbot-f0-setup/github-f0-ed25519; printf '\\n'`, aggiornare il secret nel browser GitHub e confermare senza mostrare il valore. Il modello potrà poi rilanciare il job fallito `41582026933` tramite GitHub e leggere i log.

Questo merge NON dimostra una connessione VPS riuscita: la precedente esecuzione e il rerun sono falliti su `ssh-keygen` con libcrypto prima dell'handshake. Nessun bot, wallet, registro storico, backup WAL o runtime modificato. La copia Brain locale resta non certificata offhost. Rimuovere con cautela la copia della chiave privata sul VPS dopo collegamento verificato e retention sicura del secret, in procedura separata e approvata.
