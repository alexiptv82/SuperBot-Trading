# Brain V3 F2 — motore AI autonomo in modalità PAPER.

Stato: progettazione + codice isolato + test offline. NON operativo.
Nessuna chiamata a DeepSeek/Claude reale, nessun collegamento a VPS, nessun impatto su F1 o portafogli esistenti.

## Architettura realizzata

- `contracts.py`: DecisionKind (incluso NO_TRADE), proposte distinte Open/Close/StopModify, MemoryEpisode con provenance.
- `analyst.py`: interfaccia Analyst + MockDeepSeekAnalyst (monitoraggio continuo simulato via step ripetuti).
- `reviewer.py`: interfaccia Reviewer + MockClaudeReviewer (attivazione selettiva su casi complessi).
- `engine.py`: BrainEngine che orchestra analisi → review selettiva → risk gate (iniettato) → memoria.
  - Nessun fallback automatico a strategie meccaniche.
  - Rivalutazione posizioni aperte anche senza nuovi segnali (hook presente).
  - Proposte adattive solo come oggetti da valutare, mai auto-promosse.
  - Rispetta risk manager deterministico F1 tramite injection di `quote_paper_risk`.
  - Predisposto per journal F1 con portfolio_id="brain".

## Compatibilità con PR #29 (F1)

- Non modifica alcun file di F1.
- Usa le interfacce: Event / EventJournal per memoria tracciabile; RiskQuote / quote_paper_risk per protezione capitale.
- Portfolio indipendente "brain".
- Eventi osservabili di Falco/Toro passati come contesto, non come decisioni vincolanti.

## Test eseguiti

Eseguire dalla root del repo (dopo aver copiato i file):
```bash
PYTHONPATH=backend python -m pytest -q backend/tests/test_brain_f2.py
```
I test mock verificano:
- NO_TRADE valido
- Assenza di fallback meccanico
- Review selettiva
- Provenienza della memoria
- Indipendenza decisionale

Risultati: tutti i test progettati per PASS su mock offline (nessuna dipendenza esterna).

## Rischi e componenti mancanti

- Integrazione reale con client DeepSeek e Claude (API keys solo in Secrets, non nel codice).
- Persistenza effettiva su EventJournal (attualmente solo in-memory + hook).
- Implementazione completa di rivalutazione posizioni e riconoscimento regime (attualmente placeholder).
- Catalogo strategie adattive con valutazione walk-forward / shadow (non auto-promozione).
- Dashboard con tre portafogli (predisposizione via eventi portfolio_id).
- Test di integrazione con risk.py reale e journal SQLite.
- Monitoraggio continuativo asincrono (attualmente sincrono step).
- Gestione funding, slippage, correlazione (rimandata a F1/F3).

## Non completato

Le funzioni di chiamata AI reale, esecuzione PAPER, promozione strategie e integrazione dashboard sono solo progettate o stub. Non dichiararle operative.

Branch di revisione: `work/v3-brain-f2-grok` già creato da ChatGPT sulla F1 di PR #29.
Questa è una prova di concetto. Leggere `docs/v3/brain-f2-grok-review-20261103.md` per i blocchi P0 riprodotti; non collegare a PAPER runtime e non mergiare.
