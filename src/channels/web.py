from datetime import datetime, timezone
from typing import Any

from src.channels.base import BaseChannel, NormalizedMessage


class WebChannel(BaseChannel):
    """Adapter para web chat.

    Payload esperado:
        { "session_id": "...", "message": "...", "user_id": "..." }
    """

    def parse(self, raw_payload: dict[str, Any]) -> NormalizedMessage:
        user_id = raw_payload["user_id"]
        session_id = raw_payload.get("session_id") or f"web_{user_id}"
        return NormalizedMessage(
            session_id=session_id,
            channel="web",
            user_text=raw_payload["message"].strip(),
            user_id=user_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            raw=raw_payload,
        )

    def format_response(self, text: str, session_id: str) -> dict[str, Any]:
        return {
            "session_id": session_id,
            "reply": text,
        }
