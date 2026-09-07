# BebshaX web image — builds the SPA and serves it via nginx (docs/DEMO.md §7).
# Build context is the repo root: docker compose --profile full up --build -d

# Base images are pinned to minor tags (2026-09-06). Digest pins need the
# registry (`docker manifest inspect`), which the venue build box lacks;
# after one online build, `docker image inspect --format '{{index .RepoDigests 0}}'`
# gives the digest to append as `@sha256:...`. Node 24 matches CI.
# ── Stage 1: build the SPA against the same-origin /api proxy ───────────────
FROM node:24.11-alpine AS build
WORKDIR /app
COPY apps/frontend/package.json apps/frontend/package-lock.json ./
RUN npm ci
COPY apps/frontend/ ./
# Vite inlines VITE_* at build time; /api rides the nginx proxy below (no CORS).
ARG VITE_API_BASE=/api
ENV VITE_API_BASE=${VITE_API_BASE}
# Empty = federated Neon sign-in disabled (frontend's documented default);
# operators point it at their own Neon Auth tenant at build time.
ARG VITE_NEON_AUTH_URL=""
ENV VITE_NEON_AUTH_URL=${VITE_NEON_AUTH_URL}
RUN npm run build

# ── Stage 2: nginx serves the build and proxies /api → app:8000 ─────────────
FROM nginx:1.28-alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY deploy/nginx.conf /etc/nginx/conf.d/default.conf
