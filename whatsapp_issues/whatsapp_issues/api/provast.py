"""Thin client for the Provast CRM API (``crm.provastltd.com:9191``).

An "issue" in WhatsApp maps to a Provast **Work Order**:

* create  -> ``PUT  /WorkOrder/UpdateWorkOrder`` with ``Operation: "I"``
* list    -> ``POST /WorkOrder/GetAllWorkOrder``
* sites   -> ``GET  /Site/GetSite?siteCode=<code>``
* lookups -> ``GET  /Values/GetJobTypeAndCraft``

Authentication is HTTP Basic using the configured Provast username/password.
"""

import requests
from requests.auth import HTTPBasicAuth

import frappe

from whatsapp_issues.api import settings

# Network timeout (connect, read) in seconds for all Provast calls.
_TIMEOUT = (10, 30)


def _auth():
    return HTTPBasicAuth(
        settings.get("provast_username", required=True),
        settings.get("provast_password", required=True),
    )


def _verify_tls():
    val = settings.get("provast_verify_tls")
    return True if val is None else bool(val)


def _url(path):
    base = settings.get("provast_base_url", required=True).rstrip("/")
    return f"{base}/{path.lstrip('/')}"


def _request(method, path, **kwargs):
    url = _url(path)
    try:
        resp = requests.request(
            method,
            url,
            auth=_auth(),
            verify=_verify_tls(),
            timeout=_TIMEOUT,
            **kwargs,
        )
    except requests.RequestException as exc:
        frappe.log_error(f"Provast request failed: {method} {url}\n{exc}", "Provast API")
        frappe.throw("Could not reach the work order system. Please try again later.")

    if resp.status_code >= 400:
        frappe.log_error(
            f"Provast {method} {url} -> {resp.status_code}\n{resp.text[:2000]}",
            "Provast API",
        )
        frappe.throw(f"Work order system returned an error ({resp.status_code}).")

    if not resp.content:
        return None
    try:
        return resp.json()
    except ValueError:
        return resp.text


# --------------------------------------------------------------------------- #
# Reference data
# --------------------------------------------------------------------------- #
def get_site(site_code):
    """GET /Site/GetSite?siteCode=<code> -> site detail incl. location tree."""
    return _request("GET", "Site/GetSite", params={"siteCode": site_code})


def get_job_type_and_craft():
    """GET /Values/GetJobTypeAndCraft -> available job types and crafts."""
    return _request("GET", "Values/GetJobTypeAndCraft")


# --------------------------------------------------------------------------- #
# Work orders (issues)
# --------------------------------------------------------------------------- #
def create_work_order(
    subject,
    site_code,
    site_name,
    created_by,
    job_type_id=17,
    craft="Carpentry",
    service_classification="Routine",
    service_level_agreement="5 Days",
    site_tree=None,
):
    """Create a work order (issue) via UpdateWorkOrder with Operation 'I'.

    ``site_tree`` may carry the nested Site/SiteLocation structure expected by
    Provast. When omitted a minimal Site object (just Code/Name) is sent.
    """
    site_obj = {"Code": site_code, "Name": site_name}
    if site_tree:
        site_obj.update(site_tree)

    payload = {
        "WorkOrder": {
            "CreatedBy": created_by,
            "Subject": subject,
            "Site": site_obj,
            "SiteCode": site_code,
            "SiteName": site_name,
            "FilePath": "",
            "JobTypeid": job_type_id,
            "ServiceClassification": service_classification,
            "ServiceClassification1": "Select Service Classification",
            "ServiceLevelAgreement": service_level_agreement,
            "ServiceLevelAgreement1": "Select Level Agreement",
            "Craft": craft,
            "PPMJobType": "No",
            "Frequency": None,
            "RepeatCycle": "No",
        },
        "Operation": "I",
    }
    return _request("PUT", "WorkOrder/UpdateWorkOrder", json=payload)


def get_all_work_orders(site_code, logged_in_user_id):
    """POST /WorkOrder/GetAllWorkOrder -> list of work orders for a site."""
    payload = {"SiteCode": site_code, "LoggedInUserId": logged_in_user_id}
    return _request("POST", "WorkOrder/GetAllWorkOrder", json=payload)
