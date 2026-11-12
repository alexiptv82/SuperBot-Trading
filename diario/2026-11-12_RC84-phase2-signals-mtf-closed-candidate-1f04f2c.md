# Checkpoint 12/11/2026, 17:46 Europe/Rome — RC84 fase 2: segnali MTF su barre chiuse, candidato isolato 1f04f2c

## Novità verificata

Sul ramo isolato `work/rc84-signals-mtf-closed-20261112`, nato direttamente dalla sorgente RC84 distribuita `ab7e0b7d991b8f4bd714fccfec23b09a936e6717`, è stato pubblicato il commit firmato:

[`1f04f2ca3198f00b8ade03a597a8f8b69616c862`](https://github.com/alexiptv82/SuperBot-Trading/commit/1f04f2ca3198f00b8ade03a597a8f8b69616c862) — `feat(signals): RC84 fase 2 candidata ... [skip ci]`.

Il commit è un candidato di revisione: **non è una release**, non ha PR associata e non va rilasciato senza audit. Nessuna GitHub Action è stata avviata.

## Modifiche per file

| File | Stato verificato |
|---|---|
| `backend/desk/signals.py` | Indicatori solo su candele chiuse; EMA50/EMA200 reali su barre 4h/1d chiuse native o ricavate soltanto con almeno 200 barre; dati insufficienti/vecchi/incoerenti → `UNKNOWN`; eliminato bug 1d 30–49 barre; trend 1d solo contesto con `DAILY_TREND_POINTS=0`; `trend_state` consultivo. |
| `backend/desk/cli.py` | Fetch/cache di barre native `4H` e `1Dutc`; nessuna nuova apertura quando la tendenza 4h non è verificabile. Uscite, stop, TP e DCA restano invariati. Divergenze prompt/motore registrate in ombra, senza bloccare. |
| `backend/desk/brain.py` | Stato trend aggiunto al prompt come contesto consultivo; `UNKNOWN` esplicitato. |
| `backend/desk/learning.py` | `trend4h_state`, `trend1d_state` e `trend_state` aggiunti alle feature persistite. |
| `backend/tests/test_desk_rc84_phase2.py` | 23 prove nuove. |
| `backend/tests/test_desk.py`, `test_long_s25.py` | Pin/casi adeguati con motivazione. |
| `deploy/scripts/replay_signals_rc84.py` | Replay appaiato: 7 regimi × 6 semi, motore PAPER reale e candela in formazione emulata. |
| `docs/v3/RC84-FASE2-MOTORE-SEGNALI.md` | Disegno, limiti e istruzioni della fase 2. |

Sono invariati: `engine.py`, gestione delle uscite, valori di rischio, S25 e politica Falco/Toro. La roadmap Falco SHORT-only/Toro LONG+SHORT **non è implementata da questo commit**.

## Test e confronto baseline

Fonte conversazione recente e commit:

- test nuovi fase 2: **23/23 PASS**;
- suite sulla baseline `ab7e0b7`: **6.952 PASS, 26 FAIL, 9 SKIP, 3 XFAIL**;
- suite sul candidato `1f04f2c`: **6.975 PASS, 26 FAIL, 9 SKIP, 3 XFAIL**;
- differenza: **+23 PASS**, nessun nuovo fallimento;
- i 26 fallimenti erano già presenti nella baseline, quindi non sono regressioni introdotte dal candidato.

Questi sono test locali/offline. Non provano un rollout VPS, trading reale, chiamate AI reali né comportamento live sotto carico.

## Effetto funzionale desiderato vs implementato

| Area | Desiderato | Nel candidato |
|---|---|---|
| Candele | solo chiuse | sì |
| EMA200 4h/1d | almeno 200 barre reali | sì |
| Dati insufficienti | fail-closed/UNKNOWN | sì, blocca nuove aperture sul simbolo |
| Trend 1d | contesto, non punti aggiuntivi senza nuova taratura | sì |
| Coerenza prompt/motore | applicare R:R≥2, soglie/TP Toro, non alzare proposta prudente | **solo shadow logging**, non applicato |
| Falco SHORT-only | esperimento reversibile | **non applicato** |
| Toro nuova strategia LONG | continuazione/inversione validata | **non applicata** |
| Uscite/posizioni | preservare gestione esistente | invariata |

Il nuovo gate “trend 4h verificabile” è più restrittivo delle regole RC84 distribuite. Richiede revisione per assicurare che non trasformi il Risk Manager in un blocco eccessivo rispetto alla preferenza utente “filtrare/ridurre, non azzerare”, pur essendo coerente con la sicurezza sui dati insufficienti.

## Relazione con audit e PR #91

- L'audit quantitativo precedente resta provvisorio finché [PR Draft #91](https://github.com/alexiptv82/SuperBot-Trading/pull/91), HEAD `500563a96db0e771f74a580b7278765eae0eaa92`, non viene testata ed eseguita sui wallet RC84 V3.
- PR #91 rimane separata: tre test nuovi ancora non risultano eseguiti.
- Il ramo fase 2 non ha PR e non modifica l'analizzatore quantitativo.
- Prima di valutare Falco SHORT-only/Toro duale servono sia rapporto V3 certificato sia replay/revisione del candidato segnali.

## Stato PAPER consolidato invariato

| Portafoglio | Ultimo stato verificato | Roadmap |
|---|---|---|
| **Falco** | RC84 sotto pausa, heartbeat `draining`; conteggio corrente non noto | SHORT-only reversibile proposto, non applicato |
| **Toro** | RC84 sotto pausa, heartbeat `draining`; conteggio corrente non noto | LONG+SHORT proposto; candidato segnali non installato |
| **Brain** | runner `paused`, exit `healthy`; nessun ciclo completo post-RC84 provato | indipendente, invariato |

Cutover già applicato: PR #90 `0a2fa7e14ff535a20823dbe9a5d7d96c76abd75b`, sorgente installata `ab7e0b7d991b8f4bd714fccfec23b09a936e6717`; PR #85–#91 Draft/non mergiate; tre pause conservate; resume non autorizzato; relay Telegram post-cutover non verificato.

Backup esterno `work/extbackup-bot-stopped-20261109`: preparato, non installato. Copia cifrata age sul PC: `ESITO: VERIFICA OK` e chiave pubblica coincidente; non certifica backup VPS o restore off-host. PR #80 resta riferimento storico RC84. PAPER, EventJournal, learning, wallet, snapshot e rollback devono essere preservati.

## Eseguito / preparato / rilasciato / non approvato

- **Eseguito:** implementazione e test locali su ramo isolato; commit firmato pubblicato.
- **Preparato:** correzioni MTF/candele chiuse, gate UNKNOWN, shadow logging e replay.
- **Rilasciato:** nulla.
- **Non approvato/non eseguito:** PR/merge, deploy, Action, modifica VPS, installazione, resume/restart/reset, ordini, LIVE, API a pagamento, Falco SHORT-only, nuova strategia Toro o variazioni rischio.

## Blocker e prossimi passi

1. Revisione indipendente del diff `1f04f2c`, specialmente gate 4h, cache/staleness e regressioni su uscite/DCA.
2. Eseguire e documentare il replay 7×6; non è disponibile un risultato quantitativo del replay in questa esecuzione.
3. Capire e classificare i 26 fallimenti preesistenti senza attribuirli al candidato.
4. Completare PR #91 e rigenerare l'audit sui wallet V3.
5. Solo dopo, decidere separatamente:
   - promozione della fase 2;
   - patch Falco SHORT-only;
   - strategia LONG di Toro.
6. Qualunque deploy/resume richiede approvazione esplicita, backup verificato e mantenimento delle pause fino al gate finale.

**Limite di accesso:** consultati GitHub, Library e soltanto i messaggi recenti effettivamente recuperabili. Nessuna trascrizione integrale di chat eliminate e nessuna verifica live della VPS successiva ai riscontri già documentati.
