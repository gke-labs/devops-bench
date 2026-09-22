# Stage 1: Build the Vite SPA
FROM node:20-slim AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .

# Mode argument: "dev" (uses leaderboard-dev), "staging" (uses leaderboard-test) or "production" (uses leaderboard)
ARG MODE=dev
RUN if [ "$MODE" = "dev" ]; then npm run build:dev; elif [ "$MODE" = "staging" ]; then npm run build:staging; else npm run build; fi

# Stage 2: Serve static files with Nginx
FROM nginx:alpine
RUN rm -rf /docker-entrypoint.d /docker-entrypoint.sh
COPY nginx.conf /etc/nginx/conf.d/default.conf

COPY --from=builder /app/dist /usr/share/nginx/html
EXPOSE 8080
ENTRYPOINT ["nginx", "-g", "daemon off;"]
