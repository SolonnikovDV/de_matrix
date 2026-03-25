FROM nginx:1.27-alpine

RUN apk add --no-cache bash gettext curl

COPY proxy/nginx.conf.template /etc/nginx/templates/nginx.conf.template
COPY proxy/entrypoint.sh /entrypoint.sh

RUN chmod +x /entrypoint.sh

EXPOSE 80 443

ENTRYPOINT ["/entrypoint.sh"]
