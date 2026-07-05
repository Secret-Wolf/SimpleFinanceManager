#!/bin/sh
set -e
# Fix data directory ownership if mounted from host (e.g. created by root)
chown -R appuser:appuser /app/data
# Die echte Client-IP (fuer Rate-Limit + Audit-Log) wird APP-seitig ermittelt
# (app/client_ip.py, gesteuert ueber TRUSTED_PROXIES) — bewusst NICHT ueber uvicorns
# --proxy-headers. Dadurch bekommt die App immer die echte Socket-Peer-IP und
# vertraut X-Forwarded-For nur, wenn die Verbindung tatsaechlich von einem in
# TRUSTED_PROXIES gelisteten Proxy kommt. Ein rotierender X-Forwarded-For/
# X-Real-IP kann so keine eigenen Rate-Limit-Buckets mehr erzeugen und keine
# Audit-IP faelschen. Hinter einem Reverse Proxy MUSS TRUSTED_PROXIES gesetzt sein
# (sonst landen alle Requests unter der Proxy-IP in EINEM Bucket).
# --no-proxy-headers ist wichtig: uvicorn wuerde request.client.host sonst SELBST
# aus X-Forwarded-For ableiten (proxy_headers ist per Default an) und damit der
# App-Logik die echte Socket-Peer-IP entziehen.
exec gosu appuser python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --no-proxy-headers
