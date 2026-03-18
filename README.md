# ⌚ Garmin-to-Drive Sync (Garmin Connector)

This tool automates the export of your Garmin fitness and health data into CSV files and synchronizes them directly with your Google Drive. It serves as a data foundation for analyses, dashboards, or AI-powered coaching systems.

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
`INITIAL_SYNC_DAYS` defines how many days of history should be fetched during the very first run (if no CSV files exist).

### 3. Google Drive API
Place your `credentials.json` from the Google Cloud Console in the root directory. On the first run, a browser window will open for authentication to generate the `token.json`.

### 4. Start with Docker
The easiest way is using Docker Compose:

```bash
docker-compose up -d
```

The container stays active in the background and performs the sync every 2 hours.

## 📂 File Structure & CSV Reference

- `main.py`: Main logic for Garmin API and Google Drive upload.
- `garmin_tokens/`: Stores session tokens for Garmin (prevents constant logins).
- `token.json`: Google OAuth refresh token.

### 📋 CSV Data Format
All CSV files use a pipe `|` as a delimiter and commas `,` for decimal values to ensure compatibility with various analysis tools.

#### `fitness_log.csv` (Activities)
| Column | Description |
| :--- | :--- |
| **Activity_ID** | Unique identifier from Garmin for the activity. |
| **Date** | Date of the activity (YYYY-MM-DD). |
| **Type** | Type of activity (e.g., `running`, `cycling`, `walking`). |
| **Distance_km** | Total distance covered in kilometers. |
| **Duration_min** | Total duration of the activity in minutes. |
| **Avg_Speed_kmh** | Average speed during the activity (km/h). |
| **Avg_HR** | Average heart rate during the activity. |
| **Max_HR** | Maximum heart rate reached. |
| **Calories** | Total calories burned. |
| **Elevation_Gain** | Total elevation gain in meters. |

#### `health_log.csv` (Daily Metrics)
| Column | Description |
| :--- | :--- |
| **Date** | The specific day (YYYY-MM-DD). |
| **Resting_HR** | Resting heart rate for that day. |
| **Avg_HRV** | Average Heart Rate Variability (HRV) during the night. |
| **Avg_Stress** | Average stress level (0-100). |
| **Sleep_Hours** | Total duration of sleep in hours. |
| **Sleep_Score** | Garmin Sleep Score (0-100). |
| **Steps** | Total step count for the day. |

## ⚙️ Technical Notes

- **API Security Delay:** To prevent being rate-limited or blocked by the Garmin API, especially during the initial sync (more than 30 days), a "Security Delay" is automatically applied. The script waits briefly between daily health data requests to ensure a stable and safe data transfer.

## 🔒 Security
Sensitive data such as passwords, tokens, and your personal CSV logs are listed in `.gitignore` and `.dockerignore` to prevent accidental sharing.

---
*Note: This tool is intended for private use. Please respect the terms of service of the respective API providers.*
