# jooan-rtsp-brigde

Home Assistant add-on repository for restreaming Jooan / Juanvision kp2p camera channels as standard RTSP streams.

## Contents

- `repository.yaml` - Home Assistant add-on repository metadata
- `jooan_kp2p_rtsp_bridge/` - the add-on package

## Add-on

The add-on:

- connects to Jooan / Juanvision devices over the vendor kp2p websocket protocol
- supports direct LAN mode and UID / TURN mode
- restreams configured channels as local RTSP endpoints via FFmpeg
- can be consumed by Frigate, go2rtc, VLC, or other RTSP-capable clients

See `jooan_kp2p_rtsp_bridge/DOCS.md` for setup and configuration details.

## Repository URL

```text
https://github.com/TomasReiff/jooan-rtsp-brigde
```

