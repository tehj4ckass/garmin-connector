# ⌚ Garmin-to-Drive Sync (Garmin Connector)

Dieses Tool automatisiert den Export deiner Garmin-Fitness- und Gesundheitsdaten in CSV-Dateien und synchronisiert diese direkt mit deinem Google Drive. Es dient als Datenbasis für Analysen, Dashboards oder KI-gestützte Coaching-Systeme.

## 🚀 Features

- **Delta Load:** Lädt nur neue Daten seit dem letzten Lauf (effizient und schnell).
- **Vollständige Synchronisation:**
    - **Fitness:** Aktivitäten (ID, Datum, Typ, Distanz, Dauer, Geschwindigkeit, Puls, Kalorien, Höhenmeter).
    - **Health:** Tägliche Statistiken (Ruhepuls, HRV, Stresslevel, Schlafstunden, Schlaf-Score, Schritte).
- **Cloud-Anbindung:** Automatischer Upload und Aktualisierung der Dateien in Google Drive.
- **Automatisierung:** Läuft standardmäßig alle 2 Stunden als Hintergrundprozess.
- **Docker-Ready:** Einfache Bereitstellung über Docker und Docker-Compose.

## 🛠 Setup

### 1. Voraussetzungen
- Ein Garmin-Konto.
- Ein Google Cloud Projekt mit aktivierter Drive API (für `credentials.json`).

### 2. Konfiguration
Erstelle eine `.env` Datei im Hauptverzeichnis (siehe `.env.example`):
```env
GARMIN_EMAIL=deine.email@gmail.com
GARMIN_PASSWORD=dein_passwort
```

### 3. Google Drive API
Platziere deine `credentials.json` aus der Google Cloud Console im Hauptverzeichnis. Beim ersten Start wird ein Browserfenster für die Authentifizierung geöffnet, um die `token.json` zu generieren.

### 4. Start mit Docker
Der einfachste Weg ist die Nutzung von Docker Compose:

```bash
docker-compose up -d
```

Der Container bleibt im Hintergrund aktiv und führt den Sync alle 2 Stunden aus.

## 📂 Dateistruktur

- `main.py`: Die Hauptlogik für Garmin-API und Google Drive Upload.
- `fitness_log.csv`: Gesammelte Aktivitätsdaten (Pipe-getrennt `|`).
- `health_log.csv`: Gesammelte Gesundheitsdaten (Pipe-getrennt `|`).
- `garmin_tokens/`: Speichert Session-Tokens für Garmin (vermeidet ständige Logins).
- `token.json`: Google OAuth Refresh-Token.

## 🔒 Sicherheit
Sensible Daten wie Passwörter, Tokens und deine persönlichen CSV-Logs sind in der `.gitignore` und `.dockerignore` hinterlegt, damit sie nicht versehentlich geteilt werden.

---
*Hinweis: Dieses Tool ist für den privaten Gebrauch gedacht. Bitte achte auf die Nutzungsbedingungen der jeweiligen API-Anbieter.*
