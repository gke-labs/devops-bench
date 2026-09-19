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
RUN rm -rf /docker-entrypoint.d /docker-entrypoint.sh && \
    printf 'server {\n\
    listen 8080;\n\
    root /usr/share/nginx/html;\n\
    index index.html;\n\
    location / {\n\
        try_files $uri $uri/ /index.html;\n\
    }\n\
}\n' > /etc/nginx/conf.d/default.conf

COPY --from=builder /app/dist /usr/share/nginx/html
EXPOSE 8080
ENTRYPOINT ["nginx", "-g", "daemon off;"]
