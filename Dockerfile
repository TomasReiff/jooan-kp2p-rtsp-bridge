FROM alpine:3.20

RUN apk add --no-cache \
    ca-certificates \
    ffmpeg \
    python3

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

COPY jooan_kp2p_rtsp_bridge/app /app

RUN mkdir -p /config /data

ENV PYTHONUNBUFFERED=1 \
    BRIDGE_CONFIG_PATH=/config/bridge-config.json

EXPOSE 8554

CMD ["python3", "/app/container_launcher.py"]
