# Jooan kp2p RTSP Bridge

This add-on restreams Jooan / Juanvision kp2p camera channels as local RTSP streams that standard RTSP clients can consume.

This is a **Home Assistant add-on**, not a HACS integration. The add-on does the media bridging work and exposes RTSP URLs for downstream consumers.

## What this add-on does

- Connects to the DVR or camera using the vendor kp2p websocket protocol.
- Opens one bridge process per enabled camera.
- Uses FFmpeg to publish a local RTSP stream for each enabled camera.
- Lets you configure the connection from the Home Assistant add-on UI.
- Can feed Frigate, go2rtc, VLC, or other RTSP-capable software.

## Configuration

### Global options

- `use_uid`: Enable this if you want to use the vendor cloud UID / TURN path instead of direct LAN access.
- `host` / `port`: Direct LAN connection target.
- `uid`: Device UID for cloud/TURN mode.
- `username` / `password`: DVR login credentials.
- `reconnect_delay`: Delay before retrying if a bridge process fails.
- `ffmpeg_loglevel`: FFmpeg log verbosity.
- `cameras`: List of camera bridge definitions.

### Camera list

Each item in `cameras` has:

- `channel`: Zero-based DVR channel number
- `enabled`: Whether to start this bridge
- `stream_id`: `0` = main stream, `1` = substream
- `rtsp_port`: RTSP port to expose
- `rtsp_path`: RTSP path to expose

Example uncapped camera config:

```yaml
use_uid: false
host: 192.168.1.10
port: 10000
username: admin
password: YOUR_PASSWORD
reconnect_delay: 3
ffmpeg_loglevel: warning
cameras:
  - channel: 0
    enabled: true
    stream_id: 0
    rtsp_port: 8554
    rtsp_path: cam1
  - channel: 1
    enabled: true
    stream_id: 0
    rtsp_port: 8555
    rtsp_path: cam2
  - channel: 15
    enabled: true
    stream_id: 1
    rtsp_port: 8569
    rtsp_path: cam16_sub
```

## Consumer configuration

Use the Home Assistant host IP or LAN IP in your RTSP client, **not** `127.0.0.1` unless that client runs in the same container.

Example if this add-on exposes:

- `cam1` on `8554`
- `cam2` on `8555`
- `cam3` on `8556`

Then a client can use:

```text
rtsp://HOME_ASSISTANT_HOST_IP:8554/cam1
rtsp://HOME_ASSISTANT_HOST_IP:8555/cam2
rtsp://HOME_ASSISTANT_HOST_IP:8556/cam3
```

For example, Frigate can use:

```yaml
cameras:
  cam1:
    ffmpeg:
      inputs:
        - path: rtsp://HOME_ASSISTANT_HOST_IP:8554/cam1
          roles:
            - detect
            - record
  cam2:
    ffmpeg:
      inputs:
        - path: rtsp://HOME_ASSISTANT_HOST_IP:8555/cam2
          roles:
            - detect
            - record
  cam3:
    ffmpeg:
      inputs:
        - path: rtsp://HOME_ASSISTANT_HOST_IP:8556/cam3
          roles:
            - detect
            - record
```

## Install

### Add repository by URL

1. In Home Assistant, open **Settings -> Add-ons -> Add-on Store**.
2. Open the three-dot menu and choose **Repositories**.
3. Add this repository URL:

```text
https://github.com/TomasReiff/jooan-kp2p-rtsp-bridge
```

4. Refresh the add-on store.
5. Open **Jooan kp2p RTSP Bridge**.
6. Set your credentials and define the `cameras` list you want to bridge.
7. Start the add-on.
8. Point your RTSP client to the RTSP URLs you configured.

### Local repository install

1. Copy this repository into your Home Assistant local add-ons directory.
2. Refresh the add-on store.
3. Open **Jooan kp2p RTSP Bridge**.
4. Set your credentials and define the `cameras` list you want to bridge.
5. Start the add-on.
6. Point your RTSP client to the RTSP URLs you configured.
