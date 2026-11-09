"""可选模型连接的请求范围、错误处理和密钥边界。"""

import io
import json
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from investigator import model_api as api


class ModelApiTests(unittest.TestCase):
    def setUp(self):
        self.config = api.ModelConfig("https://example.invalid/v1/", "test-model", "test-only-marker")

    def test_sends_only_displayed_answer_and_reads_message_content(self):
        self.assertNotIn(self.config.api_key, repr(self.config))
        with patch.object(api, "build_opener") as opener:
            response = {"choices": [{"message": {"content": "按报告范围关闭。"}, "finish_reason": "stop"}]}
            opener.return_value.open.return_value = io.BytesIO(json.dumps(response).encode())
            self.assertEqual(api.explain_with_model(self.config, "规则回答"), "按报告范围关闭。")
            request = opener.return_value.open.call_args.args[0]
            self.assertEqual(request.full_url, "https://example.invalid/v1/chat/completions")
            self.assertEqual(request.get_header("Authorization"), "Bearer " + self.config.api_key)
            body = json.loads(request.data)
            self.assertEqual(body["messages"][1], {"role": "user", "content": "规则回答"})
            self.assertEqual(body["model"], "test-model")
            self.assertNotIn(self.config.api_key.encode(), request.data)

    def test_insecure_remote_or_embedded_credentials_never_send(self):
        for base in ("http://example.invalid/v1", "https://user@host/v1", "https://host/v1?q=secret"):
            with self.subTest(base=base), patch.object(api, "build_opener") as opener, self.assertRaises(api.ModelError):
                api.explain_with_model(api.ModelConfig(base, "test-model", self.config.api_key), "结果")
            opener.assert_not_called()
        self.assertEqual(api.ModelConfig("http://127.0.0.1:1234/v1/chat/completions", "x", "demo").endpoint(),
                         "http://127.0.0.1:1234/v1/chat/completions")

    def test_remote_error_body_and_timeout_are_safe(self):
        errors = [(HTTPError(self.config.base_url, 401, self.config.api_key, {}, None), "401"),
                  (URLError(TimeoutError()), "超时")]
        for error, message in errors:
            with self.subTest(message=message), patch.object(api, "build_opener") as opener:
                opener.return_value.open.side_effect = error
                with self.assertRaisesRegex(api.ModelError, message) as raised:
                    api.explain_with_model(self.config, "规则回答")
                self.assertNotIn(self.config.api_key, str(raised.exception))

    def test_malformed_oversized_and_truncated_responses_do_not_replace_answer(self):
        for data in (b"{}", b"x" * (api.MAX_RESPONSE + 1),
                     b'{"choices":[{"finish_reason":"length","message":{"content":"partial"}}]}'):
            with self.subTest(size=len(data)), patch.object(api, "build_opener") as opener:
                opener.return_value.open.return_value = io.BytesIO(data)
                with self.assertRaises(api.ModelError):
                    api.explain_with_model(self.config, "规则回答")
