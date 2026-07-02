#!/bin/sh
set -e
# Fix data directory ownership if mounted from host (e.g. created by root)
chown -R appuser:appuser /app/data
# Hinter einem Reverse Proxy (Traefik/nginx) muss die echte Client-IP aus
# X-Forwarded-For uebernommen werden, sonst zaehlen Rate-Limits und Audit-Log
# nur die Proxy-IP (ein globaler Bucket fuer alle Clients = trivialer DoS).
# Welche Proxy-IPs vertrauenswuerdig sind, steuert FORWARDED_ALLOW_IPS:
#  - "*"       wenn die App NUR ueber den Proxy erreichbar ist (expose/127.0.0.1-Bind)
#  - leer      (Default 127.0.0.1) wenn der Port direkt im LAN veroeffentlicht ist
exec gosu appuser python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 \
    --proxy-headers --forwarded-allow-ips "${FORWARDED_ALLOW_IPS:-127.0.0.1}"
