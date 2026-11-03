# Checkpoint SuperBot V3 — F3-A/B (2026-11-03, Europe/Zurich)

## Fonti e continuita
- Repo: https://github.com/alexiptv82/SuperBot-Trading
- PR F3 draft: https://github.com/alexiptv82/SuperBot-Trading/pull/35
- Branch F3: `work/v3-brain-f3-offline-20261103`
- Head F3: `627045e4111b4f67ced5b48a26a0791d0e2437c0`
- F2 base PR #33 (immutata): `ec999f896addd7d90be6d85075ad4d7e09f8b667`
- Library: `/SuperBot-Ripresa/F3A-F3B-OFFLINE-SOURCES-20261103.json` (bundle sorgenti aggiornato e salvato; SHA256 locale `b7e5e49823e9ceab9a6312a70863c2ffe4bd8dcff309a2d079fc81bcf55e5475`).
- Archivio originale F2 R1.9 usato nel replay locale: `v3-brain-f2-r1.9-20261103.tar.gz` (sha archiviato in PR #33).

## Implementato e verificato
- F3-A `backend/v3/brain_f3/authorization.py`: verificatore offline di mandate di rischio firmate Ed25519 usando soltanto **chiavi pubbliche** autorizzate e iniettate fuori dai prompt; scope Brain/run, hash completo dei sette campi RiskPolicy e hash F2, TTL <=24h, identita operatore, revoche/validita firma, fail-closed. Nessuna chiave privata creata o inserita nel runtime.
- F3-B `backend/v3/brain_f3/providers.py`: adapter schema DeepSeek (analyst) e Claude (reviewer) collegabili alle interfacce di F2, trasporto iniettato, default disabled, budget callback esplicita, no raw provider text o segreti nei risultati, errori 402/429/malformed a eccezioni sanificate. Non esiste ancora un client HTTP reale.
- Test e documenti separati; PR #35 diff di 7 file, **F1/F2 invariati**, niente dipendenze runtime sulle funzioni legacy.
- Replay locale Python 3.13 su codice originale R1.9 estratto dall'archivio Library + F3: **124/124 PASS**, F3 standalone 37 PASS.
- GitHub CI https://github.com/alexiptv82/SuperBot-Trading/actions/runs/41672572888 **SUCCESS**:
  - Python 3.10 job `126044541476` **237 PASSED** (log letto).
  - Python 3.11 job `126044542043` **237 PASSED** (log letto).
- Nessun merge, deploy, restart, login VPS, reset wallet, scambio reale, API pagata, nuovo ordine o migrazione DB.

## Limiti e PROSSIMI GATE
1. La firma sintetica dei test NON prova chi sia il vero operatore. Servono gestione credenziali privata extra-processo, provisioning e rotazione delle chiavi pubbliche, identita verificata, revoche persistenti e tempo affidabile; solo allora il trust anchor puo essere reale.
2. Budget gate oggi e una callback, non un ledger permanente. Servono controllo costi, credito esaurito 402, timeouts, riconciliazione e dedup prima di implementare i transport HTTP reali DeepSeek/Claude. Nessuna chiamata AI avviata da F3.
3. Nessun executor PAPER o revisione posizioni reali. Non promuovere Brain al runtime fino a risk checks integrati, persistenza, backup e verifica indipendente. Classici Falco/Toro e protezione 450 USDT non toccati.
4. PR #35 RESTA DRAFT; rilascio/merge solo con approvazione esplicita utente.

## Ripresa dopo errore chat
Se la conversazione ChatGPT si blocca, leggere prima PR #35 e questo checkpoint, quindi PR #33 e #29. Non duplicare F3-A/B gia testate. Ripartire dalla review di sicurezza/identita operatore e dai gate trasporto/costi AI. Non inferire che siano operative le API o il trading.
