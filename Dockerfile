FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential curl \
    && rm -rf /var/lib/apt/lists/*

COPY my_agent/requirements.txt /app/my_agent/requirements.txt
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r /app/my_agent/requirements.txt

COPY my_agent /app/my_agent

EXPOSE 8000

CMD ["sh", "-c", "uvicorn my_agent.api.a2a:app --host 0.0.0.0 --port ${PORT:-8000}"]
