from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_gigachat.chat_models import GigaChat
from pydantic import BaseModel

from src.api.config import GigaChatSettings
from src.api.services.audiance.ai_utils import message_to_text
from src.api.services.errors import AIEnhancementError


JSON_SYSTEM_PROMPT = (
    "Ты возвращаешь только JSON без markdown и пояснений. "
    "Любой текст вне JSON запрещен. Все текстовые поля должны быть на русском."
)

PLAIN_SYSTEM_PROMPT = (
    "Ты отвечаешь кратко, по-русски, без markdown, дисклеймеров и вводных фраз. "
    "Верни только полезный текст ответа."
)

STRUCTURED_SYSTEM_PROMPT = (
    "Возвращай данные строго в указанной структуре. "
    "Все текстовые поля должны быть на русском, если входные данные на русском."
)


class GigaChatLLMClient:
    def __init__(self, settings: GigaChatSettings):
        credentials = settings.resolved_credentials
        if not credentials:
            raise AIEnhancementError("GigaChat credentials are not configured")

        self._llm = GigaChat(
            credentials=credentials.lstrip("="),
            scope=settings.scope,
            model=settings.model,
            base_url=settings.normalized_base_url,
            auth_url=settings.auth_url,
            verify_ssl_certs=settings.verify_ssl_certs,
            temperature=0.05,
            profanity_check=False,
        )

    def chat_json(self, prompt: str) -> str:
        response = self._llm.invoke(
            [
                SystemMessage(content=JSON_SYSTEM_PROMPT),
                HumanMessage(content=prompt),
            ]
        )
        return message_to_text(response.content)

    def chat_plain(self, prompt: str) -> str:
        response = self._llm.invoke(
            [
                SystemMessage(content=PLAIN_SYSTEM_PROMPT),
                HumanMessage(content=prompt),
            ]
        )
        return message_to_text(response.content)

    def chat_structured(self, prompt: str, schema: type[BaseModel]) -> BaseModel:
        structured_llm = self._llm.with_structured_output(schema, method="format_instructions")
        return structured_llm.invoke(
            [
                SystemMessage(content=STRUCTURED_SYSTEM_PROMPT),
                HumanMessage(content=prompt),
            ]
        )
