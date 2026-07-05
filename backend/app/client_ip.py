"""Vertrauenswuerdige Ermittlung der Client-IP hinter einem Reverse Proxy.

Rate-Limiting (slowapi) und Audit-Log duerfen sich NICHT auf einen vom Client
frei setzbaren Header verlassen. Sonst kann ein Angreifer per rotierendem
``X-Forwarded-For``/``X-Real-IP`` fuer jeden Request einen eigenen Rate-Limit-
Bucket erzeugen (unbegrenzter Login-Brute-Force) und die Audit-Log-IP faelschen.

Regel (Defense-in-Depth, unabhaengig von uvicorns Proxy-Header-Handling):
1. Ist ``TRUSTED_PROXIES`` leer, wird die Socket-Peer-IP genommen (LAN/dev).
2. Kommt die DIREKTE Verbindung NICHT von einem vertrauenswuerdigen Proxy, wird
   ``X-Forwarded-For`` ignoriert und die Socket-Peer-IP genommen. Ein Angreifer,
   der die App direkt erreicht, kann seine IP damit nicht faelschen.
3. Nur wenn der direkte Peer ein vertrauenswuerdiger Proxy ist, wird die echte
   Client-IP als rechtester NICHT-vertrauenswuerdiger Eintrag der
   ``X-Forwarded-For``-Kette gelesen (jeder Proxy haengt hinten an, links
   Angehaengtes ist client-kontrolliert und wird verworfen).

Voraussetzung: uvicorn darf ``request.client.host`` nicht selbst aus
X-Forwarded-For ueberschreiben (entrypoint startet daher ohne ``--proxy-headers``),
damit hier die echte Socket-Peer-IP ankommt.
"""

import ipaddress
from typing import List

from starlette.requests import Request

from .config import settings

_cache: dict = {"raw": None, "nets": []}


def _trusted_networks() -> List:
    """Parst settings.TRUSTED_PROXIES (IPs/CIDRs) gecached; recomputed bei Aenderung (Tests)."""
    raw = tuple(settings.TRUSTED_PROXIES)
    if _cache["raw"] != raw:
        nets = []
        for item in raw:
            try:
                nets.append(ipaddress.ip_network(item, strict=False))
            except ValueError:
                pass  # ungueltiger Eintrag wird ignoriert
        _cache["raw"] = raw
        _cache["nets"] = nets
    return _cache["nets"]


def _is_trusted(ip: str, nets: List) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return any(addr in net for net in nets)


def _strip_port(value: str) -> str:
    """'1.2.3.4:56' -> '1.2.3.4', '[::1]:56' -> '::1', sonst unveraendert."""
    value = value.strip()
    if value.startswith("[") and "]" in value:
        return value[1:value.index("]")]
    if value.count(":") == 1:  # IPv4:port (IPv6 hat mehrere ':')
        return value.rsplit(":", 1)[0]
    return value


def get_client_ip(request: Request) -> str:
    """Echte Client-IP fuer Rate-Limit/Audit. Siehe Modul-Docstring."""
    peer = request.client.host if request.client else None
    nets = _trusted_networks()

    # Kein Proxy konfiguriert, oder direkter Peer ist kein vertrauenswuerdiger Proxy:
    # der Socket-Peer ist massgeblich (X-Forwarded-For wird ignoriert).
    if not nets or peer is None or not _is_trusted(peer, nets):
        return peer or "unknown"

    # Direkter Peer ist ein Proxy -> rechtester nicht-vertrauenswuerdiger XFF-Eintrag.
    xff = request.headers.get("x-forwarded-for", "")
    for part in reversed(xff.split(",")):
        candidate = _strip_port(part)
        if not candidate:
            continue
        try:
            ipaddress.ip_address(candidate)
        except ValueError:
            continue
        if not _is_trusted(candidate, nets):
            return candidate

    # Nur Proxys in der Kette (kein externer Client erkennbar) -> Peer.
    return peer


def client_ip_key(request: Request) -> str:
    """slowapi key_func: Rate-Limit-Bucket = echte Client-IP."""
    return get_client_ip(request)
