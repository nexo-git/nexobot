import os

import google.generativeai as genai

from src.utils.logger import get_logger

logger = get_logger(__name__)

_SYSTEM_PROMPT = """Eres el asistente virtual de Nexo Shipping, especializado en resolver
situaciones complejas: quejas, reclamos, paquetes perdidos o dañados, retenciones en
aduana y escaladas a agentes humanos.

Información clave:
- Empresa de envíos USA ↔ Costa Rica con bodega en Miami.
- Tiempo de tránsito: 7 a 14 días hábiles.
- Para pérdidas o daños: solicitar número de tracking y fotos de evidencia.
- Casos de aduana: coordinar directamente con el agente aduanal de Nexo.
- Escaladas humanas: proporcionar correo soporte@nexoshipping.com o WhatsApp directo.

Responde en español con empatía, claridad y orientación concreta. Reconoce el problema
del cliente antes de ofrecer soluciones."""


class GeminiClient:
    def __init__(self) -> None:
        genai.configure(api_key=os.environ["GEMINI_API_KEY"])
        self._model = genai.GenerativeModel(
            model_name="gemini-1.5-flash",
            system_instruction=_SYSTEM_PROMPT,
        )

    def chat(self, history: list[dict[str, str]], user_text: str) -> str:
        # Convierte el historial al formato de Gemini
        gemini_history = [
            {"role": turn["role"], "parts": [turn["content"]]}
            for turn in history
            if turn["role"] in ("user", "model")
        ]
        # Gemini usa "model" en lugar de "assistant"
        for turn in gemini_history:
            if turn["role"] == "assistant":
                turn["role"] = "model"

        chat_session = self._model.start_chat(history=gemini_history)
        response = chat_session.send_message(user_text)
        reply = response.text or ""
        logger.info("Gemini respondió", extra={"chars": len(reply)})
        return reply.strip()
