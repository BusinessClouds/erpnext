"""Exercise the real documentation guard with only its HTTP boundary replaced."""

import runpy
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

GUARD = Path(__file__).resolve().parents[1] / ".github/helper/documentation.py"


class TestSharedV15DocumentationGuard(unittest.TestCase):
	def setUp(self):
		# Keep the focused suite offline and independent of requests installation.
		self.http = SimpleNamespace(get=Mock())
		with patch.dict(sys.modules, {"requests": self.http}):
			self.guard = runpy.run_path(str(GUARD))

	def respond(self, *, title="feat: add feature", body="", ok=True):
		self.http.get.return_value = SimpleNamespace(
			ok=ok, json=lambda: {"title": title, "head": {"sha": "test-commit"}, "body": body}
		)

	def test_fork_repository_looks_up_its_own_pull_request(self):
		self.respond(title="test: shared v15 source contract")
		code, _ = self.guard["check_pull_request"]("7", "BusinessClouds/erpnext")
		self.assertEqual(code, 0)
		self.http.get.assert_called_once_with("https://api.github.com/repos/BusinessClouds/erpnext/pulls/7")

	def test_feature_without_documentation_still_fails(self):
		self.respond()
		code, message = self.guard["check_pull_request"]("7", "BusinessClouds/erpnext")
		self.assertEqual(code, 1)
		self.assertIn("Documentation Link Not Found", message)

	def test_feature_with_recognized_documentation_passes(self):
		self.respond(body="https://docs.frappe.io/erpnext/user/manual/en/payment-entry")
		code, message = self.guard["check_pull_request"]("7", "BusinessClouds/erpnext")
		self.assertEqual(code, 0)
		self.assertIn("Documentation Link Found", message)

	def test_api_failure_still_fails_for_non_feature_pull_request(self):
		self.respond(title="test: shared v15 source contract", ok=False)
		code, message = self.guard["check_pull_request"]("7", "BusinessClouds/erpnext")
		self.assertEqual(code, 1)
		self.assertIn("Pull Request Not Found", message)

	def test_old_local_call_retains_upstream_repository_default(self):
		self.respond(title="test: local guard check")
		self.guard["check_pull_request"]("7")
		self.http.get.assert_called_once_with("https://api.github.com/repos/frappe/erpnext/pulls/7")

	def test_cli_passes_the_workflow_repository_to_the_guard(self):
		self.respond(title="test: shared v15 source contract")
		with (
			patch.dict(sys.modules, {"requests": self.http}),
			patch.object(sys, "argv", [str(GUARD), "7", "BusinessClouds/erpnext"]),
			patch("builtins.print"),
			self.assertRaises(SystemExit) as result,
		):
			runpy.run_path(str(GUARD), run_name="__main__")
		self.assertEqual(result.exception.code, 0)
		self.http.get.assert_called_once_with("https://api.github.com/repos/BusinessClouds/erpnext/pulls/7")


if __name__ == "__main__":
	unittest.main()
