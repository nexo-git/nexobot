from unittest.mock import MagicMock, patch

from src.ai.router import IntentRouter


class TestIntentRouter:
    @patch("src.ai.router.OpenAIClient")
    def test_routes_to_openai(self, mock_openai_cls):
        mock_openai = MagicMock()
        mock_openai.chat.return_value = "Respuesta OpenAI"
        mock_openai_cls.return_value = mock_openai

        router = IntentRouter()
        result = router.route("ses1", "¿Cuánto cuesta un envío?", [])

        mock_openai.chat.assert_called_once_with([], "¿Cuánto cuesta un envío?")
        assert result == "Respuesta OpenAI"

    @patch("src.ai.router.OpenAIClient")
    def test_routes_complex_also_to_openai(self, mock_openai_cls):
        mock_openai = MagicMock()
        mock_openai.chat.return_value = "Respuesta para queja"
        mock_openai_cls.return_value = mock_openai

        router = IntentRouter()
        result = router.route("ses1", "Tengo una queja, mi paquete está perdido", [])

        mock_openai.chat.assert_called_once()
        assert result == "Respuesta para queja"
