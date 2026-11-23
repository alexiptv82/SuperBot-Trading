# Limiti del confronto PAPER: proposta del 23/11, interazioni, procedura (NON applicata)

Codice: commit `861a2f86` (ramo `claude/limiti-paper-20261123`), cartella `deploy/falco-evoluto/limiti/`.
Nessuna modifica a runner, strategie, mandati, journal o servizi. Nessun deploy, nessun riavvio eseguito.

## Proposta del proprietario
| | Avviso giornaliero | Stop giornaliero | Guardian, perdita di sessione |
|---|---|---|---|
| Brain Scalp | 5 % → **15 %** | 8 % → **25 %** | 8 % → **25 %** |
| Falco Evoluto | 5 % → **6 %** | 8 % → **12 %** | 8 % → **12 %** |

Invariati per entrambi: rischio per trade 4 %, rischio aperto 10 %, leva 15–45×, margini, floor (Scalp 1.600, Falco 800),
protezione dei profitti (attivazione 8 %, mantiene il 75 % del picco), drawdown globale del Guardian 10 % (rischio
dimezzato) e 20 % (blocco). Le due configurazioni nuove differiscono dalle attuali **solo** in quelle tre righe (test).

## Correzione di un errore mio
Il 23/11 ho scritto che lo stop giornaliero di Brain Scalp era al 50 %: è il valore di riserva del codice, ma la
configurazione delle due run lo fissa all'**8 %**. Il blocco all'8,2 % è quindi coerente con la configurazione in uso.

## Quali limiti bloccano davvero le nuove aperture
Calcolo in `analisi_limiti.py`, verificato sul codice reale (RiskManager, Guardian, freno giornaliero) in `test_limiti.py`.
Tutti i blocchi fermano solo le NUOVE aperture: le posizioni aperte proseguono fino a stop, obiettivo o uscita.

**Brain Scalp (capitale 2.000, floor 1.600)**
| Calo da inizio giornata | Oggi (8 %) | Proposta (25 %) |
|---|---|---|
| −5 % | avviso | — |
| −8 % | **stop giornaliero + Guardian sessione** | — |
| −10 % | rischio per trade dimezzato | rischio per trade dimezzato |
| −15 % | — | avviso |
| −20 % (1.600) | floor + drawdown globale | **floor + drawdown globale: primo blocco reale** |
| −25 % | — | stop giornaliero e sessione: **non raggiungibili** con nuove aperture (sotto il floor) |

- Con la proposta lo stop giornaliero al 25 % e la sessione al 25 % non bloccano mai per primi: dal capitale iniziale li
  precedono floor e drawdown globale (entrambi a 1.600); dopo profitti il drawdown globale (20 % dal massimo
  contabilizzato) arriva sempre prima del 25 % (provato per 2.400, 3.000, 5.000). Potrebbero scattare solo con gap oltre
  gli stop.
- Conseguenza: per Scalp il freno giornaliero smette di esistere in pratica. Una sola giornata negativa può portare
  Scalp al floor; lì il blocco del floor (sull'equity contabilizzata) non si toglie da solo e il drawdown globale si toglie
  solo se le posizioni ancora aperte recuperano: **il confronto di Scalp finirebbe** fino a un intervento del proprietario.
- Il messaggio d'avviso al 15 % dirà «si ferma da solo al 25 %», ma dal capitale iniziale si fermerà al 20 % (floor).
  Il testo è nel codice (`daily_loss.py`): non l'ho cambiato.
- Se si vuole un freno giornaliero che morda prima del floor, deve stare sotto il 20 % (decisione del proprietario).

**Falco Evoluto (capitale 1.000, floor 800)**
| Calo da inizio giornata | Oggi (8 %) | Proposta (12 %) |
|---|---|---|
| −5 % / −6 % | avviso (5 %) | avviso (6 %) |
| −8 % | **stop giornaliero + sessione** | — |
| −10 % | rischio dimezzato | rischio dimezzato |
| −12 % | — | **stop giornaliero + Guardian sessione: primo blocco reale** |
| −20 % (800) | floor + drawdown globale | floor + drawdown globale |

- Lo stop al 12 % funziona davvero da stop di giornata, preceduto dal dimezzamento del rischio a −10 %.
- Dopo una giornata a −10 % (inizio 900) il floor 800 arriva a −11,1 %, prima del −12 %: da quel giorno il limite reale è il floor.
- Perdita massima di una giornata stimata a stop (senza gap): circa 20 % (il blocco scatta a −12 % con fino al 10 % di
  rischio ancora aperto, troncato dal floor).

**Differenze di finestra:** lo stop giornaliero conta dal 00:00 UTC (01:00 italiane) e include il non realizzato contro il
prezzo d'ingresso; la sessione del Guardian conta dalle 08:00 Europe/Rome sull'equity a mercato di quell'ora. Con lo
stesso valore (25/25, 12/12) scatta per primo quello con la base più sfavorevole; il blocco di sessione dura fino alle 08:00,
quello giornaliero fino a 01:00.

## Mandati
Il mandato è legato solo all'impronta della politica di rischio (`_policy_hash`: per trade, aperto, margini, floor, leva,
posizioni, stesso lato). La proposta non la cambia: **i mandati approvati restano validi** e non serve una nuova
approvazione (verificato nei test e ricontrollato dalla procedura sul file reale).

## Vincolo tecnico: il marcatore della run
`PREPARED_PAUSED_ONLY.json` registra l'impronta di `runner_config.json`; runner e servizio uscite rifiutano di AVVIARSI
se non coincidono. La procedura aggiorna quindi anche quell'impronta (gli altri sei campi restano byte per byte),
annota la modifica in `CONFIG_AMENDMENTS.jsonl` con il nome di chi approva, e conserva le copie. L'evento di preparazione
nel journal mantiene l'impronta originale: il journal non si tocca.

## Procedura (root, una run alla volta, solo con autorizzazione)
Scarico con verifica delle impronte:
```
sudo sh -c 'set -e; D=/root/limiti-861a2f86; mkdir -p $D; cd $D; B=https://raw.githubusercontent.com/alexiptv82/SuperBot-Trading/861a2f86feba2662a066045e971d05df09b6150a/deploy/falco-evoluto/limiti; for f in aggiorna_limiti.py audit_freno.py runner_config_brain_scalp_paper.json runner_config_falco_evoluto_paper.json; do curl -fsS $B/$f -o $f; done; printf "%s\n" "4ad738c20b44e7235ce5860bd9d74720aa9af7ac70d7a4c0c3e55c3ddd84123e  aggiorna_limiti.py" "3534b8dd944efddf12fb74cb33a631ae0f3994f2c50a6acc67a8530446ea6907  audit_freno.py" "a31bedc567dc8753611f34d1ec0c372e6a7b59b5588f757ee933c0c9d7f7ea29  runner_config_brain_scalp_paper.json" "98b52a3bb82bb0e7dfe76d42558d7515aff0608371db2301140da208db2839cd  runner_config_falco_evoluto_paper.json" | sha256sum -c'
```
Prefisso comune (codice installato e Python della stage): `P="cd / && PYTHONPATH=/opt/superbot-falco-scalp-5539ee474476 /opt/superbot-v3-rc70-stage/.venv/bin/python3 /root/limiti-861a2f86"`

1. **Controllo, nessuna modifica:** `sudo sh -c "$P/aggiorna_limiti.py --bot falco --controlla --nuova /root/limiti-861a2f86/runner_config_falco_evoluto_paper.json"` → `CONTROLLI_SUPERATI_NESSUNA_MODIFICA`.
2. **Applicazione:** come sopra con `--applica --approvato-da "<nome>"` → `LIMITI_AGGIORNATI`. Fa: copia di sicurezza
   verificata in `/opt/superbot-v3-backups/limiti-<bot>-<data>/`, nuova configurazione e impronta del marcatore
   (scritture atomiche, stessi permessi), annotazione, riavvio del **solo runner**, controllo del battito (mai motivo
   mandato/configurazione), uscite attive e **stesso processo** (non riavviate). Se un controllo fallisce: ripristino
   automatico (`AUTO_ROLLBACK_CONFIGURAZIONE_PRECEDENTE`).
3. **Rollback:** `--bot <bot> --rollback` → `LIMITI_PRECEDENTI_RIPRISTINATI`: riporta configurazione e marcatore, riavvia
   il solo runner. `daily_loss.json` non viene MAI riportato indietro (un blocco scattato resta) e il mandato non si tocca.

**Quando:** la procedura rifiuta da sola, senza cambiare nulla, se il freno giornaliero è agganciato oggi (qualunque motivo)
o se l'ultima valutazione del Guardian nella sessione corrente è bloccata per perdita di sessione (o manca): il nuovo limite
toglierebbe un blocco già scattato. Per **Brain Scalp** il primo momento utile è dopo le 08:00 italiane del 24/11 e dopo il
suo primo giro della nuova sessione (giro ogni 30 min). **Falco Evoluto** si può aggiornare quando i controlli passano.

## Audit del blocco all'8,2 % di Brain Scalp
Fatti verificati (superbot-ops): runner `halted:daily_loss` dalle 17:43:00 UTC del 23/11, 11 minuti dopo la seconda
apertura (17:32); stop configurato 8 %; uscite SANE; mandato valido; nessuna pausa. Con rischio massimo 4 % per posizione
e due posizioni aperte, una perdita dell'8,2 % significa che entrambe erano vicine allo stop (o una chiusa allo stop):
è il comportamento previsto del freno, non un guasto, salvo prova contraria dall'audit.
Il blocco scade da solo alle 00:00 UTC del 24/11; non va cancellato né forzato.

Per chiudere l'audit (sola lettura, journal copiato `mode=ro`, nessuna scrittura nella run):
`sudo sh -c "$P/audit_freno.py --bot scalp --giorno 2026-11-23"` — stampa aperture/chiusure con perdita allo stop, il
minuto in cui la perdita ha toccato 5 % e 8 % con il contributo di ciascuna posizione («entro lo stop» / «OLTRE LO STOP»),
il confronto con la ricostruzione del codice in uso (`COERENTE`), aperture e decisioni dopo il blocco, il Guardian del giorno.

## Verifiche
`test_limiti.py` 16 test; deploy `falco-evoluto` 52 test; mutazioni: senza rifiuto con freno agganciato (2 test falliti),
con ripristino di `daily_loss.json` nel rollback (1), senza rifiuto per perdita di sessione (1).
