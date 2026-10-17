---
name: containerize-service
description: "Author or improve a Dockerfile, .dockerignore, and Compose setup for a service with multi-stage builds, digest-pinned base images, a non-root user, signal-safe startup, health checks, no secrets in layers, and image scanning plus an SBOM. Use when containerizing a service, slimming or hardening an image, or setting up local development with Compose. Not for reviewing existing infrastructure (use the infrastructure-review skill) or build pipelines (use the ci-pipeline skill)."
---

# Containerize Service

Produce a small, reproducible, non-root image and a local Compose setup that
behave the same on every machine. The stance is **build locally, ship with
approval**: build, run, and scan the image here, but never push it or deploy it
without the user's explicit go-ahead.

## When to use

- A service has no Dockerfile, or its image is large, runs as root, or rebuilds
  slowly.
- Developers need a Compose setup with the service and its local dependencies.
- An image scan or review flagged base image, user, secret, or layer problems.

## When not to use

- Reviewing existing Dockerfiles, manifests, or cloud configuration: use the
  `infrastructure-review` skill, or delegate to the `infrastructure-reviewer`
  subagent.
- Building, tagging, and publishing images in CI: use the `ci-pipeline` skill.
- Rolling the image out to an environment: use the `deployment-safety` skill.
- A secret has already been baked into a pushed image: use the
  `secret-leak-response` skill first.
- Kubernetes manifests, probes, and rollout settings for the image: use the
  `kubernetes-workloads` skill.

## Inputs to gather

Discover these from the repository before asking. Ask the user only about what
remains ambiguous and would change the result.

- Runtime and version (`.nvmrc`, `engines`, `.python-version`,
  `pyproject.toml`), the lockfile, the build command, and the start command.
- The port the service listens on, required environment variables, files it
  writes at runtime, native dependencies, and a health endpoint if one exists.
- Existing Dockerfile, Compose file, CI image build, and registry conventions.
- Where the image runs (Compose, Kubernetes, a managed container service), which
  affects health checks and user ID requirements.

## Workflow

1. **Choose the base image.** Use an official, minimal image matching the
   project's runtime version (`-slim`, distroless, or Alpine if the project's
   native dependencies work with musl). Pin tag plus digest
   (`node:24-slim@sha256:...`). Resolve the current digest yourself, for example
   with `docker buildx imagetools inspect node:24-slim`; never copy a digest
   from documentation or an example. Suggest automated digest updates
   (Dependabot or Renovate) so pinning does not freeze security fixes.
2. **Split into stages.** A dependency stage, a build stage with dev tools, and
   a runtime stage that copies only production dependencies and build output.
   Copy the manifest and lockfile before the source so dependency layers stay
   cached when only code changes.
3. **Install from the lockfile** with lifecycle scripts disabled where possible:
   `npm ci --ignore-scripts`, `pnpm install --frozen-lockfile --ignore-scripts`,
   `pip install --require-hashes -r requirements.txt`, or `uv sync --frozen`. If
   a native package needs its install script, allow that one package explicitly
   rather than re-enabling all scripts. Use BuildKit cache mounts for package
   caches instead of leaving them in layers.
4. **Write `.dockerignore`** before relying on `COPY . .`: exclude `.git`,
   `.env*`, `node_modules`, virtual environments, build output, coverage, and
   local logs. This keeps secrets and stale artifacts out of the build context.
5. **Run as non-root with a fixed numeric UID and GID** (for example 10001), set
   with `USER 10001:10001` so platforms that check `runAsNonRoot` can verify it.
   Leave application files owned by root and readable, so the process cannot
   modify its own code. Give it explicit writable paths (a volume or `/tmp`) and
   prefer a read-only root filesystem at runtime.
6. **Start so signals arrive.** Use exec-form `CMD` or `ENTRYPOINT`
   (`["node", "dist/server.js"]`), not shell form, which wraps the process in
   `/bin/sh` and can swallow `SIGTERM`. A process running as PID 1 ignores
   `SIGTERM` unless it installs a handler, so handle it in the application for
   graceful shutdown, or run with an init (`docker run --init`, Compose
   `init: true`, or `tini`). Make the server listen on `0.0.0.0` inside the
   container, not `127.0.0.1`.
7. **Add a health check and expose only needed ports.** The check calls a cheap
   endpoint without tools the image lacks (slim images often have no `curl`).
   Kubernetes ignores the Dockerfile `HEALTHCHECK`; define probes there.
   `EXPOSE` documents the listening port; publish ports at run time.
8. **Keep secrets out of layers.** Never pass secrets through `ARG` or `ENV`;
   they persist in image metadata and history. Use a BuildKit secret mount for
   build-time credentials, for example
   `RUN --mount=type=secret,id=npmrc,target=/root/.npmrc npm ci --ignore-scripts`
   built with `docker build --secret id=npmrc,src=$HOME/.npmrc .`, and inject
   runtime secrets from the platform's secret store.
9. **Make builds reproducible:** pinned digests and lockfiles, no
   `apt-get upgrade` (rebuild on a newer base instead), `--no-install-recommends`
   for OS packages with the apt lists removed in the same layer, and no
   downloads of unversioned artifacts.
10. **Scan and inventory** the built image (see Verification), and fix or
    document findings per the project's vulnerability policy.
11. **Add Compose for local development** with named volumes for data, env files
    that are not committed (commit a `.env.example` instead), health-gated
    `depends_on`, and ports bound to `127.0.0.1`.

## Worked example (illustrative Node.js service)

```dockerfile
# syntax=docker/dockerfile:1
# Pin by digest before use: resolve with `docker buildx imagetools inspect
# node:24-slim`, then set NODE_IMAGE=node:24-slim@sha256:<resolved digest>.
ARG NODE_IMAGE=node:24-slim

FROM ${NODE_IMAGE} AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN --mount=type=cache,target=/root/.npm \
    npm ci --omit=dev --ignore-scripts

FROM ${NODE_IMAGE} AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN --mount=type=cache,target=/root/.npm \
    npm ci --ignore-scripts
COPY . .
RUN npm run build

FROM ${NODE_IMAGE} AS runtime
ENV NODE_ENV=production
WORKDIR /app
RUN groupadd --gid 10001 app \
 && useradd --uid 10001 --gid app --no-create-home --shell /usr/sbin/nologin app
COPY --from=deps /app/node_modules ./node_modules
COPY --from=build /app/dist ./dist
COPY package.json ./
USER 10001:10001
EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=3s --start-period=15s --retries=3 \
  CMD ["node", "-e", "fetch('http://127.0.0.1:3000/healthz').then(r => process.exit(r.ok ? 0 : 1)).catch(() => process.exit(1))"]
CMD ["node", "dist/server.js"]
```

A matching `.dockerignore`:

```text
.git
.env*
node_modules
dist
coverage
*.log
```

And a local-only `compose.yaml`:

```yaml
services:
  api:
    build:
      context: .
      target: runtime
    init: true
    env_file: .env # not committed; commit .env.example instead
    ports:
      - "127.0.0.1:3000:3000"
    depends_on:
      db:
        condition: service_healthy
  db:
    image: postgres:17 # pin by digest, as for the service image
    environment:
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?set POSTGRES_PASSWORD in .env}
    volumes:
      - db-data:/var/lib/postgresql/data # data path differs by image version
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 5s
      timeout: 3s
      retries: 10
volumes:
  db-data:
```

## Guardrails

- Revert or delete only files you created or changed in this session, and say
  so. Never discard someone else's uncommitted work.
- Never push images, tag releases in a registry, or deploy without explicit
  approval. Building and running locally is fine.
- Never put secrets in `ARG`, `ENV`, copied files, or the build context, and
  never commit `.env` files. Check `docker history --no-trunc` before calling an
  image clean.
- Do not use `latest` or tag-only base images in committed Dockerfiles.
- Do not run the container privileged, with the Docker socket mounted, or with
  added capabilities unless the user approves a stated need.
- Never weaken a test, check, scan threshold, or vulnerability policy to make
  work pass; document accepted findings with a reason instead.

## Verification

Use the project's own commands from `AGENTS.md`, `CLAUDE.md`, package scripts,
or the `Makefile`. Run each check separately and report its real result; never
chain alternatives with `||`.

- The image builds with BuildKit, for example `docker build -t myapp:dev .`. If
  the project uses a Dockerfile linter such as `hadolint`, it passes.
- `docker run --rm myapp:dev id -u` prints the non-root UID, not `0`.
- The container starts, serves its health endpoint, and
  `docker inspect --format '{{.State.Health.Status}}' <container>` reports
  `healthy`.
- `docker stop <container>` exits promptly with a graceful-shutdown log, not
  after the kill timeout.
- `docker history --no-trunc myapp:dev` shows no secrets; record image size.
- A vulnerability scan such as `trivy image myapp:dev` or
  `docker scout cves myapp:dev` meets the project's policy.
- An SBOM is generated, for example
  `trivy image --format cyclonedx --output sbom.cdx.json myapp:dev`, and saved
  where the project keeps build artifacts, not committed by default.
- `docker compose config --quiet` validates the Compose file (without
  `--quiet` it prints interpolated values, including secrets), and
  `docker compose up` brings the stack to healthy.

## Report

- **Files:** Dockerfile, `.dockerignore`, Compose file, `.env.example`.
- **Image:** base image with digest, final size, user ID, exposed port, and
  health check.
- **Scan and SBOM:** tool, findings by severity, accepted findings with reasons,
  and the SBOM location.
- **Verification:** each command and its result.
- **Not verified:** checks that could not run and why (for example no Docker
  daemon available), and anything left for approval such as pushing the image.

## Optional delegation

The `infrastructure-reviewer` subagent can review the finished Dockerfile and
Compose file. The `dependency-auditor` subagent can triage scan findings in
application dependencies. The workflow stays complete for a single agent.
