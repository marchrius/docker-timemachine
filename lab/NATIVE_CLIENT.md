# Client SMB nativo macOS — laboratorio

## Esito verificato il 26 ottobre 2026

La candidata **Samba 4.23.13** è stata collaudata con il client SMB del Mac,
oltre ai precedenti test Linux e al trasferimento offline dello stato.
Nessun accesso al Raspberry Pi o ai backup reali durante questa procedura.

Esiti osservati:

- Negoziazione `SMB_3.1.1`, firma corrente `AES_128_GMAC`.
- `OS_X_SERVER=TRUE` e `FILE_LEASING_SUPPORTED=TRUE` riportati da `smbutil`.
  Il flag leasing non dimostra da solo il recupero di handle dopo un guasto.
- File casuale da 1 MiB scritto, sincronizzato e letto tramite il mount macOS.
- Xattr sintetico, FinderInfo e resource fork scritti e riletti.
- Rinomina del file mantenendo dati, xattr e resource fork.
- Smontaggio e nuovo mount con nuova sessione SMB: dati e metadati riletti.
- Mount di Matteo sulla share di Anna e mount guest rifiutati.
- Payload letto anche direttamente nel container e confrontato con quello del
  client, senza dipendere soltanto dalla cache macOS; proprietario `1001:1000`.
- Mount temporanei rimossi; candidata e proxy fermati a fine prova. Volume e
  rapporti sintetici conservati per ispezione, fuori dal repository.

Il test riguarda dati sintetici nuovi. Non è ancora un backup Time Machine
completo, un test di ripristino dalla candidata o un test di continuità degli
sparsebundle esistenti.

## Rete e credenziali

Samba rimane esclusivamente su un bridge Docker `internal: true`, senza porte
pubblicate. Un proxy TCP `socat`, senza mount o configurazioni utenti, collega
il bridge interno a un bridge client separato. Solo il proxy pubblica una
porta TCP assegnata da Docker, esplicitamente su `127.0.0.1`.

Il driver verifica immagini per ID, appartenenza al progetto, assenza di
pubblicazioni dirette da Samba, binding esclusivamente loopback e bridge interno.
La connessione del Mac usa `127.0.0.1:<porta>`; nessun hostname/IP di produzione,
rete host, macvlan o pubblicazione Bonjour sulla LAN.

La prima topologia, con pubblicazione direttamente dal container connesso
soltanto alla rete interna, non ha creato il binding effettivo. Il controllo
ha fermato il container. La topologia col proxy è stata poi verificata tramite
Docker e connessione dal Mac. Riferimenti Docker:

- https://docs.docker.com/engine/network/drivers/bridge/
- https://docs.docker.com/engine/network/port-publishing/

Le credenziali casuali sono generate dall'init del laboratorio e lette in
memoria. Il mount di sistema riceve una URL con queste sole credenziali finte:
non usare questa procedura per password reali. Il driver oscura le password
negli errori e nei rapporti. Non modifica Portachiavi, `nsmb.conf`, impostazioni
Time Machine o configurazioni utenti reali.

## FinderInfo: contenuto salvato e vista AAPL

Il primo confronto con 32 byte costanti ha evidenziato una differenza dopo la
creazione del resource fork. La diagnosi ha distinto due rappresentazioni:

- Lo stream `AFP_AfpInfo` sul backend conservava esattamente i 32 byte scritti.
- Il client macOS poteva restituire una vista AAPL con quattro byte della data
  ricostruiti dalla nascita del file.

Il test verifica separatamente entrambe: confronto esatto di tutti i 32 byte
salvati e, lato client, ammissione esclusivamente del valore originale oppure
della vista con quella sola data esattamente coerente con `st_birthtime`.
Nessun altro byte viene ignorato e il resource fork resta confrontato integralmente.
Il timestamp di nascita non è oggetto di un test generale di mutazione dei tempi.

Fonti primarie consultate per la ricostruzione FinderInfo e la data AAPL:

- https://github.com/apple-oss-distributions/SMBClient/blob/main/kernel/netsmb/smb_2.h
- https://github.com/apple-oss-distributions/SMBClient/blob/main/kernel/netsmb/smb_smb_2.c
- https://github.com/samba-team/samba/blob/v4-23-stable/source3/modules/vfs_fruit.c

Gli xattr sono gestiti con `/usr/bin/xattr`: il Python del Mac usato nella
prova non espone `os.setxattr`. I primi tentativi diagnostici sono rimasti nel
volume sintetico; non sono stati eliminati file AppleDouble dai backup reali.

## Rifiuti di accesso

macOS può descrivere il rifiuto della share come timeout. Il test non accetta
un timeout generico come prova di isolamento. Richiede un errore esplicito di
autenticazione/accesso del client oppure un nuovo messaggio server che neghi
quell'utente su quella share, confrontando il numero di eventi prima e dopo
il tentativo. Sono verificati sia cross-user sia guest; nessun mount inatteso
viene considerato un successo del test.

## Mac — procedura, un comando alla volta

Prerequisiti: contesto Docker `colima`, candidata ARM64 già compilata,
strumenti SMB e xattr di macOS. Dalla radice del repository, costruire il
piccolo proxy di test sulla stessa base Alpine stabile fissata per digest:

```sh
docker --context colima build -f lab/Dockerfile.proxy -t timemachine-samba-lab:loopback-proxy .
```

Preparare una sessione nuova:

```sh
python3 lab/native-client.py prepare
```

Usare il percorso privato effettivamente stampato; il valore qui sotto è un
segnaposto:

```sh
TM_NATIVE_TEST_DIR='/private/tmp/percorso-stampato-da-prepare'
```

Avvio e controlli rete/server, senza montare ancora la share dal Mac:

```sh
python3 lab/native-client.py start --directory "$TM_NATIVE_TEST_DIR"
```

Prova nativa, montaggi sotto la directory temporanea e relativi smontaggi:

```sh
python3 lab/native-client.py probe --directory "$TM_NATIVE_TEST_DIR"
```

Arresto del solo progetto di test, consentito quando i mount di prova sono assenti:

```sh
python3 lab/native-client.py stop --directory "$TM_NATIVE_TEST_DIR"
```

Il driver usa il mount SMB di sistema e chiede una nuova sessione, senza
prompt password. I mount sono `nobrowse,soft` per questa prova controllata.
Queste opzioni limitano la portata del risultato: non qualificano il recupero
di una sessione Time Machine durante disconnessioni o sospensioni del Mac.
In caso di errore il probe tenta lo smontaggio dei propri soli mount;
la fase stop rifiuta di arrestare il progetto se uno rimane presente.

`manifest.json` registra progetto, immagini e porta; `statshares.txt` conserva
il rapporto completo del client. I rapporti negativi hanno password oscurate.
Solo le prove concluse stampano `PASS: probed`; `stop` è una fase di pulizia,
non trasforma una prova fallita in una qualificazione riuscita.

## Prossime verifiche

Restano da progettare ed eseguire un backup Time Machine di prova sulla
candidata, incrementale e recupero, e i test di interruzione con file aperti
e durable handles. Prima di modificare destinazioni o preferenze del Mac,
concordare spazio, sorgente di prova e impatto sulla pianificazione esistente.
La conservazione dell'identità reale e il rollback di produzione richiedono
ancora un piano sul container attuale e copie coerenti durante un fermo autorizzato.
Nessuna migrazione è inclusa in questa procedura.
