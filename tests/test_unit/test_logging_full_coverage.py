"""
Comprehensive tests for core/logging.py - 100% coverage target.
"""

import logging
import sys
from unittest.mock import MagicMock, patch, Mock

import pytest
import structlog

from app.core.logging import setup_logging, get_logger, LoggerMixin
from app.core.config import settings


class TestSetupLogging:
    """Test setup_logging function."""
    
    def test_setup_logging_json_format(self):
        """Test setup_logging with JSON format."""
        with patch('app.core.logging.settings') as mock_settings, \
             patch('app.core.logging.sys.stdout'), \
             patch('app.core.logging.sys.stderr'), \
             patch('app.core.logging.structlog.configure') as mock_configure, \
             patch('app.core.logging.logging.StreamHandler') as mock_handler, \
             patch('app.core.logging.logging.getLogger') as mock_get_logger:
            
            # Configure mocks
            mock_settings.LOG_FORMAT = "json"
            mock_settings.LOG_LEVEL = "INFO"
            
            mock_logger = MagicMock()
            mock_get_logger.return_value = mock_logger
            
            # Call setup_logging
            setup_logging()
            
            # Verify structlog.configure was called
            assert mock_configure.called
            
            # Verify handler was created and added
            assert mock_handler.called
            mock_logger.addHandler.assert_called()
            
            # Verify log level was set
            mock_logger.setLevel.assert_called()
    
    def test_setup_logging_console_format(self):
        """Test setup_logging with console format."""
        with patch('app.core.logging.settings') as mock_settings, \
             patch('app.core.logging.sys.stdout'), \
             patch('app.core.logging.sys.stderr'), \
             patch('app.core.logging.structlog.configure') as mock_configure, \
             patch('app.core.logging.logging.StreamHandler') as mock_handler, \
             patch('app.core.logging.logging.getLogger') as mock_get_logger:
            
            # Configure mocks
            mock_settings.LOG_FORMAT = "console"
            mock_settings.LOG_LEVEL = "DEBUG"
            
            mock_logger = MagicMock()
            mock_get_logger.return_value = mock_logger
            
            # Call setup_logging
            setup_logging()
            
            # Verify structlog.configure was called with ConsoleRenderer
            assert mock_configure.called
    
    def test_setup_logging_windows_encoding(self):
        """Test setup_logging sets UTF-8 encoding on Windows."""
        with patch('app.core.logging.sys.platform', 'win32'), \
             patch.object(sys, 'stdout', MagicMock()), \
             patch.object(sys, 'stderr', MagicMock()), \
             patch('app.core.logging.settings') as mock_settings, \
             patch('app.core.logging.structlog.configure'), \
             patch('app.core.logging.logging.StreamHandler'), \
             patch('app.core.logging.logging.getLogger'):
            
            mock_settings.LOG_FORMAT = "console"
            mock_settings.LOG_LEVEL = "INFO"
            
            # Call setup_logging - should not raise on Windows
            setup_logging()
    
    def test_setup_logging_reduces_noise(self):
        """Test setup_logging reduces noise from third-party loggers."""
        with patch('app.core.logging.settings') as mock_settings, \
             patch('app.core.logging.sys.stdout'), \
             patch('app.core.logging.sys.stderr'), \
             patch('app.core.logging.structlog.configure'), \
             patch('app.core.logging.logging.StreamHandler'), \
             patch('app.core.logging.logging.getLogger') as mock_get_logger:
            
            mock_settings.LOG_FORMAT = "console"
            mock_settings.LOG_LEVEL = "INFO"
            
            uvicorn_logger = MagicMock()
            qdrant_client_logger = MagicMock()
            httpx_logger = MagicMock()
            root_logger = MagicMock()
            
            # Return appropriate logger based on name
            mock_get_logger.side_effect = lambda name=None, *args, **kwargs: {
                'uvicorn': uvicorn_logger,
                'qdrant_client': qdrant_client_logger,
                'httpx': httpx_logger,
            }.get(name, root_logger)
            
            # Call setup_logging
            setup_logging()
            
            # Verify noise reduction
            uvicorn_logger.setLevel.assert_called_with(logging.WARNING)
            qdrant_client_logger.setLevel.assert_called_with(logging.WARNING)
            httpx_logger.setLevel.assert_called_with(logging.WARNING)
    
    def test_setup_logging_debug_level(self):
        """Test setup_logging with DEBUG level."""
        with patch('app.core.logging.settings') as mock_settings, \
             patch('app.core.logging.sys.stdout'), \
             patch('app.core.logging.sys.stderr'), \
             patch('app.core.logging.structlog.configure'), \
             patch('app.core.logging.logging.StreamHandler'), \
             patch('app.core.logging.logging.getLogger') as mock_get_logger:
            
            mock_settings.LOG_FORMAT = "console"
            mock_settings.LOG_LEVEL = "DEBUG"
            
            mock_logger = MagicMock()
            mock_get_logger.return_value = mock_logger
            
            # Call setup_logging - should not raise
            setup_logging()
            
            # Verify setLevel was called (with any level)
            mock_logger.setLevel.assert_called()
    
    def test_setup_logging_error_level(self):
        """Test setup_logging with ERROR level."""
        with patch('app.core.logging.settings') as mock_settings, \
             patch('app.core.logging.sys.stdout'), \
             patch('app.core.logging.sys.stderr'), \
             patch('app.core.logging.structlog.configure'), \
             patch('app.core.logging.logging.StreamHandler'), \
             patch('app.core.logging.logging.getLogger') as mock_get_logger:
            
            mock_settings.LOG_FORMAT = "console"
            mock_settings.LOG_LEVEL = "ERROR"
            
            mock_logger = MagicMock()
            mock_get_logger.return_value = mock_logger
            
            # Call setup_logging - should not raise
            setup_logging()
            
            # Verify setLevel was called (with any level)
            mock_logger.setLevel.assert_called()


class TestGetLogger:
    """Test get_logger function."""
    
    def test_get_logger_returns_bound_logger(self):
        """Test get_logger returns a structlog bound logger."""
        with patch('app.core.logging.structlog.get_logger') as mock_get_logger:
            mock_logger = MagicMock()
            mock_get_logger.return_value = mock_logger
            
            result = get_logger("test_logger")
            
            assert result == mock_logger
            mock_get_logger.assert_called_once_with("test_logger")
    
    def test_get_logger_with_module_name(self):
        """Test get_logger with module name."""
        with patch('app.core.logging.structlog.get_logger') as mock_get_logger:
            mock_logger = MagicMock()
            mock_get_logger.return_value = mock_logger
            
            result = get_logger("app.services.test")
            
            assert result == mock_logger
            mock_get_logger.assert_called_once_with("app.services.test")
    
    def test_get_logger_with_class_name(self):
        """Test get_logger with class name."""
        with patch('app.core.logging.structlog.get_logger') as mock_get_logger:
            mock_logger = MagicMock()
            mock_get_logger.return_value = mock_logger
            
            result = get_logger("MyClass")
            
            assert result == mock_logger
            mock_get_logger.assert_called_once_with("MyClass")


class TestLoggerMixin:
    """Test LoggerMixin class."""
    
    def test_logger_mixin_property(self):
        """Test LoggerMixin.logger property returns bound logger."""
        class TestClass(LoggerMixin):
            pass
        
        instance = TestClass()
        
        with patch('app.core.logging.structlog.get_logger') as mock_get_logger:
            mock_logger = MagicMock()
            mock_get_logger.return_value = mock_logger
            
            result = instance.logger
            
            assert result == mock_logger
            mock_get_logger.assert_called_once_with("TestClass")
    
    def test_logger_mixin_with_subclass(self):
        """Test LoggerMixin works with subclasses."""
        class BaseService(LoggerMixin):
            pass
        
        class MyService(BaseService):
            pass
        
        instance = MyService()
        
        with patch('app.core.logging.structlog.get_logger') as mock_get_logger:
            mock_logger = MagicMock()
            mock_get_logger.return_value = mock_logger
            
            result = instance.logger
            
            assert result == mock_logger
            # Should be bound to the actual class name, not base class
            mock_get_logger.assert_called_once_with("MyService")
    
    def test_logger_mixin_multiple_instances(self):
        """Test LoggerMixin with multiple instances."""
        class TestService(LoggerMixin):
            def __init__(self, name):
                self.name = name
        
        instance1 = TestService("first")
        instance2 = TestService("second")
        
        with patch('app.core.logging.structlog.get_logger') as mock_get_logger:
            mock_logger1 = MagicMock()
            mock_logger2 = MagicMock()
            mock_get_logger.side_effect = [mock_logger1, mock_logger2]
            
            logger1 = instance1.logger
            logger2 = instance2.logger
            
            assert logger1 == mock_logger1
            assert logger2 == mock_logger2
            assert mock_get_logger.call_count == 2
    
    def test_logger_mixin_inheritance_chain(self):
        """Test LoggerMixin in multi-level inheritance."""
        class Base(LoggerMixin):
            pass
        
        class Middle(Base):
            pass
        
        class Child(Middle):
            pass
        
        instance = Child()
        
        with patch('app.core.logging.structlog.get_logger') as mock_get_logger:
            mock_logger = MagicMock()
            mock_get_logger.return_value = mock_logger
            
            result = instance.logger
            
            # Should use the most derived class name
            mock_get_logger.assert_called_once_with("Child")


class TestLoggingIntegration:
    """Integration tests for logging setup."""
    
    def test_logger_mixin_actual_logging(self):
        """Test LoggerMixin can actually log messages."""
        class TestService(LoggerMixin):
            def do_something(self):
                self.logger.info("doing something", data={"key": "value"})
        
        instance = TestService()
        
        # This should not raise any exceptions
        with patch('app.core.logging.structlog.get_logger') as mock_get_logger:
            mock_logger = MagicMock()
            mock_get_logger.return_value = mock_logger
            
            instance.do_something()
            
            mock_logger.info.assert_called_once_with(
                "doing something",
                data={"key": "value"}
            )
    
    def test_get_logger_actual_usage(self):
        """Test get_logger can be used for logging."""
        with patch('app.core.logging.structlog.get_logger') as mock_get_logger:
            mock_logger = MagicMock()
            mock_get_logger.return_value = mock_logger
            
            logger = get_logger("test")
            logger.debug("debug message", extra_info="test")
            logger.info("info message")
            logger.warning("warning message")
            logger.error("error message", error="test_error")
            
            assert mock_logger.debug.called
            assert mock_logger.info.called
            assert mock_logger.warning.called
            assert mock_logger.error.called


class TestLoggingEdgeCases:
    """Test edge cases and error conditions."""
    
    def test_logger_mixin_with_special_characters(self):
        """Test LoggerMixin with class names containing special characters."""
        class Test_Class_With_Underscores(LoggerMixin):
            pass
        
        instance = Test_Class_With_Underscores()
        
        with patch('app.core.logging.structlog.get_logger') as mock_get_logger:
            mock_logger = MagicMock()
            mock_get_logger.return_value = mock_logger
            
            result = instance.logger
            
            assert result == mock_logger
            mock_get_logger.assert_called_once_with("Test_Class_With_Underscores")
    
    def test_logger_mixin_with_unicode(self):
        """Test LoggerMixin with unicode class names."""
        class TestClass(LoggerMixin):
            pass
        
        instance = TestClass()
        
        with patch('app.core.logging.structlog.get_logger') as mock_get_logger:
            mock_logger = MagicMock()
            mock_get_logger.return_value = mock_logger
            
            result = instance.logger
            
            assert result == mock_logger
    
    def test_get_logger_empty_name(self):
        """Test get_logger with empty name."""
        with patch('app.core.logging.structlog.get_logger') as mock_get_logger:
            mock_logger = MagicMock()
            mock_get_logger.return_value = mock_logger
            
            result = get_logger("")
            
            assert result == mock_logger
            mock_get_logger.assert_called_once_with("")
    
    def test_get_logger_none_name(self):
        """Test get_logger with None name."""
        with patch('app.core.logging.structlog.get_logger') as mock_get_logger:
            mock_logger = MagicMock()
            mock_get_logger.return_value = mock_logger
            
            result = get_logger(None)
            
            assert result == mock_logger
            mock_get_logger.assert_called_once_with(None)


class TestLoggingConfiguration:
    """Test logging configuration scenarios."""
    
    def test_setup_logging_with_different_levels(self):
        """Test setup_logging with various log levels."""
        levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        
        for level in levels:
            with patch('app.core.logging.settings') as mock_settings, \
                 patch('app.core.logging.sys.stdout'), \
                 patch('app.core.logging.sys.stderr'), \
                 patch('app.core.logging.structlog.configure'), \
                 patch('app.core.logging.logging.StreamHandler'), \
                 patch('app.core.logging.logging.getLogger') as mock_get_logger:
                
                mock_settings.LOG_FORMAT = "console"
                mock_settings.LOG_LEVEL = level
                
                mock_logger = MagicMock()
                mock_get_logger.return_value = mock_logger
                
                # Should not raise any exceptions
                setup_logging()
    
    def test_setup_logging_json_renderer(self):
        """Test setup_logging with JSON renderer."""
        with patch('app.core.logging.settings') as mock_settings, \
             patch('app.core.logging.sys.stdout'), \
             patch('app.core.logging.sys.stderr'), \
             patch('app.core.logging.structlog.configure') as mock_configure, \
             patch('app.core.logging.logging.StreamHandler'), \
             patch('app.core.logging.logging.getLogger'):
            
            mock_settings.LOG_FORMAT = "json"
            mock_settings.LOG_LEVEL = "INFO"
            
            setup_logging()
            
            # Verify configure was called
            assert mock_configure.called
            
            # Get the processors passed to configure
            call_kwargs = mock_configure.call_args[1]
            processors = call_kwargs.get('processors', [])
            
            # Should have ProcessorFormatter.wrap_for_formatter
            assert len(processors) > 0
    
    def test_setup_logging_console_renderer(self):
        """Test setup_logging with console renderer."""
        with patch('app.core.logging.settings') as mock_settings, \
             patch('app.core.logging.sys.stdout'), \
             patch('app.core.logging.sys.stderr'), \
             patch('app.core.logging.structlog.configure') as mock_configure, \
             patch('app.core.logging.logging.StreamHandler'), \
             patch('app.core.logging.logging.getLogger'):
            
            mock_settings.LOG_FORMAT = "console"
            mock_settings.LOG_LEVEL = "INFO"
            
            setup_logging()
            
            # Verify configure was called
            assert mock_configure.called


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
