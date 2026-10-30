import base64
import json
import unittest

from scripts.export_openrouter_usage import extract, generation_id


class UsageExportTests(unittest.TestCase):
    def row(self, **changes):
        call = {"event": "success", "start_time": "2026-10-27T23:01:00",
                "end_time": "2026-10-27T23:01:02", "response_id": "gen-fixture",
                "usage": {"prompt_tokens": 10, "completion_tokens": 3, "total_tokens": 13, "cost": .002}}
        call.update(changes)
        return extract(call, source="runs/fixture/provider-calls.json", index=0,
                       task="bike-rebalance", model="openrouter/openai/gpt-5.4-mini")

    def test_exact_timezone_and_half_open_window(self):
        self.assertIsNone(self.row(start_time="2026-10-27T23:20:00"))
        self.assertIsNone(self.row(start_time="2026-10-27T22:59:59"))
        self.assertIsNotNone(self.row(start_time="2026-10-27T15:00:00Z"))
        self.assertTrue(self.row()["started_at"].endswith("+08:00"))

    def test_missing_values_are_not_fabricated_and_estimate_is_distinct(self):
        row = self.row(usage={"prompt_tokens": 10, "completion_tokens": 3}, response_cost=.003)
        for field in ("api_cost_usd", "total_tokens", "http_status_code", "retry_count", "cancelled", "request_id"):
            self.assertIsNone(row[field])
        self.assertEqual(row["proxy_estimated_cost_usd"], .003)
        self.assertIsNone(self.row(usage={"cost": float("nan")})["api_cost_usd"])

    def test_content_headers_errors_and_nested_secrets_never_exported(self):
        sentinel = "DO_NOT_EXPORT_SENSITIVE_FIXTURE"
        row = self.row(request={"headers": {"Authorization": sentinel}, "body": {"messages": sentinel}},
                       response={"output": sentinel}, error={"message": sentinel},
                       provider_error={"category": sentinel}, extra=sentinel)
        self.assertNotIn(sentinel, json.dumps(row))

    def test_proxy_id_decodes_only_the_generation_id(self):
        encoded = base64.b64encode(b"litellm:model_id:private;response_id:gen-fixture").decode()
        self.assertEqual(generation_id("resp_" + encoded), "gen-fixture")
        self.assertIsNone(generation_id("resp_bad"))
        self.assertIsNone(generation_id("gen-with space"))


if __name__ == "__main__":
    unittest.main()
