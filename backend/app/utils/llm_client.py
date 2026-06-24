import logging
from abc import ABC, abstractmethod
from typing import Any
from langchain_groq import ChatGroq
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.language_models import BaseChatModel

from app.config import settings

logger = logging.getLogger(__name__)


class LLMClientInterface(ABC):
    @abstractmethod
    def get_primary_llm(self) -> BaseChatModel:
        pass

    @abstractmethod
    def get_fallback_llm(self) -> BaseChatModel:
        pass

    @abstractmethod
    def ask(self, messages) -> str:
        pass

    @abstractmethod
    async def aask(self, messages) -> str:
        pass

    @abstractmethod
    def get_structured_llm(self, schema: Any) -> Any:
        pass


class ConfiguredLLMClient(LLMClientInterface):
    def __init__(self):
        self._llm = None
        self._gemini_llm = None
        self._resilient_llm = None

    def get_fallback_llm(self) -> ChatGoogleGenerativeAI:
        """Returns a cached ChatGoogleGenerativeAI instance, configured via settings."""
        if self._gemini_llm is None:
            api_key = settings.effective_google_api_key
            if not api_key:
                logger.error("Neither GOOGLE_API_KEY nor GEMINI_API_KEY environment variable is set.")
                raise ValueError("Google API key is not configured in the environment.")
            
            logger.info("Initializing ChatGoogleGenerativeAI client with model: %s", settings.gemini_model)
            self._gemini_llm = ChatGoogleGenerativeAI(
                model=settings.gemini_model,
                temperature=settings.temperature,
                google_api_key=api_key
            )
        return self._gemini_llm

    def get_primary_llm(self) -> BaseChatModel:
        """Returns the primary cached LLM instance based on LLM_PROVIDER ('groq' or 'gemini')."""
        provider = settings.llm_provider.lower()
        if provider == "gemini":
            return self.get_fallback_llm()

        if self._llm is None:
            if not settings.groq_api_key:
                logger.error("GROQ_API_KEY environment variable is not set.")
                raise ValueError("GROQ_API_KEY is not configured in the environment.")

            logger.info("Initializing ChatGroq client with model: %s", settings.llm_model)
            self._llm = ChatGroq(
                model=settings.llm_model,
                temperature=settings.temperature,
                groq_api_key=settings.groq_api_key
            )
        return self._llm

    def get_resilient_llm(self) -> BaseChatModel:
        """Returns a resilient LLM runnable configured with retry and optional fallback."""
        if self._resilient_llm is None:
            provider = settings.llm_provider.lower()
            if provider == "gemini":
                # Primary is Gemini; retry is sufficient, no fallback needed.
                self._resilient_llm = self.get_fallback_llm().with_retry(stop_after_attempt=3)
            else:
                # Groq is primary
                primary_runnable = self.get_primary_llm().with_retry(stop_after_attempt=3)
                if settings.enable_gemini_fallback:
                    fallback_runnable = self.get_fallback_llm().with_retry(stop_after_attempt=3)
                    self._resilient_llm = primary_runnable.with_fallbacks([fallback_runnable])
                else:
                    self._resilient_llm = primary_runnable
        return self._resilient_llm

    def get_structured_llm(self, schema: Any) -> Any:
        """Returns a structured LLM runnable configured with the given Pydantic schema or JSON schema,
        incorporating retry logic and fallback (if applicable).
        """
        provider = settings.llm_provider.lower()
        if provider == "gemini":
            # Primary is Gemini; retry is sufficient, no fallback needed.
            return self.get_fallback_llm().with_structured_output(schema).with_retry(stop_after_attempt=3)
        else:
            # Groq is primary
            primary_structured = self.get_primary_llm().with_structured_output(schema).with_retry(stop_after_attempt=3)
            if settings.enable_gemini_fallback:
                fallback_structured = self.get_fallback_llm().with_structured_output(schema).with_retry(stop_after_attempt=3)
                return primary_structured.with_fallbacks([fallback_structured])
            else:
                return primary_structured

    def ask(self, messages) -> str:
        """Invokes LLM with automatic retry logic for network or server errors,
        and fallback to Gemini if Groq rate limits are hit.
        """
        runnable = self.get_resilient_llm()
        response = runnable.invoke(messages)
        return str(response.content).strip()

    async def aask(self, messages) -> str:
        """Invokes LLM asynchronously with automatic retry logic for network or server errors,
        and fallback to Gemini if Groq rate limits are hit.
        """
        runnable = self.get_resilient_llm()
        response = await runnable.ainvoke(messages)
        return str(response.content).strip()


# Default client instance
default_llm_client = ConfiguredLLMClient()
