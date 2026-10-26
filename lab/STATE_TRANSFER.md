# Trasferimento offline dello stato e rollback — laboratorio

## Esito verificato il 26 ottobre 2026

Nel solo Colima ARM64 è stato eseguito il percorso **4.23.8 → 4.23.13 → 4.23.8**
con dati e credenziali sintetici. Entrambi i container sono fermi a fine prova.
Nessun comando di questa procedura accede al Raspberry Pi, a `/mnt/timemachine`
o ai file `/users` reali. Nessuna porta pubblicata; rete bridge `Internal=true`.

Verificato:

- Credenziali sintetiche riutilizzate da configurazioni identiche, senza
  rigenerare password durante aggiornamento e rollback.
- Archiviazione di `/var/lib/samba` soltanto con tutti i server del test fermi.
  Nessuna copia di `/var/cache/samba` o `/run/samba`.
- Prima dell'avvio 4.23.13, confronto del contenuto dei file importati, UID,
  GID e mode con l'archivio originale: identici. Nessun dump o hash di password
  viene stampato. Gli archivi rimangono fuori dal repository, in directory privata.
- SID del server, SID dei due account, primary-group SID, UID/GID, mode delle
  directory e del file di prova, ACL POSIX: identici dopo aggiornamento e rollback.
- Accessi SMB, guest negato, isolamento fra utenti, round trip di file casuali
  da 1 MiB, stream SMB, xattr, rename/delete e pubblicazione Bonjour.
- File e stream preparati dalla 4.23.8 leggibili dalla 4.23.13.
- File e stream nuovi scritti dalla 4.23.13 leggibili dopo il ritorno alla 4.23.8.
- Database originali 4.23.8 invariati mentre la candidata usa la propria copia.
  Il rollback riavvia il container originale e **non** riapre TDB aggiornati
  con la vecchia versione.

Il volume dati sintetico viene riutilizzato nello stesso punto `/opt`, senza
copiarlo e con un solo server attivo alla volta. Questa scelta riproduce il
riutilizzo previsto dello storage esistente. Non verifica una migrazione dei
dati fra filesystem o una copia di ACL/xattr dei database in ogni ambiente.
Il confronto degli archivi controlla contenuto, tipi, link, UID/GID e mode;
non costituisce una verifica generale delle ACL/xattr dei file TDB reali.

## Mac — procedura ripetibile, un comando alla volta

Prerequisiti: le immagini locali ARM64 `reference-4.23.8` e `candidate-4.23.13`
già qualificate, e il contesto Docker `colima`. La procedura non scarica immagini.
Lanciare dalla radice del repository.

```sh
python3 lab/state-transfer.py prepare
```

Il comando stampa una directory privata in `/private/tmp`. Memorizzare il
percorso effettivamente stampato (il valore seguente è un segnaposto):

```sh
TM_STATE_TEST_DIR='/private/tmp/percorso-stampato-da-prepare'
```

Baseline: avvio, seed e verifiche; poi arresto e archiviazione offline:

```sh
python3 lab/state-transfer.py baseline --directory "$TM_STATE_TEST_DIR"
```

Candidata: import offline, confronto prima dell'avvio, accessi e identità,
scrittura di nuovi dati, arresto e controllo dei database originali:

```sh
python3 lab/state-transfer.py upgrade --directory "$TM_STATE_TEST_DIR"
```

Rollback con database originali, lettura dei dati vecchi e nuovi, arresto:

```sh
python3 lab/state-transfer.py rollback --directory "$TM_STATE_TEST_DIR"
```

Usare il driver, che controlla fase, contesto, progetto e stato dei container.
Non avviare direttamente entrambi i servizi di `compose.state.yaml`.
Ogni fase conserva container e volume sintetico; in caso di fallimento dopo
l'avvio, ferma il server coinvolto. Un test fallito non è una fase completata.
Le fasi fallite che hanno già prodotto archivi richiedono una nuova sessione
`prepare`: i file esistenti non vengono sovrascritti silenziosamente.

`fixture.tar` contiene solo credenziali casuali del laboratorio. Gli archivi
dei database includono materiale di autenticazione sintetico: non stamparli,
non caricarli e non committarli. Il codice non legge le credenziali di produzione.

## Correzioni emerse durante la prova

Il Compose con entrypoint sostituito richiede il comando s6 esplicito; senza
esso il container terminava normalmente durante il bootstrap. Il test attende
ora sia i processi sia l'autenticazione, poi la pubblicazione Bonjour con
tentativi limitati. Al primo rollback Bonjour non era ancora registrato quando
il controllo terminava; dopo la correzione dell'attesa il rollback completo è
stato superato. Non sono state cambiate le impostazioni del server reale.

## Verifiche sul backup reale, distinte dalla candidata

Il 26 ottobre Time Machine sul Mac ha riconosciuto cinque backup completati
del server 4.23.8; APFS ha confermato le cinque snapshot corrispondenti.
Da quella delle 06:56 è stato recuperato con `tmutil restore` un file del
progetto in una cartella temporanea. `cmp` ha confermato l'identità del file
recuperato con la snapshot e con l'originale corrente.

Provenienza verificata: snapshot del volume APFS → immagine sparsebundle
aperta dal mount SMB → file sul filesystem del Raspberry Pi. La prova non
ha usato una snapshot locale del disco interno del Mac. Il mount temporaneo
in lettura è stato successivamente verificato assente.

Questo dimostra il recupero di quel file dai nuovi backup. Non certifica tutti
i file, lo storico precedente al 26 ottobre o il comportamento della 4.23.13
con il client Time Machine macOS.

## Gate ancora aperti

- Client macOS contro candidata isolata: la prova di dati, metadati Apple e
  nuova sessione SMB è ora superata (vedi `NATIVE_CLIENT.md`). Restano guasti
  con handle aperti e un backup Time Machine di prova concordato.
- Riconferma e conservazione dell'identità Bonjour e dello stato del server
  attualmente attivo, che è diverso dal container descritto originariamente
  nell'handoff. La vecchia immagine e il vecchio container non sono più presenti.
- Rollback di produzione basato sul container attuale e sulla sua immagine;
  copia coerente dei database reali soltanto durante un fermo autorizzato.
- Compatibilità dei TDB reali e continuità della destinazione Time Machine:
  SID e nomi share da soli non bastano a dimostrarla.

Nessun cutover è incluso o autorizzato da questa procedura.
