from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


class SkipWebhookEvent(Exception):
    """El webhook recibido no contiene un mensaje de usuario (ej: delivery receipt)."""


@dataclass
class NormalizedMessage:
    session_id: str
    channel: str
    user_text: str
    user_id: str
    timestamp: str
    raw: dict[str, Any] = field(default_factory=dict)


class BaseChannel(ABC):
    @abstractmethod
    def parse(self, raw_payload: dict[str, Any]) -> NormalizedMessage:
        """Convierte el payload crudo del canal a un NormalizedMessage."""

    @abstractmethod
    def format_response(self, text: str, session_id: str) -> dict[str, Any]:
        """Convierte la respuesta de texto al formato que espera el canal."""
