# Checkpoint SuperBot — candidato web Arena PASS, non pubblicato

**Data:** 18/11/2026, 19:43 Europe/Rome  
**Ambito:** solo documentazione e verifica; trading esclusivamente PAPER.

## Novità verificata

- [PR #112](https://github.com/alexiptv82/SuperBot-Trading/pull/112) è open/draft, HEAD `80a51aa8b5921e8b54c9c103e6a4d8c73c91dacc`, base sullo HEAD di PR #110 `6a88857ac2ff117bd7711958c63604700f113cb0`. È un candidato web-only read-only con ispezione, preparazione, pubblicazione e rollback separati; nessun merge.
- Test dichiarati nel PR: 35 cutover + 10 UI + 3 readout e suite backend combinata 128 PASS; frontend 23 suite/175 PASS. E2E locale: immagine non patchata e mount mancante rifiutati; endpoint Arena 401 senza sessione e 200 con sessione valida; tre portafogli con T0 identico; sole route GET; file sorgente invariati. Sono prove locali/di laboratorio, non la biometria reale Samsung.
- Evidenza VPS da screenshot Termius, riportata nel commento PR #112 delle 19:38: `arena-web-prepare.service` exit 0, route GET-only, 401 senza sessione, 200 con sessione valida, T0 identico e `PASS_CANDIDATE`. Immagine candidata `sha256:8275774557cfeb41738f1cd39025e0b49e1fd769568a30ed3fee49a408f35d0e`, tag `superbot:arena-web-readonly-candidate-20261118`.
- Confine operativo esplicito della stessa prova: `web_untouched=TRUE`, `deploy_executed=NO`, `CANDIDATE_READY_FOR_SEPARATE_PUBLISH`. `--publish` non è stato eseguito; anche la UI statica richiede un rilascio separato dopo il backend. L'app Samsung non è quindi attestata aggiornata.
- Readout read-only puntuale delle 19:38: DeepSeek 1 posizione aperta/2 chiuse; Qwen 0 aperte/1 chiusa; MiniMax 1 aperta/4 chiuse. Equity e PnL non realizzato restano `n.d.` senza quotazioni verificate; non dedurre profitto complessivo.

## Stato consolidato

- Gara Arena PAPER avviata a T0 comune `1795021392344` (18/11/2026 18:03:12.344 Europe/Rome); nuove inferenze/aperture previste fino al 21/11/2026 18:03:12, uscite automatiche ancora operative per posizioni aperte. Non modificare runner, exit, T0, journal o strategie durante il cutover web.
- DeepSeek/Qwen/MiniMax hanno tre portafogli separati; il readout sopra sostituisce solo il conteggio puntuale precedente, non certifica continuità né PnL corrente.
- Falco/Toro restano spenti/ritirati; Brain storico separato e fuori classifica. Storici, SHORT Falco ed EventJournal devono essere preservati.
- PR #110 resta open/draft a `6a88857ac2ff117bd7711958c63604700f113cb0`; PR #112 è solo candidato web. RC84 PR #80 resta all'ultimo dato verificato `0e29a73a36f668643da4088178bacb8616a45ac0`.
- Backup esterno `work/extbackup-bot-stopped-20261109` preparato ma non installato. Verifica PC della copia cifrata age: output PowerShell `ESITO: VERIFICA OK` e chiave pubblica coincidente; non certifica backup o restore sulla VPS. Nessun segreto letto o riportato.

## Fatto / preparato / rilasciato

- **Fatto e verificato da riscontro:** candidato creato e sondato sulla VPS; probe autenticato/read-only PASS; web esistente dichiarato intatto; gara leggibile con T0 comune.
- **Preparato:** immagine web candidata e rollback; PR #112 con script/documentazione/test.
- **Rilasciato:** nessun backend web Arena e nessuna UI statica; nessun deploy, publish, cutover, merge o LIVE.
- **Non approvato/eseguito:** `--publish`, attivazione UI, modifica runner/exit, reset, reboot, ordini, API a pagamento o modifica rischio.

## Problemi e prossimo passo

1. Mantenere invariata la gara PAPER e continuare monitoraggio read-only di runner, exit, journal, budget e provider.
2. Se e solo se autorizzato separatamente, pubblicare prima il backend candidato con rollback pronto, senza riavviare Arena; poi verificare 401/200, GET-only, T0 e journal invariati.
3. Rilasciare la UI statica separatamente e verificare manualmente login/WebAuthn/biometria sull'app Samsung; i test automatici non certificano la biometria reale.
4. Continuare a mostrare equity/PnL non realizzato come `n.d.` finché non esistono quotazioni verificate.

## Limiti delle fonti

Questo checkpoint usa GitHub, commenti PR e screenshot riportati nelle conversazioni recenti accessibili. Non dispone di trascrizioni integrali di chat eliminate né di accesso SSH live indipendente; la prova VPS è puntuale alle 19:38, non una certificazione continua.
