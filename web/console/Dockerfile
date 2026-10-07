# 업무망 관리자 콘솔 이미지. Next.js standalone 출력만 담는다.
FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
RUN npm run build

FROM node:22-alpine
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3000 HOSTNAME=0.0.0.0
WORKDIR /app
RUN addgroup -S -g 10001 console && adduser -S -u 10001 -G console console
COPY --from=build --chown=console:console /app/.next/standalone ./
COPY --from=build --chown=console:console /app/.next/static ./.next/static
USER console
EXPOSE 3000
CMD ["node", "server.js"]
