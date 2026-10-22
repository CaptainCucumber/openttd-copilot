import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from copilot_chat import ChatInputError, format_plan, parse_request


class CopilotChatTests(unittest.TestCase):
    def test_supported_request_becomes_grounded_intent(self):
        intent = parse_request(
            "Build a railway carrying coal from a coal mine to a power station. "
            "Wait for a full load."
        )
        self.assertEqual(intent["cargo"], "coal")
        self.assertEqual(intent["loading"], "full_load")
        self.assertEqual(intent["verification"], ["two_full_load_departures", "two_deliveries"])
        self.assertIn("disposable", format_plan(intent))

    def test_paraphrase_is_supported(self):
        intent = parse_request("Please make a train route for coal to the power plant, fully loaded each trip")
        self.assertEqual(intent["mode"], "rail")

    def test_unsupported_requests_are_rejected_without_guessing(self):
        for request in [
            "Build a bus route for passengers",
            "Build a coal railway to the power station",
            "Build a railway carrying iron ore to a power station, full load",
        ]:
            with self.subTest(request=request):
                with self.assertRaises(ChatInputError):
                    parse_request(request)


if __name__ == "__main__":
    unittest.main()
