# Checkpoint verificabile — PR #114 Brain unico, inventory v2 e revisione statica

**Data:** 19/11/2026, 09:45 Europe/Rome  
**Tipo:** delta append-only rispetto al checkpoint delle 08:50.  
**Ambito:** sola documentazione; trading esclusivamente PAPER.

## Novità GitHub verificate

- [PR #114](https://github.com/alexiptv82/SuperBot-Trading/pull/114) aperta in **draft** verso `main`, titolo “Brain Unico — audit e inventario read-only”, branch `claude/brain-unico-audit-docs-20261119`.
- HEAD verificato: `3b8899531eb30dfe510575d8c1a293376c293ea9`; base `main` invariata a `a1e9722a1a9af32ee045ebf61d7e43858c9a1d5e`.
- Due commit, tre file aggiunti, 909 righe aggiunte, nessun file operativo V3 modificato:
  - `docs/v3/BRAIN-UNICO-RAPPORTO-AUDIT-20261119.md`;
  - `ops/brain-unico/inventory.py`;
  - `ops/brain-unico/test_inventory.py`.
- Nessun merge. Verifica puntuale sul ramo/HEAD: **0 workflow run, 0 check run, nessuno status pubblicato**. Lo stato combinato GitHub è `pending` perché non esistono status, non perché un test sia in corso.
- [Prima review ChatGPT](https://github.com/alexiptv82/SuperBot-Trading/pull/114#issuecomment-7003783845) sul commit iniziale `73f6bb8dbb735a1f8efd74306952a3b8127f0325`: impostazione approvata, uso su dati reali non approvato; richieste sei correzioni.
- [Seconda review ChatGPT](https://github.com/alexiptv82/SuperBot-Trading/pull/114#issuecomment-7004195533) sul commit `3b889953…`: sei criticità primarie affrontate staticamente; PR idonea a restare base di laboratorio, non a essere eseguita su dati reali.

## Contenuto e stato della patch

### Rapporto statico

Il rapporto della PR dichiara esplicitamente:

- analisi di GitHub/rami/PR, senza accesso VPS, runner, servizi o credenziali;
- `main` non rappresenta il sistema V3/Arena reale: runtime/commit effettivo devono ancora essere mappati;
- journal append-only, riconciliazione e componenti di memoria/scoreboard esistono, ma backup/restore reali e runtime non sono certificati;
- lo stato attuale è **memoria + scoreboard**, non training quantitativo provato;
- gap statico: `brain_decision` non conserva lo snapshot causale completo delle feature e i `NO_TRADE` non risultano etichettati a posteriori; senza questi elementi un dataset quantitativo affidabile non è ancora dimostrato;
- percorso proposto additivo e non distruttivo: schema decisionale point-in-time, etichettatore forward e modello locale in shadow, senza reset.

Questi sono risultati di code review sul repository, non certificazione del runtime VPS.

### Inventory v2

Il commit `3b889953…` corregge:

1. directory non leggibili: `os.walk(onerror=...)`, `traverse_errors`, `complete=false`;
2. SQLite live: DB/WAL/SHM/journal non letti né hashati per default; opzioni DB solo per copie ferme;
3. symlink/file speciali: `lstat`, solo file regolari, `O_NOFOLLOW|O_NONBLOCK`, verifica inode/device;
4. privacy: manifest privato 0600, ID disabilitati per default, validazione esplicita, sommario privo di path;
5. file instabili: unica lettura più verifica size/mtime/inode, `unstable_count`, `certifies_backup=false`;
6. test sintetici ampliati da 5 a 21 metodi.

Il manifest completo resta privato e non deve essere pubblicato o incollato nel repository.

## Test: fonte e limite

- Il messaggio commit e Claude riferiscono **21 test su fixture sintetiche PASS**.
- La conversazione recente riferisce che Claude li ha rilanciati localmente e sono ancora PASS.
- La seconda review GitHub ha svolto code review, non una riesecuzione indipendente.
- Questo checkpoint non ha eseguito codice della PR e GitHub non mostra check/Action: il PASS resta attestazione Claude, non CI indipendente.

## Rilievi residui

Prima di qualunque uso reale restano almeno due edge case documentati nella seconda review:

1. una singola riga JSONL più grande sia di `MAX_LINE` sia del chunk può essere conteggiata più volte o interpretata per segmenti; serve fixture multi-chunk e, se necessario, `discard_until_newline`;
2. `--out` uguale a `--summary-out` deve essere rifiutato in validazione per evitare collisione fra manifest privato e sommario.

La conversazione più recente non mostra un nuovo commit che li chiuda: il branch resta a `3b889953…`. La risposta Claude con il nuovo PASS non è stata pubblicata sulla PR per 403 del connettore; questa causa è riferita dall'agente, mentre GitHub prova soltanto l'assenza di un commento successivo.

## Stato consolidato e invarianti

- Unico Brain desiderato: DeepSeek decisore, Claude consulente mirato, Falco SHORT advisory non bloccante; Qwen/MiniMax/Toro storici dopo chiusura coerente Arena.
- PR #112 invariata open/draft a `86288a356209cef9264a369d24a2e8d7914c5ec2`.
- RC84 PR #80 invariata open/draft a `0e29a73a36f668643da4088178bacb8616a45ac0`.
- Extbackup `work/extbackup-bot-stopped-20261109` a `3dc2116a08058f57fc14b695431f6e3fa1a1ca45`: preparato, non installato.
- Age PC: `ESITO: VERIFICA OK`, chiave pubblica coincidente; non certifica backup o chiave VPS.
- Nessun nuovo stato live runner/exit, dataset o restore; Arena non modificata.
- Nessun force-push, merge, main/work change, VPS, servizio, database, PAPER, Arena, reset, Action o API a pagamento autorizzato/eseguito da questo checkpoint.

## Prossimo passo

Patch minima sullo stesso branch soltanto per i due edge case residui, test su fixture sintetiche e nuovo SHA remoto; poi nuova review. L'inventario reale richiede separato consenso, permessi read-only verificati, snapshot/copia coerente e prova restore distinta. Non eseguire `inventory.py` sulla VPS o sui dati reali finché questi gate non sono soddisfatti.

## Conservazione

PAPER soltanto. Storici Falco/Toro/Brain/Arena, EventJournal, memorie, scoreboard, run, posizioni e backup devono restare integralmente preservati. Nessun segreto o dettaglio d'accesso pubblicato.
