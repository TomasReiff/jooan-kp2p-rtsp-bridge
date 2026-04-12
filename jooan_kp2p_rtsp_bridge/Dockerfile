ARG BUILD_FROM=ghcr.io/home-assistant/base:latest
FROM $BUILD_FROM

RUN apk add --no-cache \
    ffmpeg \
    python3

# Install mediamtx – a lightweight RTSP relay used to accept pushes from
# ffmpeg and serve pull connections to RTSP clients.  ffmpeg's own
# "-rtsp_flags listen" server mode is unreliable on Alpine Linux builds and
# fails with "Connection refused"; mediamtx solves that cleanly.
ARG MEDIAMTX_VERSION=1.9.1
RUN ARCH="$(uname -m)" && \
    case "${ARCH}" in \
      x86_64)  MARCH=amd64 ;; \
      aarch64) MARCH=arm64v8 ;; \
      armv7l)  MARCH=armv7 ;; \
      *) echo "Unsupported architecture: ${ARCH}" >&2; exit 1 ;; \
    esac && \
    wget -qO /tmp/mediamtx.tar.gz \
      "https://github.com/bluenviron/mediamtx/releases/download/v${MEDIAMTX_VERSION}/mediamtx_v${MEDIAMTX_VERSION}_linux_${MARCH}.tar.gz" && \
    tar -xzf /tmp/mediamtx.tar.gz -C /usr/local/bin mediamtx && \
    rm /tmp/mediamtx.tar.gz && \
    chmod +x /usr/local/bin/mediamtx

COPY run.sh /run.sh
COPY app /app

RUN chmod a+x /run.sh

CMD [ "/run.sh" ]
