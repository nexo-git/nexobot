from unittest.mock import MagicMock, patch

import pytest


@patch("src.db.dynamo.boto3")
def test_get_history_returns_messages(mock_boto3):
    from src.db.dynamo import ConversationStore

    mock_table = MagicMock()
    mock_table.query.return_value = {
        "Items": [
            {"session_id": "ses1", "sk": "1#a", "role": "user", "content": "Hola"},
            {"session_id": "ses1", "sk": "2#b", "role": "assistant", "content": "Hola, bienvenido"},
        ]
    }
    mock_boto3.resource.return_value.Table.return_value = mock_table

    with patch.dict("os.environ", {"DYNAMODB_TABLE_NAME": "test-table", "AWS_REGION": "us-east-1"}):
        store = ConversationStore()
        history = store.get_history("ses1")

    assert len(history) == 2
    assert history[0]["role"] == "user"
    assert history[1]["role"] == "assistant"


@patch("src.db.dynamo.boto3")
def test_save_turn_calls_put_item(mock_boto3):
    from src.db.dynamo import ConversationStore

    mock_table = MagicMock()
    mock_boto3.resource.return_value.Table.return_value = mock_table

    with patch.dict("os.environ", {"DYNAMODB_TABLE_NAME": "test-table", "AWS_REGION": "us-east-1"}):
        store = ConversationStore()
        store.save_turn("ses1", "user", "Hola")

    mock_table.put_item.assert_called_once()
    call_args = mock_table.put_item.call_args[1]["Item"]
    assert call_args["session_id"] == "ses1"
    assert call_args["role"] == "user"
    assert call_args["content"] == "Hola"
    assert "expires_at" in call_args
