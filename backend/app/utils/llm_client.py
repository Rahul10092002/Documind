import logging
from abc import ABC, abstractmethod
from typing import Any
from langchain_groq import ChatGroq
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.language_models import BaseChatModel
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult

from app.config import settings

logger = logging.getLogger(__name__)


class TokenLoggingCallbackHandler(BaseCallbackHandler):
    def __init__(self, model_name: str):
        self.model_name = model_name

    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        try:
            for generations in response.generations:
                for generation in generations:
                    message = getattr(generation, "message", None)
                    if message:
                        ConfiguredLLMClient._log_tokens(message, label=self.model_name)
        except Exception as exc:
            logger.debug("TokenLoggingCallbackHandler failed: %s", exc)


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
    def get_structured_llm(self, schema: Any, include_raw: bool = False) -> Any:
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
                google_api_key=api_key,
                callbacks=[TokenLoggingCallbackHandler("gemini")]
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
                groq_api_key=settings.groq_api_key,
                callbacks=[TokenLoggingCallbackHandler("groq")]
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

    def get_structured_llm(self, schema: Any, include_raw: bool = False) -> Any:
        """Returns a structured LLM runnable configured with the given Pydantic schema or JSON schema,
        incorporating retry logic and fallback (if applicable).
        """
        provider = settings.llm_provider.lower()
        if provider == "gemini":
            # Primary is Gemini; retry is sufficient, no fallback needed.
            return self.get_fallback_llm().with_structured_output(schema, include_raw=include_raw).with_retry(stop_after_attempt=3)
        else:
            # Groq is primary
            primary_structured = self.get_primary_llm().with_structured_output(schema, include_raw=include_raw).with_retry(stop_after_attempt=3)
            if settings.enable_gemini_fallback:
                fallback_structured = self.get_fallback_llm().with_structured_output(schema, include_raw=include_raw).with_retry(stop_after_attempt=3)
                return primary_structured.with_fallbacks([fallback_structured])
            else:
                return primary_structured

    @staticmethod
    def _log_tokens(response: Any, label: str = "llm-call") -> None:
        """Log token usage from an ``AIMessage`` response.

        Handles Groq (``token_usage`` key) and Gemini (``usageMetadata`` key)
        shapes.  Silent on missing metadata so retries and fallbacks never
        cause log noise.
        """
        try:
            meta = getattr(response, "response_metadata", None) or {}

            # Groq / OpenAI-compatible
            usage = meta.get("token_usage") or meta.get("usage")
            if usage:
                logger.info(
                    "Token usage [%s]: prompt=%s  completion=%s  total=%s",
                    label,
                    usage.get("prompt_tokens",     usage.get("input_tokens",  "?")),
                    usage.get("completion_tokens", usage.get("output_tokens", "?")),
                    usage.get("total_tokens", "?"),
                )
                return

            # Gemini
            g = meta.get("usageMetadata")
            if g:
                logger.info(
                    "Token usage [%s]: prompt=%s  completion=%s  total=%s",
                    label,
                    g.get("promptTokenCount",     "?"),
                    g.get("candidatesTokenCount", "?"),
                    g.get("totalTokenCount",      "?"),
                )
                return

            logger.debug("Token usage [%s]: metadata unavailable.", label)
        except Exception as exc:
            logger.debug("_log_tokens failed silently: %s", exc)

    def ask(self, messages) -> str:
        """Invokes LLM with automatic retry logic for network or server errors,
        and fallback to Gemini if Groq rate limits are hit.
        """
        runnable = self.get_resilient_llm()
        response = runnable.invoke(messages)
        self._log_tokens(response, label="qa")
        return str(response.content).strip()

    async def aask(self, messages) -> str:
        """Invokes LLM asynchronously with automatic retry logic for network or server errors,
        and fallback to Gemini if Groq rate limits are hit.
        """
        runnable = self.get_resilient_llm()
        response = await runnable.ainvoke(messages)
        self._log_tokens(response, label="qa-async")
        return str(response.content).strip()


# Default client instance
default_llm_client = ConfiguredLLMClient()
