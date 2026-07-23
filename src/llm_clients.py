"""
LLM Client Wrappers
Provides unified interface for different LLM providers
"""
import os
import time
import threading
from anthropic import Anthropic, BadRequestError
from openai import OpenAI


class LLMClient:
    """Base class for LLM clients"""

    def __init__(self):
        # Cumulative token usage + per-call latency across all calls to this
        # client (thread-safe, so it's correct under the parallel runner).
        # NOTE: latency is wall-clock per generate() call, so it's only a true
        # response-time measure at --workers 1; higher concurrency inflates it.
        self.usage = {"input_tokens": 0, "output_tokens": 0, "calls": 0}
        self.latencies = []  # seconds per generate() call
        self._usage_lock = threading.Lock()

    def _record_usage(self, input_tokens, output_tokens, latency=None):
        with self._usage_lock:
            self.usage["input_tokens"] += int(input_tokens or 0)
            self.usage["output_tokens"] += int(output_tokens or 0)
            self.usage["calls"] += 1
            if latency is not None:
                self.latencies.append(round(latency, 3))

    def generate(self, system_prompt, user_message=None, conversation_history=None,
                 temperature=0.7, max_tokens=2000, response_format=None,
                 enable_thinking=False):
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

        Returns:
            String response from LLM
        """
        raise NotImplementedError


class ClaudeClient(LLMClient):
    """Anthropic Claude client"""
    
    def __init__(self, api_key=None, model="claude-sonnet-4-20250514"):
        super().__init__()
        self.client = Anthropic(api_key=api_key or os.getenv("ANTHROPIC_API_KEY"), max_retries=5)
        self.model = model
    
    def generate(self, system_prompt, user_message=None, conversation_history=None,
                 temperature=0.7, max_tokens=2000, response_format=None,
                 enable_thinking=False):

        # Build messages
        if conversation_history:
            messages = conversation_history
        elif user_message:
            messages = [{"role": "user", "content": user_message}]
        else:
            raise ValueError("Must provide either user_message or conversation_history")

        # Call API. enable_thinking selects adaptive thinking (for deliberate
        # roles like the referee, which has budget to spare) vs disabled (for
        # tight-budget roles like the role-play answer server, where thinking
        # blocks would consume the whole max_tokens and leave no text).
        # Newer models (Sonnet 5, etc.) also removed the temperature parameter
        # and 400 if it's sent; temperature/thinking are stripped and retried
        # if the model rejects them.
        kwargs = dict(
            model=self.model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system_prompt,
            messages=messages,
            thinking={"type": "adaptive"} if enable_thinking else {"type": "disabled"},
        )
        t0 = time.perf_counter()
        for _ in range(2):
            try:
                response = self.client.messages.create(**kwargs)
                break
            except BadRequestError as e:
                msg = str(e).lower()
                stripped = False
                if "temperature" in msg and "temperature" in kwargs:
                    kwargs.pop("temperature")
                    stripped = True
                if "thinking" in msg and "thinking" in kwargs:
                    kwargs.pop("thinking")
                    stripped = True
                if not stripped:
                    raise
        latency = time.perf_counter() - t0

        u = response.usage
        self._record_usage(u.input_tokens if u else 0, u.output_tokens if u else 0, latency)

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
            max_retries=5
        )
        self.model = model
    
    def generate(self, system_prompt, user_message=None, conversation_history=None,
                 temperature=0.7, max_tokens=2000, response_format=None,
                 enable_thinking=False):
        
        # Build messages
        messages = [{"role": "system", "content": system_prompt}]

        if conversation_history:
            messages.extend(conversation_history)
        elif user_message:
            messages.append({"role": "user", "content": user_message})
        else:
            raise ValueError("Must provide either user_message or conversation_history")

        # Call API (enable_thinking is a Claude-only concept, ignored here)
        kwargs = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens
        }

        if response_format == "json":
            kwargs["response_format"] = {"type": "json_object"}

        t0 = time.perf_counter()
        response = self.client.chat.completions.create(**kwargs)
        latency = time.perf_counter() - t0

        u = response.usage
        self._record_usage(u.prompt_tokens if u else 0, u.completion_tokens if u else 0, latency)

        return response.choices[0].message.content


class GPTClient(LLMClient):
    """OpenAI GPT client"""
    
    def __init__(self, api_key=None, model="gpt-4"):
        super().__init__()
        self.client = OpenAI(api_key=api_key or os.getenv("OPENAI_API_KEY"), max_retries=5)
        self.model = model
    
    def generate(self, system_prompt, user_message=None, conversation_history=None,
                 temperature=0.7, max_tokens=2000, response_format=None,
                 enable_thinking=False):
        
        # Build messages
        messages = [{"role": "system", "content": system_prompt}]
        
        if conversation_history:
            messages.extend(conversation_history)
        elif user_message:
            messages.append({"role": "user", "content": user_message})
        else:
            raise ValueError("Must provide either user_message or conversation_history")
        
        # Call API
        kwargs = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens
        }
        
        if response_format == "json":
            kwargs["response_format"] = {"type": "json_object"}
        
        t0 = time.perf_counter()
        response = self.client.chat.completions.create(**kwargs)
        latency = time.perf_counter() - t0

        u = response.usage
        self._record_usage(u.prompt_tokens if u else 0, u.completion_tokens if u else 0, latency)

        return response.choices[0].message.content


class GeminiClient(LLMClient):
    """Google Gemini client (uses OpenAI-compatible API)"""

    def __init__(self, api_key=None, model="gemini-2.5-flash"):
        super().__init__()
        self.client = OpenAI(
            api_key=api_key or os.getenv("GOOGLE_API_KEY"),
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
            max_retries=5
        )
        self.model = model

    def generate(self, system_prompt, user_message=None, conversation_history=None,
                 temperature=0.7, max_tokens=2000, response_format=None,
                 enable_thinking=False):

        # Build messages
        messages = [{"role": "system", "content": system_prompt}]

        if conversation_history:
            messages.extend(conversation_history)
        elif user_message:
            messages.append({"role": "user", "content": user_message})
        else:
            raise ValueError("Must provide either user_message or conversation_history")

        # Call API (enable_thinking is a Claude-only concept, ignored here)
        kwargs = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens
        }

        if response_format == "json":
            kwargs["response_format"] = {"type": "json_object"}

        t0 = time.perf_counter()
        response = self.client.chat.completions.create(**kwargs)
        latency = time.perf_counter() - t0

        u = response.usage
        self._record_usage(u.prompt_tokens if u else 0, u.completion_tokens if u else 0, latency)

        return response.choices[0].message.content


def get_llm_client(provider, model=None):
    """
    Factory function to get the right LLM client

    Args:
        provider: "claude", "grok", "gpt", or "gemini"
        model: Optional specific model name

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
