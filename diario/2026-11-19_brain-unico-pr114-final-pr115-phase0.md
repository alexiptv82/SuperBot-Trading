# Checkpoint verificabile — PR #114 finale e PR #115 Fase 0 Brain unico

**Data:** 19/11/2026, 10:48 Europe/Rome  
**Tipo:** delta append-only rispetto al checkpoint delle 09:45.  
**Ambito:** sola documentazione; trading esclusivamente PAPER.

## PR #114 finalizzata nel ramo, non mergiata

- [PR #114](https://github.com/alexiptv82/SuperBot-Trading/pull/114) resta open/draft verso `main`.
- HEAD verificato: `52d84778443727a29715848ba71c82e873c7c820`; base `main` invariata a `a1e9722a1a9af32ee045ebf61d7e43858c9a1d5e`.
- Tre commit, tre file, nessun merge.
- Il commit finale chiude i due edge case del checkpoint precedente:
  1. una riga JSONL oltre `MAX_LINE` e oltre il chunk viene scartata fino al newline senza essere ricontata;
  2. `--out` e `--summary-out` che risolvono allo stesso percorso vengono rifiutati prima della scrittura.
- [Terza review ChatGPT](https://github.com/alexiptv82/SuperBot-Trading/pull/114#issuecomment-7004521454): 29 metodi `test_*` presenti; Claude riporta 29 PASS e 5 regressioni che falliscono contro il commit precedente. Non rieseguiti indipendentemente da questo checkpoint.
- Stato tecnico: approvata soltanto la pianificazione della Fase 0; nessuna approvazione a merge, dati reali, backup live o deploy.

## Nuova PR #115 — Fase 0

- [PR #115](https://github.com/alexiptv82/SuperBot-Trading/pull/115) open/draft, branch `claude/brain-unico-fase0-prep-20261119`, base dipendente dal branch di #114.
- HEAD verificato: `465e0d92d76dc24b1dc8ec5df75ec557457f1498`.
- Due commit, sette file nuovi, 2606 righe aggiunte:
  - runbook Fase 0;
  - `discover.py`;
  - `snapshot.py`;
  - `audit.py`;
  - `phase0.py`;
  - spec d'esempio;
  - test sintetici.
- Ambito dichiarato: preparazione in laboratorio; nessuna esecuzione su dati, servizi, runner, journal o VPS reali.
- Verifica puntuale HEAD: **0 workflow run, 0 check run, nessuno status pubblicato**; GitHub `pending` significa assenza di status.
- Il commit iniziale `ddc08790f649f1bbed442ec8ac6df1c8d7fa22c6` riportava 49 test Fase 0 PASS su fixture; il commit correttivo `465e0d9…` riporta 85 test Fase 0 + 29 inventory PASS e 17 mutazioni su 17 rilevate. Questi risultati sono dichiarati da Claude e verificati solo come presenza dei metodi/code review, non come CI indipendente.

## Prima review #115 e correzioni P0/P1

La [prima review indipendente](https://github.com/alexiptv82/SuperBot-Trading/pull/115#issuecomment-7005189015) ha rilevato quattro P0 e rilievi P1. La [seconda review](https://github.com/alexiptv82/SuperBot-Trading/pull/115#issuecomment-7005545394) conferma in code review:

1. **P0-A chiuso:** directory preesistenti accettate solo con marcatore/utente corretto e mai sottoposte a `chmod`; nuove directory create in modo sicuro, niente symlink.
2. **P0-B chiuso:** discovery ritorna NO-GO/INCOMPLETE se dati processi/systemd non sono disponibili; redazione argomenti rafforzata.
3. **P0-C chiuso:** roster/gruppi obbligatori, nessun successo su `all([])`, NO-GO per sorgenti/gruppi senza item; ID `.` e `..` rifiutati.
4. **P0-D chiuso nel disegno:** DB WAL senza sidecar è NO-GO senza evidenza esterna di quiescenza; sidecar comparsi durante la copia causano scarto. L'evidenza resta una stringa operatore, non prova crittografica/servizio.
5. **P1:** audit e riepilogo dichiarano sempre `certifies_backup=false`; snapshot sullo stesso host e cattura cross-source non atomica.

## Decisione tecnica e autorizzazioni

- **Step 1 discovery non privilegiata:** giudicato tecnicamente idoneo per essere proposto, ma **NON autorizzato**.
- Richiede un futuro messaggio utente esplicito “AUTORIZZO STEP 1”.
- Anche Step 1 tratta metadati sensibili: rapporto privato 0600, nessuna pubblicazione integrale; condividere solo riepilogo sanitizzato.
- Vincoli: utente non-root, niente sudo/root/Docker group, niente comandi start/stop/restart, Docker, journalctl, env, journal o SQLite; niente Step 2/3.
- `codefp`, se richiesto e già leggibile, legge file Python ma non dati/journal/DB.
- Step 2, Step 3, snapshot reale, merge e deploy restano non autorizzati.

## Significato dell'apprendimento e conservazione

- Fase 0 mira a mappare commit↔servizi↔storici e preparare copie coerenti per file, manifest su copia ferma e restore in directory vuota.
- Non implementa ancora il training del Brain e non certifica il backup.
- Restano requisiti: dataset point-in-time, label anche per NO_TRADE/rifiuti, MFE/MAE/costi/funding, provenance, split temporali, shadow e promozione approvata.
- Gruppi storici obbligatori: Falco, Toro, Brain storico e le tre Arena; percorsi e completezza reale devono ancora essere verificati senza pubblicare dettagli sensibili.

## Rischi residui futuri

- completezza effettiva delle sei famiglie di dati;
- privilegi di lettura e possibili scritture SQLite SHM;
- prova indipendente di quiescenza;
- consistenza fra fonti catturate in tempi diversi;
- ancore esterne per troncamenti di coda;
- backup cifrato fuori host e restore verificato.

Questi non bloccano la sola proposta Step 1, ma bloccano snapshot/certificazione.

## Baseline invariata

- PR #112 open/draft a `86288a356209cef9264a369d24a2e8d7914c5ec2`.
- RC84 PR #80 open/draft a `0e29a73a36f668643da4088178bacb8616a45ac0`.
- Extbackup `work/extbackup-bot-stopped-20261109` a `3dc2116a08058f57fc14b695431f6e3fa1a1ca45`: preparato, non installato.
- Age PC: `ESITO: VERIFICA OK` e chiave pubblica coincidente; non certifica backup/chiave VPS.
- Nessun nuovo stato live runner/exit, dataset o restore; Arena invariata.

## Invarianti

Nessun merge, deploy, Action, accesso/modifica VPS, esecuzione Step 1/2/3, snapshot, restart, reset, ordine o API a pagamento. Solo PAPER; storici Falco/Toro/Brain/Arena, EventJournal, memorie, scoreboard, run e backup preservati. Nessun segreto o dettaglio d'accesso pubblicato.
