ARG BUILD_FROM=ghcr.io/home-assistant/base:latest
FROM $BUILD_FROM

RUN apk add --no-cache \
    ffmpeg \
    python3

COPY run.sh /run.sh
COPY app /app

RUN chmod a+x /run.sh

CMD [ "/run.sh" ]
