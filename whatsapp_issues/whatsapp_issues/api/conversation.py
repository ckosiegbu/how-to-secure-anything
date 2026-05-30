"""Conversation state machine for the WhatsApp issue bot.

States
------
idle                 -> waiting for a command (main menu)
create_subject       -> waiting for the issue title/subject
create_confirm       -> waiting for confirm/cancel of the new issue
rate_pick_order      -> waiting for the user to pick a work order to rate
rate_score           -> waiting for a 1-5 rating
rate_comment         -> waiting for an optional comment

The user can type ``menu`` / ``cancel`` at any point to reset to ``idle``.
"""

import frappe

from whatsapp_issues.api import provast, settings, whatsapp
from whatsapp_issues.whatsapp_issues.doctype.whatsapp_conversation.whatsapp_conversation import (
    get_conversation,
    save_conversation,
)

# Interactive button / row ids
ID_CREATE = "menu_create"
ID_RATE = "menu_rate"
ID_LIST = "menu_list"
ID_CONFIRM_YES = "confirm_yes"
ID_CONFIRM_NO = "confirm_no"
RATE_PREFIX = "rate_order:"   # rate_order:<work_order_id>
SCORE_PREFIX = "score:"        # score:<1-5>


def handle_message(phone, text, interactive_id=None, message_id=None):
    """Entry point: process one inbound message and reply.

    ``text`` is the message body (may be empty for pure interactive replies).
    ``interactive_id`` is the id of a tapped button/list row, if any.
    """
    convo = get_conversation(phone)

    # Idempotency: ignore a message id we've already handled.
    if message_id and convo.last_message_id == message_id:
        return
    convo.last_message_id = message_id

    selection = (interactive_id or "").strip()
    body = (text or "").strip()
    lowered = body.lower()

    # Global escape hatches.
    if lowered in ("menu", "hi", "hello", "start", "/start") or selection == "":
        if lowered in ("menu", "hi", "hello", "start", "/start"):
            return _show_menu(convo)
    if lowered in ("cancel", "stop", "quit"):
        return _show_menu(convo, prefix="Cancelled. ")

    state = convo.state or "idle"
    handler = _STATE_HANDLERS.get(state, _handle_idle)
    return handler(convo, body, selection)


# --------------------------------------------------------------------------- #
# Menu
# --------------------------------------------------------------------------- #
def _show_menu(convo, prefix=""):
    save_conversation(convo, state="idle", context={})
    whatsapp.send_buttons(
        convo.phone,
        f"{prefix}What would you like to do?",
        [
            (ID_CREATE, "Create issue"),
            (ID_RATE, "Rate an issue"),
            (ID_LIST, "List issues"),
        ],
    )


def _handle_idle(convo, body, selection):
    if selection == ID_CREATE or body.lower() in ("create", "new", "1"):
        return _start_create(convo)
    if selection == ID_RATE or body.lower() in ("rate", "2"):
        return _start_rate(convo)
    if selection == ID_LIST or body.lower() in ("list", "3"):
        return _list_issues(convo)
    return _show_menu(convo)


# --------------------------------------------------------------------------- #
# Create issue flow
# --------------------------------------------------------------------------- #
def _start_create(convo):
    save_conversation(convo, state="create_subject", context={})
    whatsapp.send_text(
        convo.phone,
        "Let's create a new issue.\n\nPlease describe the issue in a few words "
        "(this becomes the work order subject).",
    )


def _handle_create_subject(convo, body, selection):
    if not body:
        whatsapp.send_text(convo.phone, "Please type a short description of the issue.")
        return
    ctx = convo.get_context()
    ctx["subject"] = body[:140]
    save_conversation(convo, state="create_confirm", context=ctx)
    whatsapp.send_buttons(
        convo.phone,
        f'Create this issue?\n\n"{ctx["subject"]}"',
        [(ID_CONFIRM_YES, "Yes, create"), (ID_CONFIRM_NO, "Cancel")],
    )


def _handle_create_confirm(convo, body, selection):
    if selection == ID_CONFIRM_NO or body.lower() in ("no", "cancel"):
        return _show_menu(convo, prefix="No problem. ")
    if not (selection == ID_CONFIRM_YES or body.lower() in ("yes", "y", "create")):
        whatsapp.send_text(convo.phone, "Please tap Yes to create or Cancel.")
        return

    ctx = convo.get_context()
    site_code = settings.get("default_site_code", required=True)
    site_name = ctx.get("site_name") or site_code
    created_by = int(settings.get("default_logged_in_user_id", required=True))

    result = provast.create_work_order(
        subject=ctx["subject"],
        site_code=site_code,
        site_name=site_name,
        created_by=created_by,
    )

    wo_id = _extract_work_order_id(result)
    save_conversation(convo, state="idle", context={})
    if wo_id:
        whatsapp.send_text(
            convo.phone,
            f"Done! Your issue has been logged as work order {wo_id}.\n\n"
            "Type *menu* to do something else.",
        )
    else:
        whatsapp.send_text(
            convo.phone,
            "Your issue has been submitted.\n\nType *menu* to do something else.",
        )


# --------------------------------------------------------------------------- #
# Rate issue flow
# --------------------------------------------------------------------------- #
def _start_rate(convo):
    orders = _fetch_orders()
    if not orders:
        save_conversation(convo, state="idle", context={})
        whatsapp.send_text(
            convo.phone, "No issues were found to rate. Type *menu* to go back."
        )
        return

    rows = []
    for o in orders[:whatsapp.MAX_LIST_ROWS]:
        wo_id = str(_order_id(o))
        subject = _order_subject(o)
        rows.append((f"{RATE_PREFIX}{wo_id}", f"#{wo_id}", subject))

    save_conversation(convo, state="rate_pick_order", context={})
    whatsapp.send_list(
        convo.phone,
        "Which issue would you like to rate?",
        "Pick issue",
        rows,
        header="Rate an issue",
    )


def _handle_rate_pick(convo, body, selection):
    wo_id = None
    if selection.startswith(RATE_PREFIX):
        wo_id = selection[len(RATE_PREFIX):]
    elif body.strip().lstrip("#").isdigit():
        wo_id = body.strip().lstrip("#")

    if not wo_id:
        whatsapp.send_text(convo.phone, "Please pick an issue from the list.")
        return

    ctx = convo.get_context()
    ctx["work_order_id"] = wo_id
    save_conversation(convo, state="rate_score", context=ctx)
    whatsapp.send_buttons(
        convo.phone,
        f"How would you rate issue #{wo_id}?",
        [(f"{SCORE_PREFIX}1", "⭐ 1"), (f"{SCORE_PREFIX}3", "⭐ 3"), (f"{SCORE_PREFIX}5", "⭐ 5")],
    )
    # Buttons cap at 3; tell users they can also type 1-5.
    whatsapp.send_text(convo.phone, "Or reply with any number from 1 to 5.")


def _handle_rate_score(convo, body, selection):
    score = None
    if selection.startswith(SCORE_PREFIX):
        score = selection[len(SCORE_PREFIX):]
    elif body.strip().isdigit():
        score = body.strip()

    if not (score and score.isdigit() and 1 <= int(score) <= 5):
        whatsapp.send_text(convo.phone, "Please send a rating from 1 to 5.")
        return

    ctx = convo.get_context()
    ctx["rating"] = int(score)
    save_conversation(convo, state="rate_comment", context=ctx)
    whatsapp.send_text(
        convo.phone,
        "Thanks! Add a comment about your rating, or reply *skip*.",
    )


def _handle_rate_comment(convo, body, selection):
    ctx = convo.get_context()
    comment = "" if body.lower() in ("skip", "no", "none") else body

    _save_rating(
        work_order_id=ctx.get("work_order_id"),
        rating=ctx.get("rating"),
        comment=comment,
        phone=convo.phone,
    )
    save_conversation(convo, state="idle", context={})
    whatsapp.send_text(
        convo.phone,
        f"Your {ctx.get('rating')}-star rating for issue "
        f"#{ctx.get('work_order_id')} has been recorded. Thank you!\n\n"
        "Type *menu* to do something else.",
    )


# --------------------------------------------------------------------------- #
# List issues
# --------------------------------------------------------------------------- #
def _list_issues(convo):
    orders = _fetch_orders()
    save_conversation(convo, state="idle", context={})
    if not orders:
        whatsapp.send_text(convo.phone, "No issues found. Type *menu* to go back.")
        return
    lines = ["Your most recent issues:\n"]
    for o in orders[:10]:
        lines.append(f"#{_order_id(o)} — {_order_subject(o)}")
    lines.append("\nType *menu* to do something else.")
    whatsapp.send_text(convo.phone, "\n".join(lines))


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _fetch_orders():
    site_code = settings.get("default_site_code", required=True)
    user_id = int(settings.get("default_logged_in_user_id", required=True))
    result = provast.get_all_work_orders(site_code, user_id)
    return _as_order_list(result)


def _as_order_list(result):
    """Normalize the GetAllWorkOrder response into a list of dicts."""
    if result is None:
        return []
    if isinstance(result, list):
        return result
    if isinstance(result, dict):
        for key in ("Data", "data", "WorkOrders", "Result", "result"):
            val = result.get(key)
            if isinstance(val, list):
                return val
        # Single object response.
        return [result]
    return []


def _order_id(order):
    if not isinstance(order, dict):
        return order
    for key in ("Id", "ID", "WorkOrderId", "WorkOrderID", "Code", "Number", "id"):
        if order.get(key) not in (None, ""):
            return order[key]
    return "?"


def _order_subject(order):
    if not isinstance(order, dict):
        return str(order)
    for key in ("Subject", "subject", "Title", "Description", "Name"):
        if order.get(key):
            return str(order[key])[:60]
    return "(no subject)"


def _extract_work_order_id(result):
    if isinstance(result, dict):
        for key in ("Id", "ID", "WorkOrderId", "WorkOrderID", "Number", "Code", "id"):
            if result.get(key) not in (None, ""):
                return result[key]
        for key in ("Data", "data", "Result", "result", "WorkOrder"):
            nested = result.get(key)
            if isinstance(nested, dict):
                inner = _extract_work_order_id(nested)
                if inner:
                    return inner
    return None


def _save_rating(work_order_id, rating, comment, phone):
    doc = frappe.new_doc("Work Order Rating")
    doc.work_order_id = str(work_order_id)
    doc.rating = int(rating)
    doc.comment = comment or None
    doc.site_code = settings.get("default_site_code")
    doc.rated_by_phone = phone
    doc.rated_on = frappe.utils.now_datetime()
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    return doc


_STATE_HANDLERS = {
    "idle": _handle_idle,
    "create_subject": _handle_create_subject,
    "create_confirm": _handle_create_confirm,
    "rate_pick_order": _handle_rate_pick,
    "rate_score": _handle_rate_score,
    "rate_comment": _handle_rate_comment,
}
