<div align="center">

<img src="custom_components/alcedo_nvr/brand/icon.png" width="96" alt="">

# Alcedo NVR – Integration

**Verbindet die [Alcedo-NVR-App](https://github.com/DASO203/alcedo-nvr) mit Home Assistant.**

[![Im Marketplace öffnen](https://my.home-assistant.io/badges/marketplace_repository.svg)](https://my.home-assistant.io/redirect/marketplace_repository/?owner=DASO203&repository=alcedo-nvr-integration&category=integration)

[🇬🇧 English](README.md) · 🇩🇪 Deutsch

</div>

> Voraussetzung ist die App **Alcedo NVR**. Sie übernimmt Aufnahme, Erkennung und die lokale KI. Diese Integration stellt die Ergebnisse in Home Assistant bereit.

## Funktionen

| Pro Kamera | |
|---|---|
| `camera.<kamera>` | Livebild (direkt von der Kamera) und Snapshot |
| `binary_sensor.<kamera>_alarm` | **an**, solange ein von der KI **bestätigter** Alarm läuft. Attribute: Beschreibung, Sicherheit, Objekte |
| `binary_sensor.<kamera>_aktivitat` | an bei jedem Ereignis, auch wenn es noch geprüft oder verworfen wird |
| `sensor.<kamera>_letztes_ereignis` | KI-Beschreibung des letzten Ereignisses, z. B. „Eine Person öffnet das Gartentor“ |
| `sensor.<kamera>_ereignisse_heute` / `_alarme_heute` | Zähler |
| `switch.<kamera>_erkennung` | Alarmerkennung pausieren (die Aufnahme läuft weiter) |
| `binary_sensor.<kamera>_aufnahme` | Aufnahme läuft (Diagnose) |

Dazu kommen:
- **Hub-Sensoren:** Speicherbelegung, KI-Status, pCloud-Uploads, Push-Verbindung
- **Medien-Browser:** Medien → Alcedo NVR → Kamera → Ereignisse mit Clips und Snapshots (🔴 Alarm, ⚪ verworfen)
- **Event `alcedo_nvr_event`** (`type`: start / update / verdict / end) mit Kamera, Objekten, KI-Beschreibung und Dateipfaden
- **Aktion `alcedo_nvr.trigger`:** Ein beliebiger Sensor (z. B. Ring-Bewegung oder -Klingel) löst ein Ereignis aus. Kameras mit Aufnahme `on_demand` beginnen dann aufzunehmen.
- **pCloud:** Abgeschlossene Ereignisse werden über [pCloud Sync](https://github.com/DASO203/pcloud-sync-unofficial) automatisch hochgeladen.
- **Zeitverlauf aller Kameras:** in der Alcedo-Oberfläche (Seitenleiste → *Alcedo NVR* → *Zeitverlauf*)

## Installation

1. Die App [Alcedo NVR](https://github.com/DASO203/alcedo-nvr) installieren und starten
2. Diese Integration installieren: Button oben, oder **Einstellungen → Marketplace → Aus Link hinzufügen** → `DASO203/alcedo-nvr-integration`
3. Home Assistant meldet **„Neues Gerät gefunden: Alcedo NVR“** → **Hinzufügen**
   (Manuell: *Integration hinzufügen → Alcedo NVR*, dann Host und API-Key aus der Alcedo-Oberfläche → „Verbindung für die Integration“ eintragen)

## pCloud einrichten

1. [pCloud Sync](https://github.com/DASO203/pcloud-sync-unofficial) installieren und einrichten
2. **Alcedo NVR → Konfigurieren:**
   - *Nach pCloud hochladen:* **Nur bestätigte Alarme**
   - *pCloud-Unterordner:* `alcedo`
   - *Snapshot ebenfalls hochladen:* an
3. Ergebnis: `/HomeAssistant/Sync/alcedo/<kamera>/JJJJ/MM/TT/<ereignis>.mp4` (+ `.jpg`)

Die Dateien bleiben lokal erhalten. Alcedo löscht sie selbst nach der eingestellten Aufbewahrungszeit.

## Beispiele

**Push-Nachricht mit KI-Beschreibung und Bild:**

```yaml
triggers:
  - trigger: event
    event_type: alcedo_nvr_event
    event_data:
      type: verdict
      confirmed: true
actions:
  - action: notify.mobile_app_handy
    data:
      title: "Alarm: {{ trigger.event.data.camera }}"
      message: "{{ trigger.event.data.description }}"
      data:
        image: "/api/alcedo_nvr/{{ config_entry_id('camera.einfahrt') }}/{{ trigger.event.data.event_id }}/snapshot"
```

**Ring-Klingel → Alcedo:**

```yaml
triggers:
  - trigger: state
    entity_id: binary_sensor.haustuer_ding
    to: "on"
actions:
  - action: alcedo_nvr.trigger
    data:
      entity_id: camera.haustuer_ring
      label: doorbell
```

**Erkennung pausieren, wenn jemand zu Hause ist:**

```yaml
triggers:
  - trigger: state
    entity_id: group.familie
actions:
  - action: "switch.turn_{{ 'off' if trigger.to_state.state == 'home' else 'on' }}"
    target:
      entity_id: switch.garten_erkennung
```

## Sicherheit

- Der API-Key wird nur als `Authorization: Bearer`-Header an die App im lokalen Netz gesendet und ist in den Diagnosedaten geschwärzt.
- Clips und Snapshots gibt Home Assistant nur an angemeldete Nutzer oder über signierte, zeitlich begrenzte Links heraus.

## Lizenz

MIT – kein offizielles Produkt von Reolink, INSTAR, Ring oder pCloud.
