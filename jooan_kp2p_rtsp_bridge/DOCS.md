# Jooan kp2p RTSP Bridge

This bridge restreams Jooan / Juanvision kp2p camera channels as local RTSP streams that standard RTSP clients can consume.

This repository ships both a **Home Assistant add-on** and a **plain Docker container**. In both cases the bridge does the media restreaming work and exposes RTSP URLs for downstream consumers.

## What this add-on does

- Connects to the DVR or camera using the vendor kp2p websocket protocol.
- Opens one bridge process per enabled camera.
- Runs a single shared [mediamtx](https://github.com/bluenviron/mediamtx) RTSP relay for all camera paths on one RTSP port.
- Lets you configure the connection from the Home Assistant add-on UI or a mounted JSON config file.
- Can feed Frigate, go2rtc, VLC, or other RTSP-capable software.

## Configuration

### Global options

- In Home Assistant, use the add-on **Configuration** UI to edit settings. Do not edit the packaged add-on files directly; updates replace those defaults.
- In Docker/Synology mode, mount a JSON file and point `BRIDGE_CONFIG_PATH` at it if you do not use the default path `/config/bridge-config.json`.
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
- `rtsp_port`: Shared RTSP port to expose. All enabled cameras should use the same port.
- `rtsp_path`: RTSP path to expose

If the device returns `Open stream failed with result=-40`, that channel is usually unavailable on the DVR. The bridge now backs off much longer before retrying that camera so it does not flood the device with failed reconnects.

The Home Assistant add-on keeps a `/data/options.last_good.json` backup of the last saved add-on configuration. If Home Assistant unexpectedly replaces `options.json` with the packaged defaults or an empty config, the bridge restores that last good copy on startup.

Operational log lines are prefixed with local timestamps so Home Assistant logs are easier to correlate with other services. That includes relayed FFmpeg and mediamtx subprocess output as well, so warnings from those tools should no longer appear as bare untimestamped lines.

Each enabled camera also logs an `availability_daily=` line once per 24-hour reporting window. That percentage reflects how long the bridge was actively publishing that camera during the window, after which the counters reset for the next report.

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
    stream_id: 1
    rtsp_port: 8554
    rtsp_path: cam1
  - channel: 1
    enabled: true
    stream_id: 1
    rtsp_port: 8554
    rtsp_path: cam2
  - channel: 15
    enabled: true
    stream_id: 1
    rtsp_port: 8554
    rtsp_path: cam16_sub
```

## Consumer configuration

Use the Home Assistant host IP, Synology host IP, or other LAN IP in your RTSP client, **not** `127.0.0.1` unless that client runs in the same container.

Example if this add-on exposes all cameras on shared RTSP port `8554`:

```text
rtsp://HOME_ASSISTANT_HOST_IP:8554/cam1
rtsp://HOME_ASSISTANT_HOST_IP:8554/cam2
rtsp://HOME_ASSISTANT_HOST_IP:8554/cam3
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
        - path: rtsp://HOME_ASSISTANT_HOST_IP:8554/cam2
          roles:
            - detect
            - record
  cam3:
    ffmpeg:
      inputs:
        - path: rtsp://HOME_ASSISTANT_HOST_IP:8554/cam3
          roles:
            - detect
            - record
```

## Install

### Home Assistant add-on

#### Add repository by URL

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

#### Local repository install

1. Copy this repository into your Home Assistant local add-ons directory.
2. Refresh the add-on store.
3. Open **Jooan kp2p RTSP Bridge**.
4. Set your credentials and define the `cameras` list you want to bridge.
5. Start the add-on.
6. Point your RTSP client to the RTSP URLs you configured.

### Docker / Synology Container Manager

1. Either pull the published image:

```text
docker pull ghcr.io/tomasreiff/jooan-kp2p-rtsp-bridge:latest
```

Or build the image from the repository root:

```text
docker build -t jooan-kp2p-rtsp-bridge .
```

2. Copy `bridge-config.example.json` and edit it with your device settings.
3. Run the container with a config mount and published RTSP port:

```text
docker run -d --name jooan-kp2p-rtsp-bridge -p 8554:8554 -v /path/to/bridge-config.json:/config/bridge-config.json:ro -e BRIDGE_PUBLIC_RTSP_HOST=192.168.1.50 ghcr.io/tomasreiff/jooan-kp2p-rtsp-bridge:latest
```

4. In Synology Container Manager, use the same image settings:
   - image: `ghcr.io/tomasreiff/jooan-kp2p-rtsp-bridge:latest`
   - mount your config file to `/config/bridge-config.json`
   - publish the RTSP port from the config, typically `8554`
   - optionally set `BRIDGE_PUBLIC_RTSP_HOST` so startup logs print the correct host IP
   - bridge networking is fine; host networking is not required for the generic container

Example Synology Container Manager project YAML:

```yaml
services:
  jooan:
    image: ghcr.io/tomasreiff/jooan-kp2p-rtsp-bridge:latest
    container_name: jooan
    restart: unless-stopped
    environment:
      BRIDGE_CONFIG_PATH: /config/config.json
      BRIDGE_PUBLIC_RTSP_HOST: 192.168.1.50
    ports:
      - "8554:8554"
    volumes:
      - /volumeUSB4/usbshare/docker/jooan/config/config.json:/config/config.json:ro
```

The generic container looks for config files in this order:

1. `BRIDGE_CONFIG_PATH`
2. `/config/bridge-config.json`
3. `/config/options.json`
4. `/data/options.json`
