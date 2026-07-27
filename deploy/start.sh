#!/bin/sh
set -e

mosquitto -c /app/deploy/mosquitto.conf &

# ponytail: stdlib socket poll instead of netcat, so the container needs no extra package.
python3 -c "
import socket, time
for _ in range(30):
    try:
        socket.create_connection(('127.0.0.1', 1883), timeout=1).close()
        break
    except OSError:
        time.sleep(0.5)
"

python3 -m cargo.mqtt_service &

envsubst '${PORT}' < /app/deploy/nginx.conf.template > /etc/nginx/sites-enabled/default
exec nginx -g 'daemon off;'
