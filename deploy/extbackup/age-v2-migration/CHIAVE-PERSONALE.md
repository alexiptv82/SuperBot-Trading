# La tua chiave personale di recupero: 6 passi, sul TUO computer

Serve a una cosa sola: **poter aprire i backup anche se GitHub, la VPS e questa chat sparissero**. La chiave nasce sul tuo computer e **non passa mai** da Claude, da GitHub o dalla VPS.
Si condivide soltanto la parte **pubblica** (una riga che inizia con `age1…`): è fatta per essere condivisa.

**Prima di cominciare:** servono il programma `age` e Python 3.
macOS: `brew install age` · Windows: `winget install FiloSottile.age` (e Python da python.org) · Linux: `sudo apt install age`.
Scarica nella stessa cartella il file `chiave_personale.py` (è in `deploy/extbackup/age-v2-migration/` del repository: è testo, puoi leggerlo; non usa la rete).

## I passi
1. **Crea** (apri il terminale nella cartella del file):
   `python3 chiave_personale.py crea --cartella ~/Documents/superbot-chiave --proteggi`
   Ti verrà chiesta una **passphrase** per la copia protetta: scegline una tua (non quella del gestore di password) e **scrivila su carta**. Il programma stampa solo la riga `chiave pubblica: age1…`
   e un'impronta. La privata resta nei file della cartella (permessi 600) e **non viene mostrata**.
2. **Prova subito** (copia la riga `chiave pubblica` che hai ottenuto):
   `python3 chiave_personale.py prova --identita ~/Documents/superbot-chiave/chiave-personale.txt --pubblica age1…`
   Deve finire con `ESITO COMPLESSIVO: OK - la chiave funziona`.
3. **Fai due copie**, in due posti fisicamente diversi (per esempio: gestore di password + una chiavetta tenuta in casa/in cassaforte). Copia il file protetto `chiave-personale.txt.age` (e, se vuoi, anche
   quello in chiaro solo su supporti che custodisci tu). La passphrase sta **separata** dalle copie.
4. **Prova la COPIA, non l'originale** (una copia mai provata non è una copia): dal supporto della copia,
   `python3 chiave_personale.py prova --identita-protetta /percorso/della/copia/chiave-personale.txt.age --pubblica age1…` e digita la passphrase. Deve dare di nuovo `OK`.
5. **Solo dopo il passo 4**, cancella l'originale in chiaro dal computer (macOS: `rm -P chiave-personale.txt` · Linux: `shred -u chiave-personale.txt`). Tieni la copia protetta.
6. **Manda in chat soltanto** la riga `chiave pubblica: age1…` (e l'impronta, se vuoi annotarla nel diario). Il passo successivo lo fa il repository: `set_recipients.py --add age1…`.

## Regole che non si discutono
* **Mai** incollare la privata (`AGE-SECRET-KEY-1…`) in una chat, una mail, uno screenshot, un file del repository o sulla VPS. Se succede per errore: è esposta, va rifatta.
* Il programma **si rifiuta** di lavorare dentro un repository git (la privata non deve finire in un commit) e sul server (se vede le cartelle di SuperBot della VPS).
* Per la chiave che metterai come **Secret di ambiente** di GitHub (`SEGRETI-E-PROTEZIONI.md` §3) usa un secondo nome: `crea --cartella … --nome chiave-actions`; dopo averla incollata nel Secret, cancella il file locale
  (la tua chiave personale resta la copia indipendente).
* Se perdi sia la copia sia la passphrase, **quella chiave non si recupera**: i backup cifrati solo per lei diventano illeggibili. È il motivo delle due copie e del doppio destinatario (V2 + personale): con due chiavi
  diverse perdere una non perde i dati.

## Che cosa succede dopo
Nel repository si aggiunge la tua pubblica ai destinatari (`python3 deploy/extbackup/v2/set_recipients.py --add age1…`: rifiuta chiavi private, doppie o uguali alla V1 e riallinea da solo l'impronta nei wrapper). Da quel momento
ogni backup nuovo è cifrato per **entrambe** le chiavi e si apre con ciascuna. Il ripristino sul tuo PC usa `restore_external_backup.py` / `restore_brain_v3_backup.py` con `--identity` sulla tua chiave (procedura in `LEGGIMI.md` §7).
