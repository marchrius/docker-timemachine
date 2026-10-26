# Daily Samba patch images

The `Samba patch images` workflow checks the official Samba stable directory
daily at **04:17 UTC**. The tracked series is **4.23.x**, with minimum **4.23.13**
in `samba-series.json`. Only canonical stable tarballs with corresponding
detached signatures qualify. Versions are compared numerically; prereleases
and other major/minor series are excluded.

For an unpublished patch, the workflow:

1. Computes the tarball SHA-512 from the official HTTPS source.
2. Builds the `production` target on GitHub's native `ubuntu-24.04-arm` runner.
   The Docker build independently verifies the tarball's GPG signature against
   the pinned Samba signing fingerprint and checks the supplied SHA-512.
3. Reuses the vendored Alpine packaging and checked adaptation for that patch.
   Patch/application or packaging errors fail the build.
4. Verifies the installed Samba version, package consistency, VFS libraries and
   absence of builder keys/compiler. Runs the production entrypoint and SMB
   smoke tests with isolated synthetic users/data.
5. Only after those checks, publishes the tested image to
   **`ghcr.io/marchrius/timemachine:4.23.Y`** (`linux/arm64`).

Published version tags are not overwritten. If the exact tag already exists,
daily and manual checks skip compilation and publication. Code-changing pushes
on the default branch and pull requests also build existing releases for CI,
but still do not overwrite an existing image tag. Feature-branch pushes run
the discovery/unit checks; publication is restricted to the default branch.
No floating `latest` tag and no automatic Raspberry Pi deployment are included.

Package tag lookup uses the authenticated GitHub Packages API, with pagination.
Only a package 404 is treated as initial publication; authentication errors,
rate limits and server/network failures fail the check rather than pretending
that an existing image is missing. The workflow uses only its automatic
`GITHUB_TOKEN`: `contents: read`, package read for discovery, package write for
the ARM64 build/publish job. It requires no personal token or Docker Hub secret.

## Activation and first publication

GitHub scheduled workflows must be on the repository's default branch
(`master`). In a fork, Actions may also need enabling in the Actions tab.
`workflow_dispatch` allows an immediate manual check once the workflow is on
the default branch; pushes changing relevant build/CI files trigger it too.

The first run bootstraps the latest 4.23 patch if it has no image tag yet.
GHCR packages are initially private by default: after first publication, make
the package public in GitHub package settings if anonymous pulls are wanted.
The image's OCI source label links it to this repository for Actions access.

GitHub can delay scheduled runs and disables scheduled workflows in inactive
public repositories after 60 days. Check Actions if updates stop arriving.

## Local checks (Mac)

```sh
python3 -B -m unittest discover -s ci -p 'test_*.py' -v
```

```sh
python3 -B ci/samba_release.py --discover-only
```

The Dockerfile's default version/checksum retain the qualified 4.23.13 build.
CI supplies both `SAMBA_VERSION` and `SAMBA_SHA512` explicitly. To change the
major/minor series, review the Docker version guards, packaging adaptations and
compatibility qualification; changing only the JSON series is insufficient.
The existing Mac restore/Time Machine tests remain manual qualification, not a
claim that the synthetic CI smoke test is a full macOS backup test.
