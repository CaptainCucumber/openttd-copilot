from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import run_lifecycle_probe as probe


class LifecycleHarnessTests(unittest.TestCase):
    def test_reload_reuses_disposable_client_identity_and_cleanup_removes_secrets(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / "graphics.tar"
            archive.write_bytes(b"fixture graphics")
            with (mock.patch.object(probe, "ROOT", root),
                  mock.patch.object(probe, "normal_fingerprints", return_value={}),
                  mock.patch.object(probe.base, "bundle_resources", return_value=root),
                  mock.patch.object(probe.base, "stage_builtin_resources", return_value={}),
                  mock.patch.object(probe.base, "find_opengfx_archive", return_value=archive),
                  mock.patch.object(probe.base, "stage_opengfx", return_value=archive),
                  mock.patch.object(probe.base, "stage_game_script")):
                run = probe.Experiment(Path("/unused/openttd"), 30, 20261021)
                for label in ("initial-client", "reload-client"):
                    config, _ = run.stage(run.profile / label, 3979)
                    secret = config.parent / "secrets.cfg"
                    self.assertEqual(secret.stat().st_mode & 0o777, 0o600)
                    self.assertEqual(secret.read_text(), f"[network]\nclient_secret_key = {run.client_secret}\n")
                    self.assertNotIn(run.client_secret, config.read_text())
                run.stage(run.profile / "server", 3979, 3977)
                self.assertNotIn(run.client_secret, (run.profile / "server/secrets.cfg").read_text())
                with mock.patch("builtins.print"):
                    self.assertEqual(run.finish(), 0)
                self.assertTrue(all(not path.exists() for path in run.secret_files))
                manifest = (run.artifacts / "manifest.json").read_text()
                self.assertNotIn(run.password, manifest)
                self.assertNotIn(run.client_secret, manifest)


if __name__ == "__main__":
    unittest.main()
