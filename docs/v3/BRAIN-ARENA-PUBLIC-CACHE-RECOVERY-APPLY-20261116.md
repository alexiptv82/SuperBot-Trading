# AI Arena — one-shot recupero reale dello storico, backup privato (16/11/2026)

## Prova verificata via screenshot VPS delle 19:32
`Ran 13 tests in 1.115s / OK`; la lettura della cache con SHA `a60016942548699e6b8b71049570d8313bae139d8208fbf22c931fc1b5e944ad` ha confermato 25 mercati, 60 minuti di differenza, 75 GET pubbliche **stimate** (25 × 1m, 25 × 15m, 25 × 1h), nessun rebase. `RESULT=RECOVERY_PLAN_ONLY_NOT_EXECUTED`. Non è stato effettuato nessun aggiornamento.

## Contenuto del ramo isolato
`work/arena-recovery-apply-private-20261116` aggiunge `deploy/scripts/arena-recovery-apply-private-20261116.py` con tre funzioni distinte:
- `--selftest` genera 25 mercati sintetici, aggiorna in memoria dopo un gap di 90 minuti, salva e rilegge la nuova cache atomica con una copia privata indipendente dell'originale, controlla il rifiuto di un SHA vecchio. **Nessuna rete e nessuna scrittura nei bot**.
- `--preflight <sha>` verifica in sola lettura che file privato esista, SHA atteso e 25 mercati siano integri, pianifica le pagine pubbliche necessarie senza chiamarle. **Non modifica la cache.**
- `--apply <sha> --confirm-public-get=YES` è una azione manuale separata: usa il vero helper Bitget V2 `_public_get` (sole candele pubbliche), massimo 125 GET, asof fissato all'inizio, limite di 72 ore, prova tutti i timeframe e simboli con il replay fail-closed. Rifiuta gap, duplicati, dati non chiusi e incompletezza. Ricalcola inoltre i 25 indicatori reali Brain in formato compatto e richiede digest identico per DeepSeek/Qwen/MiniMax. **Prima del replace** crea `.arena-backup-<sha>.json` nella sola cartella privata di ricerca, 0600, con fsync e confronto byte. Rifiuta cache/backup cambiati, backup multipli oltre limite, permessi impropri, carenza di spazio. Salvataggio atomico e rilettura con confronto SHA/bytes. Non tocca API AI, ordini, runner, UI o journal. I backup non sono cancellati automaticamente; dopo 12 aggiornamenti richiede revisione.
- Dato rebase: se il timeframe 1m ha perso più barre dell'intera finestra di 60 minuti, recupera le ultime 60 barre, **senza fingere che tutte le barre intermedie siano presenti**. Il catalogo resta quello esatto salvato nello snapshot; nessun update automatico della top 23 / metalli.
- I controlli su limite di tempo della richiesta sono espliciti. Se uno qualsiasi fallisce prima della commit, il file cache precedente rimane inalterato. Nessuna gestione automatica di downtime oltre 72h.

## Stato verifiche e gate successivo
Il modulo è stato creato e revisionato staticamente su GitHub, **non eseguito** nella VPS. Prima fare `python3 -m py_compile`, `--selftest` e `sudo ... --preflight <sha>`. Controllare output. Solo dopo considerare il comando `--apply` con autorizzazione esplicita dell'utente alla scrittura della **sola cache di ricerca**. Nessun deploy/merge/Actions, nessun cron e nessun test AI pagato; Falco SHORT, Toro e Brain corrente restano invariati.

I futuri 14 giorni PAPER e tre portafogli da 2000 USDT non sono ancora stati avviati.
