import pytest
from unittest.mock import MagicMock, patch
from httpx import Response
from src.client import BalatroClient, BalatroAPIError

@patch("httpx.Client.post")
def test_health_success(mock_post):
    client = BalatroClient(base_url="http://localhost:12346")
    
    # Mock post response
    mock_response = MagicMock(spec=Response)
    mock_response.status_code = 200
    mock_response.json.return_value = {"jsonrpc": "2.0", "result": {"status": "ok"}, "id": 1}
    mock_post.return_value = mock_response
    
    response = client.health()
    assert response == {"status": "ok"}
    mock_post.assert_called_once()
    
    # Check that it sent correct JSON payload
    called_args, called_kwargs = mock_post.call_args
    assert called_kwargs["json"] == {"jsonrpc": "2.0", "method": "health", "params": {}, "id": 1}

@patch("httpx.Client.post")
def test_api_error_handling(mock_post):
    client = BalatroClient(base_url="http://localhost:12346")
    
    # Mock error response
    mock_response = MagicMock(spec=Response)
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "jsonrpc": "2.0",
        "error": {"code": -32001, "message": "Invalid state", "data": "Cannot use in MENU"},
        "id": 1
    }
    mock_post.return_value = mock_response
    
    with pytest.raises(BalatroAPIError) as exc_info:
        client.gamestate()
        
    assert exc_info.value.code == -32001
    assert "Invalid state" in exc_info.value.message
