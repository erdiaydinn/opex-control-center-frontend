FROM node:22-alpine AS build

WORKDIR /app
COPY package.json package-lock.json* ./
COPY scripts/ci/materialize-sheetjs.mjs ./scripts/ci/materialize-sheetjs.mjs
RUN node scripts/ci/materialize-sheetjs.mjs && npm ci

COPY . .
RUN npm run build

FROM nginx:1.27-alpine
# The official nginx image envsubst entrypoint processes *.template files from
# /etc/nginx/templates into /etc/nginx/conf.d. This is required for the
# server-side DockOS gateway secret; copying the file directly would leave the
# ${DOCKOS_GATEWAY_SECRET} placeholder unresolved. Restrict substitution so
# native nginx variables such as $host/$request_id can never collide with a
# similarly named process environment variable.
ENV NGINX_ENVSUBST_FILTER="^DOCKOS_GATEWAY_SECRET$"
COPY nginx.conf /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80
