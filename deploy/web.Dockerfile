FROM node:24.20.0-alpine3.23@sha256:0388af2af070cd4736a1567cfed02469ba117848845b4165d87a333edb53d2ca AS build
WORKDIR /build
COPY package.json package-lock.json ./
COPY apps/frontend/package.json ./apps/frontend/
COPY scripts/ops/npm-graph.mjs ./scripts/ops/npm-graph.mjs
RUN node scripts/ops/npm-graph.mjs \
	&& test "$(npm --version)" = "11.19.0" \
	&& npm ci --workspaces --include-workspace-root
COPY apps/frontend ./apps/frontend
COPY scripts/ops/web-config.mjs ./scripts/ops/web-config.mjs
COPY deploy/nginx.conf ./deploy/nginx.conf
ARG VITE_NEON_AUTH_URL=""
ENV VITE_API_BASE=/api VITE_MOCK=false VITE_NEON_AUTH_URL=${VITE_NEON_AUTH_URL}
RUN node scripts/ops/web-config.mjs nginx deploy/nginx.conf /build/nginx.conf \
	&& npm run build --workspace apps/frontend

FROM nginx:1.30.4-alpine3.24@sha256:dc5069ad14f19660b141b21236140b91656bf89bbc3e2417c70ae650cd66104c
# Pull in Alpine security fixes the pinned digest predates.
RUN apk upgrade --no-cache
COPY --from=build /build/apps/frontend/dist /usr/share/nginx/html
COPY --from=build /build/nginx.conf /etc/nginx/nginx.conf
USER 101:101
EXPOSE 8080
ENTRYPOINT ["nginx"]
CMD ["-g", "daemon off;"]
