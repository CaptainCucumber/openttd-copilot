from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import run_environment_probe as probe


class FakeAdmin:
    def __init__(self, response=None, timeout=False):
        self.response = response
        self.timeout = timeout

    def request(self, request, timeout):
        if self.timeout:
            raise TimeoutError("bounded fixture timeout")
        return {**self.response, "rid": request["rid"]}


class EnvironmentProbeTests(unittest.TestCase):
    def test_script_reply_classifies_copilot_foreign_and_timeout(self):
        copilot = probe.classify_script_reply(
            FakeAdmin({"v": 1, "seq": 0, "human_found": False}), 0.1, "copilot")
        foreign = probe.classify_script_reply(
            FakeAdmin({"v": 1, "fixture": "foreign", "loaded": True}), 0.1, "foreign")
        missing = probe.classify_script_reply(FakeAdmin(timeout=True), 0.1, "missing")
        unknown = probe.classify_script_reply(FakeAdmin({"v": 1, "ok": True}), 0.1, "unknown")
        self.assertEqual(copilot["identity"], "copilot")
        self.assertEqual(foreign["identity"], "foreign")
        self.assertEqual(missing["identity"], "none")
        self.assertEqual(missing["result"], "expected_timeout")
        self.assertEqual(unknown["identity"], "unknown")

    def test_file_fingerprint_detects_content_and_mtime(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "world.sav"
            path.write_bytes(b"save")
            first = probe.file_fingerprint(path)
            path.write_bytes(b"changed")
            second = probe.file_fingerprint(path)
            self.assertNotEqual(first, second)

    def test_stage_uses_mode_600_secret_and_both_named_scripts_can_coexist(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_save = root / "source.sav"
            source_save.write_bytes(b"save")
            graphics = root / "graphics.tar"
            graphics.write_bytes(b"graphics")
            source_a, source_b = root / "a", root / "b"
            for source in (source_a, source_b):
                source.mkdir()
                (source / "info.nut").write_text("info")
                (source / "main.nut").write_text("main")
            with (mock.patch.object(probe, "ROOT", root),
                  mock.patch.object(probe.lifecycle, "normal_fingerprints", return_value={}),
                  mock.patch.object(probe.base, "bundle_resources", return_value=root),
                  mock.patch.object(probe.base, "stage_builtin_resources", return_value={}),
                  mock.patch.object(probe.base, "find_opengfx_archive", return_value=graphics),
                  mock.patch.object(probe.base, "stage_opengfx", return_value=graphics),
                  mock.patch.object(probe.base, "find_free_port", side_effect=[3979, 3977])):
                run = probe.Experiment(Path("/unused/openttd"), source_save, 30, 1, 1)
                profile, config, _, _, metadata = run.stage(
                    "coexist", "Copilot Lifecycle Probe", [(source_a, "foreign"), (source_b, "copilot")])
                self.assertIn('"Copilot Lifecycle Probe"', config.read_text())
                self.assertEqual(sorted(metadata["scripts"]), ["copilot", "foreign"])
                self.assertEqual((profile / "secrets.cfg").stat().st_mode & 0o777, 0o600)
                with mock.patch("builtins.print"):
                    self.assertEqual(run.finish(), 0)
                self.assertFalse((profile / "secrets.cfg").exists())


if __name__ == "__main__":
    unittest.main()
