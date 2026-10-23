from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import run_native_bridge_probe as probe


class NativeBridgeProbeTests(unittest.TestCase):
    def test_engine_checkout_must_match_commit_and_be_clean(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary)
            for name in probe.ENGINE_FILES:
                path = source / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(name, encoding="utf-8")
            clean = [
                mock.Mock(stdout=f"{probe.ENGINE_COMMIT}\n"),
                mock.Mock(stdout=""),
            ]
            with mock.patch.object(probe.subprocess, "run", side_effect=clean):
                result = probe.inspect_engine_checkout(source)
            self.assertEqual(result["head"], probe.ENGINE_COMMIT)
            self.assertTrue(result["clean"])
            self.assertEqual(set(result["source_hashes"]), set(probe.ENGINE_FILES))

            dirty = [
                mock.Mock(stdout=f"{probe.ENGINE_COMMIT}\n"),
                mock.Mock(stdout=" M src/network/network_admin.cpp\n"),
            ]
            with mock.patch.object(probe.subprocess, "run", side_effect=dirty):
                with self.assertRaisesRegex(probe.base.ProbeError, "uncommitted changes"):
                    probe.inspect_engine_checkout(source)

    def test_runtime_revision_must_bind_the_committed_engine(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = root / "openttd.cfg"
            config.write_text("", encoding="utf-8")
            output = root / "version.log"
            good = mock.Mock(returncode=0, stdout="OpenTTD 20261023-m2a-g2850af59a5\n", stderr="")
            with mock.patch.object(probe.subprocess, "run", return_value=good):
                self.assertEqual(
                    probe.run_engine_revision(Path("/custom/openttd"), config, output),
                    "20261023-m2a-g2850af59a5",
                )
            bad = mock.Mock(returncode=0, stdout="OpenTTD 15.3\n", stderr="")
            with mock.patch.object(probe.subprocess, "run", return_value=bad):
                with self.assertRaisesRegex(probe.base.ProbeError, "does not name"):
                    probe.run_engine_revision(Path("/custom/openttd"), config, output)

    def test_selects_the_only_human_company_without_name_matching(self):
        companies = [
            {"company_id": 0, "name": "Renamed company", "is_ai": False},
            {"company_id": 1, "name": "AI company", "is_ai": True},
        ]
        self.assertEqual(probe.select_human_company(companies)["company_id"], 0)

    def test_requested_company_is_explicit_and_must_be_human(self):
        companies = [{"id": 4, "name": "Player", "is_ai": False},
                     {"id": 7, "name": "Bot", "is_ai": True}]
        self.assertEqual(probe.select_human_company(companies, 4)["id"], 4)
        with self.assertRaisesRegex(probe.base.ProbeError, "not human"):
            probe.select_human_company(companies, 7)
        with self.assertRaisesRegex(probe.base.ProbeError, "exactly once"):
            probe.select_human_company(companies, 99)

    def test_ambiguous_or_missing_human_company_is_rejected(self):
        with self.assertRaisesRegex(probe.base.ProbeError, "exactly one"):
            probe.select_human_company([
                {"company_id": 0, "is_ai": False}, {"company_id": 1, "is_ai": False}
            ])
        with self.assertRaisesRegex(probe.base.ProbeError, "exactly one"):
            probe.select_human_company([{ "company_id": 0, "is_ai": True }])

    def test_identity_validator_requires_versioned_world_and_companies(self):
        reply = {
            "version": 1, "request_kind": 0, "request_id": 1, "frame": 1,
            "seed": 20261021, "calendar_date": "1950-01-01", "map_width": 128,
            "map_height": 128, "landscape": "temperate",
            "companies": [{"company_id": 0, "is_ai": False}],
        }
        self.assertIs(probe.validate_identity(reply), reply)
        for key in ("version", "request_kind", "request_id", "seed", "calendar_date",
                    "map_width", "map_height", "landscape", "companies"):
            broken = dict(reply)
            broken.pop(key)
            with self.subTest(key=key), self.assertRaises(probe.base.ProbeError):
                probe.validate_identity(broken)

    def test_identity_validator_does_not_assume_one_human_when_id_was_requested(self):
        reply = {
            "version": 1, "request_kind": 0, "request_id": 1, "frame": 1,
            "seed": 1, "calendar_date": "1950-01-01", "map_width": 64,
            "map_height": 64, "landscape": "temperate",
            "companies": [{"company_id": 0, "is_ai": False},
                          {"company_id": 1, "is_ai": False}],
        }
        self.assertEqual(len(probe.validate_identity(reply)["companies"]), 2)

    def test_foreign_running_requires_saved_marker_and_zero_mutations(self):
        def response(tick, **changes):
            payload = {"fixture": "foreign", "marker": "foreign-environment-v1",
                       "loaded": True, "mutation_count": 0, "tick": tick}
            payload.update(changes)
            return {"identity": "foreign", "reply": payload}
        self.assertTrue(probe.foreign_running(response(10), response(11)))
        with self.assertRaises(probe.base.ProbeError):
            probe.foreign_running(response(10), response(11, mutation_count=1))
        with self.assertRaisesRegex(probe.base.ProbeError, "did not advance"):
            probe.foreign_running(response(10), response(10))

    def test_foreign_running_rejects_a_copilot_or_missing_response(self):
        good = {"identity": "foreign", "reply": {"fixture": "foreign",
                "marker": "foreign-environment-v1", "loaded": True, "mutation_count": 0}}
        bad = {"identity": "copilot", "reply": {}}
        with self.assertRaises(probe.base.ProbeError):
            probe.foreign_running(good, bad)

    def test_experiment_records_m2a_scope_and_zero_mutation_budget(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.sav"
            source.write_bytes(b"save")
            with (mock.patch.object(probe, "ROOT", root),
                  mock.patch.object(probe.environment, "ROOT", root),
                  mock.patch.object(probe.environment.lifecycle, "normal_fingerprints", return_value={})):
                run = probe.Experiment(Path("/unused/openttd"), source, 30, 1, 1)
                self.assertEqual(run.manifest["bridge_protocol_version"], 1)
                self.assertEqual(run.manifest["mutation_requests"], 0)
                self.assertEqual(run.manifest["fixture_save_commands"], 1)
                self.assertIn("M2a", run.manifest["scope"])
                with mock.patch("builtins.print"):
                    self.assertEqual(run.finish(), 0)


if __name__ == "__main__":
    unittest.main()
