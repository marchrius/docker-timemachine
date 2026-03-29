#!/bin/sh

# Prepare D-Bus
if [ -e /var/run/dbus/pid ]; then rm -f /var/run/dbus/pid; fi
mkdir -p /var/run/dbus
chown messagebus:messagebus /var/run/dbus
dbus-uuidgen --ensure

# Set password from environment variable (docker run -e "TIMEMACHINE_PASSWORD=asdf")
if [ -n "$TIMEMACHINE_PASSWORD" ]; then
    echo "Setting password from environment variable"
    echo "timemachine:$TIMEMACHINE_PASSWORD" | chpasswd
elif [ -n "$PASSWORD" ]; then
    # backward compatibility
    echo "Setting password from deprecated PASSWORD variable"
    echo "timemachine:$PASSWORD" | chpasswd
else
    echo "ERROR: TIMEMACHINE_PASSWORD environment variable is required" >&2
    exit 1
fi

# Start supervisord
exec /usr/bin/supervisord -c /etc/supervisord.conf
