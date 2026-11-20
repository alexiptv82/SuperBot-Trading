# 20/11/2026 (5) — Claude: skill di trading (prima selezione), validazione delle feature su dati reali

## Skill
- Ramo isolato **`claude/skills-brain-unico-20261120`** @ `0ce8adf8`, derivato da `integration/brain-unico-20261119` @ `8fa61d18`:
  - solo 32 file aggiunti (5 skill, licenza, `PROVENIENZA.md`, sezione in coda a `CLAUDE.md`, `docs/v3/SKILL-CONFRONTO-20261120.md`);
  - nessun commit di `main`;
  - **non integrato** nel ramo di laboratorio, in attesa della prova di riconoscimento.
- Branch originale `claude/skills-trading-20261120` (10 skill) **conservato** come riferimento.
- **Selezione:** exit-strategies, risk-management, position-sizing, trade-journal, walk-forward-validation. Ognuna ha una sezione "SuperBot: leggere prima", verificata sul codice del progetto.
- **Riconoscimento:** NON verificato. Questa sessione ha caricato l'elenco delle skill all'avvio: `Skill("exit-strategies")` risponde "Unknown skill" anche dal nuovo worktree. Serve una nuova sessione sul ramo, oppure `/reload-skills` dal proprietario.
- **Confronti offline**, con l'analisi senza skill scritta prima di leggere le skill:

| Skill | Esito |
|---|---|
| exit-strategies | utile: 3 spunti nuovi |
| risk-management + position-sizing | utili |
| walk-forward-validation | utile, ma **la formula del Deflated Sharpe Ratio è errata** |
| trade-journal | basso valore: il formato contrasta con l'EventJournal |

Nessuna skill ha corretto un errore dell'analisi di base.

## Validazione della memoria su dati reali
Le feature calcolate dal runtime sulle candele Bitget reali dell'archivio venivano **tutte** rifiutate dal validatore indipendente come `unknown_feature`. La causa: le finestre reali sono di 2880/720/180 candele, mentre la regola del validatore ammetteva nomi con al massimo 3 cifre. I test sintetici usavano finestre da 20 e non potevano accorgersene.

**Correzione `733182f6`:**
- **24/24** verificati su 8 simboli × 3 istanti;
- **24/24** manomissioni rilevate;
- test di regressione con i parametri reali.

Suite 5311, builder 157, Jest 137, 0 falliti. Pubblicato con il gate.

## In attesa
- Ancora dell'archivio delle candele (proprietario).
- Sonda del feed (autorizzazione, al massimo 3 tentativi).
- Prova di riconoscimento delle skill in una nuova sessione.
- Vista storica dell'Arena, backup e prova di ripristino: non iniziati in questa sessione.
