# docker-timemachine (Alpine, supervisord, env password)

Netatalk in Docker for Time Machine backups, now based on Alpine Linux, with process management via supervisord and user password set through environment variable.

## Usage Example

```sh
docker build -f Dockerfile.modern -t docker-timemachine-alpine .

docker run -e "TIMEMACHINE_PASSWORD=YourPassword" \
  -v /host/mnt/backup:/backup \
  -p 548:548 \
  --net=host \
  -d docker-timemachine-alpine
```

- **TIMEMACHINE_PASSWORD**: required, sets the password for the `timemachine` user.
- **PASSWORD**: supported for backward compatibility, prefer TIMEMACHINE_PASSWORD.
- If neither variable is set, the container will exit with an error.

Connect from macOS as user `timemachine` with the chosen password.

## Notes on Bonjour/Avahi/ZeroConf

Network discovery (Bonjour/Avahi) only works if the AFP daemon is on the same network as the client. Therefore, `--net=host` is required if you want the disk to appear in Finder. Alternatively, you can connect manually from Finder with `cmd+k` → `afp://hostname/`.

## What's new compared to the original version

- **Alpine base**: lighter and more up-to-date image.
- **supervisord**: robust process management (dbus, avahi, netatalk).
- **User password via env**: only through environment variable.
- **Security**: no default password.
- **Compatibility**: tested on recent macOS versions.

## References and inspiration

- https://github.com/arve0/timemachine (original)
- https://github.com/aequitas/timemachine
- https://github.com/bySabi/dockerfiles/tree/master/nas
- https://bitbucket.org/lonix/plex/src

---

For advanced configuration, see `afp.conf` and the Netatalk documentation.
