# jooan-kp2p-rtsp-bridge

Home Assistant add-on and plain Docker packaging for restreaming Jooan / Juanvision kp2p camera channels as standard RTSP streams.

## Contents

- `repository.yaml` - Home Assistant add-on repository metadata
- `jooan_kp2p_rtsp_bridge/` - the Home Assistant add-on package
- `Dockerfile` - generic Docker image for Synology Container Manager or plain Docker
- `bridge-config.example.json` - sample JSON config for generic containers

## Deployment modes

This repository supports both:

- a **Home Assistant add-on**
- a **standard Docker container** suitable for Synology Container Manager

Both packaging modes use the same bridge implementation.

## Container image

The generic container image is published to:

```text
ghcr.io/tomasreiff/jooan-kp2p-rtsp-bridge
```

Recommended tags:

- `latest` or `main` for the current default-branch build
- release tags such as `0.5.4` when a GitHub release is published

## Bridge behavior

The bridge:

- connects to Jooan / Juanvision devices over the vendor kp2p websocket protocol
- supports direct LAN mode and UID / TURN mode
- restreams configured channels as local RTSP endpoints via FFmpeg
- prefixes operational and subprocess log lines with local timestamps
- logs a per-camera availability percentage once per 24-hour reporting window
- can be consumed by Frigate, go2rtc, VLC, or other RTSP-capable clients

See `jooan_kp2p_rtsp_bridge/DOCS.md` for Home Assistant and Docker/Synology setup details.

## Repository URL

```text
https://github.com/TomasReiff/jooan-kp2p-rtsp-bridge
```

