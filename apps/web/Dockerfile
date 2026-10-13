# Edge OS web image for the LOCAL Docker rehearsal. Build context: the repository root (see .dockerignore).
# NEXT_PUBLIC_* values are public and inlined into the browser bundle at build time. They are the only build inputs
# besides the source and apps/web/package-lock.json. The runtime container receives no Edge OS server configuration.

ARG NODE_IMAGE=node:24.13.1-trixie-slim@sha256:1c78323e27e7aff8ac92377845119cd52ac3d3b22e197b3b14e8eb64af387f8c

FROM ${NODE_IMAGE} AS build
ENV NEXT_TELEMETRY_DISABLED=1
WORKDIR /app/apps/web
COPY apps/web/package.json apps/web/package-lock.json ./
# Install scripts stay off: bufferutil, utf-8-validate and keccak would compile native add-ons (no compiler is in the
# image; each has a JavaScript fallback) and @reown/appkit only runs a version check. The locked package set is unchanged.
RUN npm ci --ignore-scripts --no-audit --no-fund
COPY apps/web/app ./app
COPY apps/web/components ./components
COPY apps/web/lib ./lib
COPY apps/web/public ./public
COPY apps/web/next.config.ts apps/web/tsconfig.json ./
# The public values enter after the dependency layer, so a different loopback origin reuses the installed packages.
ARG NEXT_PUBLIC_API_BASE_URL
ARG NEXT_PUBLIC_PRIVY_APP_ID
ENV NEXT_PUBLIC_API_BASE_URL=${NEXT_PUBLIC_API_BASE_URL} \
    NEXT_PUBLIC_PRIVY_APP_ID=${NEXT_PUBLIC_PRIVY_APP_ID}
RUN test -n "${NEXT_PUBLIC_API_BASE_URL}" || { echo "NEXT_PUBLIC_API_BASE_URL build argument is required" >&2; exit 1; }
RUN npm run build && npm prune --omit=dev --ignore-scripts --no-audit --no-fund

FROM ${NODE_IMAGE} AS runtime
ARG EDGE_OS_SOURCE_COMMIT=unknown
LABEL org.opencontainers.image.title="edge-os-web" \
      org.opencontainers.image.revision="${EDGE_OS_SOURCE_COMMIT}" \
      edge-os.profile="LOCAL"
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1
WORKDIR /app/apps/web
COPY --from=build --chown=node:node /app/apps/web/package.json /app/apps/web/next.config.ts ./
COPY --from=build --chown=node:node /app/apps/web/node_modules ./node_modules
COPY --from=build --chown=node:node /app/apps/web/public ./public
COPY --from=build --chown=node:node /app/apps/web/.next ./.next
USER node
CMD ["node", "node_modules/next/dist/bin/next", "start", "--hostname", "0.0.0.0", "--port", "3000"]
