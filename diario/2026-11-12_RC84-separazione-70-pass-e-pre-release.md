# 12 novembre 2026 — 08:18 Roma — RC84 separazione classici, 70 test PASS

## Evidenza utente diretta da Termius
Screenshot alle **08:18**: `git pull --ff-only origin work/rc84-fix-classic-divergence-brain-market-20261111` ha aggiornato da `d131fe8` a `ab7e0b7`, test eseguiti in **clone temporaneo sulla VPS Singapore** `/root/rc84-tests-UKXAJfmd/src`, virtualenv locale:
```
PYTHONPATH="$PWD:$PWD/backend" PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
.venv/bin/python -m pytest -q backend/tests/test_long_s25.py
70 passed in 1.70s
```
Il comando verificava HEAD **`ab7e0b7d991b8f4bd714fccfec23b09a936e6717`** e il test è effettivamente arrivato a completamento. Nessun errore.

Test precedenti già confermati: 239 PASS per feed/contratti/runner/S25 e 156 PASS per E2E/exit/integration. Il totale è **465 esecuzioni di test riuscite**, ma alcuni test S25 sono ripetuti e NON sono 465 casi distinti. Le due nuove correzioni (ingressi S25 disattivati di default e policy differenziata Falco/Toro con NO_TRADE Claude rispettato) sono adesso coperte da suite green.

## Stato codice e rilascio
- [PR Draft #85](https://github.com/alexiptv82/SuperBot-Trading/pull/85) head `ab7e0b7d991b8f4bd714fccfec23b09a936e6717`, base `work/rc84-repair-baseline-20261111`, ancora non mergiata e **NON distribuita**.
- Falco: nuove aperture LONG/SHORT solo `scalp` da Claude o regole.
- Toro: nuove aperture LONG/SHORT solo `medio` e solo Claude; fallback automatico può gestire posizioni già aperte ma non introdurre nuova esposizione.
- Claude JSON valido con `decisions: []` = `NO_TRADE` effettivo. I JSON troncati restano errori; i classici non hanno più ingressi duplicati automatizzati dal fallback condiviso.
- Brain: parser metadata Bitget maxLever <=200 con cap operativo <=50x immutato; fetch pagine storiche allineate, heartbeat ultima decisione diagnostica sticky. Disponibilità Bitget SOL/BTC provata con GET pubblici da Termius, E2E DeepSeek reale sulla nuova run ancora non provato.
- Pausa `pause.flag` dei tre PAPER eseguita manualmente dall'utente 05:05. NON assumere che sia ancora presente senza check VPS; in nessun caso rimuoverla in anticipo.
- Codice RC84 originario preparato in `/opt/superbot-v3-rc84-stage` con script `v3-rc84-stage-source-only.sh` **PIN=0e29a73a36f668643da4088178bacb8616a45ac0**; gli altri helper RC84 preparazione/avvio unità sono anch'essi pin a 0e29... e non possono essere riusati direttamente per distribuire  `ab7e0b...` in una run già in funzione. Serve procedura di update della sorgente separata, auditata, non sovrascrivere checkout/strumenti in uso alla cieca.
- La PR #85 è Draft e **non si deve ancora fare merge/deploy/reset/riavvio**. Salvataggio storico verificato e rollback prima di qualunque modifica al servizio.

## Prossimo passo conciso (NON richiede altri pytest)
1. **Un preflight sola lettura sulla VPS**: controllare `pause.flag`, stato dei 4 servizi `superbot-v3-paper-{falco,toro,brain-runner,brain-exit}`, `git -C /opt/superbot-v3-rc84-stage rev-parse HEAD`, conteggio posizioni Falco/Toro e mandati Brain senza stampare token/chiavi, disponibilità e verifica backup.
2. Dopo preflight e consenso al deploy, backup dei dati reali PAPER appoggiato fuori dalle directory attive; preparazione copia versionata della sorgente `ab7e0b7...` con ambiente e unità PAPER, rollback verso `0e29...` se necessario.
3. Aggiornamento/pause-first, verifica una sola autorità di uscita, controllo DeepSeek in run reale e notifiche Telegram, ripresa progressiva, eventuale reset PAPER **solo dopo backup**. NO LIVE; Fable OFF.
4. Evitare consumo ulteriore di GitHub Actions (run di pausa e prova Bitget rimasti `queued` al check). Usare Termius per preflight strettamente necessario.

**Obiettivo:** ripartire presto con i 3 bot PAPER e valutare profittabilità, senza pretendere certificazione impossibile di zero bug.
