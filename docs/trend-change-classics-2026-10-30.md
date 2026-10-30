# Sensore di cambio di trend v1 — Falco e Toro (30/10/2026)

## Obiettivo
Leggere i cambiamenti di pressione prezzo, anche quando il mercato SHORT sta iniziando a girarsi LONG. Nessuna nuova strategia di apertura creata, nessun veto o ingresso imposto. Long e short continuano nello stesso percorso di scoring/decisione PAPER preesistente.

## Implementato sul ramo isolato
- `backend/director/trend_advisory.py`: stessa lettura pura del Brain, su 40 candele 15m *chiuse e contigue*. Ritorna `early_upshift`, `early_downshift`, continuazione o incertezza, solo `advisory_only`. Rifiuta buchi, prezzi non validi, quote vecchie; non usa trend EMA200 come filtro.
- `backend/desk/cli.py`: durante `run_cycle`, dopo `read_symbol`, pubblica l'ultimo quadro in `state['trend_observations']`, notificando il cambio di fase nel log diagnostico. Non muta i `Reading`, non assegna punti aggiuntivi, non esclude simboli, non fa ordini, non aumenta le chiamate Claude.
- L'AI per i classici resta opzionale con `DESK_CLASSICS_AI_MODE=rules_only` gia' presente sul ramo base; il sensore funziona anche senza AI.

## Limiti attuali
- Il ciclo dei classici gira ogni ~15-30 minuti secondo modalita' e usa candele 15m; la lettura non e' quindi un detector tick-by-tick. Inversioni rapidissime non possono essere garantite; per anticipare serve in futuro alimentazione a timeframe 1m/5m su canale diagnostico separato senza rallentare gli stop.
- Il punteggio tecnico LONG P1 precedente NON viene fuso: era una modifica allo scoring d'ingresso, mentre il nuovo mandato dell'utente definisce un *lettore indipendente*. Lo scorer conserva i vecchi pesi, con i rischi e limiti gia' registrati nel diario. Servira' confronto shadow fra classificatori, aperture e falsi positivi per decidere se correggere eventuali bias LONG/SHORT senza stravolgere il meccanismo SHORT che funziona.
- Il lettore non trasforma automaticamente un segnale di inversione in una posizione LONG, e non puo' intervenire sulle posizioni gia' aperte; gli stop locali rimangono la tutela.

## CI
Run `41043189208` SUCCESS Python3.10/3.11: 18 nuovi test per versione, A/B su originale classici `rule-pool`: 19/95 falliti originale contro 3/95 falliti candidato, nessuna nuova regressione. I 3 residui sono test della vecchia politica Claude e non sono stati modificati per mascherarli.
**Nessun deploy, merge, reset, API privata o modifica al portafoglio attivo.**
**Branch:** `work/classics-trend-awareness-20261030`, nato da `work/classics-manual-teaching-20261030`.
AI: chatgpt
