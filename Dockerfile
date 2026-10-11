FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    HOME=/tmp XDG_CACHE_HOME=/tmp/.cache
WORKDIR /app
# WeasyPrint braucht Pango; msmtp für den Mailversand.
# Die Kalenderschrift Barlow Condensed liegt im Projekt (static/fonts), DejaVu ist Rückfall.
RUN apt-get update && apt-get install -y --no-install-recommends \
      libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0 fonts-dejavu-core \
      msmtp ca-certificates \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN DJANGO_SECRET_KEY=build DJANGO_DEBUG=0 python manage.py collectstatic --noinput
# Threads: die Karte lädt viele TomTom-Kacheln parallel über den eigenen Server.
# Laufzeit ohne root: UID/GID 1000. Programmdateien gehören root und sind nur lesbar.
USER 1000:1000
CMD ["sh", "-c", "python manage.py migrate --noinput && gunicorn config.wsgi -b 0.0.0.0:8000 -w 3 --threads 4 --timeout 120"]
