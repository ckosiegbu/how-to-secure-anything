import json

import frappe
from frappe.model.document import Document


class WhatsAppConversation(Document):
    def get_context(self):
        """Return the deserialized context dict."""
        if not self.context_json:
            return {}
        try:
            return json.loads(self.context_json)
        except (ValueError, TypeError):
            return {}

    def set_context(self, ctx):
        self.context_json = json.dumps(ctx or {})


def get_conversation(phone):
    """Fetch (or create) the conversation row for a phone number."""
    name = frappe.db.exists("WhatsApp Conversation", {"phone": phone})
    if name:
        return frappe.get_doc("WhatsApp Conversation", name)
    doc = frappe.new_doc("WhatsApp Conversation")
    doc.phone = phone
    doc.state = "idle"
    doc.context_json = "{}"
    return doc


def save_conversation(doc, state=None, context=None, last_message_id=None):
    """Persist conversation state/context atomically."""
    if state is not None:
        doc.state = state
    if context is not None:
        doc.set_context(context)
    if last_message_id is not None:
        doc.last_message_id = last_message_id
    doc.updated_on = frappe.utils.now_datetime()
    doc.save(ignore_permissions=True)
    frappe.db.commit()
    return doc
