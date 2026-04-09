import os
import json
import time
import random
import sys
import schedule
from datetime import date, timedelta
from dotenv import load_dotenv
from garminconnect import Garmin

# Google Drive Imports
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# Ensure Unicode output works across Windows terminals (prevents crashes on emoji prints)
try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

# --- CONFIGURATION ---
load_dotenv()
EMAIL = os.getenv("GARMIN_EMAIL")
PASSWORD = os.getenv("GARMIN_PASSWORD")
TOKEN_DIR = "./garmin_tokens"

JSON_FITNESS = "fitness_data.json"
JSON_HEALTH = "health_data.json"
INITIAL_SYNC_DAYS = int(os.getenv("INITIAL_SYNC_DAYS", 365)) # How many days to fetch if no file exists

SCOPES = ['https://www.googleapis.com/auth/drive.file']


def _write_json_export(path: str, payload: dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False, default=str)


def _load_fitness_json_by_id() -> dict:
    if not os.path.exists(JSON_FITNESS):
        return {}
    try:
        with open(JSON_FITNESS, "r", encoding="utf-8") as f:
            doc = json.load(f)
        out = {}
        for a in doc.get("activities", []):
            aid = str(a.get("activity_id", "")).strip()
            if aid:
                out[aid] = a
        return out
    except Exception:
        return {}


def _load_health_json_by_date() -> dict:
    if not os.path.exists(JSON_HEALTH):
        return {}
    try:
        with open(JSON_HEALTH, "r", encoding="utf-8") as f:
            doc = json.load(f)
        out = {}
        for d in doc.get("days", []):
            day = d.get("date")
            if day:
                out[str(day)] = d
        return out
    except Exception:
        return {}


def _fitness_sync_start_date(existing_by_id: dict) -> date:
    """Delta load: resume from last activity date in JSON, else initial window."""
    max_d = None
    for a in existing_by_id.values():
        d = a.get("date")
        if not d:
            continue
        try:
            dd = date.fromisoformat(str(d)[:10])
            if max_d is None or dd > max_d:
                max_d = dd
        except Exception:
            pass
    if max_d:
        return max_d
    return date.today() - timedelta(days=INITIAL_SYNC_DAYS)


def _health_sync_start_date(existing_by_day: dict) -> date:
    max_d = None
    for k in existing_by_day.keys():
        try:
            dd = date.fromisoformat(str(k)[:10])
            if max_d is None or dd > max_d:
                max_d = dd
        except Exception:
            pass
    if max_d:
        return max_d
    return date.today() - timedelta(days=INITIAL_SYNC_DAYS)


# --- PART 1: GARMIN LOGIC ---
def init_garmin():
    client = Garmin(EMAIL, PASSWORD)
    def _is_rate_limit_error(err: Exception) -> bool:
        msg = str(err)
        return ("429" in msg) or ("Too Many Requests" in msg)

    def _sleep_backoff(attempt: int) -> None:
        # Longer exponential backoff: 5min, 15min, 30min (Garmin needs more breathing room)
        base_minutes = 5 * (3 ** attempt)  # 5, 15, 45 minutes
        jitter = random.randint(0, 120)  # Up to 2 min jitter
        wait_s = (base_minutes * 60) + jitter
        wait_min = wait_s // 60
        print(f"⏳ Garmin rate-limited (429). Waiting {wait_min} minutes before retry...")
        time.sleep(wait_s)

    # Important: never do two immediate login attempts back-to-back.
    # Strategy:
    # 1) If stored tokens exist, try to use them WITHOUT triggering SSO login.
    # 2) Only if that fails, attempt an interactive login (with backoff on 429).
    tokens_loaded = False
    if os.path.exists(TOKEN_DIR):
        try:
            client.garth.load(TOKEN_DIR)
            tokens_loaded = True
            # Ensure display_name is set; otherwise endpoints like user summary hit ".../daily/None" -> 403.
            try:
                settings = client.get_userprofile_settings()
                display_name = settings.get("displayName") if isinstance(settings, dict) else None
                if display_name:
                    client.display_name = display_name
            except Exception:
                pass

            # Lightweight "am I authenticated?" call. Should not require SSO widget login.
            client.get_user_profile()
            return client
        except Exception as e:
            if _is_rate_limit_error(e):
                print(f"❌ Garmin rate-limited (429) even when using stored tokens: {str(e)[:200]}")
                return None
            # Otherwise fall through to a real login attempt.

    max_retries = 2  # only 1 retry after initial attempt
    for attempt in range(max_retries):
        try:
            client.login()
            os.makedirs(TOKEN_DIR, exist_ok=True)
            client.garth.dump(TOKEN_DIR)
            return client
        except Exception as e:
            if _is_rate_limit_error(e) and attempt < (max_retries - 1):
                _sleep_backoff(attempt)
                continue
            suffix = " (tokens loaded but unusable)" if tokens_loaded else ""
            print(f"❌ Garmin Login failed{suffix} (will not retry): {str(e)[:200]}")
            return None

def fetch_and_save_activities(client):
    print("\n🚴 Checking fitness data (Delta Load)...")
    existing_fitness_json = _load_fitness_json_by_id()
    ids_before = set(existing_fitness_json.keys())
    start_date = _fitness_sync_start_date(existing_fitness_json)
    today = date.today()

    print(f"📊 Delta check: {len(existing_fitness_json)} existing activities in JSON.")
    print(f"📅 Syncing activities from {start_date.isoformat()} until today ({today.isoformat()})...")

    try:
        def _get_any(d: dict, keys: list[str]):
            for k in keys:
                if k in d and d.get(k) is not None:
                    return d.get(k)
            return None

        def _ms_to_kmh_float(ms):
            if ms is None:
                return None
            try:
                return round(float(ms) * 3.6, 6)
            except Exception:
                return None

        activities = client.get_activities_by_date(start_date.isoformat(), today.isoformat())

        new_count = 0
        for activity in activities:
            activity_id = str(activity.get('activityId', ''))
            distance_km = (activity.get('distance') or 0) / 1000
            elapsed_s = activity.get('duration') or 0
            moving_s = _get_any(activity, ["movingDuration", "movingDurationInSeconds", "movingTimeInSeconds"]) or elapsed_s
            duration_min = elapsed_s / 60 if elapsed_s else 0
            speed_kmh = (activity.get('averageSpeed') or 0) * 3.6
            max_speed_kmh = _ms_to_kmh_float(_get_any(activity, ["maxSpeed", "maximumSpeed"]))

            # Try to extract the requested advanced metrics from the activity summary first.
            avg_power = _get_any(activity, ["averagePower", "avgPower"])
            max_power = _get_any(activity, ["maxPower", "maximumPower"])
            np_power = _get_any(activity, ["normalizedPower", "normPower", "normalizedPowerValue"])
            work_val = _get_any(activity, ["work", "workInJoules", "totalWork", "totalWorkInJoules"])
            avg_cadence = _get_any(activity, ["averageCadence", "avgCadence"])
            te_aer = _get_any(activity, ["aerobicTrainingEffect", "trainingEffect", "aerobicEffect"])
            te_ana = _get_any(activity, ["anaerobicTrainingEffect", "anaerobicEffect"])
            training_effect_primary = _get_any(activity, ["trainingEffect"])
            te_label = _get_any(activity, ["trainingEffectLabel"])
            exercise_load = _get_any(activity, ["exerciseLoad"])
            intensity_factor = _get_any(activity, ["intensityFactor", "if"])
            tss = _get_any(activity, ["trainingStressScore", "tss"])
            vo2 = _get_any(activity, ["vo2MaxValue", "vO2MaxValue", "vo2Max", "VO2MaxValue"])
            intensity_minutes = _get_any(activity, ["intensityMinutes", "intensityMinutesValue"])
            if intensity_minutes is None:
                mod = _get_any(activity, ["moderateIntensityMinutes"])
                vig = _get_any(activity, ["vigorousIntensityMinutes"])
                try:
                    if mod is not None or vig is not None:
                        intensity_minutes = (int(mod or 0) + int(vig or 0))
                except Exception:
                    pass

            # If key fields are missing, fetch details (1 extra call per activity at most).
            needs_details = any(
                v is None
                for v in [
                    np_power, intensity_factor, tss, vo2, intensity_minutes, avg_power, max_power,
                    work_val, avg_cadence, te_aer, te_ana, training_effect_primary, te_label, exercise_load,
                ]
            )
            if needs_details and activity_id:
                try:
                    details = client.get_activity_details(activity_id) or {}
                    if isinstance(details, dict):
                        avg_power = avg_power if avg_power is not None else _get_any(details, ["averagePower", "avgPower"])
                        max_power = max_power if max_power is not None else _get_any(details, ["maxPower", "maximumPower"])
                        np_power = np_power if np_power is not None else _get_any(details, ["normalizedPower", "normPower", "normalizedPowerValue"])
                        work_val = work_val if work_val is not None else _get_any(details, ["work", "workInJoules", "totalWork", "totalWorkInJoules"])
                        avg_cadence = avg_cadence if avg_cadence is not None else _get_any(details, ["averageCadence", "avgCadence"])
                        te_aer = te_aer if te_aer is not None else _get_any(details, ["aerobicTrainingEffect", "trainingEffect", "aerobicEffect"])
                        te_ana = te_ana if te_ana is not None else _get_any(details, ["anaerobicTrainingEffect", "anaerobicEffect"])
                        training_effect_primary = training_effect_primary if training_effect_primary is not None else _get_any(details, ["trainingEffect"])
                        te_label = te_label if te_label is not None else _get_any(details, ["trainingEffectLabel"])
                        exercise_load = exercise_load if exercise_load is not None else _get_any(details, ["exerciseLoad"])
                        intensity_factor = intensity_factor if intensity_factor is not None else _get_any(details, ["intensityFactor", "if"])
                        tss = tss if tss is not None else _get_any(details, ["trainingStressScore", "tss"])
                        vo2 = vo2 if vo2 is not None else _get_any(details, ["vo2MaxValue", "vO2MaxValue", "vo2Max", "VO2MaxValue"])
                        intensity_minutes = intensity_minutes if intensity_minutes is not None else _get_any(details, ["intensityMinutes", "intensityMinutesValue"])
                        if intensity_minutes is None:
                            mod = _get_any(details, ["moderateIntensityMinutes"])
                            vig = _get_any(details, ["vigorousIntensityMinutes"])
                            try:
                                if mod is not None or vig is not None:
                                    intensity_minutes = (int(mod or 0) + int(vig or 0))
                            except Exception:
                                pass
                except Exception:
                    pass

            # Work_kJ: try to interpret Garmin's "work" value; if unavailable, approximate from avg power & moving time.
            work_kj = None
            try:
                if work_val is not None:
                    w = float(work_val)
                    # Heuristic: if it's huge, treat as Joules; else treat as kJ
                    work_kj = (w / 1000.0) if w > 5000 else w
                elif avg_power is not None and moving_s:
                    work_kj = (float(avg_power) * float(moving_s)) / 1000.0
            except Exception:
                work_kj = None

            hr_zones_data = None
            if activity_id:
                try:
                    hr_zones_data = client.get_activity_hr_in_timezones(activity_id)
                except Exception:
                    hr_zones_data = None
                time.sleep(0.12)

            def _jn(v):
                if v is None:
                    return None
                try:
                    if isinstance(v, bool):
                        return v
                    return float(v)
                except Exception:
                    return None

            te_main = training_effect_primary if training_effect_primary is not None else te_aer
            json_activity = {
                "activity_id": activity_id,
                "date": activity.get("startTimeLocal", "")[:10],
                "activity_type": activity.get("activityType", {}).get("typeKey", "Unknown"),
                "distance_km": round(distance_km, 6) if distance_km else None,
                "duration_min": round(duration_min, 4) if duration_min else None,
                "moving_time_min": (float(moving_s) / 60.0) if moving_s else None,
                "elapsed_time_min": (float(elapsed_s) / 60.0) if elapsed_s else None,
                "avg_speed_kmh": round(speed_kmh, 4) if speed_kmh else None,
                "max_speed_kmh": max_speed_kmh,
                "avg_hr": _jn(activity.get("averageHR")),
                "max_hr": _jn(activity.get("maxHR")),
                "avg_power_w": _jn(avg_power),
                "max_power_w": _jn(max_power),
                "normalized_power_w": _jn(np_power),
                "work_kj": _jn(work_kj),
                "avg_cadence_rpm": _jn(avg_cadence),
                "training_effect": _jn(te_main),
                "aerobic_training_effect": _jn(te_aer),
                "anaerobic_training_effect": _jn(te_ana),
                "training_effect_label": te_label,
                "exercise_load": _jn(exercise_load),
                "intensity_factor": _jn(intensity_factor),
                "training_stress_score": _jn(tss),
                "vo2max_estimate": _jn(vo2),
                "intensity_minutes": _jn(intensity_minutes),
                "calories": _jn(activity.get("calories")),
                "elevation_gain": _jn(activity.get("elevationGain")),
                "hr_zones": hr_zones_data,
            }
            existing_fitness_json[activity_id] = json_activity

            if activity_id and activity_id not in ids_before:
                new_count += 1

        if existing_fitness_json:
            sorted_activities = sorted(
                existing_fitness_json.values(),
                key=lambda x: (x.get("date") or "", x.get("activity_id") or ""),
            )
            _write_json_export(
                JSON_FITNESS,
                {
                    "schema_version": 1,
                    "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "source": "garmin-connector",
                    "activities": sorted_activities,
                },
            )

        print(f"✅ Fitness data secured! ({new_count} new activities)")
        return True
    except Exception as e:
        print(f"❌ Error with fitness data: {e}")
        return False

def fetch_and_save_health(client):
    print("\n💤 Checking health data (Delta Load)...")
    existing_health_json = _load_health_json_by_date()
    start_date = _health_sync_start_date(existing_health_json)
    today = date.today()

    current_date = start_date
    days_to_fetch = (today - start_date).days + 1

    print(f"📊 Delta check: {len(existing_health_json)} days of health data already stored.")
    print(f"📅 Fetching health data for {days_to_fetch} days (from {start_date.isoformat()} to {today.isoformat()})...")

    delay = 0.5 if days_to_fetch > 30 else 0

    success_count = 0

    def _get_any(d: dict, keys: list[str]):
        for k in keys:
            if k in d and d.get(k) is not None:
                return d.get(k)
        return None

    def _jn_h(v):
        if v is None:
            return None
        try:
            return float(v)
        except Exception:
            return None

    while current_date <= today:
        target_date = current_date.isoformat()
        try:
            stats = client.get_stats(target_date)
            sleep = client.get_sleep_data(target_date)

            hrv_avg = None
            try:
                hrv = client.get_hrv_data(target_date)
                if hrv and "hrvSummary" in hrv and hrv["hrvSummary"]:
                    val = hrv["hrvSummary"].get("lastNightAvg")
                    if val is not None:
                        hrv_avg = round(float(val), 1)
            except Exception:
                pass

            sleep_score = None
            sleep_hours = None
            sleep_start_local = None
            sleep_end_local = None

            if sleep and "dailySleepDTO" in sleep:
                sleep_dto = sleep["dailySleepDTO"]
                sleep_time_seconds = sleep_dto.get("sleepTimeSeconds") or 0
                sleep_hours = round(sleep_time_seconds / 3600.0, 4)

                sleep_start_local = _get_any(sleep_dto, ["sleepStartTimestampLocal", "sleepStartTimeLocal"])
                sleep_end_local = _get_any(sleep_dto, ["sleepEndTimestampLocal", "sleepEndTimeLocal"])

                if "sleepScores" in sleep_dto and "overall" in sleep_dto["sleepScores"]:
                    v = sleep_dto["sleepScores"]["overall"].get("value")
                    sleep_score = _jn_h(v)
                elif "sleepScore" in sleep_dto:
                    score_data = sleep_dto["sleepScore"]
                    sleep_score = _jn_h(score_data.get("value")) if isinstance(score_data, dict) else _jn_h(score_data)

            intensity_minutes = _get_any(stats, ["intensityMinutes", "intensityMinutesValue"])
            if intensity_minutes is None:
                mod = _get_any(stats, ["moderateIntensityMinutes"])
                vig = _get_any(stats, ["vigorousIntensityMinutes"])
                try:
                    if mod is not None or vig is not None:
                        intensity_minutes = int(mod or 0) + int(vig or 0)
                except Exception:
                    pass

            active_cal = _get_any(stats, ["activeKilocalories", "activeCalories"])
            total_cal = _get_any(stats, ["totalKilocalories", "totalCalories", "burnedKilocalories"])
            max_stress = _get_any(stats, ["maxStressLevel", "maxStress"])
            bb_high = _get_any(stats, ["bodyBatteryHighestValue", "bodyBatteryHigh", "bodyBatteryMax", "bodyBatteryHighest"])
            bb_low = _get_any(stats, ["bodyBatteryLowestValue", "bodyBatteryLow", "bodyBatteryMin", "bodyBatteryLowest"])

            day_record = {
                "date": target_date,
                "resting_hr": int(stats["restingHeartRate"]) if stats.get("restingHeartRate") is not None else None,
                "avg_hrv": hrv_avg,
                "avg_stress": _jn_h(stats.get("averageStressLevel")),
                "max_stress": _jn_h(max_stress),
                "body_battery_high": _jn_h(bb_high),
                "body_battery_low": _jn_h(bb_low),
                "sleep_hours": sleep_hours,
                "sleep_start_local": sleep_start_local,
                "sleep_end_local": sleep_end_local,
                "sleep_score": sleep_score,
                "steps": int(stats["totalSteps"]) if stats.get("totalSteps") is not None else None,
                "intensity_minutes": _jn_h(intensity_minutes),
                "active_calories": _jn_h(active_cal),
                "total_calories": _jn_h(total_cal),
            }
            existing_health_json[target_date] = day_record
            success_count += 1

            if delay > 0:
                time.sleep(delay)

        except Exception as e:
            print(f"⚠️ Error for {target_date}: {e}")

        current_date += timedelta(days=1)

    try:
        if existing_health_json:
            sorted_days = sorted(existing_health_json.values(), key=lambda x: x.get("date", ""))
            _write_json_export(
                JSON_HEALTH,
                {
                    "schema_version": 1,
                    "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "source": "garmin-connector",
                    "days": sorted_days,
                },
            )
        print(f"✅ Health data secured! ({success_count} entries processed)")
        return True
    except Exception as e:
        print(f"❌ Error saving: {e}")
        return False

# --- PART 2: GOOGLE DRIVE LOGIC ---
def get_drive_service():
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    
    # If no valid credentials exist, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception:
                # Refresh failed (e.g. revoked)
                creds = None
        
        if not creds:
            if not os.path.exists('credentials.json'):
                print("❌ 'credentials.json' not found! Please download it from the Google Cloud Console.")
                return None
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
            
        # Save credentials for the next run
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
            
    return build('drive', 'v3', credentials=creds)

def upload_to_drive(filename):
    try:
        service = get_drive_service()
        if not service:
            return

        if not os.path.exists(filename):
            print(f"❌ Local file not found for upload: '{filename}'")
            return

        abs_path = os.path.abspath(filename)
        local_size = os.path.getsize(abs_path)
        mimetype = "application/json"
        media = MediaFileUpload(abs_path, mimetype=mimetype, resumable=False)

        # Crucial: only update the "real" file in Drive root, never a trashed one.
        # Otherwise the code can update an item in the Papierkorb and leave Root unchanged.
        q_root = f"name='{filename}' and trashed=false and 'root' in parents"
        response = service.files().list(
            q=q_root,
            spaces='drive',
            fields='files(id, name, trashed, parents)'
        ).execute()
        files = response.get('files', [])

        if not files:
            # Diagnostic: log whether we are hitting trashed duplicates.
            q_trash = f"name='{filename}' and trashed=true"
            trash_resp = service.files().list(
                q=q_trash,
                spaces='drive',
                fields='files(id, name)'
            ).execute()
            trashed_files = trash_resp.get('files', [])
            if trashed_files:
                print(f"☁️ Found {len(trashed_files)} trashed Drive file(s) for '{filename}' (will not update them).")

            file_metadata = {'name': filename, 'parents': ['root']}
            print(f"☁️ Uploading new file '{filename}' to Drive root... (local {local_size} bytes)")
            created = service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id, name, webViewLink'
            ).execute()
            print(f"☁️ Created: id={created.get('id')} link={created.get('webViewLink')}")
        else:
            file_id = files[0].get('id')
            print(f"☁️ Updating file '{filename}' in Drive root... (id={file_id})")
            updated = service.files().update(
                fileId=file_id,
                media_body=media,
                fields='id, name, webViewLink'
            ).execute()
            print(f"☁️ Updated: id={updated.get('id')} link={updated.get('webViewLink')}")
    except Exception as e:
        print(f"❌ Error uploading {filename}: {e}")

# --- MAIN PROGRAM ---
def job():
    """This function runs every 2 hours."""
    # Check night mode (22:00 - 06:00)
    current_hour = time.localtime().tm_hour
    if 23 <= current_hour or current_hour < 6:
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 💤 Night mode (22:00-06:00). Sync skipped.")
        return

    print(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] ⏰ Starting scheduled data sync...")
    try:
        client = init_garmin()
        if client:
            fitness_success = fetch_and_save_activities(client)
            health_success = fetch_and_save_health(client)
            
            print("\n🚀 Starting cloud upload...")
            if fitness_success:
                upload_to_drive(JSON_FITNESS)
            if health_success:
                upload_to_drive(JSON_HEALTH)
            print("🎉 All systems up to date!")
            
            # Calculate next run (current time + 2 hours)
            next_run_time = time.strftime('%H:%M:%S', time.localtime(time.time() + 7200))
            print(f"🕒 Next sync scheduled for approx. {next_run_time} (if not in night mode).")
        else:
            print("❌ Sync failed: Garmin login failed.")
    except Exception as e:
        print(f"❌ Unexpected error in job: {e}")

if __name__ == "__main__":
    print("🚀 Garmin AI Coach Container started!")
    
    # 1. Run once immediately on container start
    job()
    
    # 2. Set schedule (every 2 hours)
    schedule.every(2).hours.do(job)
    print("\n⏳ Scheduler active. Waiting for next cycle (in 2 hours, skipping 22:00-06:00)...")
    
    # 3. Main loop to keep container alive
    while True:
        schedule.run_pending()
        time.sleep(30) # Check every 30 seconds if it's time to run again