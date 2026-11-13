# Checkpoint verificabile — PR #94: PASS tecnico, NO-GO strategico per Twin PAPER

**Data:** 13/11/2026, 10:47 Europe/Rome  
**Ambito:** sola documentazione. Nessun merge, deploy, GitHub Actions, VPS, reboot, reset, unpause, ordine o API a pagamento. Trading esclusivamente PAPER. Storici ed EventJournal da preservare.

## Sintesi

La [PR Draft #94](https://github.com/alexiptv82/SuperBot-Trading/pull/94) è avanzata dal precedente HEAD `4025db383fb92ee5e1656c55144df4833a77800d` a [`4987912775f72f9b2bf0519a41fe9216fc6b45aa`](https://github.com/alexiptv82/SuperBot-Trading/commit/4987912775f72f9b2bf0519a41fe9216fc6b45aa).

Il nuovo commit, attribuito a Claude Opus 5.5, dichiara:

- correttezza tecnica del Twin **PASS**;
- Falco invariato rispetto alla base `f8332c92cc2bc4edee3ea7363f71f15a0a37a816` nei replay confrontati;
- risultato strategico reale **negativo** per Toro LONG_ONLY e anche per Falco SHORT_ONLY rules-only;
- conclusione esplicita: il risultato **non giustifica un collaudo PAPER** del Toro gemello LONG; lasciare l'interruttore OFF.

Questo è coerente con la decisione utente già registrata: si trattava soltanto di un test per capire la situazione, senza decisione finale né autorizzazione a integrare o rilasciare.

## PR, ramo e stato verificati

- PR #94 aperta, Draft, non mergiata;
- branch `work/classics-twin-short-long-20261113`;
- base `f8332c92cc2bc4edee3ea7363f71f15a0a37a816`;
- HEAD `4987912775f72f9b2bf0519a41fe9216fc6b45aa`;
- 7 commit, 8 file complessivi, +1.200/−6;
- commit nuovo: 6 file, con correzione `cli.py`, 13 prove, due script replay/confronto, documento e JSON risultati;
- `signals.py`, `brain.py`, `engine.py` dichiarati invariati;
- commit marcato `[skip ci]`: nessuna GitHub Actions.

**Disallineamento documentale:** il testo principale della PR continua a riportare “TEST SCRITTI, NON ESEGUITI”, mentre il commit e il documento aggiunto descrivono il collaudo eseguito. Prima di qualsiasi valutazione futura, aggiornare la descrizione PR o trattare commit/documento come fonte più recente, senza nascondere la discrepanza.

## Configurazione candidata — desiderata contro implementata

### Desiderata dall'utente per il solo test

- Falco e Toro gemelli per capitale, slot, rischio e regole;
- Falco specializzato SHORT, Toro specializzato LONG;
- nessuna decisione finale: solo valutazione comparativa.

### Preparata nel branch, non attiva

- Falco SHORT_ONLY tramite modalità opzionale già presente in PR #92;
- Toro Twin `DESK_BULL_TWIN_MODE=LONG_ONLY`, OFF per default e solo PAPER;
- capitale 1.000 USDT, 10 slot, massimo 100 USDT/posizione, margine aggregato 1.000;
- kill 450, daily stop 12%, guardrail 50/60 USDT e 10×/15× come Falco;
- stessi segnali/rules classici 1h/4h, senza importare il LONG Mirror 15m bocciato in PR #93;
- nessuna conversione di SHORT respinti in LONG; `NO_TRADE` valido;
- SHORT Toro preesistenti ancora chiudibili; DCA e seconde gambe SHORT bloccate;
- `BLOCK_NEW` su configurazione invalida; LIVE forza Twin OFF;
- Toro legacy con OFF resta 3×350 medio/Claude.

### Correzione del nuovo commit

`policy_shadow_violations` applicava al Twin il vecchio contratto del prompt Toro (TP ≥5%, confidenza 65/75). È stato limitato alla modalità OFF, lasciando al Twin il contratto Falco. È dichiarato un cambiamento di solo audit/log, senza effetto sulle decisioni.

## Test e replay — fonte e limiti

Fonte: commit `4987912…` e `docs/v3/CLASSICS-TWIN-FALCO-SHORT-TORO-LONG.md`; risultati **non rieseguiti da questo checkpoint**.

### Correttezza tecnica

- 13 nuove prove nel ciclo reale per uscite SHORT residue, DCA, seconde gambe, NO_TRADE, 4H UNKNOWN, S25, BLOCK_NEW, ritorno OFF, sizing e guardrail;
- test a mutazione dichiarati per dimostrare che i controlli falliscono rimuovendo blocchi chiave;
- replay del vero `cli.run_cycle` su candele Bitget USDT-FUTURES BTC/ETH/SOL, 15m e 4H, 22/05/2025–13/11/2026, circa 26.000 cicli a 30 minuti;
- confronto Falco base/candidato dichiarato identico operazione per operazione, salvo `logged_ms`;
- Toro OFF e variabile assente dichiarati identici alla base;
- Toro LONG_ONLY: zero nuove SHORT nei replay;
- percorso Claude è pseudo-casuale deterministico, **non Claude reale**.

### Risultati strategici rules-only

| Replay, capitale iniziale 1.000 USDT | Operazioni | PnL netto | Profit factor | Lordo prima dei costi | Commissioni | Kill 450 |
|---|---:|---:|---:|---:|---:|---|
| Toro Twin LONG, dal 22/05/2025 | 229 | −556,9 | 0,83 | +25,4 | 543,5 | 10/09/2025 |
| Toro Twin LONG, periodo B dal 15/02/2026 | 112 | −551,9 | 0,61 | −280,5 | 254,1 | 15/07/2026 |
| Falco SHORT_ONLY, dal 22/05/2025 | 351 | −576,6 | 0,91 | +261,2 | 837,8 | 19/02/2026 |
| Falco SHORT_ONLY, periodo B | 98 | −602,4 | 0,63 | −378,3 | 224,1 | 02/04/2026 |

Nel percorso pseudo-Claude Toro sono riportate 2 liquidazioni, SOL 25× ed ETH 26×. La kill 450 ha bloccato nuove aperture ma non ha impedito perdite o liquidazioni sulle esposizioni già aperte.

### Limiti

- soltanto tre mercati rispetto ai circa 30 del runner;
- nessun Claude reale;
- contesto, notizie e funding esterni disattivati;
- cicli fissi a 30 minuti;
- i risultati rules-only non dimostrano che la produzione SHORT perda, ma dimostrano che queste regole isolate non bastano su questo campione;
- costi e leva cancellano anche il piccolo lordo positivo del primo periodo.

## Decisione consolidata

- **PR #94: PASS tecnico dichiarato, NO-GO strategico per un collaudo PAPER Twin.**
- Lasciare `DESK_BULL_TWIN_MODE` non impostato/OFF.
- Nessun merge, deploy, reset, unpause o modifica VPS.
- PR #93 resta FAIL e non va integrata.
- PR #92 resta Draft/non attivata.
- Configurazione finale Toro ancora non decisa.
- Brain indipendente e invariato.

## Tre portafogli e stato operativo documentato

- **Falco:** SHORT_ONLY preparato, non attivato; il replay rules-only negativo non equivale a verdetto sulla produzione completa con AI.
- **Toro:** Twin LONG tecnicamente preparato ma strategicamente non giustificato; legacy OFF preservato.
- **Brain:** invariato; ultimo stato documentato PAUSED, `approved=false`.
- Capitali di riferimento: 1.000 / 1.000 / 2.000 USDT, solo PAPER.

Nessun controllo live VPS in questa esecuzione. Ultimo stato documentato: RC84 da sorgente `ab7e0b7…`, Falco/Toro in draining, Brain PAUSED, exit healthy; non assumere che sia ancora corrente senza verifica reale.

## Backup e chiavi

- backup esterno `work/extbackup-bot-stopped-20261109`: preparato, non installato;
- copia cifrata age sul PC: PowerShell `ESITO: VERIFICA OK`, chiave pubblica coincidente;
- la prova riguarda la copia locale controllata e non certifica backup/restore VPS;
- RC84 PR #80 resta riferimento storico;
- nessun segreto o dato di accesso letto o pubblicato.

## Eseguito / preparato / rilasciato

- **Eseguito:** collaudo e replay dichiarati nel commit `4987912…`; questo checkpoint documentale.
- **Preparato:** Twin OFF/PAPER, tecnicamente verificato nel branch.
- **Rilasciato:** nulla.
- **Non approvato:** test PAPER operativo, configurazione finale Toro, merge/deploy/unpause, chiusure forzate o modifica della soglia kill.

## Blocker e prossimo passo

1. Non avviare il Twin PAPER sulla base di questi risultati.
2. Allineare la descrizione della PR #94 al nuovo commit prima di usarla come handoff.
3. Richiedere audit indipendente dei test/replay e della parità Falco.
4. Rivedere economics di commissioni, frequenza e leva prima di formulare una nuova ipotesi.
5. Definire protezione aggregata e rischio liquidazioni: kill 450 non è floor assoluto.
6. Qualunque nuova ipotesi deve avere criteri pre-registrati e dati fuori campione; nessuna autorizzazione automatica.

## Limite conversazioni

Sono stati usati solo i messaggi recenti effettivamente accessibili. Non si presume accesso a chat eliminate, trascrizioni integrali o stato live VPS.
