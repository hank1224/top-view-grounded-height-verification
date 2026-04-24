from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from top_view_grounded_height_verification.common.io_utils import (
    ROOT,
    detect_mime_type,
    dump_sdk_response,
    encode_image_to_base64,
)


DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434/api"


def normalize_ollama_base_url(base_url: str | None) -> str:
    normalized = (base_url or DEFAULT_OLLAMA_BASE_URL).rstrip("/")
    if not normalized.endswith("/api"):
        normalized = f"{normalized}/api"
    return normalized


class ProviderError(Exception):
    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class ProviderClient:
    provider_name: str

    def __init__(
        self,
        model: str,
        api_key: str,
        timeout_seconds: int,
        temperature: float,
        *,
        base_url: str | None = None,
    ) -> None:
        self.model = model
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.temperature = temperature
        self.base_url = base_url

    def run(self, *, prompt_text: str, image_path: Path) -> dict[str, Any]:
        raise NotImplementedError


class OpenAIClient(ProviderClient):
    provider_name = "openai"

    def __init__(self, model: str, api_key: str, timeout_seconds: int, temperature: float) -> None:
        super().__init__(model, api_key, timeout_seconds, temperature)
        try:
            from openai import OpenAI  # type: ignore
        except ImportError as exc:
            raise ProviderError(
                "OpenAI SDK is not installed in the active Python environment. "
                "Install it in `.venv` and run with `./.venv/bin/python`."
            ) from exc
        self._client = OpenAI(api_key=api_key, timeout=timeout_seconds)

    def run(self, *, prompt_text: str, image_path: Path) -> dict[str, Any]:
        mime_type, image_b64 = encode_image_to_base64(image_path)
        payload = {
            "model": self.model,
            "input": [
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": prompt_text},
                        {
                            "type": "input_image",
                            "image_url": f"data:{mime_type};base64,{image_b64}",
                            "detail": "high",
                        },
                    ],
                }
            ],
            "temperature": self.temperature,
        }

        response = self._client.responses.create(**payload)
        raw_text, response_json = dump_sdk_response(response)
        output_text = getattr(response, "output_text", None)
        return {
            "status_code": 200,
            "raw_response_text": raw_text,
            "response_json": response_json,
            "response_text": output_text,
            "request_summary": {
                "transport": "openai-python SDK",
                "endpoint": "client.responses.create",
                "model": self.model,
                "image_path": image_path.relative_to(ROOT).as_posix(),
                "mime_type": mime_type,
                "temperature": self.temperature,
                "structured_output": False,
            },
        }


class GeminiClient(ProviderClient):
    provider_name = "gemini"

    def __init__(self, model: str, api_key: str, timeout_seconds: int, temperature: float) -> None:
        super().__init__(model, api_key, timeout_seconds, temperature)
        try:
            from google import genai  # type: ignore
            from google.genai import types  # type: ignore
        except ImportError as exc:
            raise ProviderError(
                "google-genai SDK is not installed in the active Python environment. "
                "Install it in `.venv` and run with `./.venv/bin/python`."
            ) from exc
        self._types = types
        self._client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(timeout=self.timeout_seconds * 1000),
        )

    def run(self, *, prompt_text: str, image_path: Path) -> dict[str, Any]:
        mime_type = detect_mime_type(image_path)
        image_part = self._types.Part.from_bytes(data=image_path.read_bytes(), mime_type=mime_type)
        response = self._client.models.generate_content(
            model=self.model,
            contents=[prompt_text, image_part],
            config=self._types.GenerateContentConfig(temperature=self.temperature),
        )
        raw_text, response_json = dump_sdk_response(response)
        output_text = getattr(response, "text", None)
        return {
            "status_code": 200,
            "raw_response_text": raw_text,
            "response_json": response_json,
            "response_text": output_text,
            "request_summary": {
                "transport": "google-genai SDK",
                "endpoint": "client.models.generate_content",
                "model": self.model,
                "image_path": image_path.relative_to(ROOT).as_posix(),
                "mime_type": mime_type,
                "temperature": self.temperature,
                "structured_output": False,
            },
        }


class AnthropicClient(ProviderClient):
    provider_name = "anthropic"

    def __init__(self, model: str, api_key: str, timeout_seconds: int, temperature: float) -> None:
        super().__init__(model, api_key, timeout_seconds, temperature)
        try:
            from anthropic import Anthropic  # type: ignore
        except ImportError as exc:
            raise ProviderError(
                "Anthropic SDK is not installed in the active Python environment. "
                "Install it in `.venv` and run with `./.venv/bin/python`."
            ) from exc
        self._client = Anthropic(api_key=api_key, timeout=timeout_seconds)

    def run(self, *, prompt_text: str, image_path: Path) -> dict[str, Any]:
        mime_type, image_b64 = encode_image_to_base64(image_path)
        payload = {
            "model": self.model,
            "max_tokens": 4096,
            "temperature": self.temperature,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": mime_type,
                                "data": image_b64,
                            },
                        },
                        {
                            "type": "text",
                            "text": prompt_text,
                        },
                    ],
                }
            ],
        }
        response = self._client.messages.create(**payload)
        raw_text, response_json = dump_sdk_response(response)
        output_text = None
        if response_json:
            text_chunks = [
                item.get("text")
                for item in response_json.get("content", [])
                if item.get("type") == "text" and isinstance(item.get("text"), str)
            ]
            if text_chunks:
                output_text = "".join(text_chunks)

        return {
            "status_code": 200,
            "raw_response_text": raw_text,
            "response_json": response_json,
            "response_text": output_text,
            "request_summary": {
                "transport": "anthropic SDK",
                "endpoint": "client.messages.create",
                "model": self.model,
                "image_path": image_path.relative_to(ROOT).as_posix(),
                "mime_type": mime_type,
                "temperature": self.temperature,
                "structured_output": False,
            },
        }


class OllamaClient(ProviderClient):
    provider_name = "ollama"

    def __init__(
        self,
        model: str,
        api_key: str,
        timeout_seconds: int,
        temperature: float,
        *,
        base_url: str | None = None,
    ) -> None:
        super().__init__(
            model,
            api_key,
            timeout_seconds,
            temperature,
            base_url=normalize_ollama_base_url(base_url),
        )
        try:
            import requests  # type: ignore
        except ImportError as exc:
            raise ProviderError(
                "requests is not installed in the active Python environment. "
                "Install requirements and run with `./.venv/bin/python`."
            ) from exc
        self._requests = requests
        self.base_url = normalize_ollama_base_url(self.base_url)

    def run(self, *, prompt_text: str, image_path: Path) -> dict[str, Any]:
        mime_type, image_b64 = encode_image_to_base64(image_path)
        endpoint = f"{self.base_url}/chat"
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": prompt_text,
                    "images": [image_b64],
                }
            ],
            "stream": False,
            "think": False,
            "options": {
                "temperature": self.temperature,
            },
        }
        try:
            response = self._requests.post(endpoint, json=payload, timeout=self.timeout_seconds)
        except self._requests.exceptions.RequestException as exc:
            raise ProviderError(f"Ollama API request failed: {exc}") from exc

        raw_response_text = response.text
        try:
            response_json = response.json()
        except ValueError:
            response_json = None

        if not response.ok:
            error_message = ""
            if isinstance(response_json, dict):
                error_message = str(response_json.get("error") or "")
            if not error_message:
                error_message = raw_response_text.strip()
            raise ProviderError(
                f"Ollama API request failed with HTTP {response.status_code}: {error_message}",
                status_code=response.status_code,
            )

        if not isinstance(response_json, dict):
            raise ProviderError("Ollama API returned a non-JSON response", status_code=response.status_code)

        message = response_json.get("message")
        output_text = message.get("content") if isinstance(message, dict) else None
        if output_text is not None and not isinstance(output_text, str):
            output_text = str(output_text)

        return {
            "status_code": response.status_code,
            "raw_response_text": raw_response_text
            or json.dumps(response_json, ensure_ascii=False, indent=2),
            "response_json": response_json,
            "response_text": output_text,
            "request_summary": {
                "transport": "ollama REST API",
                "endpoint": endpoint,
                "model": self.model,
                "image_path": image_path.relative_to(ROOT).as_posix(),
                "mime_type": mime_type,
                "temperature": self.temperature,
                "base_url": self.base_url,
                "think": False,
                "structured_output": False,
            },
        }


def build_provider_client(
    provider: str,
    *,
    model: str,
    api_key: str,
    timeout_seconds: int,
    temperature: float,
    base_url: str | None = None,
) -> ProviderClient:
    if provider == "openai":
        return OpenAIClient(model, api_key, timeout_seconds, temperature)
    if provider == "gemini":
        return GeminiClient(model, api_key, timeout_seconds, temperature)
    if provider == "anthropic":
        return AnthropicClient(model, api_key, timeout_seconds, temperature)
    if provider == "ollama":
        return OllamaClient(
            model,
            api_key,
            timeout_seconds,
            temperature,
            base_url=base_url,
        )
    raise ProviderError(f"Unsupported provider: {provider}")
