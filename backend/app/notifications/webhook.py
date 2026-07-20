import ipaddress
import socket
import time
from urllib.parse import urlparse

import httpx
from sqlalchemy.orm import Session

from app.models import Notification


def _is_private_host(hostname: str) -> bool:
    try:
        infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror:
        return True
    for info in infos:
        address = info[4][0]
        ip = ipaddress.ip_address(address)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast:
            return True
    return False


def validate_webhook_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return False
    if parsed.hostname in {"localhost", "127.0.0.1", "::1"}:
        return False
    return not _is_private_host(parsed.hostname)


def create_notification(db: Session, event_type: str, payload: dict, anomaly_id: str | None = None) -> Notification:
    notification = Notification(event_type=event_type, payload=payload, anomaly_id=anomaly_id, status="pending")
    db.add(notification)
    db.flush()
    return notification


def send_webhook(db: Session, notification: Notification, url: str, max_attempts: int = 3) -> None:
    if not validate_webhook_url(url):
        notification.status = "failed"
        notification.last_error = "Webhook URL не прошел SSRF-валидацию"
        return

    with httpx.Client(timeout=5.0) as client:
        for attempt in range(1, max_attempts + 1):
            notification.attempts = attempt
            try:
                response = client.post(url, json=notification.payload)
                response.raise_for_status()
                notification.status = "sent"
                notification.last_error = None
                db.flush()
                return
            except Exception as exc:
                notification.last_error = str(exc)
                notification.status = "retrying" if attempt < max_attempts else "failed"
                db.flush()
                if attempt < max_attempts:
                    time.sleep(0.2 * (2 ** (attempt - 1)))
