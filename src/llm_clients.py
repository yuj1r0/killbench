"""
LLM Client Wrappers
Provides unified interface for different LLM providers
"""
import os
import time
import threading
from anthropic import Anthropic, BadRequestError
from openai import OpenAI, BadRequestError as OpenAIBadRequestError

# Reasoning-effort vocabulary differs per provider. The benchmark speaks two
# levels -- None (provider default) and "max" (hardest the model will think) --
# and each client translates. Verified live 2026-09-02:
#   - OpenAI accepts "max" only on the Responses API (Chat Completions 400s).
#   - Grok tops out at "xhigh"; its default is already "high".
#   - Gemini's scale is low/medium/high, no "max".
#   - Claude Haiku 4.5 rejects the effort parameter entirely.
EFFORT_MAX = {
    "claude": "max",
    "gpt": "max",
    "grok": "xhigh",
    "gemini": "high",
}


def _detail(block, field):
    """Usage detail blocks arrive as a dict from some SDKs and as a typed
    object from others; getattr() on a dict silently returns the default and
    would zero out thinking-token accounting."""
    if block is None:
        return 0
    if isinstance(block, dict):
        return block.get(field, 0) or 0
    return getattr(block, field, 0) or 0


def resolve_effort(provider, effort):
    """Translate the benchmark's effort label into a provider-native value."""
    if not effort or effort == "default":
        return None
    if effort == "max":
        return EFFORT_MAX.get(provider)
    return effort  # explicit passthrough (low/medium/high/xhigh)


class LLMClient:
    """Base class for LLM clients"""

    def __init__(self):
        # Cumulative token usage + per-call latency across all calls to this
        # client (thread-safe, so it's correct under the parallel runner).
        # NOTE: latency is wall-clock per generate() call, so it's only a true
        # response-time measure at --workers 1; higher concurrency inflates it.
        # cached_input_tokens are billed at a steep discount and thinking_tokens
        # are billed as output, so both are tracked separately for costing.
        self.usage = {
            "input_tokens": 0,
            "output_tokens": 0,
            "cached_input_tokens": 0,
            "thinking_tokens": 0,
            "calls": 0,
        }
        self.latencies = []  # seconds per generate() call
        self._usage_lock = threading.Lock()

    def _record_usage(self, input_tokens, output_tokens, latency=None,
                      cached_input_tokens=0, thinking_tokens=0):
        with self._usage_lock:
            self.usage["input_tokens"] += int(input_tokens or 0)
            self.usage["output_tokens"] += int(output_tokens or 0)
            self.usage["cached_input_tokens"] += int(cached_input_tokens or 0)
            self.usage["thinking_tokens"] += int(thinking_tokens or 0)
            self.usage["calls"] += 1
            if latency is not None:
                self.latencies.append(round(latency, 3))

    def generate(self, system_prompt, user_message=None, conversation_history=None,
                 temperature=0.7, max_tokens=2000, response_format=None,
                 enable_thinking=False, effort=None):
        """
        Generate a response from the LLM

        Args:
            system_prompt: System instructions
            user_message: Single user message (optional if conversation_history provided)
            conversation_history: List of messages (optional)
            temperature: 0.0-1.0
            max_tokens: Max response length
            response_format: "json" for JSON responses
            enable_thinking: Request extended/adaptive thinking (Claude only; ignored
                by other providers). Off by default so tight token budgets aren't
                consumed by thinking blocks.
            effort: None/"default" for the provider default, or "max" for the
                hardest reasoning setting the model supports. Applied to the
                doctor only -- the referee and answer server stay fixed so the
                cross-model comparison isn't confounded.

        Returns:
            String response from LLM
        """
        raise NotImplementedError

    @staticmethod
    def _messages_from(conversation_history, user_message):
        if conversation_history:
            return list(conversation_history)
        if user_message:
            return [{"role": "user", "content": user_message}]
        raise ValueError("Must provide either user_message or conversation_history")


class ClaudeClient(LLMClient):
    """Anthropic Claude client"""

    # Anthropic won't cache a block below ~1024 tokens; ~8000 chars clears that
    # with margin. The referee/answer-server system prompts and case YAML are
    # re-sent on every turn of a case, so caching them is the single biggest
    # cost lever in the harness.
    CACHE_MIN_CHARS = 8000

    def __init__(self, api_key=None, model="claude-sonnet-4-20250514"):
        super().__init__()
        self.client = Anthropic(api_key=api_key or os.getenv("ANTHROPIC_API_KEY"),
                                max_retries=5, timeout=300.0)
        self.model = model

    def generate(self, system_prompt, user_message=None, conversation_history=None,
                 temperature=0.7, max_tokens=2000, response_format=None,
                 enable_thinking=False, effort=None):

        messages = self._messages_from(conversation_history, user_message)

        # Cache the system prompt when it's big enough to be worth it. Cache
        # reads bill at 0.1x, and this prompt repeats every turn within a case.
        if len(system_prompt) >= self.CACHE_MIN_CHARS:
            system = [{"type": "text", "text": system_prompt,
                       "cache_control": {"type": "ephemeral"}}]
        else:
            system = system_prompt

        # Call API. enable_thinking selects adaptive thinking (for deliberate
        # roles like the referee, which has budget to spare) vs disabled (for
        # tight-budget roles like the role-play answer server, where thinking
        # blocks would consume the whole max_tokens and leave no text).
        # Newer models (Sonnet 5, etc.) also removed the temperature parameter
        # and 400 if it's sent; temperature/thinking/effort are stripped and
        # retried if the model rejects them (Haiku 4.5 rejects effort).
        kwargs = dict(
            model=self.model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system,
            messages=messages,
        )
        # The installed SDK has no typed `output_config` kwarg, so it rides
        # along in extra_body; the REST API accepts it (verified 2026-09-02).
        # Crucially, an explicit `thinking` block SUPPRESSES effort-driven
        # reasoning -- opus-5 returns 0 thinking tokens at effort=max when
        # `thinking` is sent, and 154 when it is omitted. So when an effort
        # level is requested we let the model's own adaptive thinking govern.
        native_effort = resolve_effort("claude", effort)
        if native_effort:
            kwargs["extra_body"] = {"output_config": {"effort": native_effort}}
        else:
            kwargs["thinking"] = ({"type": "adaptive"} if enable_thinking
                                  else {"type": "disabled"})

        t0 = time.perf_counter()
        response = None
        for _ in range(4):
            try:
                response = self.client.messages.create(**kwargs)
                break
            except BadRequestError as e:
                msg = str(e).lower()
                stripped = False
                if "effort" in msg and "extra_body" in kwargs:
                    kwargs.pop("extra_body")
                    stripped = True
                elif "temperature" in msg and "temperature" in kwargs:
                    kwargs.pop("temperature")
                    stripped = True
                elif "thinking" in msg and "thinking" in kwargs:
                    kwargs.pop("thinking")
                    stripped = True
                if not stripped:
                    raise
        if response is None:
            raise RuntimeError("Claude request failed after parameter stripping")
        latency = time.perf_counter() - t0

        u = response.usage
        details = getattr(u, "output_tokens_details", None) if u else None
        # Anthropic reports input_tokens EXCLUDING cached reads and cache
        # writes, whereas OpenAI and Gemini fold cached tokens into their input
        # total. Normalise to "total billable input" here so the scorer can
        # apply one uniform formula across providers.
        cache_read = getattr(u, "cache_read_input_tokens", 0) if u else 0
        cache_write = getattr(u, "cache_creation_input_tokens", 0) if u else 0
        total_input = (u.input_tokens if u else 0) + (cache_read or 0) + (cache_write or 0)
        self._record_usage(
            total_input,
            u.output_tokens if u else 0,
            latency,
            cached_input_tokens=cache_read or 0,
            thinking_tokens=_detail(details, "thinking_tokens"),
        )

        # Newer models may return thinking blocks before the text block, so
        # return the first text block rather than assuming content[0]; default
        # to "" so an empty/thinking-only response never crashes the run.
        return next((b.text for b in response.content if b.type == "text"), "")


class GrokClient(LLMClient):
    """xAI Grok client (uses OpenAI-compatible API)"""

    def __init__(self, api_key=None, model="grok-beta"):
        super().__init__()
        self.client = OpenAI(
            api_key=api_key or os.getenv("XAI_API_KEY"),
            base_url="https://api.x.ai/v1",
            max_retries=5, timeout=300.0
        )
        self.model = model

    def generate(self, system_prompt, user_message=None, conversation_history=None,
                 temperature=0.7, max_tokens=2000, response_format=None,
                 enable_thinking=False, effort=None):

        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(self._messages_from(conversation_history, user_message))

        # Call API (enable_thinking is a Claude-only concept, ignored here)
        kwargs = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens
        }

        if response_format == "json":
            kwargs["response_format"] = {"type": "json_object"}

        native_effort = resolve_effort("grok", effort)
        if native_effort:
            kwargs["reasoning_effort"] = native_effort

        t0 = time.perf_counter()
        try:
            response = self.client.chat.completions.create(**kwargs)
        except OpenAIBadRequestError as e:
            # Fall back if this model rejects the effort level rather than
            # failing the whole batch.
            if "reasoning_effort" in str(e).lower() and "reasoning_effort" in kwargs:
                kwargs.pop("reasoning_effort")
                response = self.client.chat.completions.create(**kwargs)
            else:
                raise
        latency = time.perf_counter() - t0

        u = response.usage
        details = getattr(u, "completion_tokens_details", None) if u else None
        self._record_usage(
            u.prompt_tokens if u else 0,
            u.completion_tokens if u else 0,
            latency,
            thinking_tokens=_detail(details, "reasoning_tokens"),
        )

        return response.choices[0].message.content


class GPTClient(LLMClient):
    """OpenAI GPT client (Responses API).

    GPT-5.x reasoning models reject both `max_tokens` and any temperature other
    than the default, and only the Responses API accepts effort="max" -- Chat
    Completions 400s on it. All three verified live 2026-09-02.
    """

    def __init__(self, api_key=None, model="gpt-4"):
        super().__init__()
        self.client = OpenAI(api_key=api_key or os.getenv("OPENAI_API_KEY"),
                             max_retries=5, timeout=300.0)
        self.model = model

    def generate(self, system_prompt, user_message=None, conversation_history=None,
                 temperature=0.7, max_tokens=2000, response_format=None,
                 enable_thinking=False, effort=None):

        messages = self._messages_from(conversation_history, user_message)

        kwargs = {
            "model": self.model,
            "instructions": system_prompt,
            "input": messages,
            "max_output_tokens": max_tokens,
        }

        if response_format == "json":
            # The API requires the literal word "json" somewhere in the input
            # messages (it does not scan `instructions`), so make sure it's there.
            kwargs["text"] = {"format": {"type": "json_object"}}
            if not any("json" in str(m.get("content", "")).lower() for m in messages):
                messages = list(messages)
                messages[-1] = dict(messages[-1])
                messages[-1]["content"] = f"{messages[-1].get('content', '')}\n\nRespond with json."
                kwargs["input"] = messages

        native_effort = resolve_effort("gpt", effort)
        if native_effort:
            kwargs["reasoning"] = {"effort": native_effort}

        t0 = time.perf_counter()
        try:
            response = self.client.responses.create(**kwargs)
        except OpenAIBadRequestError as e:
            if "effort" in str(e).lower() and "reasoning" in kwargs:
                kwargs.pop("reasoning")
                response = self.client.responses.create(**kwargs)
            else:
                raise
        latency = time.perf_counter() - t0

        u = response.usage
        in_details = getattr(u, "input_tokens_details", None) if u else None
        out_details = getattr(u, "output_tokens_details", None) if u else None
        self._record_usage(
            getattr(u, "input_tokens", 0) if u else 0,
            getattr(u, "output_tokens", 0) if u else 0,
            latency,
            cached_input_tokens=_detail(in_details, "cached_tokens"),
            thinking_tokens=_detail(out_details, "reasoning_tokens"),
        )

        # output_text is "" when the model spent its whole budget on reasoning;
        # that's a real outcome the orchestrator already handles, so don't raise.
        return response.output_text or ""


class GeminiClient(LLMClient):
    """Google Gemini client (native google-genai SDK).

    Deliberately NOT the OpenAI-compat shim: that endpoint never reports
    reasoning tokens (verified 2026-09-02 -- reasoning_tokens=None at every
    effort level) while the native SDK reports thoughts_token_count. Since
    thinking tokens bill as output, the shim under-reports Gemini's cost by
    roughly 2x, which would corrupt the headline cost comparison.
    """

    def __init__(self, api_key=None, model="gemini-2.5-flash"):
        super().__init__()
        from google import genai
        self.genai = genai
        from google.genai import types
        self.types = types
        self.client = genai.Client(api_key=api_key or os.getenv("GOOGLE_API_KEY"))
        self.model = model

    def generate(self, system_prompt, user_message=None, conversation_history=None,
                 temperature=0.7, max_tokens=2000, response_format=None,
                 enable_thinking=False, effort=None):

        types = self.types
        messages = self._messages_from(conversation_history, user_message)

        # Gemini calls the assistant role "model".
        contents = [
            types.Content(
                role="model" if m.get("role") == "assistant" else "user",
                parts=[types.Part(text=str(m.get("content", "")))],
            )
            for m in messages
        ]

        cfg = {
            "system_instruction": system_prompt,
            "max_output_tokens": max_tokens,
            "temperature": temperature,
        }
        if response_format == "json":
            cfg["response_mime_type"] = "application/json"

        native_effort = resolve_effort("gemini", effort)
        if native_effort:
            cfg["thinking_config"] = types.ThinkingConfig(thinking_level=native_effort)

        t0 = time.perf_counter()
        response = self.client.models.generate_content(
            model=self.model, contents=contents,
            config=types.GenerateContentConfig(**cfg),
        )
        latency = time.perf_counter() - t0

        um = getattr(response, "usage_metadata", None)
        thoughts = getattr(um, "thoughts_token_count", 0) if um else 0
        candidates = getattr(um, "candidates_token_count", 0) if um else 0
        self._record_usage(
            getattr(um, "prompt_token_count", 0) if um else 0,
            # Thinking tokens bill as output but are reported separately.
            (candidates or 0) + (thoughts or 0),
            latency,
            cached_input_tokens=getattr(um, "cached_content_token_count", 0) if um else 0,
            thinking_tokens=thoughts or 0,
        )

        return self._extract_text(response)

    @staticmethod
    def _extract_text(response):
        """response.text raises when a candidate has no text part (e.g. the
        budget went entirely to thinking), so pull parts defensively."""
        try:
            text = response.text
            if text:
                return text
        except Exception:
            pass
        for cand in (getattr(response, "candidates", None) or []):
            content = getattr(cand, "content", None)
            for part in (getattr(content, "parts", None) or []):
                if getattr(part, "text", None):
                    return part.text
        return ""


def get_llm_client(provider, model=None):
    """
    Factory function to get appropriate LLM client

    Args:
        provider: "claude", "grok", "gpt", or "gemini"
        model: Optional model override

    Returns:
        LLMClient instance
    """
    if provider.lower() == "claude":
        return ClaudeClient(model=model) if model else ClaudeClient()
    elif provider.lower() == "grok":
        return GrokClient(model=model) if model else GrokClient()
    elif provider.lower() == "gpt":
        return GPTClient(model=model) if model else GPTClient()
    elif provider.lower() in ("gemini", "google"):
        return GeminiClient(model=model) if model else GeminiClient()
    else:
        raise ValueError(f"Unknown provider: {provider}")
