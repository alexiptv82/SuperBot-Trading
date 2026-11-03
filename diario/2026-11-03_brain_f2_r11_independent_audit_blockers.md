# SuperBot V3 — 2026-11-03: audit indipendente Brain F2 R1.1, NO-GO

**Metodo:** solo archivio offline ricevuto dall'utente. Nessuna modifica a VPS, bot, wallet, F1, branch operativi, merge o deploy. La PR #33 resta DRAFT.

## Pacchetto e provenienza
- Tarball: `v3-brain-f2-r1.1-20261103.tar.gz`, 13.224 byte.
- SHA256 calcolato: `f71026faa5f329d578aaba43ca778e80ede0617a9c74fbcd6bed2bf1b17fe4d4`; **diverso** dall'hash dichiarato da Grok `caa97c27711ef5358a968dc9b1e5142296a539398d59c060db2203cf32595dec`. Richiedere conferma identità e nuovo hash calcolato dopo packaging.
- Archivio ispezionato: nessun link/absolute path/traversal; solo file/directory.
- F1 `backend/v3/events.py` blob `cd4ce09233cdfc41be43dd7083aac791e8e2c56d` e `backend/v3/risk.py` blob `514159b990c99740aee4f73b3bdd8839226e65bc` coincidono con PR #33.

## Test svolti realmente
- Test F2 inclusi nel tarball: **16/16 PASS**, Python locale **3.13.5**.
- Suite completa F1+F2 da 121 PASS in Python 3.10 e 3.11: **solo dichiarata da Grok**, non riprodotta in questa revisione.
- Nove controlli indipendenti avversariali su dati sintetici: **8 FAIL, 1 PASS**. Codice test e log conservati dall'auditor e disponibili per consegna a Grok.

## Blocker reali riprodotti
1. `OPEN/APPROVED` possibile con `journal=None`; risk quote allowed ma nessuna persistenza obbligatoria.
2. `paused` e `daily_loss_latched` omessi vengono assunti `False`; `OPEN/APPROVED` anche con EventJournal SQLite valido.
3. Policy `minimum_equity=Decimal('NaN')` solleva `InvalidOperation` prima del try, non fail-closed; floor string non valido produce TypeError.
4. `str(exc)` del provider AI copiato in `decision.rationale` può contenere dati sensibili.
5. `portfolio_id='hawk'` accettato dal Brain e scritto come evento Hawk nel journal.
6. Analista che ritorna `None` causa AttributeError senza `NO_TRADE`.
7. Revisore che ritorna `None` causa AttributeError senza `NO_TRADE`.
8. Test `test_close_and_modify_not_executable` contiene `assert True` e `test_independent_portfolio_observation` contiene `or True`, senza verificare gli invarianti.

## Gate per R1.2
Fail-closed obbligatorio per journal/pausa/latch/policy malformata/AI malformata; stringhe errore solo da allowlist; confine rigido portfolio brain/run; rafforzare event_id idempotente across restart; test non tautologici CLOSE/MODIFY_STOP e isolamento; verificare suite F1+F2 + test negativi su Python 3.10 e 3.11; sha archivio finale corretto. NON modificare F1 `events.py`/`risk.py`.

**Verdetto:** R1.1 non promossa, non integrata in PR #33 come soluzione approvata. Prossimo incarico tecnico Grok: R1.2 offline isolato; nuova revisione ChatGPT prima di ogni integrazione.
