<div align="center">

<img src="custom_components/alcedo_nvr/brand/icon.png" width="96" alt="">

# Alcedo NVR – Integration

**Connects the [Alcedo NVR app](https://github.com/DASO203/alcedo-nvr) to Home Assistant.**

[![Open in the Marketplace](https://my.home-assistant.io/badges/marketplace_repository.svg)](https://my.home-assistant.io/redirect/marketplace_repository/?owner=DASO203&repository=alcedo-nvr-integration&category=integration)

🇬🇧 English · [🇩🇪 Deutsch](README.de.md)

</div>

> Requires the **Alcedo NVR app** (recording, detection, local AI). This integration brings the results into Home Assistant.

## Features

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
- **Timeline of all cameras** in the Alcedo web UI (sidebar → *Alcedo NVR* → *Timeline*)

## Install

1. Install and start the [Alcedo NVR app](https://github.com/DASO203/alcedo-nvr)
2. Install this integration via the button above or **Settings → Marketplace → Add from link** → `DASO203/alcedo-nvr-integration`
3. Home Assistant shows **"New device discovered: Alcedo NVR"** → **Add**
   (manual: *Add integration → Alcedo NVR*, host and API key from the Alcedo web UI)

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
