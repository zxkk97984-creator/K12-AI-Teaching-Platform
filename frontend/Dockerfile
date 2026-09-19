# T29 static web image. The unique bootstrap builds frontend/dist; this image
# only serves that immutable output and proxies same-origin API requests.
FROM nginx:alpine

COPY frontend/dist /usr/share/nginx/html
COPY frontend/nginx.t29.conf /etc/nginx/conf.d/default.conf

EXPOSE 15173
