# SuperBot V3 — Coordinamento 2026-11-03: sviluppo senza Work

L'utente segnala che Work ha esaurito il proprio utilizzo fino a domani e mette a disposizione Claude e Grok per lavorare in parallelo. Nessuna richiesta di modificare la VPS o di effettuare merge/deploy per questo messaggio.

## Verifiche attuali GitHub
- PR #29: `[DRAFT] SuperBot V3 F1 — append-only events + deterministic PAPER risk quoting`, `work/v3-foundations-event-risk-20261102`, HEAD `91e6040ca7d81874fda9afd8c1a3cb10c6efe55e`, non mergiata. Contiene eventi idempotenti, risk quoting, audit/contabilità legacy, offline import non attivo, certificazione backup offline e molti test.
- PR #32: `F0: diagnostica metadati Falco/Toro con ACL minima, reversibile e senza lettura file`, `work/f0-classic-metadata-acl-20261103`, HEAD `e9122d5406012cfcc9ccc410df55afc2f98de61b`, DRAFT, NON mergiata e non applicata. CI run `41598191790`: SUCCESS. Script aggiuntivo `ops/f0/classic_metadata_acl.sh` con `--check` read-only, `--apply` esplicito root da Termius; aggiunge ACL directory search solo su hawk/bull e conserva rollback. Nessuna modifica permessi fatta.
- F0 diagnostica ristretta via GitHub Actions PASS run `41596313485`: lettura remota metadati Brain, Hawk/Bull `UNAVAILABLE` agli attuali permessi. Questo non equivale a assenza file.
- Vecchia infrastruttura backup esterno cifrato `age` già presente. Workflow `.github/workflows/sg-extbackup-watch.yml` usa chiave SSH **legacy root** `SINGAPORE_SSH_PRIVATE_KEY` per leggere `/opt/superbot-extbackup/status.json`; nessun motivo di ripetere o ampliare privilegi. Ultimo watcher identificato come verde nel checkpoint precedente, ma non certifica contenuto, destinazione esterna o restore. Il piano backup deve riesaminare sicurezza, copertura storici e restore OFFHOST prima dell'import V3.

## Divisione lavoro proposta all'utente
- ChatGPT nella chat attuale: coordinamento generale, audit PR #32, mappatura e certificazione backup esterno con approccio least privilege, verifiche e diario. Non operare su VPS oltre diagnostica limitata già approvata, senza ulteriori approvazioni per ACL o chiavi.
- Grok: revisione tecnica del codice V3 PR #29 e progettazione/prototipo **isolato** F2 Brain observer + autonomous decisions with periodic re-evaluation and provenance. Sviluppo su branch indipendente, PR DRAFT, NO merge, no deploy, test Python, nessuna modifica di script F0/backup e nessuna incorporazione dati live. Riusare interfacce contrattuali PR #29 evitando di cambiarle.
- Claude: lasciare all'attuale HiTV (progetto indipendente) per non creare conflitti di contesto; disponibile per revisione futura SuperBot su richiesta.

## Gate permanenti
Tre bot STOP e PAPER. Niente restart, reset wallet, import memorie, merge PR #29/#32, deploy o comandi arbitrari SSH senza consenso distinto. Mantenere storia legacy e copia Brain SQLite/WAL; hard floor 450 USDT da preservare. L'apprendimento Brain non può introdurre strategie non verificate direttamente in runtime: memorie e proposte sotto controllo/evidenza separati. Nuova V3 1000 per portfolio è obiettivo documentato ma non azzerato; configurazione non operativa.
