# Checkpoint 12/11/2026, 21:50 Europe/Rome — RC84 Fase 3 Falco SHORT_ONLY preparata in PR Draft #92; test non eseguiti, nessun rilascio

## Novità verificata

Dopo il congelamento del candidato Fase 2 `dc98413ee555c7f0aefeeca8a5367b41ba370c92`, è stata aperta la [PR Draft #92](https://github.com/alexiptv82/SuperBot-Trading/pull/92):

- branch: `work/rc84-phase3-falco-short-only-20261112`;
- base: `work/rc84-signals-mtf-closed-20261112` a `dc98413ee555c7f0aefeeca8a5367b41ba370c92`;
- HEAD: [`fefa7edc8a4a8e8571d0f9f6ff339d30df87880c`](https://github.com/alexiptv82/SuperBot-Trading/commit/fefa7edc8a4a8e8571d0f9f6ff339d30df87880c);
- stato GitHub: aperta, Draft, non mergiata; 3 commit, 3 file, +263/−19;
- creata il 12/11/2026 alle 21:36 Europe/Rome.

I tre commit sono:

1. [`3ffae1f4fa5a50796b7a374b2f2df20d463ce432`](https://github.com/alexiptv82/SuperBot-Trading/commit/3ffae1f4fa5a50796b7a374b2f2df20d463ce432) — gate PAPER reversibile Falco SHORT_ONLY e protezione esposizione LONG residua;
2. [`1a15e55345ccbbc9d7562a8352c97f57797aaf4c`](https://github.com/alexiptv82/SuperBot-Trading/commit/1a15e55345ccbbc9d7562a8352c97f57797aaf4c) — test di regressione isolati;
3. [`fefa7edc8a4a8e8571d0f9f6ff339d30df87880c`](https://github.com/alexiptv82/SuperBot-Trading/commit/fefa7edc8a4a8e8571d0f9f6ff339d30df87880c) — documento, reversibilità e gate di rilascio.

Tutti sono `[skip ci]`. Nessuna GitHub Actions è stata richiesta.

## Revisione indipendente recuperabile

La conversazione recente accessibile riporta una revisione Grok del candidato `dc98413...` con esito **PASS CON RISERVE**. La revisione dichiara verifica diretta del commit, del documento `docs/v3/RC84-FASE2-MOTORE-SEGNALI.md`, del diff di `backend/desk/cli.py` e del percorso decisionale; non dichiara esecuzione di suite, merge o deploy. Il testo integrale della chat non è recuperabile dal servizio di contesto: non vengono attribuiti dettagli ulteriori non verificati.

## Fase 3 preparata: comportamento desiderato vs implementato nel ramo

| Area | Stato verificato nella PR Draft |
|---|---|
| Falco PAPER | `DESK_HAWK_ENTRY_MODE=SHORT_ONLY` nega nuove LONG e LONG split da Claude/Rules; SHORT scalp resta possibile secondo RC84 |
| Reversibilità | default `BOTH`; valore sconosciuto fallisce verso SHORT_ONLY per non abilitare LONG accidentalmente |
| LONG residui | stop/TP/uscite restano; seconda gamba split LONG annullata prima di `on_bar`; DCA LONG bloccato; nessuna chiusura forzata |
| Learning/visibilità | LONG rifiutati registrati come `candidate/falco_short_only` con feature e heartbeat, non come trade/outcome |
| Toro | Claude medio LONG/SHORT invariato; Rules Toro rifiutato come in RC84 |
| Brain | codice, servizi, AI, NO_TRADE e mandato invariati |
| LIVE | invariato; gate limitato al percorso PAPER Falco |
| Rischio | equity floor 450, capitale, leva, SL/TP, funding e limiti invariati; policy TP/R:R/guardrail ancora shadow |

S25: nuove aperture su Falco erano già negate dalla RC84; Toro S25 resta disabilitato di default. Prima di una futura ripartenza va verificato che `DESK_S25_TORO_ENTRY_APPROVED` non sia attivo.

## Test e limiti

La PR aggiunge `backend/tests/test_desk_rc84_phase3_short_only.py` con 9 funzioni più casi parametrizzati per:

- rifiuto LONG/long split da Rules e Claude;
- SHORT valido e ritorno reversibile a BOTH;
- refusi fail-closed;
- Toro invariato;
- evento candidate senza apertura;
- annullamento split LONG residuo;
- blocco DCA LONG residuo senza chiusura forzata.

**I test sono scritti ma non eseguiti.** Non esistono risultati pytest, replay Fase 3 o regressione completa da registrare. La PR non è pronta per merge. Prima di qualunque proposta di rilascio servono Python 3.11 locale, suite mirate RC82/RC84/Fasi 2–3, replay, confronto con base e revisione indipendente.

Restano inoltre aperti: calendario XAU/XAG, verifica read-only Bitget/filtri 4H, policy TP/R:R e guardrail `POLICY_SHADOW`, collaudo Brain separato e correlazione tra bot da misurare.

## Stato operativo, backup e chiavi

Ultimo stato operativo documentato invariato e non riverificato live in questa esecuzione: Falco/Toro `draining`, Brain `paused`, Brain exit `healthy`, tre pause e resume non autorizzato. La sorgente installata documentata resta `ab7e0b7d991b8f4bd714fccfec23b09a936e6717`.

Backup esterno `work/extbackup-bot-stopped-20261109`: preparato, non installato. Copia cifrata age sul PC: PowerShell `ESITO: VERIFICA OK` e chiave pubblica coincidente; non certifica backup o restore VPS. RC84 PR #80 resta riferimento storico. Nessun segreto letto o pubblicato.

## Eseguito / preparato / rilasciato / non approvato

- **Eseguito:** creazione su GitHub del ramo e della PR Draft #92 con codice, test non eseguiti e documentazione.
- **Preparato:** esperimento PAPER Falco SHORT_ONLY reversibile.
- **Rilasciato/installato:** nulla.
- **Non approvato/non eseguito:** esecuzione test Fase 3, merge, deploy, Actions, modifica systemd/VPS/pause, restart/resume, reset, wallet, ordini, LIVE o API a pagamento.

## Prossimo passo e ripresa

Riprendere dalla PR Draft #92 all'HEAD `fefa7edc8a4a8e8571d0f9f6ff339d30df87880c`. Eseguire localmente con Python 3.11 i test Fase 3 e le regressioni concordate; poi audit indipendente e replay. Non aggiungere l'opt-in Falco alle unità, non rimuovere pause e non effettuare unpause finché i gate non sono verdi e non esiste approvazione esplicita. Preservare PAPER, storici, learning ed EventJournal.

