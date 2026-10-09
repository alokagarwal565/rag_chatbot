"""Gemini provider (google-genai SDK) with key rotation and per-tier model fallback.

Attempt order for a tier is (model, key) pairs: the primary model on every key, then the
fallback model on every key. A key that returns 429 / RESOURCE_EXHAUSTED is put on a
cooldown so later requests skip it. Server errors, timeouts and "model not found" move to
the next attempt. Streaming can only fall back before the first token has been emitted.
"""
import asyncio
import time
from dataclasses import dataclass
from typing import AsyncGenerator, Dict, List, Optional, Tuple

from google import genai
from google.genai import types

from app.config import settings
from app.logging_config import get_logger

logger = get_logger(__name__)

KEY_COOLDOWN_SECONDS = 60.0


class LLMProviderError(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


@dataclass
class LLMResult:
    text: str
    model: str
    key_index: int
    input_tokens: int = 0
    output_tokens: int = 0
    attempts: int = 1


def _is_quota_error(err: Exception) -> bool:
    s = str(err).lower()
    return getattr(err, "code", None) == 429 or "resource_exhausted" in s or "quota" in s or "429" in s


def _is_thinking_error(err: Exception) -> bool:
    """Some models reject thinking_budget=0 with a bare 400 INVALID_ARGUMENT."""
    s = str(err).lower()
    return "thinking" in s or "invalid_argument" in s or getattr(err, "code", None) == 400


def _is_model_error(err: Exception) -> bool:
    """Request/model problems (4xx other than quota) are not key-specific: skip the model's other keys."""
    code = getattr(err, "code", None)
    return isinstance(code, int) and 400 <= code < 500 and code != 429


class GeminiProvider:
    def __init__(self, api_keys: Optional[List[str]] = None, timeout_seconds: float = None):
        self.api_keys = api_keys if api_keys is not None else settings.get_gemini_api_keys()
        self.timeout_seconds = timeout_seconds or settings.llm_timeout_seconds
        self._clients: Dict[int, genai.Client] = {}
        self._key_cooldown_until: Dict[int, float] = {}
        # Models that rejected thinking_budget=0 (thinking cannot be disabled on them).
        self._no_thinking_override: set = set()

    @property
    def available(self) -> bool:
        return bool(self.api_keys)

    def tier_models(self, tier: str) -> List[str]:
        if tier == "heavy":
            models = [settings.gemini_model_heavy, settings.gemini_model_fallback_heavy]
        else:
            models = [settings.gemini_model_fast, settings.gemini_model_fallback_fast]
        out = []
        for m in models:
            if m and m not in out:
                out.append(m)
        return out

    def _client(self, idx: int) -> genai.Client:
        if idx not in self._clients:
            self._clients[idx] = genai.Client(api_key=self.api_keys[idx])
        return self._clients[idx]

    def _attempts(self, tier: str) -> List[Tuple[str, int]]:
        now = time.monotonic()
        keys = [i for i in range(len(self.api_keys)) if self._key_cooldown_until.get(i, 0) <= now]
        if not keys:  # every key cooling down: try them all anyway rather than fail outright
            keys = list(range(len(self.api_keys)))
        return [(m, k) for m in self.tier_models(tier) for k in keys]

    def _config(self, model: str, system: Optional[str], max_tokens: int,
                temperature: float, json_mode: bool) -> types.GenerateContentConfig:
        kwargs = dict(temperature=temperature, max_output_tokens=max_tokens)
        if system:
            kwargs["system_instruction"] = system
        if json_mode:
            kwargs["response_mime_type"] = "application/json"
        if model not in self._no_thinking_override:
            kwargs["thinking_config"] = types.ThinkingConfig(thinking_budget=0)
        return types.GenerateContentConfig(**kwargs)

    def _record_failure(self, model: str, key_idx: int, err: Exception) -> None:
        if _is_quota_error(err):
            self._key_cooldown_until[key_idx] = time.monotonic() + KEY_COOLDOWN_SECONDS
        logger.warning("gemini_attempt_failed", model=model, key_index=key_idx, error=str(err)[:300])

    async def generate(self, prompt: str, system: Optional[str] = None, tier: str = "fast",
                       max_tokens: int = None, temperature: float = 0.0,
                       json_mode: bool = False, timeout: float = None) -> LLMResult:
        if not self.available:
            raise LLMProviderError("NO_API_KEY", "No GEMINI_API_KEY configured in .env")
        max_tokens = max_tokens or settings.llm_max_output_tokens
        timeout = timeout or self.timeout_seconds
        last_error: Optional[Exception] = None
        n = 0
        bad_models: set = set()
        for model, key_idx in self._attempts(tier):
            if model in bad_models:
                continue
            for _ in range(2):  # second pass only when retrying without the thinking override
                n += 1
                try:
                    resp = await asyncio.wait_for(
                        self._client(key_idx).aio.models.generate_content(
                            model=model, contents=prompt,
                            config=self._config(model, system, max_tokens, temperature, json_mode)),
                        timeout=timeout)
                    usage = getattr(resp, "usage_metadata", None)
                    return LLMResult(
                        text=resp.text or "", model=model, key_index=key_idx,
                        input_tokens=getattr(usage, "prompt_token_count", 0) or 0,
                        output_tokens=getattr(usage, "candidates_token_count", 0) or 0,
                        attempts=n)
                except Exception as e:  # noqa: BLE001 - every failure moves to the next attempt
                    last_error = e
                    if _is_thinking_error(e) and model not in self._no_thinking_override:
                        self._no_thinking_override.add(model)
                        continue
                    self._record_failure(model, key_idx, e)
                    if _is_model_error(e):
                        bad_models.add(model)
                    break
        raise LLMProviderError("ALL_FALLBACKS_EXHAUSTED", f"Gemini failed on every key/model: {last_error}")

    async def generate_streaming(self, prompt: str, system: Optional[str] = None, tier: str = "fast",
                                 max_tokens: int = None, meta: Optional[dict] = None
                                 ) -> AsyncGenerator[str, None]:
        """Yields text deltas. `meta` (if given) receives the model and key that served the stream."""
        if not self.available:
            raise LLMProviderError("NO_API_KEY", "No GEMINI_API_KEY configured in .env")
        max_tokens = max_tokens or settings.llm_max_output_tokens
        last_error: Optional[Exception] = None
        bad_models: set = set()
        for model, key_idx in self._attempts(tier):
            if model in bad_models:
                continue
            for _ in range(2):
                started = False
                try:
                    stream = await asyncio.wait_for(
                        self._client(key_idx).aio.models.generate_content_stream(
                            model=model, contents=prompt,
                            config=self._config(model, system, max_tokens, 0.0, False)),
                        timeout=settings.llm_first_token_timeout_seconds)
                    it = stream.__aiter__()
                    deadline = time.monotonic() + self.timeout_seconds
                    while True:
                        wait = settings.llm_first_token_timeout_seconds if not started else max(0.5, deadline - time.monotonic())
                        try:
                            chunk = await asyncio.wait_for(it.__anext__(), timeout=wait)
                        except StopAsyncIteration:
                            break
                        text = getattr(chunk, "text", None)
                        if text:
                            if not started and meta is not None:
                                meta.update(model=model, key_index=key_idx)
                            started = True
                            yield text
                    if not started and meta is not None:
                        meta.update(model=model, key_index=key_idx)
                    return
                except Exception as e:  # noqa: BLE001
                    if started:
                        raise LLMProviderError("STREAM_INTERRUPTED", f"Gemini stream broke mid-answer: {e}")
                    last_error = e
                    if _is_thinking_error(e) and model not in self._no_thinking_override:
                        self._no_thinking_override.add(model)
                        continue
                    self._record_failure(model, key_idx, e)
                    if _is_model_error(e):
                        bad_models.add(model)
                    break
        raise LLMProviderError("ALL_FALLBACKS_EXHAUSTED", f"Gemini streaming failed on every key/model: {last_error}")
