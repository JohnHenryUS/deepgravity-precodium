from abc import ABC, abstractmethod
from typing import List, Dict, Any, Tuple, Optional, Generator

class BaseLLMProvider(ABC):
    """
    Abstract Base Class for LLM Providers in the DeepGravity ecosystem.
    Defines the contract for interacting with local (Ollama) or cloud (Deepseek, OpenAI) models.
    """

    @abstractmethod
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the provider with a configuration dictionary.
        """
        self.config = config

    @abstractmethod
    def generate_response(
        self, 
        messages: List[Dict[str, str]], 
        tools: Optional[List[Dict[str, Any]]] = None
    ) -> Tuple[Optional[str], Optional[List[Dict[str, Any]]], Optional[str]]:
        """
        Send a list of messages to the model (with optional tool schemas) and return
        the generated text response, any tool calls, and any reasoning content.
        
        Returns:
            Tuple[text_content, list_of_tool_calls, reasoning_content]
        """
        pass

    @abstractmethod
    def generate_stream(
        self, 
        messages: List[Dict[str, str]], 
        tools: Optional[List[Dict[str, Any]]] = None
    ) -> Generator[Dict[str, Any], None, None]:
        """
        Send a list of messages and yield stream chunks for real-time console or UI output.
        """
        pass
