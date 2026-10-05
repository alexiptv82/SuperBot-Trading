FROM python:3.11-slim

WORKDIR /app

# Installa dipendenze sistema
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copia e installa dipendenze Python
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

# Copia il codice backend
COPY backend/ ./backend/

# Crea cartella dati
RUN mkdir -p /app/data

EXPOSE 8001

CMD ["python", "-m", "uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8001"]
