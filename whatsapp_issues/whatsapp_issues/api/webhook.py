"""WhatsApp Cloud API webhook endpoints.

Exposed (via Frappe's REST layer) at:

    GET  /api/method/whatsapp_issues.api.webhook.verify
    POST /api/method/whatsapp_issues.api.webhook.receive

Configure both as the callback URL in the Meta App Dashboard. The GET handler
answers the subscription challenge; the POST handler validates the
``X-Hub-Signature-256`` header and dispatches inbound messages to the
conversation state machine.
"""

import frappe
from werkzeug.wrappers import Response

from whatsapp_issues.api import conversation, settings, whatsapp


@frappe.whitelist(allow_guest=True)
def verify():
    """Webhook subscription verification (GET).

    Meta sends hub.mode=subscribe, hub.verify_token, hub.challenge. We echo the
    challenge back as plain text iff the verify token matches. The challenge
    must be returned as the raw response body (not JSON-wrapped), so we return
    a werkzeug Response directly.
    """
    params = frappe.local.form_dict
    mode = params.get("hub.mode")
    token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge") or ""

    expected = settings.get("verify_token", required=True)
    if mode == "subscribe" and token and hmac_equal(token, expected):
        return Response(challenge, status=200, mimetype="text/plain")

    return Response("Verification failed", status=403, mimetype="text/plain")


def hmac_equal(a, b):
    """Constant-time string comparison."""
    import hmac as _hmac

    return _hmac.compare_digest(str(a), str(b))


@frappe.whitelist(allow_guest=True)
def receive():
    """Inbound message webhook (POST)."""
    raw = frappe.request.get_data() if frappe.request else b""
    signature = (
        frappe.get_request_header("X-Hub-Signature-256")
        or frappe.get_request_header("x-hub-signature-256")
        or ""
    )

    if not whatsapp.verify_signature(raw, signature):
        frappe.local.response["http_status_code"] = 401
        frappe.log_error("Rejected webhook: bad signature", "WhatsApp")
        return {"status": "invalid signature"}

    try:
        payload = frappe.parse_json(raw) if raw else {}
    except Exception:
        payload = {}

    # Acknowledge immediately; process best-effort. Meta retries on non-200,
    # so we always return 200 once the signature is valid.
    try:
        _dispatch(payload)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "WhatsApp webhook processing")

    return {"status": "received"}


def _dispatch(payload):
    """Walk the Cloud API webhook payload and route each message."""
    for entry in payload.get("entry", []) or []:
        for change in entry.get("changes", []) or []:
            value = change.get("value", {}) or {}
            messages = value.get("messages") or []
            for msg in messages:
                _handle_one(msg)


def _handle_one(msg):
    phone = msg.get("from")
    if not phone:
        return
    message_id = msg.get("id")
    msg_type = msg.get("type")

    text = ""
    interactive_id = None

    if msg_type == "text":
        text = (msg.get("text") or {}).get("body", "")
    elif msg_type == "interactive":
        interactive = msg.get("interactive") or {}
        itype = interactive.get("type")
        if itype == "button_reply":
            reply = interactive.get("button_reply") or {}
            interactive_id = reply.get("id")
            text = reply.get("title", "")
        elif itype == "list_reply":
            reply = interactive.get("list_reply") or {}
            interactive_id = reply.get("id")
            text = reply.get("title", "")
    elif msg_type == "button":
        # Template quick-reply button.
        text = (msg.get("button") or {}).get("text", "")
    else:
        # Unsupported message types (image, audio, etc.) -> nudge to menu.
        text = ""

    conversation.handle_message(
        phone=phone,
        text=text,
        interactive_id=interactive_id,
        message_id=message_id,
    )
