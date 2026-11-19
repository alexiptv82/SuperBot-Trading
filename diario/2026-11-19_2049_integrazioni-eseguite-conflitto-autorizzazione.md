# Checkpoint verificabile — 19/11/2026 20:49 Europe/Rome

**Tipo:** delta consolidato rispetto al checkpoint delle 19:44; solo documentazione; PAPER soltanto.

## Esito sintetico

Dopo il checkpoint precedente sono comparsi tre commit documentali sul ramo `diario` e il ramo isolato `integration/brain-unico-20261119` è avanzato da `33a0de73a9903ba1ff76326aa4cb7c688a1e4aca` a `0b86f18b1d96d63c4a443f124c316e1090b8ba41`. Le integrazioni sono quindi **fatti Git verificati**, ma la provenienza dell'autorizzazione dichiarata in `AUTORIZZAZIONI.md` è **in conflitto con le conversazioni recenti effettivamente accessibili**: queste non mostrano un consenso espresso dell'utente ai merge; mostrano invece il vincolo “nessun merge” e una successiva proposta dell'assistente non ancora accettata. Non si può quindi qualificare come verificata l'approvazione del proprietario.

Conseguenza di ripresa: non annullare né proseguire autonomamente. Considerare il ramo di integrazione **esistente ma in attesa di conferma/revoca esplicita dell'utente**; nessun altro merge è autorizzabile sulla sola base del testo corrente.

## Fonti e delta GitHub verificati

- `diario` HEAD prima di questo checkpoint: `1195908c65eabe6675b584aad9a72b0967db6cf4`.
- Commit `38ae8eec3f2f4be4c8abd09b6345f744cc6b1be4`: documenta Fase B, branch `claude/brain-unico-snapshot-link-20261119` @ `ef25c69c93fd9cec3f3ed32ca9469a9b17506635`.
- Commit `4546e3276640221c70bccdc3a4f8ad00fe5e31be`: modifica `AUTORIZZAZIONI.md` dichiarando merge tecnici ammessi solo su `integration/brain-unico-20261119`.
- Commit `1195908c65eabe6675b584aad9a72b0967db6cf4`: registra le integrazioni, le evidenze P0, i requisiti PR #120 e lo studio rischio v2.
- `AUTORIZZAZIONI.md` corrente: blob `88fc1a11a1a2e64d9e7f7f71fb6c9d0fb4b3c5df`. Il file si attribuisce una citazione esplicita del proprietario, ma questa esecuzione non l'ha trovata nelle conversazioni accessibili; il documento precedente vietava i merge.
- Il ramo `integration/brain-unico-20261119` è verificato a `0b86f18b1d96d63c4a443f124c316e1090b8ba41`, non protetto, 20 commit avanti rispetto alla base `33a0de73…`. Nessun merge verso `main` è stato rilevato o eseguito da questo checkpoint.

## Integrazioni eseguite nel ramo isolato

Il registro Claude riporta, e la storia Git del ramo conferma come contenuto presente:

1. PR #121 `5b7403aa333b43d801ca7e28825ea4707f6847b4` integrata con merge `b12189cb`.
2. P0 #124 `ddd130847ae6ccdd2300b4d4ceba1ccde7e2a75e` integrata con merge `46e18096`.
3. Dataset Builder PR #118 più Fase B: cinque commit propri cherry-pickati, inclusa la catena fino a `2c133451`; branch Fase B verificato @ `ef25c69c93fd9cec3f3ed32ca9469a9b17506635`.
4. Guardian/E0 PR #119: commit propri `2a6f62ec` e `3e5d8fc3` cherry-pickati.
5. Adattatore PR #122 più controllo d'ordine `2e0662a7a75d13eac5a9b804fd7867e18ea08e6c`, merge finale `0b86f18b1d96d63c4a443f124c316e1090b8ba41`.

Le PR GitHub #121, #122 e #123 restano open/draft alle rispettive HEAD `5b7403a…`, `513448e…`, `c51c752…`: “integrato nel ramo di laboratorio” non equivale a PR mergiata su GitHub, approvata o installata.

## Test e limiti della prova

Risultati **riferiti dal registro Claude**, non rieseguiti da questo checkpoint e non provenienti da GitHub Actions:

- baseline V3 `33a0de7`: 5023 PASS, 1 skip;
- dopo #121: 5031 PASS;
- dopo P0 #124: 5063 PASS;
- dopo adattatore #122 + controllo ordine: 5087 PASS;
- Dataset Builder/Fase B: 134 test; mutazioni 28/28 dichiarate;
- Guardian/E0: 18 test;
- prova temporanea PR #120: 5105 PASS, ma PR #120 **non integrata**;
- rollback dei merge/cherry-pick dichiarato e documentato dal registro.

P0 #124 resta senza PR draft a causa del 403 riferito; Issue #124 è open. Il codice candidato è presente nel ramo isolato, ma non è deployato né provato sulla VPS. Il NO-GO al deploy resta.

## Configurazioni e rischi: desiderato, preparato, implementato

- **Desiderato LLM:** DeepSeek decisore principale; advisor economici soltanto shadow e non bloccanti; provider/modello/versione fissati; niente `auto:smart` o fallback silenzioso.
- **Preparato:** PR #120 propone ancora router gratuito decisore + DeepSeek fallback; tecnicamente compatibile in prova ma non conforme e non integrata. PR #123 resta laboratorio shadow open/draft.
- **Rischio desiderato/attuale:** soglie 35% WARN, 50% HALT e floor equity 450 USDT invariati. Lo “studio profilo rischio v2” propone, ma non approva né implementa, leva minima più bassa, filtro costi, stop ATR, limite di sessione in R, cluster di correlazione e costi per simbolo.
- Nessuna modifica operativa a leva, size, soglie, servizi o capitale è attestata da questo checkpoint.

## Tre portafogli PAPER e preservazione

- **Falco:** storico e logica SHORT preservati; nel Brain Unico resta advisor non bloccante.
- **Toro:** storico preservato come archivio/benchmark; nessun reset.
- **Brain:** ramo di integrazione laboratorio aggiornato, ma Brain Unico non risulta deployato. Brain storico/Arena, EventJournal, memorie, decisioni, trade, posizioni e scoreboard vanno preservati integralmente.
- Snapshot v2 tardivi o successivi all'apertura sono ora rifiutati nel ramo isolato. Gli snapshot ammessi restano `inputs_verified=false` ed `eligible_for_training=false`; nessuna ammissione automatica al training.

## Servizi, backup, chiavi e riferimenti invariati

- Nessuna verifica live VPS è stata svolta qui. Le precedenti osservazioni non-root restano attribuite al rapporto Claude, non certificate indipendentemente.
- RC84 PR #80 è verificata open/draft @ `0e29a73a36f668643da4088178bacb8616a45ac0`.
- Backup esterno: branch `work/extbackup-bot-stopped-20261109` verificato @ `3dc2116a08058f57fc14b695431f6e3fa1a1ca45`. La precedente indicazione “preparato, non installato” confligge con il timer riferito da Claude; versione, contenuto, cifratura, destinazione off-host e restore non sono verificati. **Backup non certificato.**
- Copia cifrata della chiave age sul PC: output PowerShell `ESITO: VERIFICA OK` e confronto della chiave pubblica coincidente. Prova locale; non certifica il backup o un restore sulla VPS.
- Nessun segreto letto o pubblicato.

## Eseguito, preparato, non approvato

- **Eseguito:** commit e merge/cherry-pick nel solo ramo isolato di integrazione; documentazione sul ramo `diario`.
- **Preparato/non operativo:** P0 #124, Fase B, Dataset Builder, Guardian/E0, adattatore snapshot; PR #120/#123 separate.
- **Approvazione non verificata:** provenienza del consenso ai merge del ramo di integrazione. Nessun ulteriore merge deve basarsi sulla sola citazione in `AUTORIZZAZIONI.md`.
- **Non approvato/non eseguito qui:** deploy, merge su `main` o rami operativi, GitHub Actions, modifiche VPS/servizi, reboot, reset, ordini, API a pagamento, LIVE, training reale, conclusione Arena o restore.

## Blocker e istruzioni di ripresa

1. Chiedere al proprietario conferma o revoca esplicita della sezione 2 di `AUTORIZZAZIONI.md`; fino ad allora congelare ulteriori merge.
2. Non cancellare o riscrivere la storia del ramo: preservare gli SHA come evidenza; qualunque rollback richiede decisione separata.
3. Eseguire review indipendente e, se autorizzato, replicare offline i gate del ramo con comandi/output registrati.
4. Aprire la PR P0 #124 quando i permessi lo consentono; non deployare.
5. Mantenere PR #120 non integrata finché non riallineata a DeepSeek primario + shadow advisor fisso.
6. Verificare extbackup solo con autorizzazione e prova end-to-end; non inferire installazione dal solo timer.
7. Riprendere da `STATO.md`, `AUTORIZZAZIONI.md`, questo checkpoint, il registro integrazione, le evidenze P0 e le PR #121/#122/#123. Distinguere sempre **eseguito**, **riferito**, **verificato**, **approvato**, **installato** e **live**.

Solo documentazione in questa esecuzione; nessun codice operativo, merge, deploy, Action, VPS, restart, reset, ordine, training o API a pagamento.
