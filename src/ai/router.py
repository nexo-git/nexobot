from src.ai.openai_client import OpenAIClient
from src.utils.logger import get_logger

logger = get_logger(__name__)


class IntentRouter:
    def __init__(self) -> None:
        self._openai = OpenAIClient()

    def route(
        self,
        session_id: str,
        user_text: str,
        history: list[dict[str, str]],
    ) -> str:
        logger.info("Enviando a OpenAI", extra={"session_id": session_id})
        return self._openai.chat(history, user_text)
