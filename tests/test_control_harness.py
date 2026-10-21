from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


MODULE_PATH = Path(__file__).resolve().parents[1] / "tools" / "run_control_probe.py"
SPEC = importlib.util.spec_from_file_location("run_control_probe", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
probe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe)


class ControlHarnessTests(unittest.TestCase):
    def test_event_parser_accepts_only_prefixed_object_records(self) -> None:
        self.assertIsNone(probe.parse_event_line("info: normal OpenTTD output"))
        event = probe.parse_event_line('COPILOT_EVENT {"protocol": 1, "kind": "probe_complete", "ok": true}')
        self.assertEqual(event, {"protocol": 1, "kind": "probe_complete", "ok": True})
        wrapped = probe.parse_event_line(
            '[2026-10-21 12:00:00] dbg: [script:4] [0] [I] COPILOT_EVENT {"protocol": 1, "kind": "probe_started"}'
        )
        self.assertEqual(wrapped["kind"], "probe_started")

    def test_event_parser_rejects_malformed_or_missing_kind(self) -> None:
        with self.assertRaises(probe.ProbeError):
            probe.parse_event_line("COPILOT_EVENT not-json")
        with self.assertRaises(probe.ProbeError):
            probe.parse_event_line('COPILOT_EVENT {"protocol": 1}')
        with self.assertRaises(probe.ProbeError):
            probe.parse_event_line('COPILOT_EVENT {"protocol": 2, "kind": "x"}')
        for protocol in ('true', '1.0', '"1"'):
            with self.assertRaises(probe.ProbeError):
                probe.parse_event_line('COPILOT_EVENT {"protocol": ' + protocol + ', "kind": "x"}')

    def test_success_requires_protocol_and_every_check(self) -> None:
        checks = {name: True for name in probe.REQUIRED_CHECKS}
        complete = {"protocol": 1, "kind": "probe_complete", "checks": checks}
        self.assertIs(probe.validate_success_events([complete]), complete)
        with self.assertRaises(probe.ProbeError):
            probe.validate_success_events([{**complete, "checks": {**checks, "station_readback": False}}])
        with self.assertRaises(probe.ProbeError):
            probe.validate_success_events([complete, {"protocol": 1, "kind": "probe_failed", "detail": "late failure"}])

    def test_config_pins_fixture_and_disables_admin_auth(self) -> None:
        text = probe.config_text(45678)
        self.assertIn("ini_version = 7", text)
        self.assertIn("language = english.lng", text)
        self.assertIn("server_port = 45678", text)
        self.assertIn("server_admin_port = 0", text)
        self.assertIn("server_game_type = local", text)
        self.assertIn("landscape = temperate", text)
        self.assertIn("map_x = 7", text)
        self.assertIn("map_y = 7", text)
        self.assertIn("starting_year = 1950", text)
        self.assertIn("amount_of_rivers = 0", text)
        self.assertIn('[game_scripts]\n"Copilot Control Probe" =', text)
        self.assertNotIn("admin_password", text)
        self.assertNotIn("server_password", text)
        self.assertNotIn("server_advertise", text)

    def test_argv_is_isolated_and_pins_seed_and_loopback(self) -> None:
        binary = Path("/Applications/OpenTTD.app/Contents/MacOS/openttd")
        config = Path("/tmp/control-probe/openttd.cfg").resolve()
        server = probe.build_server_argv(binary, config, 45678, 20261021)
        client = probe.build_client_argv(binary, config, 45678)
        for argv in (server, client):
            self.assertIn("-X", argv)
            self.assertIn("-x", argv)
            self.assertEqual(argv[argv.index("-c") + 1], str(config))
        self.assertEqual(server[server.index("-G") + 1], "20261021")
        self.assertIn("127.0.0.1:45678", server)
        self.assertIn("127.0.0.1:45678", client)
        self.assertIn("null:ticks=100000000", client)

    def test_server_and_client_configs_are_separate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            server, client = Path(temporary) / "server", Path(temporary) / "client"
            server.mkdir()
            client.mkdir()
            server_config, server_private = probe.write_config(server, 45678, True, server=True)
            client_config, client_private = probe.write_config(client, 45678, False, server=False)
            self.assertIn("Copilot Control Probe", server_config.read_text(encoding="utf-8"))
            self.assertNotIn("game_scripts", client_config.read_text(encoding="utf-8"))
            self.assertNotIn("client_name", server_private.read_text(encoding="utf-8"))
            self.assertIn("client_name = Copilot Probe Human", client_private.read_text(encoding="utf-8"))
            self.assertNotEqual(server_config, client_config)

    def test_bundled_resources_are_copied_without_symlinks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            resources = root / "Resources"
            (resources / "lang").mkdir(parents=True)
            (resources / "baseset").mkdir()
            (resources / "game").mkdir()
            (resources / "lang" / "english.lng").write_text("language", encoding="utf-8")
            (resources / "baseset" / "openttd.grf").write_bytes(b"grf")
            (resources / "baseset" / "no_sound.obs").write_bytes(b"sound")
            (resources / "game" / "compat_1.11.nut").write_text("compat", encoding="utf-8")
            (resources / "game" / "ignore.txt").write_text("ignore", encoding="utf-8")
            profile = root / "profile"
            profile.mkdir()

            metadata = probe.stage_builtin_resources(profile, resources)

            self.assertEqual(metadata["file_counts"], {"lang": 1, "baseset": 2, "game_compat": 1})
            self.assertEqual((profile / "lang" / "english.lng").read_text(encoding="utf-8"), "language")
            self.assertTrue((profile / "baseset" / "openttd.grf").is_file())
            self.assertTrue((profile / "game" / "compat_1.11.nut").is_file())
            self.assertFalse((profile / "game" / "ignore.txt").exists())
            self.assertEqual(metadata["source_sha256"]["baseset"], metadata["staged_sha256"]["baseset"])

    def test_disposable_run_directories_are_never_replaced(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "runtime"
            artifacts = Path(temporary) / "artifacts"
            first_name, first_profile, first_artifacts = probe.create_run(root, artifacts)
            first_profile.joinpath("marker").write_text("keep", encoding="utf-8")
            second_name, second_profile, second_artifacts = probe.create_run(root, artifacts)
            self.assertNotEqual(first_name, second_name)
            self.assertTrue(first_profile.joinpath("marker").is_file())
            self.assertNotEqual(first_profile, second_profile)
            self.assertNotEqual(first_artifacts, second_artifacts)
            self.assertRegex(first_name, probe.RUN_NAME_RE)

    def test_inspect_is_read_only_and_points_at_final_save(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            run = Path(temporary) / "run"
            profile = run / "profile"
            profile.mkdir(parents=True)
            config = profile / "openttd.cfg"
            final_save = profile / "save" / "final.sav"
            final_save.parent.mkdir()
            config.write_text("[misc]\n", encoding="utf-8")
            (run / "manifest.json").write_text(
                json.dumps(
                    {
                        "binary": "/Applications/OpenTTD.app/Contents/MacOS/openttd",
                        "server_config": str(config),
                        "server_profile": str(profile),
                        "final_save": str(final_save),
                    }
                ),
                encoding="utf-8",
            )
            command = probe.inspect_command(run)
            self.assertIn("-X", command)
            self.assertIn("-x", command)
            self.assertIn("-g", command)
            self.assertIn("cocoa", command)
            self.assertIn(str(final_save), command)
            self.assertFalse((run / "launched").exists())


if __name__ == "__main__":
    unittest.main()
