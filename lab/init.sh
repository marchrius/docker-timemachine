#!/bin/sh
set -eu

[ "${TIMEMACHINE_ISOLATED_LAB:-}" = yes ] || {
  echo 'This initializer is for the isolated synthetic laboratory only.' >&2
  exit 1
}
umask 022
mkdir -p /run/dbus /run/samba
umask 077
mkdir -p /run/lab/users
for user in anna matteo; do
  case "$user" in
    anna) uid=1002; share='Time Machine di Anna'; limit=500G ;;
    matteo) uid=1001; share='Time Machine di Matteo'; limit=1300G ;;
  esac
  password=$(head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n')
  # Generated fixtures, never the real /users files or production passwords.
  cat > "/run/lab/users/$user.conf" <<EOF
TM_USERNAME=$user
TM_GROUPNAME=timemachine
PASSWORD=$password
SHARE_NAME='$share'
VOLUME_SIZE_LIMIT=$limit
TM_UID=$uid
TM_GID=1000
EOF
  cat > "/run/lab/$user.auth" <<EOF
username = $user
password = $password
EOF
  # Only paths in the lab's synthetic named volume are touched.
  mkdir -p "/opt/$user"
  chown "$uid:1000" "/opt/$user"
  chmod 2755 "/opt/$user"
done
unset password
umask 022
exec /entrypoint.sh "$@"
