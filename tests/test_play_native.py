import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from mcp_server import ToolError
from play_native import parse_request


class NativeTextTests(unittest.TestCase):
    def setUp(self):
        self.world = {"industries": [
            {"industry_id": 10, "name": "Canley Coal Mine"},
            {"industry_id": 1, "name": "Canley Power Station"}]}

    def test_names_resolve_to_observed_ids(self):
        result = parse_request(
            "build a coal railway from Canley Coal Mine to Canley Power Station; "
            "full load; budget 50000; reserve 10000", self.world, "job")
        self.assertEqual((result["source_id"], result["destination_id"]), (10, 1))
        self.assertEqual(result["construction_cap"], 50000)
        self.assertEqual(result["operating_reserve"], 10000)
        self.assertIs(result["wait_for_full_load"], True)

    def test_explicit_observed_ids(self):
        result = parse_request("build coal railway from 10 to 1; full load; budget 50; reserve 0",
                               self.world, "job")
        self.assertEqual(result["source_id"], 10)

    def test_unknown_and_ambiguous_names_are_not_guessed(self):
        for world in (self.world, {"industries": self.world["industries"] * 2}):
            with self.assertRaises(ToolError):
                parse_request("build coal railway from Unknown to 1; full load; budget 50; reserve 0",
                              world, "job")
        with self.assertRaises(ToolError):
            parse_request("build coal railway from Canley Coal Mine to 1; full load; budget 50; reserve 0",
                          {"industries": self.world["industries"] * 2}, "job")

    def test_unsupported_or_extra_constraints_are_rejected(self):
        for text in ("build road from 10 to 1", "do not build coal railway from 10 to 1; "
                     "full load; budget 50; reserve 0",
                     "build coal railway from 10 to 1; full load; budget 50; reserve 0; borrow more",
                     "build coal railway from 10 to 1; full load; budget -1; reserve 0"):
            with self.subTest(text=text), self.assertRaises(ToolError):
                parse_request(text, self.world, "job")


if __name__ == "__main__":
    unittest.main()
