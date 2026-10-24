# DevTrack AI — Frontend image (Track 6 ownership).
# NOTE: build context is the REPO ROOT (see docker-compose.yml), so paths
# below are prefixed with `frontend/` and `infra/`.
# Stage 1: build the React app (Track 4 owned source under ./frontend).
FROM node:20-alpine AS builder

WORKDIR /app

# Install first for layer caching.
COPY frontend/package.json frontend/package-lock.json* ./
RUN if [ -f package-lock.json ]; then npm ci --no-audit --no-fund; else npm install --no-audit --no-fund; fi

COPY frontend/ ./
# Track 4 provides `build` (vite build -> ./dist). If absent the build fails
# loudly so CI catches it instead of shipping an empty nginx root.
RUN npm run build

# Stage 2: serve the static bundle via Nginx.
FROM nginx:1.27-alpine AS runtime

# Minimal SPA server block (Track 6 owned, lives in infra/).
COPY --from=builder /app/dist /usr/share/nginx/html
COPY infra/nginx/frontend-default.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
