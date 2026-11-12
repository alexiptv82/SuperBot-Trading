# Checkpoint 12/11/2026, 15:48 Europe/Rome — Audit quantitativo provvisorio; PR #91 corregge il layout RC84 ma i test nuovi non sono eseguiti

## Novità verificata

Dopo il checkpoint delle 14:45 sono comparsi:

1. il commit firmato [`7a6589f1dd09b6d59e97fbe0055af9b5caa69c9e`](https://github.com/alexiptv82/SuperBot-Trading/commit/7a6589f1dd09b6d59e97fbe0055af9b5caa69c9e), discendente di `44f30aa...`, che corregge l'analizzatore LONG/SHORT;
2. la [PR Draft #91](https://github.com/alexiptv82/SuperBot-Trading/pull/91), ramo `work/rc84-audit-v3-wallet-layout-20261112`, HEAD `500563a96db0e771f74a580b7278765eae0eaa92`, base `7a6589f1dd09b6d59e97fbe0055af9b5caa69c9e`;
3. un rapporto quantitativo recuperabile dalle conversazioni recenti, con risultati LONG S25 e SHORT Rules, ma con una lacuna di provenienza del dataset chiarita dalla stessa PR #91.

Nessun merge, deploy, Action o modifica ai bot è stato eseguito.

## Correzioni dell'analizzatore nel commit 7a6589f

Il commit corregge i limiti documentati nel checkpoint precedente:

- cutoff RC84: `12/11/2026 12:37 Europe/Rome = 11:37 UTC`;
- report principale per ora di **apertura** e secondario per ora di chiusura;
- identità trade = simbolo + ID + ora apertura, perché gli ID possono ripartire dopo reset;
- archivi dei reset e parziali aggregati;
- collegamento `trade_history` ↔ `learning_log`;
- separazione portafoglio/lato/strategia/orizzonte, funding e netto senza funding;
- diagnostica S25 e contesto d'ingresso.

La fonte GitHub dichiara **13 prove sintetiche con il motore PAPER vero**; la PR #91 le descrive come 13/13 verdi. Sono prove sintetiche del runner, non prova del dataset RC84 né di stato live.

## Numeri recuperati dal rapporto recente: descrittivi e provvisori

| Gruppo | N | Esito | P&L PAPER | Metriche recuperate |
|---|---:|---|---:|---|
| LONG S25 | 6 | 0 vittorie, 6 stop | **−270,21 USDT** | R medio −1,12; R:R pianificato 0,97; MAE 1,08R; MFE 0,29R; durata 5,1h |
| SHORT Rules Scalp | 13 | 12 vittorie | **+581,13 USDT** | win rate 92,3%; PF 32,90; R medio +1,42; R:R 1,75; MAE 0,53R; MFE 1,80R |

Dettaglio recuperato:

- LONG S25: Falco −63,60 USDT; Toro −206,61 USDT; funding LONG totale circa −1,25 USDT (Falco −0,28, Toro −0,97);
- SHORT Rules Scalp: Falco 11 trade, +515,04 USDT, win rate 90,9%, PF 29,28; Toro 2 trade, +66,09 USDT, win rate 100%;
- segnali S25 duplicati fra Falco e Toro su BCH, BNB e RUNE, con aperture quasi simultanee;
- per il contesto accessibile non era disponibile una EMA200 4h reale ricostruita: l'ipotesi “rimbalzo dentro un ribasso” resta plausibile ma non dimostrata per ogni trade.

Questi dati sono descrittivi su campione piccolo e **non autorizzano modifiche di strategia**.

## Lacuna critica di provenienza del dataset

La PR #91 documenta che il comando precedente `--vps /opt/superbot-desk-data` cercava solo `hawk/` e `bull/`, cioè layout legacy. Il cutover PR #90 usa invece i wallet RC84 V3 sotto `/opt/superbot-v3-paper-runs/classic-hawk-paper20261111` e `classic-bull-paper20261111`.

Di conseguenza, i numeri sopra sono reali rispetto al dataset analizzato, ma **non sono ancora certificati come provenienti dai wallet RC84 V3 correnti**. Non vanno presentati come prova definitiva del comportamento della versione distribuita `ab7e0b7...` finché il rapporto non viene rigenerato con layout RC84 esplicito e integrità confermata.

## PR #91: preparato, non collaudato

PR #91 modifica tre file:

- `deploy/scripts/audit_long_short.py`;
- `deploy/scripts/test_audit_long_short.py`;
- `docs/v3/RC84-FASE1-ANALISI-LONG-SHORT-LEGGIMI.md`.

Aggiunge `--layout rc84`, richiede i due wallet V3 e i tre file fondamentali, fallisce se manca un wallet o se la copia non diventa coerente, mantiene `--layout legacy` separato e documenta il comando Termius fail-closed con `pipefail`.

Stato verificato della PR:

- Draft, aperta e non mergiata;
- HEAD `500563a96db0e771f74a580b7278765eae0eaa92`;
- quattro commit documentali/strumentali [skip ci];
- controlli statici dichiarati PASS;
- **tre nuovi test di layout/mancanza file/copia incoerente non ancora eseguiti**;
- nessuna esecuzione del nuovo comando sui wallet RC84 V3 provata.

## Stato consolidato PAPER invariato

| Portafoglio | Ultimo stato verificato | Limiti |
|---|---|---|
| **Falco** | RC84 avviato sotto pausa; heartbeat `draining` | conteggio corrente non noto; relay Telegram post-cutover da verificare |
| **Toro** | RC84 avviato sotto pausa; heartbeat `draining` | conteggio corrente non noto; relay Telegram post-cutover da verificare |
| **Brain** | runner `paused`, exit `healthy` | nessun ciclo completo post-RC84 provato; notifiche non verificate |

Cutover già applicato: PR #90 HEAD `0a2fa7e14ff535a20823dbe9a5d7d96c76abd75b`, sorgente installata `ab7e0b7d991b8f4bd714fccfec23b09a936e6717`; PR #85–#91 restano Draft/non mergiate; tre pause conservate; resume non autorizzato. I conteggi Falco 7/Toro 3 restano dello snapshot precedente.

Backup esterno `work/extbackup-bot-stopped-20261109`: preparato, non installato. Copia cifrata age sul PC: `ESITO: VERIFICA OK` e chiave pubblica coincidente; non certifica backup VPS né restore off-host. PR #80 resta riferimento storico RC84. PAPER, EventJournal, learning, wallet, snapshot e rollback devono essere preservati.

## Eseguito / preparato / rilasciato / non approvato

- **Eseguito e verificato:** pubblicazione commit `7a6589f...`; creazione PR #91; disponibilità del rapporto quantitativo e dei numeri sopra; verifica GitHub della lacuna layout.
- **Preparato:** analizzatore corretto per wallet RC84 V3 e tre test aggiuntivi.
- **Rilasciato operativo:** nulla; nessun codice di trading o servizio modificato da questa attività.
- **Non eseguito/non approvato:** tre nuovi test; audit sui wallet V3 certificati; modifiche E1–E7; merge/deploy/Action; VPS write; resume/restart/reset; ordini/LIVE/API a pagamento.

## Blocker e prossimo passo

1. Eseguire localmente i tre test nuovi della PR #91 e verificare SHA/blob dello script.
2. Solo dopo, eseguire in Termius il comando read-only con `--layout rc84` su copie coerenti; nessuna scrittura ai wallet.
3. Salvare output integrità e confrontarlo con i numeri provvisori: se differisce, prevale il rapporto V3 certificato.
4. Ricostruire il contesto storico reale 4h/1d prima di concludere che ogni S25 fosse un rimbalzo in trend ribassista.
5. Mantenere tre pause e non riprendere i bot senza approvazione separata.
6. Controllare separatamente relay Telegram e primo ciclo Brain, sempre read-only prima del resume.

**Limiti di accesso:** consultati GitHub, Library e soltanto i messaggi recenti effettivamente recuperabili. Nessuna trascrizione integrale di chat eliminate e nessuna verifica live della VPS successiva ai riscontri documentati.
