import pytest
from src.channels.web import WebChannel
from src.channels.whatsapp import WhatsAppChannel


class TestWebChannel:
    def test_parse_basic(self):
        ch = WebChannel()
        payload = {"user_id": "u1", "message": "Hola", "session_id": "ses1"}
        msg = ch.parse(payload)
        assert msg.channel == "web"
        assert msg.user_text == "Hola"
        assert msg.session_id == "ses1"
        assert msg.user_id == "u1"

    def test_parse_generates_session_id(self):
        ch = WebChannel()
        payload = {"user_id": "u2", "message": "Test"}
        msg = ch.parse(payload)
        assert msg.session_id == "web_u2"

    def test_format_response(self):
        ch = WebChannel()
        result = ch.format_response("Hola, soy Nexo", "ses1")
        assert result["session_id"] == "ses1"
        assert result["reply"] == "Hola, soy Nexo"


class TestWhatsAppChannel:
    def _make_payload(self, wa_id: str, text: str) -> dict:
        return {
            "entry": [{
                "changes": [{
                    "value": {
                        "messages": [{
                            "from": wa_id,
                            "text": {"body": text},
                            "timestamp": "1700000000",
                        }]
                    }
                }]
            }]
        }

    def test_parse_basic(self):
        ch = WhatsAppChannel()
        payload = self._make_payload("50688887777", "¿Cuánto cuesta un envío?")
        msg = ch.parse(payload)
        assert msg.channel == "whatsapp"
        assert msg.session_id == "whatsapp_50688887777"
        assert msg.user_text == "¿Cuánto cuesta un envío?"

    def test_parse_invalid_raises(self):
        ch = WhatsAppChannel()
        with pytest.raises(ValueError):
            ch.parse({"bad": "payload"})

    def test_format_response(self):
        ch = WhatsAppChannel()
        result = ch.format_response("¡Hola!", "whatsapp_50688887777")
        assert result["to"] == "50688887777"
        assert result["text"]["body"] == "¡Hola!"
        assert result["messaging_product"] == "whatsapp"
