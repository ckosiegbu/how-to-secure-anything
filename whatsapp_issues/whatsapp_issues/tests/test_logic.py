"""Unit tests for the pure logic of the WhatsApp Issues app.

These tests stub out the ``frappe`` module so they can run standalone
(``python -m pytest`` or ``python -m unittest``) without a Frappe bench. They
cover the security-critical signature verification and the defensive response
parsing helpers.
"""

import hashlib
import hmac
import sys
import types
import unittest


# A single fake ``frappe`` is installed once and shared by every test. Its
# config is mutable so individual tests can change values without reimporting
# app modules (reimporting would leave them bound to a stale frappe reference,
# since ``from package import submodule`` returns the cached package attribute).
_FAKE_CONF = {"whatsapp_issues": {}}


def _ensure_fake_frappe():
    if isinstance(sys.modules.get("frappe"), types.ModuleType) and getattr(
        sys.modules["frappe"], "_is_test_fake", False
    ):
        return sys.modules["frappe"]

    fake = types.ModuleType("frappe")
    fake._is_test_fake = True
    fake.local = True  # truthy so settings._config() calls get_conf()
    fake.get_conf = lambda: _FAKE_CONF
    fake.throw = lambda msg, *a, **k: (_ for _ in ()).throw(ValueError(msg))
    fake.log_error = lambda *a, **k: None
    sys.modules["frappe"] = fake
    return fake


def _set_conf(conf):
    """Replace the contents of the shared fake config in place."""
    _FAKE_CONF.clear()
    _FAKE_CONF.update(conf)


class SignatureTests(unittest.TestCase):
    def setUp(self):
        _ensure_fake_frappe()
        _set_conf({"whatsapp_issues": {"app_secret": "topsecret"}})
        from whatsapp_issues.api import whatsapp

        self.whatsapp = whatsapp

    def _sign(self, body, secret=b"topsecret"):
        return "sha256=" + hmac.new(secret, body, hashlib.sha256).hexdigest()

    def test_valid_signature(self):
        body = b'{"hello":"world"}'
        self.assertTrue(self.whatsapp.verify_signature(body, self._sign(body)))

    def test_tampered_body_fails(self):
        body = b'{"hello":"world"}'
        sig = self._sign(body)
        self.assertFalse(self.whatsapp.verify_signature(b'{"hello":"evil"}', sig))

    def test_wrong_secret_fails(self):
        body = b'{"a":1}'
        self.assertFalse(
            self.whatsapp.verify_signature(body, self._sign(body, b"wrong"))
        )

    def test_missing_header_fails(self):
        self.assertFalse(self.whatsapp.verify_signature(b"x", ""))
        self.assertFalse(self.whatsapp.verify_signature(b"x", None))

    def test_malformed_header_fails(self):
        self.assertFalse(self.whatsapp.verify_signature(b"x", "md5=abc"))

    def test_string_body_accepted(self):
        body = '{"u":"f00"}'
        sig = self._sign(body.encode("utf-8"))
        self.assertTrue(self.whatsapp.verify_signature(body, sig))

    def test_no_secret_fails_closed(self):
        _set_conf({"whatsapp_issues": {}})
        body = b"x"
        sig = "sha256=" + hmac.new(b"", body, hashlib.sha256).hexdigest()
        self.assertFalse(self.whatsapp.verify_signature(body, sig))


class ResponseParsingTests(unittest.TestCase):
    def setUp(self):
        _ensure_fake_frappe()
        _set_conf({"whatsapp_issues": {}})
        # conversation imports doctype modules that need frappe.model; stub them.
        self._stub_doctype_module()
        from whatsapp_issues.api import conversation

        self.c = conversation

    def _stub_doctype_module(self):
        pkg = "whatsapp_issues.whatsapp_issues.doctype.whatsapp_conversation"
        mod_name = pkg + ".whatsapp_conversation"
        m = types.ModuleType(mod_name)
        m.get_conversation = lambda phone: None
        m.save_conversation = lambda *a, **k: None
        sys.modules[mod_name] = m

    def test_list_passthrough(self):
        self.assertEqual(self.c._as_order_list([{"Id": 1}]), [{"Id": 1}])

    def test_none_is_empty(self):
        self.assertEqual(self.c._as_order_list(None), [])

    def test_wrapped_data_key(self):
        out = self.c._as_order_list({"Data": [{"Id": 9}]})
        self.assertEqual(out, [{"Id": 9}])

    def test_single_object_wrapped(self):
        out = self.c._as_order_list({"Subject": "x"})
        self.assertEqual(out, [{"Subject": "x"}])

    def test_order_id_variants(self):
        self.assertEqual(self.c._order_id({"WorkOrderId": 42}), 42)
        self.assertEqual(self.c._order_id({"Code": "WO-7"}), "WO-7")
        self.assertEqual(self.c._order_id({}), "?")

    def test_order_subject_variants(self):
        self.assertEqual(self.c._order_subject({"Subject": "Leak"}), "Leak")
        self.assertEqual(self.c._order_subject({}), "(no subject)")

    def test_extract_work_order_id_nested(self):
        self.assertEqual(self.c._extract_work_order_id({"Data": {"Id": 5}}), 5)
        self.assertEqual(self.c._extract_work_order_id({"Number": "WO-1"}), "WO-1")
        self.assertIsNone(self.c._extract_work_order_id({"foo": "bar"}))


if __name__ == "__main__":
    unittest.main()
