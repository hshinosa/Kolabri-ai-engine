"""
Tests for Notification Service - 100% Coverage
"""
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from app.services.notification_service import NotificationService, get_notification_service


class TestNotificationService:
    """Test NotificationService class."""
    
    @pytest.fixture
    def notification_service(self):
        """Create notification service instance."""
        return NotificationService()

    @pytest.mark.asyncio
    async def test_send_intervention_uses_x_api_key(self, notification_service):
        """Test send_intervention sends the shared secret with X-API-Key."""
        with patch('app.services.notification_service.httpx.AsyncClient') as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 200
            post_mock = AsyncMock(return_value=mock_response)
            mock_client.return_value.__aenter__.return_value.post = post_mock

            await notification_service.send_intervention(
                group_id="group_1",
                message="Test intervention",
                intervention_type="silence",
            )

            headers = post_mock.call_args.kwargs["headers"]
            assert headers["X-API-Key"] == notification_service.secret
            assert "X-AI-Engine-Secret" not in headers
    
    @pytest.mark.asyncio
    async def test_send_with_retry_success(self, notification_service):
        """Test _send_with_retry on first attempt success."""
        with patch('app.services.notification_service.httpx.AsyncClient') as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_response)
            
            result = await notification_service._send_with_retry(
                url="http://test.com/webhook",
                payload={"test": "data"},
                headers={"Content-Type": "application/json"}
            )
            
            assert result is True
    
    @pytest.mark.asyncio
    async def test_send_with_retry_201_success(self, notification_service):
        """Test _send_with_retry with 201 status code."""
        with patch('app.services.notification_service.httpx.AsyncClient') as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 201
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_response)
            
            result = await notification_service._send_with_retry(
                url="http://test.com/webhook",
                payload={"test": "data"},
                headers={"Content-Type": "application/json"}
            )
            
            assert result is True
    
    @pytest.mark.asyncio
    async def test_send_with_retry_failure_then_success(self, notification_service):
        """Test _send_with_retry fails first then succeeds."""
        with patch('app.services.notification_service.httpx.AsyncClient') as mock_client:
            mock_response_fail = MagicMock()
            mock_response_fail.status_code = 500
            mock_response_success = MagicMock()
            mock_response_success.status_code = 200
            
            mock_post = AsyncMock(side_effect=[mock_response_fail, mock_response_success])
            mock_client.return_value.__aenter__.return_value.post = mock_post
            
            result = await notification_service._send_with_retry(
                url="http://test.com/webhook",
                payload={"test": "data"},
                headers={"Content-Type": "application/json"},
                max_retries=3
            )
            
            assert result is True
            assert mock_post.call_count == 2
    
    @pytest.mark.asyncio
    async def test_send_with_retry_all_failures(self, notification_service):
        """Test _send_with_retry all attempts fail."""
        with patch('app.services.notification_service.httpx.AsyncClient') as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 500
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_response)
            
            result = await notification_service._send_with_retry(
                url="http://test.com/webhook",
                payload={"test": "data"},
                headers={"Content-Type": "application/json"},
                max_retries=3
            )
            
            assert result is False
    
    @pytest.mark.asyncio
    async def test_send_with_retry_exception(self, notification_service):
        """Test _send_with_retry with exception."""
        with patch('app.services.notification_service.httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(side_effect=Exception("Connection error"))
            
            result = await notification_service._send_with_retry(
                url="http://test.com/webhook",
                payload={"test": "data"},
                headers={"Content-Type": "application/json"},
                max_retries=2
            )
            
            assert result is False
    
    @pytest.mark.asyncio
    async def test_send_intervention_success(self, notification_service):
        """Test send_intervention successful."""
        with patch.object(notification_service, '_send_with_retry', return_value=True) as mock_send:
            result = await notification_service.send_intervention(
                group_id="group_1",
                message="Test intervention",
                intervention_type="redirect",
                metadata={"key": "value"}
            )
            
            assert result is True
            mock_send.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_send_intervention_failure(self, notification_service):
        """Test send_intervention failure."""
        with patch.object(notification_service, '_send_with_retry', return_value=False) as mock_send:
            result = await notification_service.send_intervention(
                group_id="group_1",
                message="Test intervention",
                intervention_type="silence"
            )
            
            assert result is False
    
    @pytest.mark.asyncio
    async def test_send_intervention_no_metadata(self, notification_service):
        """Test send_intervention with no metadata."""
        with patch.object(notification_service, '_send_with_retry', return_value=True) as mock_send:
            result = await notification_service.send_intervention(
                group_id="group_1",
                message="Test intervention",
                intervention_type="off_topic"
            )
            
            assert result is True
            # Verify metadata defaults to empty dict
            call_args = mock_send.call_args
            assert call_args[0][1]["metadata"] == {}
    
    @pytest.mark.asyncio
    async def test_notify_teacher_success(self, notification_service):
        """Test notify_teacher successful."""
        with patch.object(notification_service, '_send_with_retry', return_value=True) as mock_send:
            result = await notification_service.notify_teacher(
                course_id="course_1",
                group_id="group_1",
                alert_type="low_participation",
                message="Group has low participation",
                data={"threshold": 0.3}
            )
            
            assert result is True
    
    @pytest.mark.asyncio
    async def test_notify_teacher_no_data(self, notification_service):
        """Test notify_teacher with no data."""
        with patch.object(notification_service, '_send_with_retry', return_value=True) as mock_send:
            result = await notification_service.notify_teacher(
                course_id="course_1",
                group_id="group_1",
                alert_type="off_topic",
                message="Group is off-topic"
            )
            
            assert result is True
            # Verify data defaults to empty dict
            call_args = mock_send.call_args
            assert call_args[0][1]["data"] == {}
    
    @pytest.mark.asyncio
    async def test_notify_teacher_failure(self, notification_service):
        """Test notify_teacher failure."""
        with patch.object(notification_service, '_send_with_retry', return_value=False) as mock_send:
            result = await notification_service.notify_teacher(
                course_id="course_1",
                group_id="group_1",
                alert_type="silence",
                message="Group is silent"
            )
            
            assert result is False
    
    @pytest.mark.asyncio
    async def test_send_intervention_payload_structure(self, notification_service):
        """Test send_intervention creates correct payload structure."""
        captured_payload = None
        
        async def capture_payload(url, payload, headers, max_retries=3):
            nonlocal captured_payload
            captured_payload = payload
            return True
        
        with patch.object(notification_service, '_send_with_retry', side_effect=capture_payload):
            await notification_service.send_intervention(
                group_id="group_123",
                message="Test message",
                intervention_type="redirect",
                metadata={"test": "data"}
            )
            
            assert captured_payload is not None
            assert captured_payload["groupId"] == "group_123"
            assert captured_payload["message"] == "Test message"
            assert captured_payload["type"] == "redirect"
            assert captured_payload["metadata"] == {"test": "data"}
            assert "timestamp" in captured_payload
    
    @pytest.mark.asyncio
    async def test_notify_teacher_payload_structure(self, notification_service):
        """Test notify_teacher creates correct payload structure."""
        captured_payload = None
        
        async def capture_payload(url, payload, headers, max_retries=3):
            nonlocal captured_payload
            captured_payload = payload
            return True
        
        with patch.object(notification_service, '_send_with_retry', side_effect=capture_payload):
            await notification_service.notify_teacher(
                course_id="course_456",
                group_id="group_789",
                alert_type="low_quality",
                message="Low quality discussion",
                data={"score": 0.25}
            )
            
            assert captured_payload is not None
            assert captured_payload["courseId"] == "course_456"
            assert captured_payload["groupId"] == "group_789"
            assert captured_payload["type"] == "low_quality"
            assert captured_payload["message"] == "Low quality discussion"
            assert captured_payload["data"] == {"score": 0.25}


class TestGetNotificationService:
    """Test get_notification_service singleton."""
    
    def test_get_notification_service_singleton(self):
        """Test get_notification_service returns singleton."""
        # Clear singleton first
        from app.services import notification_service
        notification_service._notification_service = None
        
        service1 = get_notification_service()
        service2 = get_notification_service()
        
        assert service1 is service2
        assert isinstance(service1, NotificationService)
    
    def test_get_notification_service_initialization(self):
        """Test get_notification_service initializes correctly."""
        from app.services import notification_service
        notification_service._notification_service = None
        
        service = get_notification_service()
        
        assert service.base_url is not None
        assert service.secret is not None
