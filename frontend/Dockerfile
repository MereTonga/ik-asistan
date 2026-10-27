# --- Aşama 1: Bağımlılıkları kur ---
FROM node:20-slim AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

# --- Aşama 2: Uygulamayı derle ---
FROM node:20-slim AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
# Tarayıcının API'ye ulaşacağı adres build sırasında gömülür (NEXT_PUBLIC_*).
# Farklı bir adres için: docker compose build --build-arg NEXT_PUBLIC_API_URL=http://... frontend
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
RUN npm run build

# --- Aşama 3: Sadece çalıştırmak için gerekenler ---
FROM node:20-slim AS runner
WORKDIR /app

ENV NODE_ENV=production

COPY --from=builder /app/public ./public
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static

EXPOSE 3000

CMD ["node", "server.js"]
