# jooan-rtsp-brigde

Home Assistant add-on repository for restreaming Jooan / Juanvision kp2p camera channels as RTSP for Frigate.

## Contents

- `repository.yaml` - Home Assistant add-on repository metadata
- `jooan_kp2p_frigate_bridge/` - the add-on package

## Add-on

The add-on:

- connects to Jooan / Juanvision devices over the vendor kp2p websocket protocol
- supports direct LAN mode and UID / TURN mode
- restreams configured channels as local RTSP endpoints via FFmpeg
- is intended for Frigate consumption

See `jooan_kp2p_frigate_bridge/DOCS.md` for setup and configuration details.

## Repository URL

```text
https://github.com/TomasReiff/jooan-rtsp-brigde
```

