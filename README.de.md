<div align="center">

<img src="custom_components/alcedo_nvr/brand/icon.png" width="96" alt="">

# Alcedo NVR – Integration

**Verbindet die [Alcedo-NVR-App](https://github.com/DASO203/alcedo-nvr) mit Home Assistant.**

[![Im Marketplace öffnen](https://my.home-assistant.io/badges/marketplace_repository.svg)](https://my.home-assistant.io/redirect/marketplace_repository/?owner=DASO203&repository=alcedo-nvr-integration&category=integration)

[🇬🇧 English](README.md) · 🇩🇪 Deutsch

</div>

> Voraussetzung ist die App **Alcedo NVR**. Sie übernimmt Aufnahme, Erkennung und die lokale KI. Diese Integration stellt die Ergebnisse in Home Assistant bereit.

## Funktionen

**Kameras übernehmen statt neu eintragen:** Kameras, die Home Assistant schon kennt (Reolink-Integration, Generische Kamera/RTSP, ring-mqtt …), werden beim Einrichten angeboten und später automatisch als *Entdeckt* gemeldet.

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
- **Dashboard-Karte `custom:alcedo-timeline-card`:** Zeitstrahl aller Kameras (24 h / 3 T / 7 T), Klick zum Abspielen, **Zeitraffer** aller Alarme
- **pCloud-Archiv:** Alarme, die lokal schon gelöscht sind, bleiben im Zeitstrahl sichtbar (☁) und werden aus pCloud abgespielt (ab pCloud Sync 0.2.0).
- **Aktion `alcedo_nvr.create_timelapse`:** Zeitraffer erstellen und den Dateipfad zurückgeben, z. B. für pCloud Sync

## Installation

1. Die App [Alcedo NVR](https://github.com/DASO203/alcedo-nvr) installieren und starten
2. Diese Integration installieren: Button oben, oder **Einstellungen → Marketplace → Aus Link hinzufügen** → `DASO203/alcedo-nvr-integration`
3. Home Assistant meldet **„Neues Gerät gefunden: Alcedo NVR“** → **Hinzufügen**
   (Manuell: *Integration hinzufügen → Alcedo NVR*, dann Host und API-Key aus der Alcedo-Oberfläche → „Verbindung für die Integration“ eintragen)
4. **Vorhandene Kameras übernehmen:** Der Assistent listet alle Kameras, die Home Assistant schon kennt. Haken setzen, fertig. Zugangsdaten musst du nicht erneut eingeben.
5. **pCloud** (nur wenn pCloud Sync installiert ist): auswählen, was hochgeladen wird.

## Kameras aus Home Assistant übernehmen

| Quelle in Home Assistant | Was Alcedo übernimmt |
|---|---|
| Reolink-Integration | Host, Zugangsdaten, Kanal und exakter Stream-Pfad. Alcedo nutzt dann die KI der Kamera (Person/Fahrzeug/Tier). |
| Generische Kamera, ONVIF, andere Kameras mit RTSP-Stream | die Stream-Adresse. INSTAR (`/11`) und Reolink-Pfade werden erkannt, der Substream dient der Bewegungserkennung. |
| ring-mqtt | *Stream Source* des Info-Sensors. Ring wird nur bei Bedarf aufgenommen. |

**Später hinzugekommene Kameras** meldet Home Assistant unter **Einstellungen → Geräte & Dienste → Entdeckt** („Neue Kamera: Einfahrt“). **Hinzufügen** → Aufnahme und Erkennung wählen (*Automatisch* passt fast immer) → fertig. Mit **Ignorieren** wird die Kamera nie wieder angeboten.

Unter **Alcedo NVR → Konfigurieren** findest du:
- *Kameras aus Home Assistant übernehmen* (auch ignorierte)
- *Übernommene Kameras entfernen*
- *pCloud-Upload & Archiv*
- *Automatische Kamerasuche* an/aus

Zugangsdaten gehen nur an die Alcedo-App in deinem lokalen Netz und erscheinen nie in Dialogen oder Logs. Kameras ohne RTSP-Stream (z. B. die Ring-Integration von Home Assistant, die nur WebRTC kann) können nicht übernommen werden. Für Ring brauchst du ring-mqtt.

## Dashboard-Karte

Die Karte wird automatisch registriert. Im Dashboard **Karte hinzufügen → Alcedo NVR Timeline** wählen oder per YAML:

```yaml
type: custom:alcedo-timeline-card
title: Kameras
hours: 24                     # Startzeitraum
periods: [24, 72, 168]        # Knöpfe
cameras: [einfahrt, garten]   # optional, Standard: alle
show_rejected: true           # verworfene Ereignisse grau anzeigen
timelapse_mode: clips         # clips | snapshots (schneller)
timelapse_speed: 4            # 1-16
only_confirmed: true          # Zeitraffer nur aus bestätigten Alarmen
```

Der Zeitraffer wird in der App mit niedriger Priorität erstellt. Bereits berechnete Teile werden wiederverwendet, ein Wochen-Zeitraffer nach einem Tages-Zeitraffer geht deshalb schnell.

## pCloud einrichten

1. [pCloud Sync](https://github.com/DASO203/pcloud-sync-unofficial) installieren und einrichten
2. **Alcedo NVR → Konfigurieren:**
   - *Nach pCloud hochladen:* **Nur bestätigte Alarme**
   - *pCloud-Unterordner:* `alcedo`
   - *Snapshot ebenfalls hochladen:* an
3. Ergebnis: `/HomeAssistant/Sync/alcedo/<kamera>/JJJJ/MM/TT/<ereignis>.mp4` (+ `.jpg`)

Die Dateien bleiben lokal erhalten. Alcedo löscht sie selbst nach der eingestellten Aufbewahrungszeit.

**pCloud-Archiv im Zeitstrahl** (Option *pCloud-Archiv im Zeitstrahl anzeigen*, Standard an, ab pCloud Sync 0.2.0): Ist ein Alarm lokal schon gelöscht, aber in pCloud vorhanden, zeigt die Zeitstrahl-Karte ihn weiter an (Markierung ☁). Beim Klick wird der Clip über Home Assistant direkt aus pCloud abgespielt, der pCloud-Link selbst gelangt nie in den Browser. Alcedo merkt sich jeden Upload und gleicht höchstens alle 15 Minuten mit dem pCloud-Ordner ab. So erscheinen auch ältere Uploads, und in pCloud gelöschte Dateien verschwinden aus dem Zeitstrahl. Den Zeitraffer erstellt die App weiterhin nur aus lokal vorhandenen Clips.

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
