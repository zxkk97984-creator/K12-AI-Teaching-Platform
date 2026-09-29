# ./k12 start --build generates frontend/dist from current source before this
# image is built. Nginx serves the result and proxies same-origin API requests.
FROM nginx:alpine

COPY frontend/dist /usr/share/nginx/html
COPY frontend/nginx.t29.conf /etc/nginx/conf.d/default.conf

EXPOSE 15173
