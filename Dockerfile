# Wir nutzen eine schlanke Python-Version
FROM python:3.11-slim

# Setze das Arbeitsverzeichnis im Container
WORKDIR /app

# Kopiere die requirements.txt und installiere die Pakete
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Kopiere alle anderen Dateien ins Arbeitsverzeichnis
COPY . .

# Führe das Skript aus (-u sorgt dafür, dass wir die Print-Ausgaben direkt im Docker-Log sehen)
CMD ["python", "-u", "garmin_connector.py"]