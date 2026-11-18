# Checkpoint 18/11/2026, 17:50 Europe/Rome — FIX UNIVERSO COLLAUDATO; REGRESSIONE SMOKE CORRETTA; VPS INVARIATA

**Tipo:** delta append-only rispetto al checkpoint delle 16:51. Solo documentazione; nessun merge, deploy, Action, modifica VPS, T0, ordine o API a pagamento in questa esecuzione.

## Novità verificate

1. **PR #110 collaudata in laboratorio isolato.** Il commento Claude sulla PR registra sul precedente HEAD `9b417e7e24c3a59aa003937cc2bb47685ace3863`:
   - 39/39 PASS sui tre file richiesti (`test_trial_setup.py`, `test_universe.py`, `test_arena_runner.py`);
   - stessi 27 simboli in ordine diverso accettati, con config e snapshot invariati;
   - duplicati, simbolo sostituito, hash falsificato, snapshot stale/mancante o schema errato ancora rifiutati.
2. **Regressione smoke trovata e corretta.** Il nuovo gate richiedeva `symbols_sha256`, mentre lo snapshot sintetico di `smoke.py` non lo generava. Il commit [`6a88857ac2ff117bd7711958c63604700f113cb0`](https://github.com/alexiptv82/SuperBot-Trading/commit/6a88857ac2ff117bd7711958c63604700f113cb0) aggiunge lo stesso SHA-256 di `",".join(symbols)`; il commit GitHub dichiara 202 test Arena PASS, 0 falliti e `[skip ci]`.
3. **Suite completa riportata PASS.** Il commento PR #110 delle 17:19 Europe/Rome riporta 202/202 PASS dopo la correzione. Fonte: esecuzione Claude Code riportata nel commento e nel messaggio commit; non è una GitHub Action e non è stata rieseguita indipendentemente da questo checkpoint.
4. **Nuovo HEAD PR #110.** La PR resta aperta e draft a `6a88857ac2ff117bd7711958c63604700f113cb0`. Il confronto operativo documentato indica soltanto tre file cambiati rispetto allo stage precedente `3dd6aa588339c6136d52e9ff027c91e5e3f80377`: `trial_setup.py`, `smoke.py`, `test_trial_setup.py`; runner ed exit worker non risultano modificati.
5. **Piano operativo proposto, non eseguito.** Poiché lo script `--update-stage` rifiuta con exit worker attivi e le uscite Arena risultavano sane, è stata proposta un'attivazione tramite checkout isolato pinnato a `6a88857a`, lasciando runtime/stage a `3dd6aa58`. Questa è una proposta preparatoria: nessun checkout VPS, installazione, attivazione o T0 è attestato.

## Stato consolidato per la ripresa

- **Arena PAPER:** DeepSeek/Qwen/MiniMax, tre portafogli separati, uscite autonome, durata desiderata 72h e massimo 18 USD. Run ancora all'ultimo stato provato `PREPARED_PAUSED_NO_T0`, zero posizioni e runner decisionali fermi.
- **Falco/Toro/Brain:** Falco e Toro restano spenti/ritirati ma storici, SHORT Falco ed EventJournal vanno preservati. Brain storico continua separato e fuori classifica; non è stato modificato.
- **Desiderato vs implementato:** fix order-insensitive e regressione smoke ora collaudati nel PR; non sono installati sullo stage/VPS. Uscite e runtime VPS restano sull'ultimo SHA attestato `3dd6aa58`.
- **Budget/chiavi:** Qwen/MiniMax limite 6 USD verificato via introspezione non pagata; DeepSeek Arena configurato separatamente 0600 ma senza validazione live/hard-cap provider. Nessuna inferenza pagata in questo checkpoint.
- **Backup:** age PC `ESITO: VERIFICA OK` e chiave pubblica coincidente non certificano il backup VPS. `work/extbackup-bot-stopped-20261109` resta preparato e non installato. Storici e backup esistenti non vanno rimossi.
- **Riferimenti invariati:** RC84 PR #80 resta all'ultimo dato verificato `0e29a73a36f668643da4088178bacb8616a45ac0`.
- **Conversazioni:** accessibili soltanto estratti recenti e riscontri GitHub; nessuna trascrizione integrale di chat eliminate.

## Fatto / preparato / rilasciato

- **Fatto:** test mirati 39/39 e suite Arena 202/202 riportati PASS; regressione smoke corretta; PR #110 avanzata a `6a88857a`.
- **Preparato:** possibile checkout isolato dell'activator con pin distinto da runtime/stage, più preflight finale e snapshot fresco.
- **Rilasciato/attivo:** nessun nuovo codice sul VPS, nessun T0, runner decisionale, inferenza pagata, merge, deploy, Action o LIVE.
- **Non approvato:** installazione/checkout operativo VPS, assegnazione T0, avvio gara, sostituzione ripetuta delle run, stop delle uscite, modifica Brain o web produzione.

## Blocker e prossimo passo

1. Prima di ogni operazione VPS verificare stage/runtime SHA, tre exit healthy, runner inattivi, snapshot ancora fresco entro 6 ore e coerente, flag inferenza Qwen/MiniMax e budget; non pubblicare segreti.
2. Valutare il checkout activator isolato solo con autorizzazione separata e rollback documentato; non usare `--update-stage`, non fermare le uscite e non ripetere `--replace-prepared`/smoke.
3. T0 comune e avvio dei tre runner PAPER richiedono autorizzazione esplicita successiva. L'esito test non equivale ad autorizzazione o stato live VPS.

## Limiti

Questo checkpoint verifica repository, commenti e risultati dichiarati da Claude Code; non dispone di SSH live e non certifica la continuità dello stato VPS. Nessun accesso remoto è stato installato.
