from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import native_play_session as module


class NativeMapProfileTests(unittest.TestCase):
    def config(self, style):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            archive = root / "opengfx.tar"
            archive.write_bytes(b"test resources")
            session = module.NativeSession.__new__(module.NativeSession)
            session.map_style = style
            session.password, session.client_secret = "test-password", "test-client"
            session.secret_files = []
            with patch.object(module.base, "stage_builtin_resources", return_value={}), \
                 patch.object(module.base, "stage_opengfx", return_value=archive):
                config, metadata = session.stage(root / "server", 1234, 1235)
            self.assertIsNone(metadata["game_script"])
            self.assertEqual((root / "server/secrets.cfg").stat().st_mode & 0o777, 0o600)
            return config.read_text()

    def test_normal_map_has_towns_trees_hills_water_and_larger_world(self):
        text = self.config("normal")
        for setting in ("map_x = 8", "map_y = 8", "tree_placer = 2",
                        "terrain_type = 1", "quantity_sea_lakes = 1",
                        "amount_of_rivers = 1", "number_towns = 2"):
            self.assertIn(setting, text)
        self.assertNotIn("[game_scripts]", text)

    def test_explicit_fixture_preserves_old_geometry_and_seed_scope(self):
        text = self.config("railway-fixture")
        for setting in ("map_x = 7", "map_y = 7", "tree_placer = 0",
                        "terrain_type = 0", "quantity_sea_lakes = 0"):
            self.assertIn(setting, text)
