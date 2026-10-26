# Candidata Samba 4.23.13 — laboratorio ARM64

Solo Mac / Docker context `colima`. Nessuna istruzione di cutover eseguibile.
Il Compose usa una rete interna senza porte pubblicate e un volume sintetico
distinto per ciascuna versione. Non aggiungere mount dei backup o `/users` reali.

## Provenienza e verifica

- Base Alpine 3.24.3, digest `be2656061b536c1883c4034790e21d0a09c5aaaf51968b89368a3c0371ea2c9a`.
- Tarball ufficiale `https://download.samba.org/pub/samba/stable/samba-4.23.13.tar.gz`.
- Firma ufficiale del tar **non compresso**, verificata con fingerprint
  `81F5E2832BD2545A1897B713AA99442FB680B620`.
- SHA-512 dell'archivio firmato fissato nel Dockerfile:
  `3c86afef17fd0f776356014b689e9ef9caf469f1dde8a446e34d4fb4b275e7a6286d1a6a762d5804174a91833f57806c757ca45b072d04307aa9cc3560492716`.
- Ricetta Alpine e file originali in `vendor/alpine-samba`, con origine fissata
  al commit `4e1bac0beab79f432056cb63312c4d94491a3dc0` (vedi `ORIGIN`).
- Modifiche applicate nella copia di lavoro del builder: versione 4.23.13,
  checksum del sorgente verificato e una patch musl adattata, descritta in
  `patches/README.md`. Nessun cambiamento di policy SMB/Time Machine.
- Percorsi, opzioni configure, ripartizione pacchetti e librerie della ricetta
  Alpine conservati. Nessun repository Edge, nessun binario Samba 4.23.8
  copiato nel runtime candidato.

La firma Samba autentica il sorgente; la firma APK locale serve a verificare
il trasporto dei pacchetti tra builder e runtime della stessa build. Non è
una firma ufficiale Alpine. La chiave privata temporanea rimane nel builder
e nella cache Docker locale; il runtime riceve soltanto la chiave pubblica.
Non pubblicare lo stage builder o esportarne cache/layer con la chiave privata.

## Dipendenze e aggiornamenti

`APKBUILD` elenca tutte le build dependencies (compilatori tramite alpine-sdk,
Python/Perl, ACL/attr, GnuTLS, talloc/tdb/tevent, PAM, LDAP, CUPS e altre).
Il runtime installa server, client e common-tools della stessa build; APK
risolve le loro librerie coerenti dal repository locale firmato, più attr,
Avahi, D-Bus e s6 dalla base stabile. Non copiare manualmente il solo smbd.

Il manifest dei pacchetti runtime e la prova di verifica del sorgente vengono
conservati nell'immagine in `/usr/share/timemachine-lab/`.
Il log completo include le versioni delle dipendenze di build installate.
Le dipendenze Alpine non sono ancora archiviate/fissate individualmente:
questa build **non è riproducibile bit per bit**. Per una release da distribuire
occorre conservare pacchetti, indici, manifest e immagine per digest, oltre a
definire la gestione delle nuove release di sicurezza. Non fare `apk upgrade`
su un container candidato qualificato: ricostruire, ritestare e confrontare.

La ricetta Alpine usa `options="!check"` e disabilita alcuni test C upstream
per compatibilità. Il successo di abuild non equivale al superamento della
suite upstream Samba. I nostri test SMB sono una verifica distinta.

## Mac — comandi singoli dalla radice del repository

Build della sola candidata, senza avvio:

```sh
python3 lab/build-candidate.py
```

Lo script salva il log completo in una directory temporanea del Mac e ne
stampa il percorso. Usa due job di compilazione per default. Durante il
processo Docker mantiene attivo `caffeinate -i -w`, se disponibile, per
evitare la sola sospensione per inattività. L'asserzione termina con Docker.

Avvio del solo laboratorio candidato, dopo build riuscita:

```sh
docker --context colima compose -f lab/compose.yaml up -d candidate
```

Il controllo preliminare del runtime si può eseguire senza rete o volumi:

```sh
docker --context colima run --rm --network none --entrypoint /bin/sh timemachine-samba-lab:candidate-4.23.13 /lab/verify-runtime.sh
```

Test funzionali su dati sintetici:

```sh
docker --context colima compose -f lab/compose.yaml exec -T candidate sh /lab/smoke.sh
```

Arresto del solo laboratorio candidato, conservando i dati sintetici:

```sh
docker --context colima compose -f lab/compose.yaml stop candidate
```

## Gate ancora necessari prima della produzione

Confronto testparm completo, verifica runtime, accessi/stream SMB e riavvio
sintetico sono stati eseguiti con successo; esiti dettagliati in `README.md`.
Anche importazione offline dello stato e rollback sintetico sono stati
verificati: vedere `STATE_TRANSFER.md` per ambito e limiti.
Client macOS nativo, metadati Apple e nuova sessione SMB sono stati verificati
su dati sintetici: vedere `NATIVE_CLIENT.md`.
Restano backup Time Machine nuovo
su destinazione sintetica e test di riconnessione/durable handles.
Questi controlli non dimostrano ancora la continuità degli sparsebundle reali.

Sul Raspberry Pi sono ancora da riconfermare configurazione e identità
effettive, solo con comandi di lettura selettivi e senza stampare segreti.
Trasferimento SID/stato e compatibilità dei TDB richiedono copie coerenti
offline e prove dedicate; preservare i database del vecchio container
senza farli aprire da una Samba nuova durante la preparazione.

La migrazione richiede autorizzazione esplicita separata. Non fermare il
server attivo, non montare i backup in scrittura, non cambiare permessi o
destinazione Time Machine durante la qualificazione.
