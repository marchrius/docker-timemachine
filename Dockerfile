# Modern Alpine-based Dockerfile for Time Machine
FROM alpine:latest

LABEL org.opencontainers.image.authors="Arve Seljebu arve.seljebu@gmail.com"

# Install dependencies
RUN apk update && apk add --no-cache \
    netatalk \
    avahi \
    dbus \
    supervisor \
    && rm -rf /var/cache/apk/*

# Add user
RUN adduser -h /backup -D timemachine

# Time machine volume
VOLUME /backup

# Port
EXPOSE 548

# AFP config
COPY afp.conf /etc/netatalk/afp.conf

# Supervisord config
COPY supervisord.conf /etc/supervisord.conf

# Entrypoint script
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Start supervisord as PID 1
ENTRYPOINT ["/entrypoint.sh"]
