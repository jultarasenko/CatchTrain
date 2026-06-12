FROM python:3.12-slim

WORKDIR /app

COPY watchdog/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY watchdog/ ./watchdog/
COPY uz_watcher/ ./uz_watcher/

CMD ["python", "-m", "watchdog.main"]
