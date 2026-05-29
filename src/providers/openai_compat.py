import os
from typing import List, Dict, Any, Tuple, Optional, Generator
from openai import OpenAI
from src.providers.base import BaseLLMProvider

class OpenAICompatProvider(BaseLLMProvider):
    """
    Universal OpenAI-compatible LLM client.
    Handles DeepSeek, Ollama, Groq, and standard OpenAI endpoints.
    """

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.base_url = config.get("base_url")
        self.model_name = config.get("model")
        self.temperature = config.get("temperature", 0.2)
        self.max_tokens = config.get("max_tokens")
        self.preserve_keys = set(config.get("preserve_keys", []))

        # Resolve API Key
        api_key = config.get("api_key")
        if not api_key:
            env_var = config.get("api_key_env_var")
            if env_var:
                api_key = os.environ.get(env_var)
        
        # Fallback to empty string (useful for local Ollama which doesn't require keys)
        if not api_key:
            api_key = "local-no-key"

        timeout = config.get("timeout", 60.0)
        self.client = OpenAI(
            base_url=self.base_url,
            api_key=api_key,
            timeout=timeout
        )

    def generate_response(
        self, 
        messages: List[Dict[str, str]], 
        tools: Optional[List[Dict[str, Any]]] = None
    ) -> Tuple[Optional[str], Optional[List[Dict[str, Any]]]]:
        """
        Executes a blocking chat completion request, translating tool calling outputs.
        """
        # Standardize and sanitize messages to standard OpenAI parameters
        sanitized_messages = []
        last_assistant_had_tool_calls = False
        last_tool_call_ids = set()
        
        allowed_keys = {"role", "content", "name", "tool_calls", "tool_call_id"}.union(self.preserve_keys)
        
        for msg in messages:
            # Build clean dictionary with only valid keys and non-None custom keys
            msg_copy = {}
            for k in allowed_keys:
                if k in msg:
                    if k in {"role", "content", "name", "tool_calls", "tool_call_id"}:
                        msg_copy[k] = msg[k]
                    elif msg[k] is not None:
                        msg_copy[k] = msg[k]
            role = msg_copy.get("role")
            
            if role == "assistant":
                content = msg_copy.get("content")
                has_content = content is not None and str(content).strip() != ""
                raw_tool_calls = msg_copy.get("tool_calls")
                has_tools = isinstance(raw_tool_calls, list) and len(raw_tool_calls) > 0
                
                if not has_content and not has_tools:
                    # Strip empty assistant messages
                    continue
                
                # Track tool_call state for subsequent orphan detection
                last_assistant_had_tool_calls = has_tools
                last_tool_call_ids = {tc.get("id") for tc in raw_tool_calls if tc.get("id")} if has_tools else set()
                
                sanitized_messages.append(msg_copy)
            
            elif role == "tool":
                tc_id = msg_copy.get("tool_call_id")
                if last_assistant_had_tool_calls and tc_id in last_tool_call_ids:
                    sanitized_messages.append(msg_copy)
                # else: strip orphaned tool message
            
            else:
                sanitized_messages.append(msg_copy)

        kwargs = {
            "model": self.model_name,
            "messages": sanitized_messages,
            "temperature": self.temperature
        }
        if self.max_tokens:
            kwargs["max_tokens"] = self.max_tokens
        if tools:
            kwargs["tools"] = tools

        # Provider workaround: some backends require extra fields.
        # The provider config can include an "extra_body" map if needed.
        extra = self.config.get("extra_body", {})
        if extra:
            kwargs["extra_body"] = extra

        try:
            response = self.client.chat.completions.create(**kwargs)
        except Exception as e:
            if "Unsupported value: 'temperature'" in str(e) or "temperature" in str(e).lower() and "support" in str(e).lower():
                kwargs.pop("temperature", None)
                response = self.client.chat.completions.create(**kwargs)
            else:
                raise e
        
        try:
            message = response.choices[0].message
            
            tool_calls = None
            if message.tool_calls:
                tool_calls = []
                for tool_call in message.tool_calls:
                    tool_calls.append({
                        "id": tool_call.id,
                        "type": tool_call.type,
                        "function": {
                            "name": tool_call.function.name,
                            "arguments": tool_call.function.arguments
                        }
                    })

            # Capture reasoning_content for thinking models (DeepSeek, etc.)
            reasoning_content = None
            if hasattr(message, "reasoning_content") and message.reasoning_content:
                reasoning_content = message.reasoning_content

            return message.content, tool_calls, reasoning_content

        except Exception as e:
            raise RuntimeError(f"Error during OpenAI API response generation: {e}")

    def generate_stream(
        self, 
        messages: List[Dict[str, str]], 
        tools: Optional[List[Dict[str, Any]]] = None
    ) -> Generator[Dict[str, Any], None, None]:
        """
        Streams chat completions chunk-by-chunk for live UI updates.
        """
        # Standardize and sanitize messages to standard OpenAI parameters
        sanitized_messages = []
        last_assistant_had_tool_calls = False
        last_tool_call_ids = set()
        
        allowed_keys = {"role", "content", "name", "tool_calls", "tool_call_id"}.union(self.preserve_keys)
        
        for msg in messages:
            # Build clean dictionary with only valid keys and non-None custom keys
            msg_copy = {}
            for k in allowed_keys:
                if k in msg:
                    if k in {"role", "content", "name", "tool_calls", "tool_call_id"}:
                        msg_copy[k] = msg[k]
                    elif msg[k] is not None:
                        msg_copy[k] = msg[k]
            role = msg_copy.get("role")
            
            if role == "assistant":
                content = msg_copy.get("content")
                has_content = content is not None and str(content).strip() != ""
                raw_tool_calls = msg_copy.get("tool_calls")
                has_tools = isinstance(raw_tool_calls, list) and len(raw_tool_calls) > 0
                
                if not has_content and not has_tools:
                    # Strip empty assistant messages
                    continue
                
                # Track tool_call state for subsequent orphan detection
                last_assistant_had_tool_calls = has_tools
                last_tool_call_ids = {tc.get("id") for tc in raw_tool_calls if tc.get("id")} if has_tools else set()
                
                sanitized_messages.append(msg_copy)
            
            elif role == "tool":
                tc_id = msg_copy.get("tool_call_id")
                if last_assistant_had_tool_calls and tc_id in last_tool_call_ids:
                    sanitized_messages.append(msg_copy)
                # else: strip orphaned tool message
            
            else:
                sanitized_messages.append(msg_copy)

        kwargs = {
            "model": self.model_name,
            "messages": sanitized_messages,
            "temperature": self.temperature,
            "stream": True
        }
        if self.max_tokens:
            kwargs["max_tokens"] = self.max_tokens
        if tools:
            kwargs["tools"] = tools

        # Provider workaround: some backends require extra fields.
        # The provider config can include an "extra_body" map if needed.
        extra = self.config.get("extra_body", {})
        if extra:
            kwargs["extra_body"] = extra

        try:
            stream = self.client.chat.completions.create(**kwargs)
        except Exception as e:
            if "Unsupported value: 'temperature'" in str(e) or "temperature" in str(e).lower() and "support" in str(e).lower():
                kwargs.pop("temperature", None)
                stream = self.client.chat.completions.create(**kwargs)
            else:
                raise e
                
        try:
            for chunk in stream:
                if not chunk.choices:
                    continue
                choice = chunk.choices[0]
                delta = choice.delta
                
                # Format chunk details
                result = {
                    "content": delta.content if hasattr(delta, "content") else None,
                    "reasoning_content": None,
                    "tool_calls": None
                }
                
                # Capture reasoning_content for thinking/reasoning models (DeepSeek, etc.)
                if hasattr(delta, "reasoning_content") and delta.reasoning_content:
                    result["reasoning_content"] = delta.reasoning_content
                
                if hasattr(delta, "tool_calls") and delta.tool_calls:
                    result["tool_calls"] = delta.tool_calls
                    
                yield result

                # Proactive socket release: break immediately if model signals completion
                if hasattr(choice, "finish_reason") and choice.finish_reason is not None:
                    break

        except Exception as e:
            raise RuntimeError(f"Error in API stream: {e}")
