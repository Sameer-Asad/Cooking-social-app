# ── Stage 1: builder ─────────────────────────────────────────────────────
FROM node:20 AS builder

WORKDIR /build
COPY package.json package-lock.json* ./
RUN npm install

COPY . .
# Vite dev server is what actually runs for local dev (Sec 2: "local dev
# only for now"), so we don't run `npm run build` here — this stage only
# exists so `npm install` (with devDependencies) is cached in its own
# layer, separate from the slim runtime stage below.

# ── Stage 2: runtime (dev server) ───────────────────────────────────────
FROM node:20-slim AS runtime

RUN useradd -m appuser
WORKDIR /app

COPY --from=builder /build/node_modules ./node_modules
COPY --from=builder /build/package.json ./package.json
COPY . .

RUN chown -R appuser:appuser /app
USER appuser

EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
