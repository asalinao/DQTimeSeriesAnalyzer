import ipaddress
import socket
import time
from urllib.parse import urlparse

import httpx
from sqlalchemy.orm import Session

from app.models import Notification


BLOCKED_HOSTS = {"localhost", "127.0.0.1", "::1"}


def validate_webhook_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return False
    if parsed.hostname in BLOCKED_HOSTS:
        return False
    return not resolves_to_private_address(parsed.hostname)


def resolves_to_private_address(hostname: str) -> bool:
    try:
        addresses = [item[4][0] for item in socket.getaddrinfo(hostname, None)]
    except socket.gaierror:
        return True
    return any(is_private_address(address) for address in addresses)


def is_private_address(address: str) -> bool:
    ip = ipaddress.ip_address(address)
    return ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast


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
                notification.status = "retrying" if attempt < max_attempts else "failed"
                notification.last_error = str(exc)
                db.flush()
                if attempt < max_attempts:
                    time.sleep(0.2 * 2 ** (attempt - 1))
