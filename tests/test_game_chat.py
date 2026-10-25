from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

from unittest.mock import patch

from tools import game_chat


class GameChatLauncherTests(unittest.TestCase):
    def test_command_uses_absolute_scoped_native_server_and_python(self):
        command = game_chat.launch_command("/custom/copilot", seed=6, visible=False)
        self.assertEqual(command[0:4], ["/custom/copilot", "-C", str(game_chat.ROOT), "--agent"])
        self.assertEqual(command[4], "openttd")
        self.assertEqual(command[5:8], ["--no-custom-instructions", "--disable-builtin-mcps",
                                         "--additional-mcp-config"])
        config = json.loads(command[8])
        server = config["mcpServers"]["openttd-copilot-native"]
        self.assertEqual(server["command"], sys.executable)
        self.assertEqual(Path(server["args"][1]), game_chat.SERVER)
        self.assertTrue(Path(server["args"][1]).is_absolute())
        self.assertEqual(server["tools"], [
            "open_native_map", "inspect_native_game", "plan_native_railway",
            "build_native_railway", "plan_native_bus", "build_native_bus",
            "get_native_status", "close_native_map",
        ])
        self.assertIn("--no-show", server["args"])

    def test_allowlist_and_prompt_do_not_authorize_construction(self):
        command = game_chat.launch_command("copilot")
        allowlisted = [arg for arg in command if arg.startswith("--allow-tool=")]
        self.assertEqual(set(allowlisted), {
            "--allow-tool=openttd-copilot-native(inspect_native_game)",
            "--allow-tool=openttd-copilot-native(plan_native_railway)",
            "--allow-tool=openttd-copilot-native(plan_native_bus)",
            "--allow-tool=openttd-copilot-native(get_native_status)",
        })
        prompt = command[-1].casefold()
        self.assertIn("do not construct anything", prompt)
        self.assertNotIn("build_native_railway", prompt)
        self.assertIn("--deny-tool=shell", command)
        self.assertIn("--deny-tool=write", command)
        for tool in ("shell", "bash", "sql", "skill", "read", "edit", "write"):
            self.assertIn("--excluded-tools=" + tool, command)

    def test_save_path_is_resolved_and_passed_to_native_server(self):
        with tempfile.TemporaryDirectory() as directory:
            save = Path(directory) / "copy.sav"
            save.write_bytes(b"save")
            command = game_chat.launch_command("copilot", save=save)
        config = json.loads(command[command.index("--additional-mcp-config") + 1])
        args = config["mcpServers"]["openttd-copilot-native"]["args"]
        self.assertEqual(args[args.index("--save") + 1], str(save.resolve()))
        self.assertIn("copied save", command[-1])

    def test_seed_and_save_validation_rejects_invalid_inputs_without_launching(self):
        for seed in (-1, 0x1_0000_0000, True, 1.5):
            with self.subTest(seed=seed), self.assertRaises(ValueError):
                game_chat.launch_command("copilot", seed=seed)
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "missing.sav"
            wrong = Path(directory) / "save.txt"
            wrong.write_text("not a save", encoding="utf-8")
            for save in (missing, wrong):
                with self.subTest(save=save), self.assertRaises(ValueError):
                    game_chat.launch_command("copilot", save=save)

    def test_launcher_does_not_call_subprocess_until_main(self):
        with patch.object(game_chat.shutil, "which", return_value="/bin/copilot"), \
             patch.object(game_chat.subprocess, "call") as call:
            with patch("sys.argv", ["game_chat.py", "--no-show"]):
                game_chat.main()
        call.assert_called_once()

    def test_normal_map_is_random_and_fixture_remains_explicit(self):
        with patch.object(game_chat.secrets, "randbits", return_value=123456):
            normal = game_chat.launch_command("copilot")
            fixture = game_chat.launch_command("copilot", map_style="railway-fixture")
        def args(command):
            return json.loads(command[8])["mcpServers"]["openttd-copilot-native"]["args"]
        self.assertEqual(args(normal)[args(normal).index("--seed") + 1], "123456")
        self.assertEqual(args(normal)[args(normal).index("--map-style") + 1], "normal")
        self.assertEqual(args(fixture)[args(fixture).index("--seed") + 1], "6")
        with self.assertRaises(ValueError):
            game_chat.launch_command("copilot", map_style="made-up")


if __name__ == "__main__":
    unittest.main()
