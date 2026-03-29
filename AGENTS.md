# Project Management and Automation Rules

## Docker Image Versioning (Auto-increment)

- The `VERSION` file in the root of the repository holds the current version in `MAJOR.MINOR.PATCH` format.
- Version bumping is handled automatically by GitHub Actions on every push to `main`.
- The version increment follows these rules, based on commit messages and following [Conventional Commits 1.0.0](https://www.conventionalcommits.org/en/v1.0.0/):
  - If any commit message contains a `BREAKING CHANGE` footer or an exclamation mark after the type/scope (e.g., `feat!:` or `fix!:`), increment the **MAJOR** version and reset MINOR and PATCH to 0.
  - If any commit message type is `feat`, increment the **MINOR** version and reset PATCH to 0.
  - If any commit message type is `fix`, increment the **PATCH** version.
  - If multiple types are present, the highest priority is: `BREAKING CHANGE` (major) > `feat` (minor) > `fix` (patch).
- After incrementing, the new version is committed and pushed automatically.
- The Docker image is tagged with both `latest` and the new version (e.g., `1.2.3`).
- All commit messages must follow the Conventional Commits 1.0.0 specification for automated versioning to work correctly.

## Docker & Compose

- The main Dockerfile is `Dockerfile.modern` (Alpine, supervisord, env password).
- Use `docker-compose.yml` for local development and deployment.
- The user password for Time Machine is set via the `TIMEMACHINE_PASSWORD` environment variable (required). The legacy `PASSWORD` variable is supported for backward compatibility.
- The backup volume is mapped to `/backup`.
- The container must run with `--net=host` for proper Bonjour/Avahi/ZeroConf support.

## Security

- No default password: the container will exit if no password is provided.
- Only the files needed for the modern Alpine-based setup are kept in the repository. Legacy scripts and folders are removed.

## CI/CD

- GitHub Actions workflow builds and pushes the Docker image to GitHub Container Registry (ghcr.io) on every push or PR to `main`.
- The workflow reads and updates the `VERSION` file according to the rules above.
- The workflow uses `stefanzweifel/git-auto-commit-action` for automatic version commits.

## Documentation

- The README must always be in English and reflect the latest usage, environment variables, and project structure.
- All new features, fixes, and breaking changes must be documented in the commit messages using Conventional Commits.
