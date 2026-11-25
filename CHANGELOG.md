# Changelog

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
