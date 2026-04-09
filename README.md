# ⌚ Garmin-to-Drive Sync (Garmin Connector)

This tool automates the export of your Garmin fitness and health data into JSON files and synchronizes them directly with your Google Drive. It is specifically designed to provide a structured, long-term data foundation that can be easily integrated into **AI-powered coaching systems**, custom dashboards, or personal health analytics.

## 🚀 Features

- **Delta Load:** Only fetches new data since the last run (efficient and fast).
- **Full Synchronization:**
    - **Fitness:** Activities (ID, Date, Type, Distance, Duration, Speed, Heart Rate, Calories, Elevation).
    - **Health:** Daily statistics (Resting HR, HRV, Stress level, Sleep hours, Sleep score, Steps).
- **Cloud Connectivity:** Automatic upload and update of files in Google Drive.
- **Automation:** Runs by default every 2 hours as a background process.
- **Docker-Ready:** Easy deployment via Docker and Docker Compose.

## 🛠 Setup

### 1. Prerequisites
- A Garmin account.
- A Google Cloud project with the Drive API enabled (to get `credentials.json`).

### 2. Configuration
Create a `.env` file in the root directory (see `.env.example`):
```env
GARMIN_EMAIL=your.email@gmail.com
GARMIN_PASSWORD=your_password
INITIAL_SYNC_DAYS=90
```
`INITIAL_SYNC_DAYS` defines how many days of history should be fetched during the very first run (if no JSON export files exist yet).

### 3. Google Drive API
Place your `credentials.json` from the Google Cloud Console in the root directory. On the first run, a browser window will open for authentication to generate the `token.json`.

### 4. Start with Docker
The easiest way is using Docker Compose:

```bash
docker-compose up -d
```

The container stays active in the background and performs the sync every 2 hours.

## 📂 File Structure & JSON export

- `garmin_connector.py`: Einstiegspunkt — Garmin-API, JSON-Export, Google-Drive-Upload und Scheduler.
- `garmin_tokens/`: Stores session tokens for Garmin (prevents constant logins).
- `token.json`: Google OAuth refresh token.

### JSON files

- **`fitness_data.json`:** `schema_version` 2 — enthält `athlete` (aktueller Snapshot: u. a. VO₂max Laufen/Radfahren, HR-Zonen, Alter/Gewicht/Größe, Fitnessalter, Ruhepuls, Laktat-Schwellen-HF, Rad-FTP, `fetched_at`) sowie `activities` wie zuvor.
- **`health_data.json`:** Top-level object with `days` (array). Each day includes date, resting HR, HRV, stress, body battery, sleep fields, steps, intensity minutes, and calories.

Both files include `schema_version`, `generated_at`, and `source` metadata for tooling.

## ⚙️ Technical Notes

- **API Security Delay:** To prevent being rate-limited or blocked by the Garmin API, especially during the initial sync (more than 30 days), a "Security Delay" is automatically applied. The script waits briefly between daily health data requests to ensure a stable and safe data transfer.

## 🔒 Security
Sensitive data such as passwords, tokens, and your personal JSON exports are listed in `.gitignore` and `.dockerignore` to prevent accidental sharing.

---
*Note: This tool is intended for private use. Please respect the terms of service of the respective API providers.*
