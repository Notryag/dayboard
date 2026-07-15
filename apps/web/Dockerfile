FROM node:22-alpine AS deps

WORKDIR /app

COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci

FROM node:22-alpine AS builder

WORKDIR /app

COPY --from=deps /app/node_modules ./node_modules
COPY apps/web/ ./

ARG NEXT_PUBLIC_DAYBOARD_API_BASE_URL=/dayboard-api
ARG NEXT_PUBLIC_DAYBOARD_BASE_PATH=/dayboard
ENV NEXT_PUBLIC_DAYBOARD_API_BASE_URL=$NEXT_PUBLIC_DAYBOARD_API_BASE_URL \
    NEXT_PUBLIC_DAYBOARD_BASE_PATH=$NEXT_PUBLIC_DAYBOARD_BASE_PATH

RUN npm run build

FROM node:22-alpine AS runner

WORKDIR /app

RUN addgroup -S -g 1001 dayboard \
    && adduser -S -D -H -u 1001 -G dayboard dayboard

ENV NODE_ENV=production \
    NEXT_PUBLIC_DAYBOARD_API_BASE_URL=/dayboard-api \
    NEXT_PUBLIC_DAYBOARD_BASE_PATH=/dayboard \
    HOSTNAME=0.0.0.0 \
    PORT=3001

COPY --chown=dayboard:dayboard --from=builder /app/.next/standalone ./
COPY --chown=dayboard:dayboard --from=builder /app/.next/static ./.next/static
COPY --chown=dayboard:dayboard --from=builder /app/public ./public

USER dayboard

EXPOSE 3001

CMD ["node", "server.js"]
