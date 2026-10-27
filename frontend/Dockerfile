# --- Aşama 1: Bağımlılıkları kur ---
FROM node:22-slim AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

# --- Aşama 2: Uygulamayı derle ---
FROM node:22-slim AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
# Tarayıcının API'ye ulaşacağı adres build sırasında gömülür (NEXT_PUBLIC_*).
# Farklı bir adres için: docker compose build --build-arg NEXT_PUBLIC_API_URL=http://... frontend
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
RUN npm run build

# --- Aşama 3: Sadece çalıştırmak için gerekenler ---
FROM node:22-slim AS runner
WORKDIR /app

# standalone server.js varsayılan olarak localhost dinler; container dışından erişim için 0.0.0.0
ENV NODE_ENV=production HOSTNAME=0.0.0.0 PORT=3000

# Root olarak çalışmaz
RUN groupadd -g 1001 nodejs && useradd -m -u 1001 -g nodejs nextjs

COPY --from=builder --chown=nextjs:nodejs /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

USER nextjs

EXPOSE 3000

CMD ["node", "server.js"]
