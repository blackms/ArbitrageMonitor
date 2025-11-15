"""Tests for logging configuration"""

import logging

import structlog

from src.utils.logging import get_logger, setup_logging


def test_setup_logging_default():
    """Test logging setup with default level"""
    setup_logging()
    logger = get_logger("test")

    # Logger should be a structlog logger (proxy or bound)
    assert hasattr(logger, 'info')
    assert hasattr(logger, 'error')


def test_setup_logging_custom_level():
    """Test logging setup with custom level"""
    setup_logging(log_level="DEBUG")
    logger = get_logger("test")

    # Logger should be a structlog logger (proxy or bound)
    assert hasattr(logger, 'info')
    assert hasattr(logger, 'error')


def test_get_logger_with_name():
    """Test getting logger with name"""
    setup_logging()
    logger = get_logger("test_module")

    # Logger should be a structlog logger (proxy or bound)
    assert hasattr(logger, 'info')
    assert hasattr(logger, 'error')


def test_get_logger_without_name():
    """Test getting logger without name"""
    setup_logging()
    logger = get_logger()

    # Logger should be a structlog logger (proxy or bound)
    assert hasattr(logger, 'info')
    assert hasattr(logger, 'error')


def test_logger_can_log_messages():
    """Test that logger can log messages with context"""
    setup_logging(log_level="INFO")
    logger = get_logger("test")

    # These should not raise exceptions
    logger.info("test_message", key="value", number=42)
    logger.warning("warning_message", chain="BSC")
    logger.error("error_message", error="test_error")
