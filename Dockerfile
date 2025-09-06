# Kick Off Kings — container image with gunicorn
FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
COPY app.py /app/app.py
RUN mkdir -p /app/data /app/static
COPY static/ /app/static/
VOLUME ["/app/data"]
ENV NFL_YEAR=2025 NFL_SEASONTYPE=2 FLASK_SECRET=change-me USERS=user1,user2
EXPOSE 8000
CMD ["gunicorn", "-b", "0.0.0.0:8000", "app:app", "--workers", "2", "--threads", "4", "--timeout", "90"]
