import os
import time
import uuid
from typing import Any

import boto3
from boto3.dynamodb.conditions import Key

from src.utils.logger import get_logger

logger = get_logger(__name__)

_MAX_HISTORY_TURNS = 10
_TTL_SECONDS = 86400        # 24 horas (historial)
_METADATA_TTL = 7 * 86400  # 7 días (flags de sesión)


class ConversationStore:
    def __init__(self) -> None:
        region = os.environ.get("AWS_REGION", "us-east-1")
        self._table_name = os.environ["DYNAMODB_TABLE_NAME"]
        self._table = boto3.resource("dynamodb", region_name=region).Table(
            self._table_name
        )

    def get_history(self, session_id: str) -> list[dict[str, str]]:
        """Retorna los últimos N turnos de conversación en formato messages de OpenAI."""
        response = self._table.query(
            KeyConditionExpression=Key("session_id").eq(session_id),
            ScanIndexForward=False,
            Limit=_MAX_HISTORY_TURNS,
        )
        items: list[dict[str, Any]] = response.get("Items", [])
        items.reverse()
        return [{"role": item["role"], "content": item["content"]} for item in items if "role" in item]

    def save_turn(self, session_id: str, role: str, content: str) -> None:
        """Persiste un turno de conversación con TTL de 24 h."""
        now = int(time.time())
        sk = f"{now}#{uuid.uuid4().hex}"
        self._table.put_item(
            Item={
                "session_id": session_id,
                "sk": sk,
                "role": role,
                "content": content,
                "expires_at": now + _TTL_SECONDS,
            }
        )
        logger.debug("Turno guardado", extra={"session_id": session_id})

    def get_human_mode(self, session_id: str) -> bool:
        """Retorna True si la sesión está en modo humano (bot silenciado)."""
        response = self._table.get_item(
            Key={"session_id": session_id, "sk": "METADATA"}
        )
        return response.get("Item", {}).get("human_mode", False)

    def set_human_mode(self, session_id: str, human_mode: bool) -> None:
        """Activa o desactiva el modo humano para una sesión específica."""
        self._table.put_item(
            Item={
                "session_id": session_id,
                "sk": "METADATA",
                "human_mode": human_mode,
                "expires_at": int(time.time()) + _METADATA_TTL,
            }
        )
        logger.info(
            "human_mode actualizado",
            extra={"session_id": session_id, "human_mode": human_mode},
        )
