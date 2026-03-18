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

# --- KONFIGURATION ---
load_dotenv()
EMAIL = os.getenv("GARMIN_EMAIL")
PASSWORD = os.getenv("GARMIN_PASSWORD")
TOKEN_DIR = "./garmin_tokens"

CSV_FITNESS = "fitness_log.csv"
CSV_HEALTH = "health_log.csv"
INITIAL_START_DATE = "2025-06-01" # Startdatum für den allerersten Lauf

SCOPES = ['https://www.googleapis.com/auth/drive.file']

# --- HILFSFUNKTION FÜR DELTA LOAD ---
def get_start_date_and_existing_data(filename, key_column):
    """Liest die CSV, gibt die bestehenden Daten und das Startdatum für das Delta zurück."""
    existing_data = {}
    max_date_str = None

    if os.path.exists(filename):
        with open(filename, mode='r', encoding='utf-8') as file:
            reader = csv.DictReader(file, delimiter='|')
            for row in reader:
                existing_data[row[key_column]] = row
                row_date = row['Datum']
                if not max_date_str or row_date > max_date_str:
                    max_date_str = row_date

    if max_date_str:
        # Wir gehen 2 Tage zurück, um laufende Tage (heute/gestern) zu aktualisieren
        start_date = date.fromisoformat(max_date_str) - timedelta(days=2)
        return start_date, existing_data
    else:
        # Datei existiert nicht oder ist leer -> Initial-Load ab 01.06.2025
        return date.fromisoformat(INITIAL_START_DATE), existing_data


# --- TEIL 1: GARMIN LOGIK ---
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
        print(f"❌ Garmin Login fehlgeschlagen: {e}")
        return None

def fetch_and_save_activities(client):
    print("\n🚴 Prüfe Fitness-Daten (Delta Load)...")
    start_date, existing_fitness = get_start_date_and_existing_data(CSV_FITNESS, 'Activity_ID')
    today = date.today()
    
    print(f"Lade Aktivitäten vom {start_date.isoformat()} bis {today.isoformat()}...")
    
    try:
        # Holt alle Aktivitäten im Zeitraum
        activities = client.get_activities_by_date(start_date.isoformat(), today.isoformat())
        
        new_count = 0
        for activity in activities:
            activity_id = str(activity.get('activityId', ''))
            distance_km = activity.get('distance', 0) / 1000 if activity.get('distance') else 0
            duration_min = activity.get('duration', 0) / 60 if activity.get('duration') else 0
            speed_kmh = activity.get('averageSpeed', 0) * 3.6 if activity.get('averageSpeed') else 0
            
            row = {
                'Activity_ID': activity_id,
                'Datum': activity.get('startTimeLocal', '')[:10],
                'Typ': activity.get('activityType', {}).get('typeKey', 'Unbekannt'),
                'Distanz_km': str(round(distance_km, 2)).replace('.', ','),
                'Dauer_min': str(round(duration_min, 1)).replace('.', ','),
                'Avg_Speed_kmh': str(round(speed_kmh, 1)).replace('.', ','),
                'Avg_Puls': activity.get('averageHR', 'N/A'),
                'Max_Puls': activity.get('maxHR', 'N/A'),
                'Kalorien': activity.get('calories', 0),
                'Hoehenmeter': str(round(activity.get('elevationGain', 0), 0)).replace('.', ',') if activity.get('elevationGain') else "0"
            }
            
            # Wenn ID neu ist, zählen wir mit
            if activity_id not in existing_fitness:
                new_count += 1
                
            # Dictionary aktualisieren (überschreibt alte Werte, fügt neue hinzu)
            existing_fitness[activity_id] = row
            
        # Daten chronologisch sortieren
        sorted_data = sorted(existing_fitness.values(), key=lambda x: x['Datum'])
        
        if sorted_data:
            with open(CSV_FITNESS, mode='w', newline='', encoding='utf-8') as file:
                writer = csv.DictWriter(file, fieldnames=sorted_data[0].keys(), delimiter='|')
                writer.writeheader()
                writer.writerows(sorted_data)
                
        print(f"✅ Fitness-Daten gesichert! ({new_count} neue/aktualisierte Aktivitäten gefunden)")
        return True
    except Exception as e:
        print(f"❌ Fehler bei Fitness-Daten: {e}")
        return False

def fetch_and_save_health(client):
    print("\n💤 Prüfe Health-Daten (Delta Load)...")
    start_date, existing_health = get_start_date_and_existing_data(CSV_HEALTH, 'Datum')
    today = date.today()
    
    current_date = start_date
    days_to_fetch = (today - start_date).days + 1
    
    print(f"Lade Health-Daten für {days_to_fetch} Tage (ab {start_date.isoformat()})...")
    
    # Kleine Verzögerung bei riesigem Initial-Load, damit Garmin uns nicht blockt
    delay = 0.5 if days_to_fetch > 30 else 0 

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
                'Datum': target_date,
                'Ruhepuls': stats.get('restingHeartRate', 'N/A'),
                'Avg_HRV': hrv_avg,
                'Avg_Stress': stats.get('averageStressLevel', 'N/A'),
                'Schlaf_Stunden': str(sleep_hours).replace('.', ','),
                'Schlaf_Score': sleep_score,
                'Schritte': stats.get('totalSteps', 0)
            }
            
            existing_health[target_date] = row
            
            # Anti-Blockade-Pause für Garmin
            if delay > 0:
                time.sleep(delay)
                
        except Exception as e:
            print(f"⚠️ Fehler für {target_date}: {e}")
            
        current_date += timedelta(days=1)
        
    sorted_data = sorted(existing_health.values(), key=lambda x: x['Datum'])
    
    try:
        if sorted_data:
            with open(CSV_HEALTH, mode='w', newline='', encoding='utf-8') as file:
                writer = csv.DictWriter(file, fieldnames=sorted_data[0].keys(), delimiter='|')
                writer.writeheader()
                writer.writerows(sorted_data)
        print("✅ Health-Daten gesichert!")
        return True
    except Exception as e:
        print(f"❌ Fehler beim Speichern: {e}")
        return False

# --- TEIL 2: GOOGLE DRIVE LOGIK ---
def get_drive_service():
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    
    # Wenn keine gültigen Anmeldedaten vorliegen, lassen wir den Nutzer sich anmelden.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception:
                # Refresh fehlgeschlagen (z.B. Revoked)
                creds = None
        
        if not creds:
            if not os.path.exists('credentials.json'):
                print("❌ 'credentials.json' nicht gefunden! Bitte von Google Cloud Console herunterladen.")
                return None
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
            
        # Speichere die neuen Tokens für das nächste Mal
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
            
    return build('drive', 'v3', credentials=creds)

def upload_to_drive(filename):
    try:
        service = get_drive_service()
        if not service:
            return

        response = service.files().list(q=f"name='{filename}'", spaces='drive', fields='files(id, name)').execute()
        files = response.get('files', [])
        media = MediaFileUpload(filename, mimetype='text/csv')
        
        if not files:
            file_metadata = {'name': filename}
            print(f"☁️ Lade neue Datei '{filename}' hoch...")
            service.files().create(body=file_metadata, media_body=media, fields='id').execute()
        else:
            file_id = files[0].get('id')
            print(f"☁️ Aktualisiere Datei '{filename}'...")
            service.files().update(fileId=file_id, media_body=media).execute()
    except Exception as e:
        print(f"❌ Fehler beim Upload von {filename}: {e}")

# --- HAUPTPROGRAMM ---
def job():
    """Diese Funktion wird alle 2 Stunden ausgeführt."""
    print(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] ⏰ Starte geplanten Daten-Sync...")
    client = init_garmin()
    if client:
        fitness_success = fetch_and_save_activities(client)
        health_success = fetch_and_save_health(client)
        
        print("\n🚀 Starte Cloud-Upload...")
        if fitness_success: upload_to_drive(CSV_FITNESS)
        if health_success: upload_to_drive(CSV_HEALTH)
        print("🎉 Alle Systeme aktuell!")

if __name__ == "__main__":
    print("🚀 Garmin AI Coach Container gestartet!")
    
    # 1. Einmal sofort ausführen beim Start des Containers
    job()
    
    # 2. Den Zeitplan festlegen (alle 2 Stunden)
    schedule.every(2).hours.do(job)
    print("\n⏳ Zeitschaltuhr aktiv. Warte auf den nächsten Zyklus (in 2 Stunden)...")
    
    # 3. Die Endlosschleife, die den Container am Leben hält
    while True:
        schedule.run_pending()
        time.sleep(60) # Prüft jede Minute, ob es Zeit für einen neuen Lauf ist