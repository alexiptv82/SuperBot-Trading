# 2026-10-26 notte — Claude: regime di mercato, banco storico e controllo di fedelta'

Richiesta dell'utente: Hawk e Bull devono tornare ad aprire quasi di continuo (scalp), migliorando apertura e gestione: short quando il
mercato cambia, long quando il mercato gira al rialzo, niente short a caso in un mercato rialzista, non perdere i long quando il mercato
torna ribassista, gestire meglio il profitto. Bull a tetto 250 "per il momento".

## Cosa e' stato fatto
- Ramo `work/hawk-regime-v1` (base rule-pool): `regime.py`, integrazione in `brain.rules_decisions` e `cli.run_cycle`, tetto Bull 250,
  `signals_pre_p1.py`, banco storico e controllo di fedelta'. Nulla deployato. Dettagli e numeri: vedi STATO.md, sezione "Regime di mercato".
- Cammino fatto (per non rifare gli stessi errori): il primo banco si bloccava dopo un mese (soglia minima di capitale del motore), poi il conto
  da 1000$ si esauriva, poi il banco apriva piu' long dei bot: causa 1) pesi di P1 (trend 4h 14 invece di 20, 1d 10 invece di 15, +10 rimbalzo RSI),
  2) trend 1d assente nei bot fino al 22/10, 3) selezione delle aperture diversa (Claude, scarti, dati). Il motore e' fedele; le aperture no.
- Per questo la scelta dei parametri e' stata fatta sui TRADE VERI di Hawk (stessi trade, solo effetto del regime).

## Errori miei da ricordare
- Ho detto all'utente che P1 era stata attivata dal mio deploy 35f08cf: SBAGLIATO, era gia' nel deploy 63641f7 (STATO.md lo diceva). Corretto con l'utente.
- Il banco con dati completi e' stato preso per "come girano i bot": non lo e' (trend 1d assente, selezione diversa).

## Da fare (non iniziato)
- Decisioni dell'utente: pesi classici o P1; deploy regime "solo filtro"; tetto Bull 250; rinnovo calendario Claude prima dell'8/11.
- Se l'utente approva: merge `work/hawk-regime-v1` in `rule-pool` con AI Write (src work/*, dst rule-pool), test Python 3.11, baseline del workflow
  di deploy da `63641f7` a `35f08cf` (la guardia pretende la versione in esecuzione), poi trigger di deploy con `sha=` esatto. Dopo il deploy
  osservare 3-4 giorni: ogni apertura registra `reg_state` e `reg_turn` nelle feature (si puo' misurare per stato di mercato).
