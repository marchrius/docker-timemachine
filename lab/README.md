# Laboratorio Time Machine / Samba

## Stato e confini

Mac: backup automatici verificati abilitati (`AutoBackup=1`, 25 ottobre 2026).
Questo non prova l'esito dell'ultimo backup. Raspberry Pi: nessuna modifica.

Branch di lavoro: `timemachine-samba-lab`, base upstream `ca169df`.
`Dockerfile.baseline` serve a collaudare il laboratorio con Samba 4.23.8;
non costituisce il sostituto aggiornato né una build bit per bit riproducibile.
Conserva entrypoint e servizi s6 del repository, senza le modifiche del branch
`smb_parameters`: non cambiare contemporaneamente versione Samba e semantica SMB.

Rete Docker interna, nessuna porta pubblicata, nessuna rete host/macvlan,
nessun indirizzo 192.168.3.54, nessun mount del RAID o degli utenti reali.
Solo volume sintetico e credenziali casuali effimere in `/run/lab`.
L'inizializzatore modifica ownership/mode esclusivamente delle cartelle sintetiche.
Non usare questo Compose per produzione e non collegarlo alla LAN.

## Esito verificato il 25 ottobre 2026 — Mac / Colima ARM64

- Build completata: Alpine 3.24.3, Samba 4.23.8, digest base fissato nel Dockerfile.
- Compose valido e test `smoke.sh` completato con `PASS`.
- Confermati UID/GID, due account, sintassi Samba, quattro processi attivi,
  accessi autenticati, guest negato, isolamento fra utenti, round trip dei dati,
  proprietario dei file, xattr, rename/delete e record Bonjour di entrambe le share.
- Ispezione Docker: `Ports={}`, solo named volume sintetico su `/opt`,
  rete `bridge` con `Internal=true`, subnet `172.22.0.0/16`.
- Risolti nel laboratorio un errore di umask dell'inizializzatore e un controllo
  troppo restrittivo sulle maiuscole del nome Bonjour. EntryPoint upstream invariato.
- Container di laboratorio fermato dopo i test; immagine e volume conservati.
- Nessun comando eseguito sul Raspberry Pi, nessun accesso agli sparsebundle.
- Non ancora eseguiti: build 4.23.13, prova riavvio/idempotenza, test macOS
  degli stream Apple e Time Machine, continuità identità e rollback offline.

## Mac — un comando alla volta

Eseguire dalla radice del repository, verificando l'esito di ogni comando.
Docker deve usare Colima locale ARM64, non un contesto remoto.

```sh
docker --context colima compose -f lab/compose.yaml config --quiet
```

```sh
docker --context colima compose -f lab/compose.yaml build reference
```

```sh
docker --context colima compose -f lab/compose.yaml up -d reference
```

```sh
docker --context colima compose -f lab/compose.yaml exec -T reference sh /lab/smoke.sh
```

Una successiva ripetizione dopo riavvio del solo laboratorio verifica
che l'inizializzazione riparta. Non applicare questi comandi al server reale.
Per fermare il laboratorio, preservando il volume sintetico:

```sh
docker --context colima compose -f lab/compose.yaml stop reference
```

I test verificano accessi SMB reali, guest negato, isolamento bidirezionale,
scrittura/lettura/rename/delete di file sintetici, UID/GID, xattr Linux,
configurazione e processi, registrazione Avahi nella rete isolata.
Non verificano ancora gli stream Apple tramite client macOS, Bonjour sulla LAN,
una sessione Time Machine, riconnessioni/durable handles o continuità degli sparsebundle.

## Candidato aggiornato — da costruire e qualificare

Release 4.23.13 confermata nelle fonti ufficiali:
https://www.samba.org/samba/history/samba-4.23.13.html
Correzione 15995 riportata nella 4.23.9:
https://www.samba.org/samba/history/samba-4.23.9.html
Non è una diagnosi della causa degli errori osservati.

Ricetta Alpine 3.24, attualmente 4.23.8:
https://github.com/alpinelinux/aports/blob/3.24-stable/main/samba/APKBUILD
Upstream container:
https://github.com/mbentley/docker-timemachine

Percorso preferito da valutare: ricostruire i pacchetti Alpine della suite
4.23.13 su base 3.24, usando ricetta e patch Alpine revisionate e fissate a commit.
Prima di costruire: verificare firma sorgente Samba, bloccare digest base,
hash sorgenti/patch, dipendenze e opzioni di compilazione. Installare librerie,
tool e moduli VFS della stessa build; non copiare soltanto smbd e non usare Edge.
Documentare l'onere di manutenzione degli aggiornamenti di sicurezza.
La fattibilità e compatibilità ABI non sono ancora dimostrate.

## Raspberry Pi — prossime verifiche solo in lettura

Ricontrollare per nome `timemachine-core-1`, non per tag/ancestor:
versione e opzioni build Samba, immagine ID, rete/macvlan, mount, UID/GID/mode,
configurazione effettiva inclusi default, SID locale, hostname/mDNS e Avahi.
Non stampare Docker environment completo, file `/users/*.conf` o hash passdb.
Acquisire soltanto configurazioni prive di segreti e dati identificativi necessari.
Non leggere/modificare TDB attivi con operazioni invasive.

## Prima del cutover — serve autorizzazione esplicita

Non è incluso alcun Compose di produzione o script di migrazione eseguibile.
La compatibilità perfetta resta un obiettivo da verificare, non una garanzia.

1. Qualificare candidato ARM64, librerie/moduli e comportamento su dati sintetici;
   confrontare testparm completo, UID/GID, ACL/xattr, autenticazione, SID e Avahi.
2. Provare un backup Time Machine nuovo su spazio esclusivamente di prova,
   con identità chiaramente distinta. Non selezionare il laboratorio al posto
   della destinazione attuale senza concordare il test.
3. Pianificare un fermo autorizzato e verificare assenza di scritture Time Machine.
   Solo a Samba fermo acquisire copia coerente di configurazioni e stato necessario,
   preservando attributi e permessi. Archiviare segreti fuori dal repository.
4. Provare migrazione/rollback dello stato su copie offline. Non importare
   lock/leasing/cache runtime. Non presumere TDB retrocompatibili dopo un upgrade.
   Tenere il vecchio container e i suoi database intatti per il rollback.
5. Autorizzazione separata al cutover: un solo server scrivente sul RAID,
   stessi path/share/UID/GID e identità verificata, nessuna riscrittura permessi.
6. Verificare riconoscimento della destinazione dal Mac, backup incrementale,
   storico accessibile, pianificazione attiva e log. Arrestare il solo candidato
   e ripristinare il vecchio container se le verifiche falliscono.

Immagine storica per rollback da riconfermare: `7404a92fd48c`, non il tag mobile.
Una copia fatta prima dell'upgrade non va sovrascritta dai database aggiornati.
I nomi share/IP da soli non provano l'identità Time Machine.
`fruit:time machine max size` è reporting, non una quota rigida.
Non eliminare file di backup o correggere permessi in modo ricorsivo.
