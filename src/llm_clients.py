"""
LLM Client Wrappers
Provides unified interface for different LLM providers
"""
import os
from anthropic import Anthropic
from openai import OpenAI


class LLMClient:
    """Base class for LLM clients"""
    
    def generate(self, system_prompt, user_message=None, conversation_history=None, 
                 temperature=0.7, max_tokens=2000, response_format=None):
        """
        Generate a response from the LLM
        
        Args:
            system_prompt: System instructions
            user_message: Single user message (optional if conversation_history provided)
            conversation_history: List of messages (optional)
            temperature: 0.0-1.0
            max_tokens: Max response length
            response_format: "json" for JSON responses
        
        Returns:
            String response from LLM
        """
        raise NotImplementedError


class ClaudeClient(LLMClient):
    """Anthropic Claude client"""
    
    def __init__(self, api_key=None, model="claude-sonnet-4-20250514"):
        self.client = Anthropic(api_key=api_key or os.getenv("ANTHROPIC_API_KEY"))
        self.model = model
    
    def generate(self, system_prompt, user_message=None, conversation_history=None,
                 temperature=0.7, max_tokens=2000, response_format=None):
        
        # Build messages
        if conversation_history:
            messages = conversation_history
        elif user_message:
            messages = [{"role": "user", "content": user_message}]
        else:
            raise ValueError("Must provide either user_message or conversation_history")
        
        # Call API
        response = self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system_prompt,
            messages=messages
        )
        
        return response.content[0].text


class GrokClient(LLMClient):
    """xAI Grok client (uses OpenAI-compatible API)"""
    
    def __init__(self, api_key=None, model="grok-beta"):
        self.client = OpenAI(
            api_key=api_key or os.getenv("XAI_API_KEY"),
            base_url="https://api.x.ai/v1"
        )
        self.model = model
    
    def generate(self, system_prompt, user_message=None, conversation_history=None,
                 temperature=0.7, max_tokens=2000, response_format=None):
        
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
        
        response = self.client.chat.completions.create(**kwargs)
        
        return response.choices[0].message.content


class GPTClient(LLMClient):
    """OpenAI GPT client"""
    
    def __init__(self, api_key=None, model="gpt-4"):
        self.client = OpenAI(api_key=api_key or os.getenv("OPENAI_API_KEY"))
        self.model = model
    
    def generate(self, system_prompt, user_message=None, conversation_history=None,
                 temperature=0.7, max_tokens=2000, response_format=None):
        
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
        
        response = self.client.chat.completions.create(**kwargs)
        
        return response.choices[0].message.content


def get_llm_client(provider, model=None):
    """
    Factory function to get the right LLM client
    
    Args:
        provider: "claude", "grok", or "gpt"
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
    else:
        raise ValueError(f"Unknown provider: {provider}")
