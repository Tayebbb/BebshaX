# BebshaX web image — builds the SPA and serves it via nginx (docs/DEMO.md §7).
# Build context is the repo root: docker compose --profile full up --build -d

# ── Stage 1: build the SPA against the same-origin /api proxy ───────────────
FROM node:24-alpine AS build
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
FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY deploy/nginx.conf /etc/nginx/conf.d/default.conf
