# Checkpoint 13/11/2026, 06:50 Europe/Rome — PR #93 Toro LONG mirror 15m collaudata offline, NON pronta

## Novità verificate

### 1. Decisione utente successiva al checkpoint delle 05:48

Conversazione recente effettivamente accessibile, 13/11/2026 ore 05:52–06:00 Europe/Rome:

- Falco deve lavorare soltanto SHORT; la strategia SHORT classica resta congelata e non va modificata;
- Toro viene ripensato come LONG_ONLY, separato da Falco;
- come base di studio, l'utente propone di leggere la logica SHORT e applicarne una versione speculare/inversa ai LONG;
- “ok procedi” autorizza la preparazione/studio, non un merge, deploy, modifica VPS, unpause o rilascio operativo;
- Brain resta indipendente e invariato.

Questa decisione **sostituisce la roadmap provvisoria delle 05:48** che riportava Toro LONG+SHORT autonomo con 10 slot. I valori numerici finali di Toro restano da approvare separatamente.

### 2. PR Draft #93: studio isolato Toro LONG

È stata aperta la [PR Draft #93](https://github.com/alexiptv82/SuperBot-Trading/pull/93), branch `work/toro-long-mirror-15m-20261113`:

- base esatta: `f8332c92cc2bc4edee3ea7363f71f15a0a37a816` (PR #92 Falco SHORT_ONLY);
- HEAD corrente: [`1de3b7d80afcf8fc1abe6e0290e863b3b09cad39`](https://github.com/alexiptv82/SuperBot-Trading/commit/1de3b7d80afcf8fc1abe6e0290e863b3b09cad39);
- stato: aperta, Draft, non mergiata; 5 commit, 5 file, +780/−0;
- commit `[skip ci]`: nessuna GitHub Actions avviata.

Aggiunge soltanto file nuovi di studio: lettore puro `long_mirror_15m.py`, test, replay sintetico e documento. Non è importato dal runner, non chiama API, non apre/chiude posizioni e non imposta size, leva, SL o TP. I file di motore SHORT congelati `brain.py`, `signals.py`, `cli.py`, `engine.py` risultano identici alla base tramite blob Git e test fingerprint.

Il prototipo usa candele 15m chiuse e trend 4H verificato per produrre solo etichette `LONG_CONTINUATION_CANDIDATE`, `LONG_BOUNCE_CANDIDATE` o `NO_TRADE`. Non è una semplice inversione equivalente allo SHORT: timeframe 15m, finestre, conferme, soglie e categoria BOUNCE sono ipotesi nuove.

### 3. Test e replay — fonte e limiti

Risultati documentati nel commit HEAD e nel corpo/documento della PR, non rieseguiti da questo checkpoint:

- studio + fingerprint: **17/17 PASS** su Python 3.11;
- regressioni pertinenti: **404 PASS**;
- suite completa Python 3.13: **7.080 passed, 1 failed, 9 skipped, 3 xfailed**; il solo fail è lo stesso problema ambiente SQLAlchemy già noto;
- replay sintetico: 3 regimi × 6 semi × 60 giorni, con costi; nessun dato Bitget reale e nessun ordine.

Il replay sintetico **non mostra un vantaggio dimostrato**: in rialzo il continuation medio (+0,063%/trade) non supera il controllo casuale (+0,076%); in ribasso i risultati restano negativi; nel laterale le perdite sono marcate. Prova meccanica, assenza di lookahead e peso dei costi, non redditività.

### 4. Desiderato / preparato / implementato / rilasciato

| Area | Stato |
|---|---|
| Falco | Desiderato SHORT_ONLY PAPER; PR #92 preparata/collaudata, ancora Draft e non rilasciata |
| Strategia SHORT | Congelata; file core invariati nello studio PR #93 |
| Toro | Desiderato LONG_ONLY; prototipo 15m preparato e collaudato offline, non collegato al runner |
| Numeri Toro | PR propone 1.000 USDT, massimo 5 slot × 200 USDT; proposta tecnica da riconfermare, non configurazione attiva |
| Brain | Indipendente, invariato; collaudo dedicato ancora necessario |
| Rilascio | Nessuno: PR #92 e #93 Draft, nessun merge/deploy/opt-in/unpause |
| LIVE | Vietato; solo PAPER |

## Stato operativo, backup e chiavi

Ultimo stato documentato, **non verificato live in questa esecuzione**: sorgente VPS RC84 `ab7e0b7d991b8f4bd714fccfec23b09a936e6717`; Falco/Toro `draining`, Brain `paused`, Brain exit `healthy`; tre pause e resume non autorizzato.

Backup esterno `work/extbackup-bot-stopped-20261109`: preparato, non installato. Copia cifrata age sul PC: PowerShell `ESITO: VERIFICA OK` e chiave pubblica coincidente; questo non certifica backup o restore VPS. RC84 PR #80 resta riferimento storico. Nessun segreto letto o pubblicato.

## Blocker e prossimo passo

1. Backtest comparativo con storico reale 15m, separato per rialzo/ribasso/laterale e con costi, funding, MAE/MFE e drawdown.
2. Progettare un filtro del laterale e riesaminare separatamente CONTINUATION e BOUNCE; nessun edge è provato.
3. Confermare con l'utente i valori finali Toro: il precedente desiderio di 10 slot è superato nella direzione, ma 5 × 200 è ancora proposta tecnica.
4. Risolvere rischio/capienza: 5 × 200 usa tutto il capitale; valutare 5 × 180 o tetto totale 900. Leva deve rispettare stop, liquidazione, equity floor 450 e daily stop.
5. Progettare, in una fase separata, LONG_ONLY PAPER senza bloccare uscite di SHORT preesistenti e senza toccare Falco.
6. Verificare scheduler sulle chiusure 15m, costo API, policy `POLICY_SHADOW`, S25 OFF e calendario XAU/XAG.
7. Revisione indipendente Grok della PR #93 e consenso separato prima di qualunque integrazione al runner; backup/rollback e preflight sugli SHA esatti prima di un eventuale deploy/unpause.

## Ripresa

Riprendere da PR #92 HEAD `f8332c92cc2bc4edee3ea7363f71f15a0a37a816` per Falco SHORT_ONLY e PR #93 HEAD `1de3b7d80afcf8fc1abe6e0290e863b3b09cad39` per lo studio Toro LONG. Considerare la PR #93 un laboratorio offline senza edge dimostrato, non una strategia eseguibile. Preservare PAPER, pause, storici, learning ed EventJournal; nessun merge, deploy, VPS, reset, wallet, ordine o API a pagamento.
