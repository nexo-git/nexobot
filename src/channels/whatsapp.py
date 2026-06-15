from datetime import datetime, timezone
from typing import Any

from src.channels.base import BaseChannel, NormalizedMessage, SkipWebhookEvent
from src.utils.logger import get_logger

logger = get_logger(__name__)


class WhatsAppChannel(BaseChannel):
    """Adapter para WhatsApp Business API Cloud.

    Parsea el payload webhook de Meta:
        entry[0].changes[0].value.messages[0]
    """

    def parse(self, raw_payload: dict[str, Any]) -> NormalizedMessage:
        try:
            entry = raw_payload["entry"][0]
            change = entry["changes"][0]["value"]
            if "messages" not in change:
                raise SkipWebhookEvent("status update, not a message")
            message = change["messages"][0]
            wa_id: str = message["from"]
            text: str = message.get("text", {}).get("body", "").strip()
            ts = message.get("timestamp", "")
        except SkipWebhookEvent:
            raise
        except (KeyError, IndexError) as exc:
            raise ValueError(f"Payload de WhatsApp inválido: {exc}") from exc

        session_id = f"whatsapp_{wa_id}"
        return NormalizedMessage(
            session_id=session_id,
            channel="whatsapp",
            user_text=text,
            user_id=wa_id,
            timestamp=ts or datetime.now(timezone.utc).isoformat(),
            raw=raw_payload,
        )

    def format_response(self, text: str, session_id: str) -> dict[str, Any]:
        # El envío real se hace llamando a la API de Meta por separado.
        # Este método devuelve el payload listo para esa llamada.
        wa_id = session_id.removeprefix("whatsapp_")
        return {
            "messaging_product": "whatsapp",
            "to": wa_id,
            "type": "text",
            "text": {"body": text},
        }
