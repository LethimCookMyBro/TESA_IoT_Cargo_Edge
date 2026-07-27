FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        mosquitto nginx gettext-base \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY cargo ./cargo
COPY training ./training
COPY webapp ./webapp
COPY models ./models
COPY dataset ./dataset
COPY deploy ./deploy

RUN rm -f /etc/nginx/sites-enabled/default && chmod +x /app/deploy/start.sh

ENV PORT=8080
EXPOSE 8080

CMD ["/app/deploy/start.sh"]
