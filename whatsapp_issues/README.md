# WhatsApp Issues

A [Frappe](https://frappeframework.com/) v13 app that puts a **WhatsApp
Business** front end on issue (work order) management. Users chat with your
WhatsApp number to:

- **Create an issue** – logged as a work order in the Provast CRM
  (`crm.provastltd.com`).
- **Rate an issue** – a 1–5 star rating plus an optional comment, stored
  locally in Frappe.
- **List recent issues** – pulled live from Provast.

The bot is a small conversational state machine that uses WhatsApp
**interactive buttons and lists** so users mostly tap instead of type.

```
WhatsApp user
      │  (Cloud API webhook)
      ▼
Frappe  ──  whatsapp_issues.api.webhook   (verify + receive, HMAC-checked)
      │
      ├─ conversation.py   state machine  ──► whatsapp.py  (Graph API, outbound)
      │
      └─ provast.py  ──►  Provast CRM REST API  (create / list work orders)
                          Work Order Rating DocType  (ratings, local)
```

## How an "issue" maps to Provast

| Bot action     | Provast call                                              |
| -------------- | --------------------------------------------------------- |
| Create issue   | `PUT /api/v1/WorkOrder/UpdateWorkOrder` with `Operation:"I"` |
| List issues    | `POST /api/v1/WorkOrder/GetAllWorkOrder`                  |
| Site lookup    | `GET /api/v1/Site/GetSite?siteCode=<code>`                |
| Job types/craft| `GET /api/v1/Values/GetJobTypeAndCraft`                   |

Ratings have no Provast endpoint, so they are persisted in the
**`Work Order Rating`** DocType (referencing the work order id).

## Install

```bash
# from your bench directory
bench get-app whatsapp_issues /path/to/whatsapp_issues
bench --site your-site.local install-app whatsapp_issues
bench --site your-site.local migrate
```

## Configuration

All secrets live in the site's `site_config.json` (never in code). Add a
`whatsapp_issues` block:

```json
{
  "whatsapp_issues": {
    "verify_token": "a-random-string-you-also-paste-into-meta",
    "app_secret": "your-meta-app-secret",
    "access_token": "whatsapp-cloud-api-permanent-token",
    "phone_number_id": "1234567890",
    "graph_api_version": "v19.0",

    "provast_base_url": "https://crm.provastltd.com:9191/api/v1",
    "provast_username": "victor@venco.co",
    "provast_password": "********",
    "provast_verify_tls": true,

    "default_site_code": "CU0044",
    "default_logged_in_user_id": 17521
  }
}
```

Every key may alternatively be supplied via an environment variable
(`WHATSAPP_VERIFY_TOKEN`, `WHATSAPP_APP_SECRET`, `WHATSAPP_ACCESS_TOKEN`,
`WHATSAPP_PHONE_NUMBER_ID`, `PROVAST_BASE_URL`, `PROVAST_USERNAME`,
`PROVAST_PASSWORD`, `PROVAST_DEFAULT_SITE_CODE`, `PROVAST_DEFAULT_USER_ID`).
See `whatsapp_issues/api/settings.py` for the full mapping.

> **Note:** `default_site_code` / `default_logged_in_user_id` are the site and
> Provast user the bot files work orders under. A natural next step is to map
> each WhatsApp sender to their own site/user; that lookup is intentionally
> isolated in `settings.py` + `conversation.py` so it is easy to extend.

## Webhook setup (Meta App Dashboard)

In **WhatsApp → Configuration → Webhook**, set the callback URL and verify
token. Frappe exposes the endpoints at:

| Purpose            | Method | URL                                                                 |
| ------------------ | ------ | ------------------------------------------------------------------- |
| Subscription verify| `GET`  | `https://your-site/api/method/whatsapp_issues.api.webhook.verify`   |
| Inbound messages   | `POST` | `https://your-site/api/method/whatsapp_issues.api.webhook.receive`  |

Use the **same `verify_token`** you configured above. Subscribe to the
**`messages`** field.

### Security

- The `POST` handler rejects any request whose `X-Hub-Signature-256` HMAC does
  not match the `app_secret` (`whatsapp.verify_signature`). If no `app_secret`
  is configured the handler **fails closed** (rejects everything).
- The `GET` verify handler compares the verify token in constant time.
- Inbound message ids are de-duplicated (`last_message_id`) so Meta's retries
  do not create duplicate work orders.
- Provast credentials and the Cloud API token are read from `site_config.json`
  / env only; nothing sensitive is committed.

## Conversation flow

```
user: hi
bot : [Create issue] [Rate an issue] [List issues]

— Create —
bot : Describe the issue…
user: Broken handle on visitor's chair
bot : Create this issue? "Broken handle…"  [Yes, create] [Cancel]
user: (taps Yes)
bot : Done! Your issue has been logged as work order 12345.

— Rate —
bot : (list of recent work orders)  Pick issue ▾
user: (taps #12345)
bot : How would you rate issue #12345?  [⭐1] [⭐3] [⭐5]  (or type 1–5)
user: 5
bot : Add a comment, or reply skip.
user: Fixed quickly, thanks
bot : Your 5-star rating for issue #12345 has been recorded.
```

Type `menu` to return to the main menu or `cancel` to abort at any point.

## Tests

Pure logic (HMAC signature verification, response parsing) is covered by
standalone unit tests that stub `frappe`, so they run without a bench:

```bash
cd whatsapp_issues
python3 -m unittest whatsapp_issues.tests.test_logic -v
```

For DocType / end-to-end tests inside a bench:

```bash
bench --site your-site.local run-tests --app whatsapp_issues
```

## Layout

```
whatsapp_issues/
├── setup.py, requirements.txt, hooks.py, modules.txt
└── whatsapp_issues/
    ├── api/
    │   ├── settings.py       config access (site_config.json / env)
    │   ├── provast.py        Provast CRM client (work orders)
    │   ├── whatsapp.py       Cloud API client + signature verification
    │   ├── conversation.py   conversation state machine
    │   └── webhook.py        verify (GET) + receive (POST) endpoints
    ├── whatsapp_issues/doctype/
    │   ├── work_order_rating/      stores 1–5 ratings locally
    │   └── whatsapp_conversation/  per-sender state + idempotency
    └── tests/test_logic.py
```
