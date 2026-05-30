"""Configuration access for the WhatsApp Issues app.

All secrets and environment-specific values are read from the site's
``site_config.json`` (or, as a fallback, environment variables). Nothing
sensitive is hardcoded or committed to source control.

Add the following keys to ``sites/<your-site>/site_config.json``::

    {
        "whatsapp_issues": {
            "verify_token": "<random string you also paste into Meta>",
            "app_secret": "<Meta app secret, used to verify X-Hub-Signature-256>",
            "access_token": "<WhatsApp Cloud API permanent access token>",
            "phone_number_id": "<WhatsApp Cloud API phone number id>",
            "graph_api_version": "v19.0",

            "provast_base_url": "https://crm.provastltd.com:9191/api/v1",
            "provast_username": "victor@venco.co",
            "provast_password": "<password>",
            "provast_verify_tls": true,

            "default_site_code": "CU0044",
            "default_logged_in_user_id": 17521
        }
    }
"""

import os

import frappe

_CONF_KEY = "whatsapp_issues"

# Maps config keys to the environment variable used as a fallback.
_ENV_FALLBACKS = {
    "verify_token": "WHATSAPP_VERIFY_TOKEN",
    "app_secret": "WHATSAPP_APP_SECRET",
    "access_token": "WHATSAPP_ACCESS_TOKEN",
    "phone_number_id": "WHATSAPP_PHONE_NUMBER_ID",
    "graph_api_version": "WHATSAPP_GRAPH_API_VERSION",
    "provast_base_url": "PROVAST_BASE_URL",
    "provast_username": "PROVAST_USERNAME",
    "provast_password": "PROVAST_PASSWORD",
    "default_site_code": "PROVAST_DEFAULT_SITE_CODE",
    "default_logged_in_user_id": "PROVAST_DEFAULT_USER_ID",
}

_DEFAULTS = {
    "graph_api_version": "v19.0",
    "provast_base_url": "https://crm.provastltd.com:9191/api/v1",
    "provast_verify_tls": True,
}


def _config():
    """Return the ``whatsapp_issues`` block from site_config.json (or {})."""
    conf = frappe.get_conf() if frappe.local else {}
    block = conf.get(_CONF_KEY) or {}
    if not isinstance(block, dict):
        frappe.throw("site_config.json key 'whatsapp_issues' must be an object")
    return block


def get(key, required=False):
    """Fetch a config value: site_config block -> env var -> default."""
    block = _config()
    if key in block and block[key] not in (None, ""):
        return block[key]

    env_name = _ENV_FALLBACKS.get(key)
    if env_name and os.environ.get(env_name):
        return os.environ[env_name]

    if key in _DEFAULTS:
        return _DEFAULTS[key]

    if required:
        frappe.throw(
            f"Missing required config '{key}'. Set whatsapp_issues.{key} in "
            f"site_config.json or the {_ENV_FALLBACKS.get(key, key.upper())} "
            "environment variable."
        )
    return None
