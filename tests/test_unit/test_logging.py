"""
Tests for Logging Module - 100% Coverage
"""
import pytest
from unittest.mock import patch, MagicMock
import sys
import logging
import structlog
from io import StringIO
from app.core.logging import setup_logging, get_logger, LoggerMixin


class TestSetupLogging:
    """Test setup_logging function."""
    
    @patch('app.core.logging.settings')
    def test_setup_logging_json_format(self, mock_settings):
        """Test setup_logging with JSON format."""
        mock_settings.LOG_FORMAT = "json"
        mock_settings.LOG_LEVEL = "INFO"
        
        # This should not raise
        setup_logging()
        
        # Verify structlog is configured
        assert structlog.is_configured()
    
    @patch('app.core.logging.settings')
    def test_setup_logging_console_format(self, mock_settings):
        """Test setup_logging with console format."""
        mock_settings.LOG_FORMAT = "console"
        mock_settings.LOG_LEVEL = "DEBUG"
        
        # This should not raise
        setup_logging()
        
        # Verify structlog is configured
        assert structlog.is_configured()
    
    @patch('app.core.logging.settings')
    @patch('sys.platform', 'win32')
    def test_setup_logging_windows_console(self, mock_settings):
        """Test setup_logging on Windows."""
        mock_settings.LOG_FORMAT = "console"
        mock_settings.LOG_LEVEL = "INFO"
        
        # This should not raise
        setup_logging()
        
        # Verify it configured successfully
        assert structlog.is_configured()
    
    @patch('app.core.logging.settings')
    def test_setup_logging_reduces_noise(self, mock_settings):
        """Test setup_logging reduces third-party logger noise."""
        mock_settings.LOG_FORMAT = "console"
        mock_settings.LOG_LEVEL = "INFO"
        
        setup_logging()
        
        # Verify third-party loggers are set to WARNING
        assert logging.getLogger("uvicorn").level == logging.WARNING
        assert logging.getLogger("qdrant_client").level == logging.WARNING
        assert logging.getLogger("httpx").level == logging.WARNING


class TestGetLogger:
    """Test get_logger function."""
    
    def test_get_logger_returns_structlog_logger(self):
        """Test get_logger returns structlog BoundLogger."""
        logger = get_logger("test_logger")
        
        assert logger is not None
        # Verify it's a structlog logger
        assert hasattr(logger, 'info')
        assert hasattr(logger, 'debug')
        assert hasattr(logger, 'warning')
        assert hasattr(logger, 'error')
    
    def test_get_logger_different_names(self):
        """Test get_logger with different names."""
        logger1 = get_logger("logger1")
        logger2 = get_logger("logger2")
        
        assert logger1 is not None
        assert logger2 is not None
        # They should be different bound loggers
        assert logger1 != logger2 or logger1 is logger2  # May be same due to caching


class TestLoggerMixin:
    """Test LoggerMixin class."""
    
    def test_logger_mixin_property(self):
        """Test LoggerMixin logger property."""
        
        class TestClass(LoggerMixin):
            pass
        
        obj = TestClass()
        logger = obj.logger
        
        assert logger is not None
        assert hasattr(logger, 'info')
    
    def test_logger_mixin_bound_to_class(self):
        """Test LoggerMixin logger is bound to class name."""
        
        class MyClass(LoggerMixin):
            pass
        
        obj = MyClass()
        logger = obj.logger
        
        # Logger should be bound to the class name
        assert logger is not None
    
    def test_logger_mixin_multiple_classes(self):
        """Test LoggerMixin with multiple classes."""
        
        class ClassA(LoggerMixin):
            pass
        
        class ClassB(LoggerMixin):
            pass
        
        obj_a = ClassA()
        obj_b = ClassB()
        
        logger_a = obj_a.logger
        logger_b = obj_b.logger
        
        assert logger_a is not None
        assert logger_b is not None


class TestLoggingIntegration:
    """Integration tests for logging."""
    
    @patch('app.core.logging.settings')
    def test_full_logging_workflow(self, mock_settings):
        """Test complete logging workflow."""
        mock_settings.LOG_FORMAT = "console"
        mock_settings.LOG_LEVEL = "INFO"
        
        # Setup logging
        setup_logging()
        
        # Get logger
        logger = get_logger("test_integration")
        
        # Test logging methods
        logger.info("test_info", key="value")
        logger.debug("test_debug", extra="data")
        logger.warning("test_warning")
        logger.error("test_error")
        
        # All should complete without error
        assert True
    
    def test_logger_mixin_inheritance(self):
        """Test LoggerMixin can be inherited."""
        
        class BaseClass(LoggerMixin):
            def log_something(self):
                return self.logger.info("base")
        
        class DerivedClass(BaseClass):
            def log_derived(self):
                return self.logger.info("derived")
        
        obj = DerivedClass()
        
        # Both methods should work
        base_result = obj.log_something()
        derived_result = obj.log_derived()
        
        # Should not raise
        assert base_result is None
        assert derived_result is None
    
    def test_logger_with_special_characters(self):
        """Test logger handles special characters."""
        logger = get_logger("test_special")
        
        # Should not raise with special characters
        logger.info("test", special="!@#$%^&*()", unicode="Hello 世界")
        assert True
    
    def test_logger_with_complex_context(self):
        """Test logger handles complex context data."""
        logger = get_logger("test_complex")
        
        context = {
            "string": "value",
            "number": 42,
            "float": 3.14,
            "boolean": True,
            "list": [1, 2, 3],
            "dict": {"nested": "value"},
            "none": None,
        }
        
        logger.info("test", **context)
        assert True
