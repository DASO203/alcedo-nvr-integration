# Changelog

## [0.3.0] - 2026-11-25

### Added
- **Take over cameras that already exist in Home Assistant** - Reolink integration (host, login, channel → camera AI is used), Generic camera / ONVIF / other RTSP cameras, INSTAR (`/11`), ring-mqtt (`stream_Source`). No second setup.
  - during setup (step "Take over existing cameras")
  - later as **discovered device** ("New camera: Einfahrt") with one confirmation; *Ignore* hides it for good
  - *Configure → Take over cameras from Home Assistant / Remove taken-over cameras*
- **pCloud archive**: uploads are remembered; alarms whose local files were already deleted stay in the timeline card (marked ☁) and are streamed back from pCloud. Older uploads are found by listing the pCloud folder. Requires pCloud Sync 0.2.0.
- Option *Automatic camera search* (on/off)

### Changed
- Setup and options rewritten: guided steps, a menu under *Configure*, every field explained (German and English)
- The integration reloads itself when the app's camera list changes; devices of removed cameras are cleaned up

## [0.2.0] - 2026-11-25

### Added
- Dashboard card `custom:alcedo-timeline-card` (registered automatically): timeline of all cameras for 24 h / 3 days / 7 days, click to play clips or recordings, one-click **timelapse**
- Action `alcedo_nvr.create_timelapse` (returns the file path, e.g. for pCloud Sync)
- Signed media proxy for clips, recordings, snapshots and timelapses (whitelisted paths only)

## [0.1.0] - 2026-11-25

### Added
- Discovery of the Alcedo NVR app via the Supervisor, manual setup as fallback
- Camera, alarm (AI confirmed), activity, recording and push connection entities
- Sensors with the AI description, event / alarm counters, storage, AI status, pCloud uploads
- Detection switch per camera
- Media browser for event clips and snapshots
- Event `alcedo_nvr_event` and action `alcedo_nvr.trigger` (e.g. Ring)
- Automatic upload of finished events via pCloud Sync
- English and German translations
