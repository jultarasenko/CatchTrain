FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY uz_watcher/ ./uz_watcher/

CMD ["python", "-m", "uz_watcher.main"]
