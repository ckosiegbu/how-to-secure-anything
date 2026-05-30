app_name = "whatsapp_issues"
app_title = "Whatsapp Issues"
app_publisher = "Venco"
app_description = (
    "WhatsApp Business interface for creating and rating issues "
    "(backed by Provast CRM work orders)"
)
app_email = "chude@venco.co"
app_license = "MIT"

# Includes in <head>
# ------------------

# Installation
# ------------
# before_install = "whatsapp_issues.install.before_install"
# after_install = "whatsapp_issues.install.after_install"

# Whitelisted methods used as the WhatsApp Cloud API webhook are reachable at:
#   /api/method/whatsapp_issues.api.webhook.verify   (GET  - subscription verify)
#   /api/method/whatsapp_issues.api.webhook.receive  (POST - inbound messages)
#
# These are exposed via @frappe.whitelist(allow_guest=True) decorators in
# whatsapp_issues/api/webhook.py - no additional hook registration is required.
