# Adattamento della patch Alpine per Samba 4.23.13

La patch `musl_uintptr.patch` originale rimane in `../vendor/alpine-samba`.
Nel sorgente Samba 4.23.13 verificato con firma ufficiale, il guard di
`third_party/cmocka/cmocka.h` include già `!defined(HAVE_UINTPTR_T)`.
La patch della ricetta 4.23.8 non si applica più a quella riga.

Questa copia adatta soltanto il contesto e il guard risultante per preservare
`HAVE_UINTPTR_T` e aggiungere il controllo Alpine `__DEFINED_uintptr_t`.
Il secondo hunk resta invariato. Non modifica il comportamento SMB/VFS.
Il checksum dell'adattamento è fissato in `build-packages.sh` e sostituisce
solo il checksum di questa patch nella ricetta di build temporanea.
