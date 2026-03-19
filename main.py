import os
import csv
import time
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

# --- CONFIGURATION ---
load_dotenv()
EMAIL = os.getenv("GARMIN_EMAIL")
PASSWORD = os.getenv("GARMIN_PASSWORD")
TOKEN_DIR = "./garmin_tokens"

CSV_FITNESS = "fitness_log.csv"
CSV_HEALTH = "health_log.csv"
INITIAL_SYNC_DAYS = int(os.getenv("INITIAL_SYNC_DAYS", 365)) # How many days to fetch if no file exists

SCOPES = ['https://www.googleapis.com/auth/drive.file']

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
    if os.path.exists(TOKEN_DIR):
        try:
            client.garth.load(TOKEN_DIR)
            client.login()
            return client
        except Exception:
            pass 
            
    try:
        client.login()
        os.makedirs(TOKEN_DIR, exist_ok=True)
        client.garth.dump(TOKEN_DIR)
        return client
    except Exception as e:
        print(f"❌ Garmin Login failed: {e}")
        return None

def fetch_and_save_activities(client):
    print("\n🚴 Checking fitness data (Delta Load)...")
    start_date, existing_fitness = get_start_date_and_existing_data(CSV_FITNESS, 'Activity_ID')
    today = date.today()
    
    print(f"📊 Delta check: {len(existing_fitness)} existing activities found in CSV.")
    print(f"📅 Syncing new activities from {start_date.isoformat()} until today ({today.isoformat()})...")
    
    try:
        # Fetch all activities in range
        activities = client.get_activities_by_date(start_date.isoformat(), today.isoformat())
        
        new_count = 0
        for activity in activities:
            activity_id = str(activity.get('activityId', ''))
            distance_km = activity.get('distance', 0) / 1000 if activity.get('distance') else 0
            duration_min = activity.get('duration', 0) / 60 if activity.get('duration') else 0
            speed_kmh = activity.get('averageSpeed', 0) * 3.6 if activity.get('averageSpeed') else 0
            
            row = {
                'Activity_ID': activity_id,
                'Date': activity.get('startTimeLocal', '')[:10],
                'Type': activity.get('activityType', {}).get('typeKey', 'Unknown'),
                'Distance_km': str(round(distance_km, 2)).replace('.', ','),
                'Duration_min': str(round(duration_min, 1)).replace('.', ','),
                'Avg_Speed_kmh': str(round(speed_kmh, 1)).replace('.', ','),
                'Avg_HR': activity.get('averageHR', 'N/A'),
                'Max_HR': activity.get('maxHR', 'N/A'),
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
                writer = csv.DictWriter(file, fieldnames=sorted_data[0].keys(), delimiter='|')
                writer.writeheader()
                writer.writerows(sorted_data)
                
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
            
            if sleep and 'dailySleepDTO' in sleep:
                sleep_dto = sleep['dailySleepDTO']
                sleep_time_seconds = sleep_dto.get('sleepTimeSeconds') or 0
                sleep_hours = round(sleep_time_seconds / 3600, 1)
                
                if 'sleepScores' in sleep_dto and 'overall' in sleep_dto['sleepScores']:
                    sleep_score = sleep_dto['sleepScores']['overall'].get('value', 'N/A')
                elif 'sleepScore' in sleep_dto:
                    score_data = sleep_dto['sleepScore']
                    sleep_score = score_data.get('value', 'N/A') if isinstance(score_data, dict) else score_data

            row = {
                'Date': target_date,
                'Resting_HR': stats.get('restingHeartRate', 'N/A'),
                'Avg_HRV': hrv_avg,
                'Avg_Stress': stats.get('averageStressLevel', 'N/A'),
                'Sleep_Hours': str(sleep_hours).replace('.', ','),
                'Sleep_Score': sleep_score,
                'Steps': stats.get('totalSteps', 0)
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
                writer = csv.DictWriter(file, fieldnames=sorted_data[0].keys(), delimiter='|')
                writer.writeheader()
                writer.writerows(sorted_data)
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