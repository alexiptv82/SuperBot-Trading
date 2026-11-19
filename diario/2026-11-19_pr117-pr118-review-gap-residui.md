# Checkpoint 19/11/2026, 12:47 Europe/Rome — PR #117/#118, REVIEW E GAP RESIDUI

**Ambito:** sola documentazione; trading esclusivamente PAPER. Nessun merge, deploy, Action, modifica codice operativo, VPS, root, snapshot, stop Arena, reboot, reset, ordine, wallet o API a pagamento.

## Riscontro delle novità

Dopo il checkpoint delle 11:44 sono stati pubblicati due checkpoint Claude sul ramo `diario` (commit `0aaa61f…` e `1e84f92…`) e due nuove PR draft. La Library era ancora alla v117 e non includeva queste novità: questo delta riallinea le due copie e registra i limiti emersi dalla seconda review.

### PR #117 — finalizzazione anticipata Arena

- [PR #117](https://github.com/alexiptv82/SuperBot-Trading/pull/117) open/draft, non mergiata; branch `claude/brain-unico-fase0-conclusion-20261119`, base PR #116 `9bf08ac36f868aaf96fb9e63d6c43a3912230aae`.
- HEAD verificata `6dcdedc36c3aafb4a2bed2a8f7b8edcc74b80482`; 2 commit, 9 file, +2248/−83.
- La prima review ha vietato di presentare letture DB come innocue e ha richiesto checkpoint coerente prima dello stop. Il secondo commit sostituisce `status` con `status-services` solo systemd e rende obbligatorio un `full` PRE-stop recente e valido prima di `stop-openings`.
- `stop-openings` è progettato per i soli runner Arena; non chiude posizioni, non ferma exit service e non garantisce uscite entro un tempo fisso. Su NO-GO non deve fermare o distruggere nulla.
- L'audit distingue `no_breach_proven` da `fully_checked=false`; dati mancanti restano gap e una perdita aggregata non prova il rispetto del freno giornaliero.
- Nuovo hash dichiarato del bundle: `4dcaff8b5cb583df20e7386dca2a8c78bdf472260595bf461d4913df4266a7b3`; sostituisce i precedenti, ma non è stato ricalcolato indipendentemente in questo checkpoint.
- Test riferiti da Claude: 76 bundle + 90 Fase 0 + 24 audit rischio + 29 inventory PASS; 28/28 mutazioni rilevate. Non replicati indipendentemente.
- 0 workflow run, 0 check run e nessuno status sulla HEAD al controllo.

### PR #118 — Training Dataset Builder

- [PR #118](https://github.com/alexiptv82/SuperBot-Trading/pull/118) open/draft, non mergiata; branch `claude/brain-unico-training-dataset-20261119`, indipendente su `main`.
- HEAD verificata `e983d36f7be8d9965ed37283d3d4ca86b658fdab`; 3 commit, 13 file, +2795.
- Schema v2 preparato offline: lettori Falco/Toro, Brain storico e tre Arena; feature point-in-time, NO_TRADE/rifiuti, etichette, annotazioni manuali, split cronologico/embargo, sufficienza e attestazione.
- Correzioni presenti: flag `verified` manuale ignorato; eleggibilità unica per split/sufficienza; barriera sul prefisso osservabile; MFE/MAE dichiarati approssimati; PnL mancante distinto da zero; metadati/hash candele.
- Test riferiti da Claude: 88 sintetici PASS; 33/33 mutazioni rilevate. Non replicati indipendentemente.
- 0 workflow run, 0 check run e nessuno status sulla HEAD al controllo.

## Due gap residui nella PR #118

La seconda review pubblicata dopo l'ultimo commit rileva due problemi non ancora chiusi da un nuovo SHA:

1. **Conflitto simbolo/ciclo:** il collegamento per `cycle_id` può precedere il controllo del simbolo e associare feature di un simbolo a un trade di un altro. Serve fail-closed su simboli noti discordanti, contatore `symbol_conflict` e fixture sintetica.
2. **Attestazione non ancora legata fortemente allo snapshot reale:** JSON formalmente validi possono apparire attestati senza vincolo sufficiente fra run, manifest, snapshot e audit. Prima di dati reali servono riconciliazione degli hash e stato conservativo quando manca un'ancora attendibile.

Finché questi punti non hanno patch, nuovo SHA e review, il builder resta solo laboratorio e non va usato per training reale o shadow su dati veri.

## Stato consolidato e portafogli PAPER

- **Falco:** storico PAPER/SHORT da preservare integralmente; advisory-only per il futuro Brain. Runner non da riattivare automaticamente.
- **Toro:** storico PAPER da preservare; proposte LONG non promosse. Runner non da riattivare automaticamente.
- **Brain storico:** fermo secondo l'ultimo riscontro; EventJournal, memoria, scoreboard, decisioni e posizioni storiche restano fonti da conservare, non prova di apprendimento quantitativo.
- **Brain Unico desiderato:** un decisore AI con revisore, dati causali verificabili, addestramento offline/shadow e promozione solo dopo evidenze e consenso. PR #114–#118 preparano audit, snapshot, finalizzazione e dataset; nulla è rilasciato.
- **Arena DeepSeek/Qwen/MiniMax:** PAPER e non bloccante per la roadmap. Può essere conclusa anticipatamente solo con checkpoint coerente, uscite verificate, riconciliazione, copia/manifest e consenso operativo separato. Nessuno stop o accesso ai journal è avvenuto qui.

## Backup, chiavi e baseline

- Verifica PC della copia cifrata age: PowerShell `ESITO: VERIFICA OK` e chiave pubblica coincidente. Non certifica il backup né il restore sulla VPS.
- `work/extbackup-bot-stopped-20261109` a `3dc2116a08058f57fc14b695431f6e3fa1a1ca45`: preparato, non installato.
- RC84 PR #80 invariata open/draft a `0e29a73a36f668643da4088178bacb8616a45ac0`.
- PR #112 invariata open/draft a `86288a356209cef9264a369d24a2e8d7914c5ec2`.
- Nessun backup esterno cifrato/restore indipendente certificato; `certifies_backup=false`.

## Fatto / preparato / rilasciato

- **Fatto:** push fast-forward e review pubbliche delle PR #117/#118; checkpoint Claude sul diario; verifica GitHub di stato, SHA, diff e assenza CI.
- **Preparato:** finalizzazione ordinata Arena, audit rischio, bundle aggiornato, Dataset Builder schema v2 e test sintetici.
- **Rilasciato:** nulla. Nessun merge, deploy, root, lettura dati reali, snapshot, stop, training o modello.
- **Non approvato:** qualunque esecuzione del bundle, accesso a storici reali, intervento Arena, training, merge o deploy.

## Blocker e prossimo passo

1. Patch minima PR #118 sui due gap residui, nuovi test sintetici e nuovo SHA; poi review statica.
2. Verifica indipendente dei byte/hash del bundle PR #117 prima di qualunque esecuzione.
3. Copie attestate e specifica reale delle sei fonti; accesso dati soltanto con consenso separato.
4. Backup esterno cifrato, witness e restore su copia vuota restano gate futuri.
5. Solo dopo i gate valutare preflight root o finalizzazione Arena; mai interpretare il design come autorizzazione.

## Nota di consistenza del diario

Il commit `1e84f92…` è stato registrato su GitHub alle 12:37 circa Europe/Rome, mentre la sezione aggiunta in `STATO.md` è etichettata “13:10”. Lo storico viene preservato senza riscrittura; questo checkpoint registra la discrepanza e usa l'ora verificata 12:47 Europe/Rome.

## Istruzioni di ripresa e limiti

Leggere `STATO.md`, questo checkpoint, i due checkpoint Claude e le PR #117/#118 con le seconde review. Distinguere sempre codice preparato, test dichiarati, review statica e stato live. Le conversazioni sono accessibili solo come estratti recenti indicizzati; nessuna trascrizione integrale di chat eliminate e nessun controllo SSH/live VPS in questa esecuzione. Preservare PAPER, storici, EventJournal, memorie, scoreboard, run e backup.
