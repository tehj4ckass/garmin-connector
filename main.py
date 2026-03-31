import os
import csv
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

CSV_FITNESS = "fitness_log.csv"
CSV_HEALTH = "health_log.csv"
INITIAL_SYNC_DAYS = int(os.getenv("INITIAL_SYNC_DAYS", 365)) # How many days to fetch if no file exists

SCOPES = ['https://www.googleapis.com/auth/drive.file']

FITNESS_FIELDNAMES = [
    "Activity_ID",
    "Date",
    "Type",
    "Distance_km",
    "Duration_min",
    "Moving_Time_min",
    "Elapsed_Time_min",
    "Avg_Speed_kmh",
    "Max_Speed_kmh",
    "Avg_HR",
    "Max_HR",
    "Avg_Power_W",
    "Max_Power_W",
    "Normalized_Power_W",
    "Work_kJ",
    "Avg_Cadence_rpm",
    "Training_Effect_Aerobic",
    "Training_Effect_Anaerobic",
    "Intensity_Factor",
    "Training_Stress_Score",
    "VO2Max_Estimate",
    "Intensity_Minutes",
    "Calories",
    "Elevation_Gain",
]

HEALTH_FIELDNAMES = [
    "Date",
    "Resting_HR",
    "Avg_HRV",
    "Avg_Stress",
    "Max_Stress",
    "Body_Battery_High",
    "Body_Battery_Low",
    "Sleep_Hours",
    "Sleep_Start_Local",
    "Sleep_End_Local",
    "Sleep_Score",
    "Steps",
    "Intensity_Minutes",
    "Active_Calories",
    "Total_Calories",
]

# --- HELPER FUNCTION FOR DELTA LOAD ---
def get_start_date_and_existing_data(filename, key_column):
    """Reads the CSV, returns existing data and the start date for the delta load."""
    existing_data = {}
    max_date_str = None

    if os.path.exists(filename):
        with open(filename, mode='r', encoding='utf-8') as file:
            reader = csv.DictReader(file, delimiter='|')
            
            for row in reader:
                existing_data[row[key_column]] = row
                row_date = row['Date']
                if not max_date_str or row_date > max_date_str:
                    max_date_str = row_date

    if max_date_str:
        # Start exactly from the last found date to ensure all data for that day is complete
        start_date = date.fromisoformat(max_date_str)
        return start_date, existing_data
    else:
        # File doesn't exist or is empty -> Initial load starting X days ago
        return date.today() - timedelta(days=INITIAL_SYNC_DAYS), existing_data


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
    start_date, existing_fitness = get_start_date_and_existing_data(CSV_FITNESS, 'Activity_ID')
    today = date.today()
    
    print(f"📊 Delta check: {len(existing_fitness)} existing activities found in CSV.")
    print(f"📅 Syncing new activities from {start_date.isoformat()} until today ({today.isoformat()})...")
    
    try:
        def _fmt_num(val, decimals=None):
            if val is None or val == "N/A":
                return "N/A"
            try:
                f = float(val)
                if decimals is None:
                    # Keep integers without trailing .0 when possible
                    if f.is_integer():
                        return str(int(f))
                    return str(f).replace(".", ",")
                return str(round(f, decimals)).replace(".", ",")
            except Exception:
                return "N/A"

        def _get_any(d: dict, keys: list[str]):
            for k in keys:
                if k in d and d.get(k) is not None:
                    return d.get(k)
            return None

        def _seconds_to_minutes_str(seconds, decimals=1):
            if seconds is None:
                return "N/A"
            try:
                return _fmt_num(float(seconds) / 60.0, decimals)
            except Exception:
                return "N/A"

        def _ms_to_kmh_str(ms, decimals=1):
            if ms is None:
                return "N/A"
            try:
                return _fmt_num(float(ms) * 3.6, decimals)
            except Exception:
                return "N/A"

        # Fetch all activities in range
        activities = client.get_activities_by_date(start_date.isoformat(), today.isoformat())
        
        new_count = 0
        for activity in activities:
            activity_id = str(activity.get('activityId', ''))
            distance_km = (activity.get('distance') or 0) / 1000
            elapsed_s = activity.get('duration') or 0
            moving_s = _get_any(activity, ["movingDuration", "movingDurationInSeconds", "movingTimeInSeconds"]) or elapsed_s
            duration_min = elapsed_s / 60 if elapsed_s else 0
            speed_kmh = (activity.get('averageSpeed') or 0) * 3.6
            max_speed_kmh = _ms_to_kmh_str(_get_any(activity, ["maxSpeed", "maximumSpeed"]), 1)

            # Try to extract the requested advanced metrics from the activity summary first.
            avg_power = _get_any(activity, ["averagePower", "avgPower"])
            max_power = _get_any(activity, ["maxPower", "maximumPower"])
            np_power = _get_any(activity, ["normalizedPower", "normPower", "normalizedPowerValue"])
            work_val = _get_any(activity, ["work", "workInJoules", "totalWork", "totalWorkInJoules"])
            avg_cadence = _get_any(activity, ["averageCadence", "avgCadence"])
            te_aer = _get_any(activity, ["aerobicTrainingEffect", "trainingEffect", "aerobicEffect"])
            te_ana = _get_any(activity, ["anaerobicTrainingEffect", "anaerobicEffect"])
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
                for v in [np_power, intensity_factor, tss, vo2, intensity_minutes, avg_power, max_power, work_val, avg_cadence, te_aer, te_ana]
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
            
            row = {
                'Activity_ID': activity_id,
                'Date': activity.get('startTimeLocal', '')[:10],
                'Type': activity.get('activityType', {}).get('typeKey', 'Unknown'),
                'Distance_km': _fmt_num(distance_km, 2),
                'Duration_min': _fmt_num(duration_min, 1),
                'Moving_Time_min': _seconds_to_minutes_str(moving_s, 1),
                'Elapsed_Time_min': _seconds_to_minutes_str(elapsed_s, 1),
                'Avg_Speed_kmh': _fmt_num(speed_kmh, 1),
                'Max_Speed_kmh': max_speed_kmh,
                'Avg_HR': activity.get('averageHR', 'N/A'),
                'Max_HR': activity.get('maxHR', 'N/A'),
                'Avg_Power_W': _fmt_num(avg_power, 0),
                'Max_Power_W': _fmt_num(max_power, 0),
                'Normalized_Power_W': _fmt_num(np_power, 0),
                'Work_kJ': _fmt_num(work_kj, 0),
                'Avg_Cadence_rpm': _fmt_num(avg_cadence, 0),
                'Training_Effect_Aerobic': _fmt_num(te_aer, 1),
                'Training_Effect_Anaerobic': _fmt_num(te_ana, 1),
                'Intensity_Factor': _fmt_num(intensity_factor, 2),
                'Training_Stress_Score': _fmt_num(tss, 0),
                'VO2Max_Estimate': _fmt_num(vo2, 1),
                'Intensity_Minutes': _fmt_num(intensity_minutes, 0),
                'Calories': activity.get('calories', 0),
                'Elevation_Gain': str(round(activity.get('elevationGain', 0), 0)).replace('.', ',') if activity.get('elevationGain') else "0"
            }
            
            # Count if ID is new
            if activity_id not in existing_fitness:
                new_count += 1
                
            # Update dictionary (overwrites old values, adds new ones)
            existing_fitness[activity_id] = row
            
        # Sort data chronologically
        sorted_data = sorted(existing_fitness.values(), key=lambda x: x['Date'])
        
        if sorted_data:
            with open(CSV_FITNESS, mode='w', newline='', encoding='utf-8') as file:
                writer = csv.DictWriter(file, fieldnames=FITNESS_FIELDNAMES, delimiter='|', extrasaction='ignore')
                writer.writeheader()
                for r in sorted_data:
                    for k in FITNESS_FIELDNAMES:
                        if k not in r:
                            r[k] = "N/A"
                    writer.writerow(r)
                
        print(f"✅ Fitness data secured! ({new_count} new/updated activities found)")
        return True
    except Exception as e:
        print(f"❌ Error with fitness data: {e}")
        return False

def fetch_and_save_health(client):
    print("\n💤 Checking health data (Delta Load)...")
    start_date, existing_health = get_start_date_and_existing_data(CSV_HEALTH, 'Date')
    today = date.today()
    
    current_date = start_date
    days_to_fetch = (today - start_date).days + 1
    
    print(f"📊 Delta check: {len(existing_health)} days of health data already stored.")
    print(f"📅 Fetching missing health data for {days_to_fetch} days (from {start_date.isoformat()} to {today.isoformat()})...")
    
    # Small delay for large initial loads to avoid being blocked by Garmin
    delay = 0.5 if days_to_fetch > 30 else 0 

    success_count = 0
    while current_date <= today:
        target_date = current_date.isoformat()
        try:
            def _fmt_num(val, decimals=None):
                if val is None or val == "N/A":
                    return "N/A"
                try:
                    f = float(val)
                    if decimals is None:
                        if f.is_integer():
                            return str(int(f))
                        return str(f).replace(".", ",")
                    return str(round(f, decimals)).replace(".", ",")
                except Exception:
                    return "N/A"

            def _get_any(d: dict, keys: list[str]):
                for k in keys:
                    if k in d and d.get(k) is not None:
                        return d.get(k)
                return None

            def _seconds_to_minutes(val, decimals=0):
                if val is None:
                    return "N/A"
                try:
                    return _fmt_num(float(val) / 60.0, decimals)
                except Exception:
                    return "N/A"

            def _seconds_to_hours(val, decimals=1):
                if val is None:
                    return "N/A"
                try:
                    return _fmt_num(float(val) / 3600.0, decimals)
                except Exception:
                    return "N/A"

            stats = client.get_stats(target_date)
            sleep = client.get_sleep_data(target_date)
            
            hrv_avg = 'N/A'
            try:
                hrv = client.get_hrv_data(target_date)
                if hrv and 'hrvSummary' in hrv and hrv['hrvSummary']:
                    val = hrv['hrvSummary'].get('lastNightAvg')
                    if val is not None:
                        hrv_avg = str(round(float(val), 1)).replace('.', ',')
            except Exception:
                pass 
            
            sleep_score = 'N/A'
            sleep_hours = 0.0
            time_in_bed_hours = "N/A"
            awake_min = "N/A"
            sleep_start_local = "N/A"
            sleep_end_local = "N/A"
            light_min = "N/A"
            deep_min = "N/A"
            rem_min = "N/A"
            
            if sleep and 'dailySleepDTO' in sleep:
                sleep_dto = sleep['dailySleepDTO']
                sleep_time_seconds = sleep_dto.get('sleepTimeSeconds') or 0
                sleep_hours = round(sleep_time_seconds / 3600, 1)
                time_in_bed_hours = _seconds_to_hours(_get_any(sleep_dto, ["timeInBedSeconds", "totalTimeInBedSeconds"]), 1)
                awake_min = _seconds_to_minutes(_get_any(sleep_dto, ["awakeDuration", "awakeTimeSeconds", "awakeDurationSeconds"]), 0)

                sleep_start_local = _get_any(sleep_dto, ["sleepStartTimestampLocal", "sleepStartTimeLocal"])
                sleep_end_local = _get_any(sleep_dto, ["sleepEndTimestampLocal", "sleepEndTimeLocal"])

                # Sleep stages: try map first, then list aggregation.
                stages_map = sleep_dto.get("sleepLevelsMap") if isinstance(sleep_dto.get("sleepLevelsMap"), dict) else None
                if stages_map:
                    light_min = _seconds_to_minutes(_get_any(stages_map, ["light", "LIGHT"]), 0)
                    deep_min = _seconds_to_minutes(_get_any(stages_map, ["deep", "DEEP"]), 0)
                    rem_min = _seconds_to_minutes(_get_any(stages_map, ["rem", "REM"]), 0)
                else:
                    levels = sleep_dto.get("sleepLevels")
                    if isinstance(levels, list):
                        sums = {"light": 0, "deep": 0, "rem": 0}
                        for lvl in levels:
                            if not isinstance(lvl, dict):
                                continue
                            level_name = (lvl.get("sleepLevel") or lvl.get("level") or "").lower()
                            dur = lvl.get("durationInSeconds") or lvl.get("duration") or 0
                            if level_name in sums:
                                try:
                                    sums[level_name] += float(dur)
                                except Exception:
                                    pass
                        if sums["light"] > 0 or sums["deep"] > 0 or sums["rem"] > 0:
                            light_min = _seconds_to_minutes(sums["light"], 0)
                            deep_min = _seconds_to_minutes(sums["deep"], 0)
                            rem_min = _seconds_to_minutes(sums["rem"], 0)
                
                if 'sleepScores' in sleep_dto and 'overall' in sleep_dto['sleepScores']:
                    sleep_score = sleep_dto['sleepScores']['overall'].get('value', 'N/A')
                elif 'sleepScore' in sleep_dto:
                    score_data = sleep_dto['sleepScore']
                    sleep_score = score_data.get('value', 'N/A') if isinstance(score_data, dict) else score_data

            # Daily intensity minutes (if available)
            intensity_minutes = _get_any(stats, ["intensityMinutes", "intensityMinutesValue"])
            if intensity_minutes is None:
                mod = _get_any(stats, ["moderateIntensityMinutes"])
                vig = _get_any(stats, ["vigorousIntensityMinutes"])
                try:
                    if mod is not None or vig is not None:
                        intensity_minutes = (int(mod or 0) + int(vig or 0))
                except Exception:
                    pass

            active_cal = _get_any(stats, ["activeKilocalories", "activeCalories"])
            total_cal = _get_any(stats, ["totalKilocalories", "totalCalories", "burnedKilocalories"])
            floors = _get_any(stats, ["floorsClimbed", "floors", "totalFloorsClimbed"])
            max_stress = _get_any(stats, ["maxStressLevel", "maxStress"])
            bb_high = _get_any(stats, ["bodyBatteryHighestValue", "bodyBatteryHigh", "bodyBatteryMax", "bodyBatteryHighest"])
            bb_low = _get_any(stats, ["bodyBatteryLowestValue", "bodyBatteryLow", "bodyBatteryMin", "bodyBatteryLowest"])

            row = {
                'Date': target_date,
                'Resting_HR': stats.get('restingHeartRate', 'N/A'),
                'Avg_HRV': hrv_avg,
                'Avg_Stress': stats.get('averageStressLevel', 'N/A'),
                'Max_Stress': _fmt_num(max_stress, 0),
                'Body_Battery_High': _fmt_num(bb_high, 0),
                'Body_Battery_Low': _fmt_num(bb_low, 0),
                'Sleep_Hours': str(sleep_hours).replace('.', ','),
                'Sleep_Start_Local': sleep_start_local or "N/A",
                'Sleep_End_Local': sleep_end_local or "N/A",
                'Sleep_Score': sleep_score,
                'Steps': stats.get('totalSteps', 0),
                'Intensity_Minutes': _fmt_num(intensity_minutes, 0),
                'Active_Calories': _fmt_num(active_cal, 0),
                'Total_Calories': _fmt_num(total_cal, 0),
            }
            
            existing_health[target_date] = row
            success_count += 1
            
            # Anti-blocking delay
            if delay > 0:
                time.sleep(delay)
                
        except Exception as e:
            print(f"⚠️ Error for {target_date}: {e}")
            
        current_date += timedelta(days=1)
        
    sorted_data = sorted(existing_health.values(), key=lambda x: x['Date'])
    
    try:
        if sorted_data:
            with open(CSV_HEALTH, mode='w', newline='', encoding='utf-8') as file:
                writer = csv.DictWriter(file, fieldnames=HEALTH_FIELDNAMES, delimiter='|', extrasaction='ignore')
                writer.writeheader()
                for r in sorted_data:
                    for k in HEALTH_FIELDNAMES:
                        if k not in r:
                            r[k] = "N/A"
                    writer.writerow(r)
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
        media = MediaFileUpload(abs_path, mimetype='text/csv', resumable=False)

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
    if 22 <= current_hour or current_hour < 6:
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 💤 Night mode (22:00-06:00). Sync skipped.")
        return

    print(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] ⏰ Starting scheduled data sync...")
    try:
        client = init_garmin()
        if client:
            fitness_success = fetch_and_save_activities(client)
            health_success = fetch_and_save_health(client)
            
            print("\n🚀 Starting cloud upload...")
            if fitness_success: upload_to_drive(CSV_FITNESS)
            if health_success: upload_to_drive(CSV_HEALTH)
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