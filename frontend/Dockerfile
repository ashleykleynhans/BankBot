# syntax=docker/dockerfile:1
FROM node:24-alpine AS build

WORKDIR /app

# Install dependencies from the lockfile first (layer-cached across builds)
COPY package.json package-lock.json ./
RUN npm ci

# Build the Svelte app
COPY . .
RUN npm run build

FROM nginx:alpine AS runtime

# Serve the built app and proxy /ws + /api to the bankbot service
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
