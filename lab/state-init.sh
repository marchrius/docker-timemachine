#!/bin/sh
set -eu
[ "${TIMEMACHINE_ISOLATED_LAB:-}" = yes ]
[ "${STATE_TRANSFER_LAB:-}" = yes ]
[ "$(hostname)" = tm-state-lab ]

# First reference boot creates only synthetic users and data. Later boots
# replay the same synthetic configuration, never fresh/random passwords.
if [ ! -f /lab/state-fixture.tar ]; then
  [ "${EXPECTED_SAMBA_VERSION}" = 4.23.8 ]
  exec /bin/sh /lab/init.sh "$@"
fi
umask 022
mkdir -p /run/dbus /run/samba
umask 077
mkdir -p /run/lab
tar -xpf /lab/state-fixture.tar -C /run/lab
umask 022
exec /entrypoint.sh "$@"
