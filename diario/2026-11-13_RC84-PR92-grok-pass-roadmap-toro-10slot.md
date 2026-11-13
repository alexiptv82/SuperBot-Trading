# Checkpoint 13/11/2026, 05:48 Europe/Rome — Grok PASS statico su PR #92; roadmap aggiornata: SHORT congelato, Toro 10 slot autonomo

## Novità verificate

### 1. Audit Grok della PR #92

La [PR Draft #92](https://github.com/alexiptv82/SuperBot-Trading/pull/92), branch `work/rc84-phase3-falco-short-only-20261112`, è stata aggiornata nel testo alle 05:03 Europe/Rome senza nuovi commit:

- base: `dc98413ee555c7f0aefeeca8a5367b41ba370c92`;
- HEAD invariato: [`f8332c92cc2bc4edee3ea7363f71f15a0a37a816`](https://github.com/alexiptv82/SuperBot-Trading/commit/f8332c92cc2bc4edee3ea7363f71f15a0a37a816);
- stato: aperta, Draft, non mergiata; 4 commit, 4 file, +488/−19;
- verdict Grok: **PASS** per la sola modalità Falco SHORT_ONLY.

Fonte: testo corrente della PR. Grok dichiara audit statico del commit esatto e dei test documentati; **non** ha rieseguito pytest/replay, non ha verificato la VPS e non approva policy di rischio, strategia LONG Toro o ciclo AI Brain. Nessun deploy, merge o Action.

I risultati già documentati restano: 24/24 prove Fase 3 PASS, suite Python 3.13 7.063 ok/1 fail residuo noto, moduli SQLAlchemy Python 3.11 49/49 PASS, replay default BOTH identico su 42 percorsi. Questa esecuzione non li ha rilanciati.

### 2. Decisione utente di roadmap

Conversazione recente effettivamente accessibile, 13/11/2026 ore 05:01 Europe/Rome:

- la strategia SHORT dei classici è **congelata** e non deve essere cambiata “neanche una virgola”;
- Falco resta candidato SHORT_ONLY con capacità fino a 10 slot;
- Toro viene proposto con capacità/limiti e budget pari a Falco, quindi **10 slot** anziché 3, mantenendo LONG+SHORT;
- Toro deve restare autonomo: strategie indipendenti e nessuna copia automatica dei trade Falco;
- Brain resta indipendente e invariato; nessun quarto portafoglio.

Configurazione desiderata interpretata per il futuro esperimento PAPER: Falco 1.000 USDT, 10 slot, SHORT_ONLY; Toro 1.000 USDT, 10 slot, LONG+SHORT autonomo. Applicando letteralmente i limiti Falco correnti, il tetto candidato è 100 USDT per operazione e 1.000 USDT complessivi; questi valori devono essere riconfermati insieme alle policy rischio prima dell'implementazione.

Questa è una **decisione di roadmap**, non codice, configurazione systemd, reset o autorizzazione al rilascio. La PR #92 non modifica Toro e non dimostra che la strategia SHORT sia bit-per-bit invariata fuori dal perimetro già testato: il confronto dedicato resta un gate.

## Desiderato / preparato / implementato / rilasciato

| Area | Stato |
|---|---|
| Falco | Desiderato SHORT_ONLY PAPER, 10 slot; candidato e collaudo presenti in PR #92 |
| Strategia SHORT classici | Congelata per decisione utente; nessuna modifica autorizzata |
| Toro | Desiderato 10 slot, stesso budget/capacità Falco, LONG+SHORT autonomo; **non implementato** |
| Brain | Indipendente, invariato; collaudo dedicato ancora necessario |
| Rilascio | Nessuno: PR #92 Draft, nessun merge/deploy/opt-in/unpause |
| LIVE | Vietato; solo PAPER |

## Stato operativo, backup e chiavi

Ultimo stato documentato, non verificato live in questa esecuzione: Falco/Toro `draining`, Brain `paused`, Brain exit `healthy`; tre pause e resume non autorizzato. Sorgente VPS documentata: `ab7e0b7d991b8f4bd714fccfec23b09a936e6717`.

Backup esterno `work/extbackup-bot-stopped-20261109`: preparato, non installato. Copia cifrata age sul PC: PowerShell `ESITO: VERIFICA OK` e chiave pubblica coincidente; questo non certifica backup o restore VPS. RC84 PR #80 resta riferimento storico. Nessun segreto letto o pubblicato.

## Blocker e prossimo passo

1. Congelare formalmente il comportamento SHORT con confronto base/candidato e test di non regressione: nessuna variazione a segnali, sizing, SL/TP, DCA, split o uscite SHORT.
2. Progettare Toro 10 slot su ramo/PR separato, senza toccare PR #92, con LONG e SHORT autonomi e nessuna duplicazione automatica Falco.
3. Confermare i limiti numerici Toro e le policy ancora `POLICY_SHADOW`: TP, R:R minimo, margine/leva ed equity floor 450.
4. Verificare `DESK_S25_TORO_ENTRY_APPROVED` OFF, dati reali 4H e calendario XAU/XAG.
5. Collaudare Brain separatamente, con NO_TRADE valido.
6. Solo dopo: backup/rollback, preflight sugli SHA esatti, eventuali unit ancora in pausa e consenso separato per deploy e unpause.

## Ripresa

Riprendere dalla PR #92 all'HEAD esatto `f8332c92cc2bc4edee3ea7363f71f15a0a37a816`. Considerare chiuso solo il gate di audit statico Grok della modalità Falco SHORT_ONLY. Trattare Toro 10 slot come roadmap non implementata. Preservare PAPER, pause, storici, learning ed EventJournal; nessun merge, deploy, VPS, reset, wallet, ordine o API a pagamento.
