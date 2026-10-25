import struct
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import run_native_dispatcher_probe as probe


class NativeDispatcherProbeTests(unittest.TestCase):
    def test_finance_comparison_ignores_automatic_company_naming(self):
        company = {"id": 0, "money": 100000, "loan": 100000, "name": "Unnamed"}
        before = {"companies": [company]}
        after = {"companies": [{**company, "name": "Copilot Player Transport"}]}
        self.assertEqual(probe.finances(before), probe.finances(after))
        after["companies"][0]["money"] -= 1
        self.assertNotEqual(probe.finances(before), probe.finances(after))

    def test_wrong_world_matrix_encodes_every_nonidentity_kind(self):
        requests = probe.wrong_world_requests()
        self.assertEqual([payload[2] for _, payload, _ in requests], list(range(1, 19)))
        for name, payload, status in requests:
            with self.subTest(name=name):
                if payload[2] == 18:
                    self.assertIn(b'"world_id":"dispatcher-probe-wrong-world"', payload)
                else:
                    self.assertIn(b"dispatcher-probe-wrong-world\0", payload)
                self.assertEqual(status, 5)

    def test_guard_matrix_has_unique_ids_and_covers_versions_kinds_and_json(self):
        requests = probe.guard_requests()
        ids = [struct.unpack_from("<HBI", payload)[2] for _, payload, _ in requests]
        self.assertEqual(len(ids), len(set(ids)))
        names = {name for name, _, _ in requests}
        self.assertTrue({"unsupported_version_0", "unsupported_version_4",
                         "unsupported_version_65535", "missing_company",
                         "unsupported_kind_v1_1", "unsupported_kind_v2_3",
                         "unsupported_kind_v3_255", "malformed_bus_json"} <= names)
        for name, _, status in requests:
            if name in ("unsupported_kind_v1_1", "unsupported_kind_v2_3"):
                self.assertEqual(status, 1)

    def test_malformed_matrix_covers_header_fields_trailing_and_unterminated_string(self):
        cases = dict(probe.malformed_requests())
        self.assertEqual(len(cases["short_header"]), 2)
        self.assertEqual(len(cases["missing_identity_company"]), 7)
        self.assertEqual(len(cases["identity_trailing_bytes"]), 9)
        self.assertFalse(cases["unterminated_bus_string"].endswith(b"\0"))

    def test_exact_error_contract_checks_version_kind_id_status_and_trailing_bytes(self):
        request = struct.pack("<HBI", 4, 18, 99)
        expected = struct.pack("<HBIB", 3, 18, 99, 1)
        probe.check_response(request, expected, 1)
        for changed in (expected + b"\0", expected[:-1],
                        struct.pack("<HBIB", 4, 18, 99, 1),
                        struct.pack("<HBIB", 3, 17, 99, 1),
                        struct.pack("<HBIB", 3, 18, 98, 1),
                        struct.pack("<HBIB", 3, 18, 99, 2)):
            with self.subTest(changed=changed), self.assertRaises(probe.AdminProtocolError):
                probe.check_response(request, changed, 1)
