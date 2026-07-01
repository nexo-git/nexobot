"""Lambda handler principal de Nexo Chatbot.

Flujo POST:
  1. Detectar canal (web | whatsapp) por header X-Channel o campo "channel" en body
  2. Parsear payload → NormalizedMessage
  3. Recuperar historial de DynamoDB
  4. Rutear intent → OpenAI
  5. Persistir ambos turnos (user + assistant)
  6. Devolver respuesta formateada

Flujo GET (webhook WhatsApp):
  Meta verifica el webhook con un GET — respondemos con el hub.challenge.
"""

import json
import os
from typing import Any

import requests
from dotenv import load_dotenv

load_dotenv()

from src.ai.router import IntentRouter
from src.channels.base import NormalizedMessage, SkipWebhookEvent
from src.channels.web import WebChannel
from src.channels.whatsapp import WhatsAppChannel
from src.db.dynamo import ConversationStore
from src.utils.logger import get_logger

logger = get_logger(__name__)

_CHANNEL_MAP = {
    "web": WebChannel,
    "whatsapp": WhatsAppChannel,
}

# Instancias reutilizadas entre invocaciones (Lambda warm start)
_store = ConversationStore()
_router = IntentRouter()

_WHATSAPP_TOKEN = os.environ.get("WHATSAPP_ACCESS_TOKEN", "")
_WHATSAPP_PHONE_NUMBER_ID = os.environ.get("WHATSAPP_PHONE_NUMBER_ID", "")
_VERIFY_TOKEN = os.environ.get("WHATSAPP_VERIFY_TOKEN", "")
_OWNER_NUMBER = os.environ.get("OWNER_WHATSAPP_NUMBER", "")
_ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN", "")
_API_BASE_URL = os.environ.get("API_BASE_URL", "")

_ESCALATION_MARKER = "[ESCALAR]"


def _detect_channel(event: dict[str, Any]) -> str:
    headers = event.get("headers") or {}
    channel = (
        headers.get("x-channel")
        or headers.get("X-Channel")
        or (event.get("body_parsed") or {}).get("channel")
        or "web"
    )
    return channel.lower()


def _parse_body(event: dict[str, Any]) -> dict[str, Any]:
    body = event.get("body") or "{}"
    if isinstance(body, str):
        return json.loads(body)
    return body


def _ok(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(payload, ensure_ascii=False),
    }


def _plain(text: str) -> dict[str, Any]:
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "text/plain"},
        "body": text,
    }


def _error(message: str, status: int = 500) -> dict[str, Any]:
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps({"error": message}, ensure_ascii=False),
    }


def _send_whatsapp_reply(to: str, text: str) -> None:
    """Envía la respuesta de vuelta al usuario via WhatsApp Cloud API."""
    url = f"https://graph.facebook.com/v19.0/{_WHATSAPP_PHONE_NUMBER_ID}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": text},
    }
    headers = {
        "Authorization": f"Bearer {_WHATSAPP_TOKEN}",
        "Content-Type": "application/json; charset=utf-8",
    }
    try:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        resp = requests.post(url, data=body, headers=headers, timeout=10)
        if not resp.ok:
            logger.warning(f"Error enviando a WhatsApp: {resp.status_code} {resp.text}")
    except Exception as exc:
        logger.exception(f"Error en _send_whatsapp_reply: {exc}")


def _notify_owner(session_id: str, client_number: str, last_message: str) -> None:
    """Envía WhatsApp al dueño con links de pausa/reanudación cuando hay una escalación."""
    if not _OWNER_NUMBER or not _ADMIN_TOKEN or not _API_BASE_URL:
        logger.warning("Variables de notificación no configuradas, omitiendo aviso al dueño")
        return
    pause_url  = f"{_API_BASE_URL}/admin/handoff?action=pause&session={session_id}&token={_ADMIN_TOKEN}"
    resume_url = f"{_API_BASE_URL}/admin/handoff?action=resume&session={session_id}&token={_ADMIN_TOKEN}"
    text = (
        f"⚠️ *Escalación nexo bot*\n\n"
        f"👤 *Cliente:* {client_number}\n"
        f"💬 *Motivo:* \"{last_message[:120]}\"\n\n"
        f"⏸️ Pausar bot (para atender vos):\n{pause_url}\n\n"
        f"▶️ Reanudar bot (cuando terminés):\n{resume_url}"
    )
    _send_whatsapp_reply(_OWNER_NUMBER, text)


def _handle_admin_conversations(event: dict[str, Any]) -> dict[str, Any]:
    """Endpoint GET /admin/conversations[/{session_id}] — lista o detalla conversaciones."""
    params = event.get("queryStringParameters") or {}
    token  = params.get("token", "")

    if not _ADMIN_TOKEN or token != _ADMIN_TOKEN:
        return {"statusCode": 403, "headers": {"Content-Type": "application/json"}, "body": '{"error":"Acceso denegado"}'}

    raw_path = event.get("rawPath", "")
    parts = raw_path.rstrip("/").split("/")
    session_id = parts[-1] if parts[-1] != "conversations" else None

    if session_id:
        messages  = _store.get_full_history(session_id)
        human_mode = _store.get_human_mode(session_id)
        return _ok({"session_id": session_id, "human_mode": human_mode, "messages": messages})

    conversations = _store.list_all_sessions()
    return _ok({"conversations": conversations})


def _handle_admin_reply(event: dict[str, Any]) -> dict[str, Any]:
    """Endpoint POST /admin/reply — envía un mensaje como el negocio al cliente."""
    headers = event.get("headers") or {}
    auth    = headers.get("authorization") or headers.get("Authorization") or ""
    token   = auth.removeprefix("Bearer ").strip()

    if not _ADMIN_TOKEN or token != _ADMIN_TOKEN:
        return {"statusCode": 403, "headers": {"Content-Type": "application/json"}, "body": '{"error":"Acceso denegado"}'}

    body = _parse_body(event)
    session_id = body.get("session_id", "")
    message    = body.get("message", "").strip()

    if not session_id or not message:
        return _error("session_id y message son requeridos", 400)

    phone_number = session_id.removeprefix("whatsapp_")
    _send_whatsapp_reply(phone_number, message)
    _store.save_turn(session_id, "assistant", message)

    return _ok({"ok": True})


def _handle_admin_handoff(event: dict[str, Any]) -> dict[str, Any]:
    """Endpoint GET /admin/handoff — pausa o reanuda el bot para una sesión específica."""
    params = event.get("queryStringParameters") or {}
    action  = params.get("action", "")
    session = params.get("session", "")
    token   = params.get("token", "")

    if not _ADMIN_TOKEN or token != _ADMIN_TOKEN or action not in ("pause", "resume") or not session:
        return {"statusCode": 403, "headers": {"Content-Type": "text/plain"}, "body": "Acceso denegado"}

    human_mode = (action == "pause")
    _store.set_human_mode(session, human_mode)

    if not human_mode:
        client_number = session.removeprefix("whatsapp_")
        closing_msg = "¡Esperamos haberte ayudado! 😊 El asistente virtual de *nexo* queda de nuevo a tu disposición por cualquier consulta."
        _send_whatsapp_reply(client_number, closing_msg)
        _store.save_turn(session, "assistant", closing_msg)

    emoji  = "⏸️" if human_mode else "▶️"
    estado = "PAUSADO" if human_mode else "REANUDADO"
    numero = session.removeprefix("whatsapp_")
    html = (
        f"<html><body style='font-family:sans-serif;text-align:center;padding:40px;max-width:400px;margin:auto'>"
        f"<h2>{emoji} Bot {estado}</h2>"
        f"<p style='color:#666'>Cliente: <strong>+{numero}</strong></p>"
        f"<p style='font-size:14px;color:#999'>nexo bot · {'Atendé al cliente y tocá Reanudar cuando terminés.' if human_mode else 'El bot retomará la conversación.'}</p>"
        f"</body></html>"
    )
    return {"statusCode": 200, "headers": {"Content-Type": "text/html"}, "body": html}


def _handle_webhook_verification(event: dict[str, Any]) -> dict[str, Any]:
    """Meta verifica el webhook con un GET — devolvemos el challenge."""
    params = event.get("queryStringParameters") or {}
    mode = params.get("hub.mode")
    token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge")

    if mode == "subscribe" and token == _VERIFY_TOKEN:
        logger.info("Webhook de WhatsApp verificado")
        return _plain(challenge)

    return _error("Verificación fallida", 403)


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    method   = event.get("requestContext", {}).get("http", {}).get("method", "POST")
    raw_path = event.get("rawPath", "")

    if "/admin/conversations" in raw_path:
        return _handle_admin_conversations(event)
    if raw_path.endswith("/admin/reply") and method == "POST":
        return _handle_admin_reply(event)
    if raw_path.endswith("/admin/handoff"):
        return _handle_admin_handoff(event)

    # Verificación del webhook de WhatsApp
    if method == "GET":
        return _handle_webhook_verification(event)

    try:
        body = _parse_body(event)
        event["body_parsed"] = body

        # Detectar si es un webhook de WhatsApp por su estructura
        is_whatsapp = "entry" in body and "object" in body
        channel_name = "whatsapp" if is_whatsapp else _detect_channel(event)

        channel_cls = _CHANNEL_MAP.get(channel_name)
        if channel_cls is None:
            return _error(f"Canal desconocido: {channel_name}", 400)

        channel = channel_cls()
        try:
            msg: NormalizedMessage = channel.parse(body)
        except SkipWebhookEvent:
            return _ok({"status": "ok"})

        logger.info(
            "Mensaje recibido",
            extra={"session_id": msg.session_id, "channel": msg.channel},
        )

        # Si la sesión está en modo humano, el bot se mantiene silencioso
        if _store.get_human_mode(msg.session_id):
            logger.info("Sesión en modo humano, guardando turno", extra={"session_id": msg.session_id})
            _store.save_turn(msg.session_id, "user", msg.user_text)
            return _ok({"status": "human_mode"})

        history = _store.get_history(msg.session_id)
        reply = _router.route(msg.session_id, msg.user_text, history)

        # Detectar marcador de escalación y removerlo antes de enviarlo al cliente
        needs_escalation = reply.startswith(_ESCALATION_MARKER)
        if needs_escalation:
            reply = reply[len(_ESCALATION_MARKER):].lstrip()
            logger.info("Escalación detectada", extra={"session_id": msg.session_id})

        _store.save_turn(msg.session_id, "user", msg.user_text)
        _store.save_turn(msg.session_id, "assistant", reply)

        if needs_escalation:
            _notify_owner(msg.session_id, msg.user_id, msg.user_text)

        # WhatsApp requiere enviar la respuesta activamente via API
        if channel_name == "whatsapp":
            _send_whatsapp_reply(msg.user_id, reply)
            return _ok({"status": "ok"})

        return _ok(channel.format_response(reply, msg.session_id))

    except Exception as exc:
        logger.exception(f"Error: {exc}")
        return _error("internal")
