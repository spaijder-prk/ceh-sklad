from __future__ import annotations

import copy
import importlib.util
import json
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "scripts" / "apply_github_ruleset.py"
RULESET_PATH = ROOT / ".github" / "rulesets" / "main.json"

spec = importlib.util.spec_from_file_location("apply_github_ruleset", SCRIPT_PATH)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ApplyGithubRulesetTests(unittest.TestCase):
    def setUp(self) -> None:
        self.expected = json.loads(RULESET_PATH.read_text(encoding="utf-8"))

    def test_validate_accepts_expected_ruleset_with_api_metadata(self) -> None:
        actual = copy.deepcopy(self.expected)
        actual["id"] = 123
        pull_request = next(rule for rule in actual["rules"] if rule["type"] == "pull_request")
        pull_request["parameters"]["future_github_default"] = False

        self.assertEqual(module.validate_ruleset(actual, self.expected), [])

    def test_validate_reports_security_relevant_drift(self) -> None:
        actual = copy.deepcopy(self.expected)
        actual["enforcement"] = "disabled"
        actual["bypass_actors"] = [{"actor_id": 1, "actor_type": "RepositoryRole"}]
        pull_request = next(rule for rule in actual["rules"] if rule["type"] == "pull_request")
        pull_request["parameters"]["required_review_thread_resolution"] = False
        status = next(rule for rule in actual["rules"] if rule["type"] == "required_status_checks")
        status["parameters"]["required_status_checks"] = [
            {"context": "Итоговая проверка проекта"}
        ]

        errors = module.validate_ruleset(actual, self.expected)
        joined = "\n".join(errors)
        self.assertIn("enforcement", joined)
        self.assertIn("bypass_actors", joined)
        self.assertIn("required_review_thread_resolution", joined)
        self.assertIn("required status checks", joined)

    def test_check_only_is_read_only_and_can_work_without_admin_token(self) -> None:
        actual = copy.deepcopy(self.expected)
        actual["id"] = 123
        responses = [
            [{"id": 123, "name": module.RULESET_NAME}],
            actual,
        ]
        with mock.patch.object(sys, "argv", [str(SCRIPT_PATH), "--check-only"]), mock.patch.dict(
            os.environ,
            {"GITHUB_REPOSITORY": "spaijder-prk/ceh-sklad"},
            clear=True,
        ), mock.patch.object(module, "_request", side_effect=responses) as request:
            result = module.main()

        self.assertEqual(result, 0)
        self.assertEqual([call.args[0] for call in request.call_args_list], ["GET", "GET"])
        self.assertTrue(all(call.args[2] is None for call in request.call_args_list))

    def test_apply_requires_admin_token(self) -> None:
        with mock.patch.object(sys, "argv", [str(SCRIPT_PATH)]), mock.patch.dict(
            os.environ,
            {"GITHUB_REPOSITORY": "spaijder-prk/ceh-sklad"},
            clear=True,
        ):
            self.assertEqual(module.main(), 2)


if __name__ == "__main__":
    unittest.main()
