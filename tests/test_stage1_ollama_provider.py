from __future__ import annotations

import base64
import unittest
from pathlib import Path

from top_view_grounded_height_verification.common.io_utils import ROOT
from top_view_grounded_height_verification.common.providers import (
    DEFAULT_OLLAMA_BASE_URL,
    OllamaClient,
    ProviderError,
    normalize_ollama_base_url,
)
from top_view_grounded_height_verification.stage1.runner import build_provider_clients, parse_args


class FakeResponse:
    def __init__(
        self,
        *,
        ok: bool,
        status_code: int,
        text: str,
        payload: dict[str, object] | None,
    ) -> None:
        self.ok = ok
        self.status_code = status_code
        self.text = text
        self._payload = payload

    def json(self) -> dict[str, object]:
        if self._payload is None:
            raise ValueError("not json")
        return self._payload


class FakeRequests:
    class exceptions:
        class RequestException(Exception):
            pass

    def __init__(self, response: FakeResponse) -> None:
        self.response = response
        self.calls: list[dict[str, object]] = []

    def post(self, endpoint: str, *, json: dict[str, object], timeout: int) -> FakeResponse:
        self.calls.append({"endpoint": endpoint, "json": json, "timeout": timeout})
        return self.response


class OllamaProviderTests(unittest.TestCase):
    def test_normalize_ollama_base_url(self) -> None:
        self.assertEqual(normalize_ollama_base_url(None), DEFAULT_OLLAMA_BASE_URL)
        self.assertEqual(normalize_ollama_base_url("http://localhost:11434"), DEFAULT_OLLAMA_BASE_URL)
        self.assertEqual(normalize_ollama_base_url("http://localhost:11434/api"), DEFAULT_OLLAMA_BASE_URL)
        self.assertEqual(normalize_ollama_base_url("http://example.test/ollama/"), "http://example.test/ollama/api")

    def test_ollama_client_run_posts_chat_payload(self) -> None:
        image_path = ROOT / "data" / "package_drawings" / "images" / "sot-23" / "canonical-values.png"
        fake_requests = FakeRequests(
            FakeResponse(
                ok=True,
                status_code=200,
                text='{"message":{"content":"{\\"ok\\": true}"}}',
                payload={"message": {"content": '{"ok": true}'}},
            )
        )
        client = OllamaClient(
            "llava-test",
            "",
            timeout_seconds=17,
            temperature=0.25,
            base_url="http://localhost:11434",
        )
        client._requests = fake_requests

        result = client.run(prompt_text="Return JSON only.", image_path=image_path)

        self.assertEqual(result["response_text"], '{"ok": true}')
        self.assertEqual(result["request_summary"]["transport"], "ollama REST API")
        self.assertEqual(fake_requests.calls[0]["endpoint"], "http://localhost:11434/api/chat")
        self.assertEqual(fake_requests.calls[0]["timeout"], 17)
        payload = fake_requests.calls[0]["json"]
        self.assertEqual(payload["model"], "llava-test")
        self.assertEqual(payload["stream"], False)
        self.assertEqual(payload["think"], False)
        self.assertEqual(payload["options"], {"temperature": 0.25})
        message = payload["messages"][0]
        self.assertEqual(message["content"], "Return JSON only.")
        self.assertEqual(
            message["images"],
            [base64.b64encode(image_path.read_bytes()).decode("ascii")],
        )

    def test_ollama_client_http_error_preserves_status_code(self) -> None:
        image_path = ROOT / "data" / "package_drawings" / "images" / "sot-23" / "canonical-values.png"
        fake_requests = FakeRequests(
            FakeResponse(
                ok=False,
                status_code=500,
                text='{"error":"model failed"}',
                payload={"error": "model failed"},
            )
        )
        client = OllamaClient("llava-test", "", timeout_seconds=17, temperature=0.0)
        client._requests = fake_requests

        with self.assertRaises(ProviderError) as context:
            client.run(prompt_text="Return JSON only.", image_path=image_path)
        self.assertEqual(context.exception.status_code, 500)
        self.assertIn("model failed", str(context.exception))

    def test_stage1_parse_args_accepts_ollama_model(self) -> None:
        args = parse_args(
            argv=[
                "--task-name",
                "top_view_detection",
                "--providers",
                "ollama",
                "--ollama-model",
                "llava-test",
            ]
        )
        self.assertEqual(args.models["ollama"], "llava-test")

    def test_stage1_dry_run_ollama_does_not_require_model_or_api_key(self) -> None:
        args = parse_args(
            argv=[
                "--task-name",
                "top_view_detection",
                "--providers",
                "ollama",
                "--dry-run",
                "--env-path",
                str(Path("/tmp/tvghv-missing-env-file")),
            ]
        )
        clients = build_provider_clients(args)
        self.assertEqual(clients["ollama"].model, "ollama-dry-run")


if __name__ == "__main__":
    unittest.main()
