"""WhatsApp Cloud API client (outbound) and signature verification.

Sends messages through the Graph API endpoint
``POST /<version>/<phone-number-id>/messages`` and verifies the
``X-Hub-Signature-256`` header on inbound webhook calls.
"""

import hashlib
import hmac

import requests

import frappe

from whatsapp_issues.api import settings

_TIMEOUT = (10, 30)

# WhatsApp interactive replies allow at most 3 buttons and 10 list rows.
MAX_BUTTONS = 3
MAX_LIST_ROWS = 10


def _graph_url():
    version = settings.get("graph_api_version", required=True)
    phone_id = settings.get("phone_number_id", required=True)
    return f"https://graph.facebook.com/{version}/{phone_id}/messages"


def _headers():
    token = settings.get("access_token", required=True)
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


def verify_signature(raw_body, signature_header):
    """Validate the X-Hub-Signature-256 header against the app secret.

    ``raw_body`` must be the exact bytes of the request body. Returns True on
    a valid signature, False otherwise. Uses a constant-time comparison.
    """
    app_secret = settings.get("app_secret")
    if not app_secret:
        # Fail closed: if no secret is configured we cannot trust the payload.
        frappe.log_error("app_secret not configured; rejecting webhook", "WhatsApp")
        return False
    if not signature_header or not signature_header.startswith("sha256="):
        return False

    if isinstance(raw_body, str):
        raw_body = raw_body.encode("utf-8")

    expected = hmac.new(
        app_secret.encode("utf-8"), raw_body, hashlib.sha256
    ).hexdigest()
    received = signature_header.split("=", 1)[1].strip()
    return hmac.compare_digest(expected, received)


def _send(payload):
    try:
        resp = requests.post(
            _graph_url(), headers=_headers(), json=payload, timeout=_TIMEOUT
        )
    except requests.RequestException as exc:
        frappe.log_error(f"WhatsApp send failed\n{exc}", "WhatsApp")
        return None

    if resp.status_code >= 400:
        frappe.log_error(
            f"WhatsApp send -> {resp.status_code}\n{resp.text[:2000]}", "WhatsApp"
        )
    try:
        return resp.json()
    except ValueError:
        return None


def send_text(to, body):
    """Send a plain text message."""
    return _send(
        {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "text",
            "text": {"body": body[:4096]},
        }
    )


def send_buttons(to, body, buttons):
    """Send an interactive reply-button message.

    ``buttons`` is a list of (id, title) tuples (max 3, titles <= 20 chars).
    """
    rows = [
        {"type": "reply", "reply": {"id": str(bid), "title": title[:20]}}
        for bid, title in buttons[:MAX_BUTTONS]
    ]
    return _send(
        {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {"text": body[:1024]},
                "action": {"buttons": rows},
            },
        }
    )


def send_list(to, body, button_text, rows, header=None):
    """Send an interactive list message.

    ``rows`` is a list of (id, title, description) tuples (max 10).
    """
    list_rows = []
    for row in rows[:MAX_LIST_ROWS]:
        rid, title = row[0], row[1]
        desc = row[2] if len(row) > 2 else None
        entry = {"id": str(rid), "title": title[:24]}
        if desc:
            entry["description"] = desc[:72]
        list_rows.append(entry)

    interactive = {
        "type": "list",
        "body": {"text": body[:1024]},
        "action": {
            "button": button_text[:20],
            "sections": [{"title": "Options", "rows": list_rows}],
        },
    }
    if header:
        interactive["header"] = {"type": "text", "text": header[:60]}

    return _send(
        {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "interactive",
            "interactive": interactive,
        }
    )
