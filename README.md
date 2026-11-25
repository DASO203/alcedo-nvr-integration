<div align="center">

<img src="custom_components/alcedo_nvr/brand/icon.png" width="96" alt="">

# Alcedo NVR – Integration

**Connects the [Alcedo NVR app](https://github.com/DASO203/alcedo-nvr) to Home Assistant.**

[![Open in the Marketplace](https://my.home-assistant.io/badges/marketplace_repository.svg)](https://my.home-assistant.io/redirect/marketplace_repository/?owner=DASO203&repository=alcedo-nvr-integration&category=integration)

🇬🇧 English · [🇩🇪 Deutsch](README.de.md)

</div>

> Requires the **Alcedo NVR app** (recording, detection, local AI). This integration brings the results into Home Assistant.

## Features

- **Takes over cameras that already exist in Home Assistant** (Reolink integration, Generic camera / RTSP, ring-mqtt): offered during setup and later as *Discovered* – no second setup
- `camera.*` per camera (live stream straight from the camera, snapshots)
- `binary_sensor.*_alarm` – on while an alarm **confirmed by the local AI** is active (attributes: AI description, confidence, objects)
- `binary_sensor.*_activity` – any event, also unreviewed / rejected
- `sensor.*_last_event` – AI description of the last event, plus counters for today
- `switch.*_detection` – pause alarm detection (recording continues)
- Hub sensors: storage usage, AI status, pCloud uploads, push connection
- **Media browser**: Alcedo NVR → camera → events (clips & snapshots)
- Event **`alcedo_nvr_event`** (`type`: start / update / verdict / end)
- Action **`alcedo_nvr.trigger`** – start an event from any sensor (e.g. Ring motion / doorbell); `on_demand` cameras start recording
- **pCloud**: finished events are uploaded automatically via [pCloud Sync](https://github.com/DASO203/pcloud-sync-unofficial) (off / confirmed alarms / all)
- **Dashboard card `custom:alcedo-timeline-card`** (registered automatically): timeline of all cameras (24 h / 3 d / 7 d), click to play, **Timelapse** button
- **pCloud archive**: alarms already deleted locally stay in the timeline and are played from pCloud (pCloud Sync 0.2.0+)
- Action **`alcedo_nvr.create_timelapse`** - returns the file path (e.g. upload a weekly timelapse with pCloud Sync)

```yaml
type: custom:alcedo-timeline-card
hours: 24
periods: [24, 72, 168]
```

## Install

1. Install and start the [Alcedo NVR app](https://github.com/DASO203/alcedo-nvr)
2. Install this integration via the button above or **Settings → Marketplace → Add from link** → `DASO203/alcedo-nvr-integration`
3. Home Assistant shows **"New device discovered: Alcedo NVR"** → **Add**
   (manual: *Add integration → Alcedo NVR*, host and API key from the Alcedo web UI)
4. The setup lists the cameras Home Assistant already knows → select the ones Alcedo should record
5. If pCloud Sync is installed: choose what is uploaded

New cameras added to Home Assistant later appear under **Settings → Devices & services → Discovered** ("New camera: …"). Everything else is under **Alcedo NVR → Configure**.

## Cameras from Home Assistant

| Source in Home Assistant | What Alcedo takes over |
|---|---|
| Reolink integration | host, login, channel, exact stream path → Reolink camera AI (person / vehicle / animal) is used |
| Generic camera, ONVIF, other cameras with RTSP stream | the stream URL; INSTAR (`/11`) and Reolink paths are recognised, sub stream is used for motion detection |
| ring-mqtt | *Stream Source* of the camera info sensor → Ring is recorded on demand only |

Credentials are only passed to the Alcedo app in your local network and are never shown in dialogs or logs. Cameras without an RTSP stream (e.g. the Ring core integration, which uses WebRTC only) cannot be offered.

## pCloud

Install [pCloud Sync](https://github.com/DASO203/pcloud-sync-unofficial), then **Alcedo NVR → Configure → Upload to pCloud: only confirmed alarms**. Files end up in `<pCloud Sync folder>/alcedo/<camera>/YYYY/MM/DD/`. Local files are kept and cleaned up by Alcedo's retention.

## Example: notification with AI description

```yaml
triggers:
  - trigger: event
    event_type: alcedo_nvr_event
    event_data:
      type: verdict
      confirmed: true
actions:
  - action: notify.mobile_app_phone
    data:
      title: "Alarm: {{ trigger.event.data.camera }}"
      message: "{{ trigger.event.data.description }}"
```

More examples: [README.de.md](README.de.md#beispiele).

## License

MIT. Not affiliated with Reolink, INSTAR, Ring or pCloud.
