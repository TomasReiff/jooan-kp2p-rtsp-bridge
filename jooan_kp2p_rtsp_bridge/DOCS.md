# Jooan kp2p RTSP Bridge

This add-on restreams Jooan / Juanvision kp2p camera channels as local RTSP streams that standard RTSP clients can consume.

This is a **Home Assistant add-on**, not a HACS integration. The add-on does the media bridging work and exposes RTSP URLs for downstream consumers.

## What this add-on does

- Connects to the DVR or camera using the vendor kp2p websocket protocol.
- Opens one bridge process per enabled camera.
- Runs a [mediamtx](https://github.com/bluenviron/mediamtx) RTSP relay per camera to accept the encoded stream from FFmpeg and serve it to RTSP clients.
- Lets you configure the connection from the Home Assistant add-on UI.
- Can feed Frigate, go2rtc, VLC, or other RTSP-capable software.

## Configuration

### Global options

- Use the Home Assistant add-on **Configuration** UI to edit settings. Do not edit the packaged add-on files directly; updates replace those defaults.
- `use_uid`: Enable this if you want to use the vendor cloud UID / TURN path instead of direct LAN access.
- `host` / `port`: Direct LAN connection target.
- `uid`: Device UID for cloud/TURN mode.
- `username` / `password`: DVR login credentials.
- `reconnect_delay`: Delay before retrying if a bridge process fails.
- `unavailable_stream_reconnect_delay`: Delay before retrying a channel that reports `result=-40` / unavailable.
- `ffmpeg_loglevel`: FFmpeg log verbosity.
- `cameras`: List of camera bridge definitions.

### Camera list

Each item in `cameras` has:

- `channel`: Zero-based DVR channel number
- `enabled`: Whether to start this bridge. Leave unused or offline channels disabled.
- `stream_id`: `0` = main stream, `1` = substream
- `rtsp_port`: RTSP port to expose
- `rtsp_path`: RTSP path to expose

If the device returns `Open stream failed with result=-40`, that channel is usually unavailable on the DVR. The bridge now backs off much longer before retrying that camera so it does not flood the device with failed reconnects.

The add-on ships with the full initial default camera config and keeps a `/data/options.last_good.json` backup of the last saved add-on configuration. If Home Assistant unexpectedly replaces `options.json` with the packaged defaults or an empty config, the bridge restores that last good copy on startup.

Example uncapped camera config:

```yaml
use_uid: false
host: 192.168.1.10
port: 10000
username: admin
password: YOUR_PASSWORD
reconnect_delay: 3
unavailable_stream_reconnect_delay: 60
ffmpeg_loglevel: warning
cameras:
  - channel: 0
    enabled: true
    stream_id: 0
    rtsp_port: 8551
    rtsp_path: cam1
  - channel: 1
    enabled: true
    stream_id: 0
    rtsp_port: 8552
    rtsp_path: cam2
  - channel: 15
    enabled: true
    stream_id: 1
    rtsp_port: 8566
    rtsp_path: cam16_sub
```

## Consumer configuration

Use the Home Assistant host IP or LAN IP in your RTSP client, **not** `127.0.0.1` unless that client runs in the same container.

Example if this add-on exposes:

- `cam1` on `8551`
- `cam2` on `8552`
- `cam3` on `8553`

Then a client can use:

```text
rtsp://HOME_ASSISTANT_HOST_IP:8551/cam1
rtsp://HOME_ASSISTANT_HOST_IP:8552/cam2
rtsp://HOME_ASSISTANT_HOST_IP:8553/cam3
```

For example, Frigate can use:

```yaml
cameras:
  cam1:
    ffmpeg:
      inputs:
        - path: rtsp://HOME_ASSISTANT_HOST_IP:8551/cam1
          roles:
            - detect
            - record
  cam2:
    ffmpeg:
      inputs:
        - path: rtsp://HOME_ASSISTANT_HOST_IP:8552/cam2
          roles:
            - detect
            - record
  cam3:
    ffmpeg:
      inputs:
        - path: rtsp://HOME_ASSISTANT_HOST_IP:8553/cam3
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
