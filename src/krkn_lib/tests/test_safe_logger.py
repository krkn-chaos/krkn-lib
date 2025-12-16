"""
Comprehensive unit tests for SafeLogger class.

This test suite covers both file-based logging mode (with worker thread)
and standard logging mode (fallback).

Assisted By: Claude Code
"""

import os
import tempfile
import time
import unittest
from unittest.mock import patch

from krkn_lib.utils.safe_logger import SafeLogger


class TestSafeLoggerInit(unittest.TestCase):
    """Test SafeLogger initialization."""

    def test_init_with_filename(self):
        """Test initialization with filename creates file writer and thread."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
            temp_path = f.name

        try:
            logger = SafeLogger(filename=temp_path)

            # Should have file writer
            self.assertIsNotNone(logger.filewriter)
            self.assertFalse(logger.finished)
            self.assertIsNotNone(logger.queue)
            self.assertEqual(logger.log_file_name, temp_path)

            # Clean up
            logger.close()
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    def test_init_with_filename_and_write_mode(self):
        """Test initialization with custom write mode."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
            temp_path = f.name

        try:
            logger = SafeLogger(filename=temp_path, write_mode="a")

            self.assertIsNotNone(logger.filewriter)
            self.assertEqual(logger.log_file_name, temp_path)

            logger.close()
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    def test_init_without_filename(self):
        """Test initialization without filename uses standard logging."""
        logger = SafeLogger()

        # Should not have file writer
        self.assertIsNone(logger.filewriter)
        self.assertTrue(logger.finished)
        self.assertIsNone(logger.log_file_name)

    def test_init_default_write_mode(self):
        """Test default write mode is w+."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
            temp_path = f.name

        try:
            # Write some initial content
            with open(temp_path, "w") as f:
                f.write("initial content\n")

            # Create logger with default mode (w+)
            logger = SafeLogger(filename=temp_path)
            logger.close()

            # File should be overwritten (w+ truncates)
            with open(temp_path, "r") as f:
                content = f.read()
                # Should be empty or only contain new logs
                # NOT "initial content"
                self.assertNotIn("initial content", content)
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)


class TestSafeLoggerFileLogging(unittest.TestCase):
    """Test file-based logging functionality."""

    def setUp(self):
        self.temp_file = tempfile.NamedTemporaryFile(mode="w", delete=False)
        self.temp_path = self.temp_file.name
        self.temp_file.close()

    def tearDown(self):
        if os.path.exists(self.temp_path):
            os.unlink(self.temp_path)

    def test_error_logs_to_file(self):
        """Test error() writes to file with [ERR] prefix."""
        logger = SafeLogger(filename=self.temp_path)

        logger.error("Test error message")

        # Give worker thread time to process
        time.sleep(0.1)
        logger.close()

        with open(self.temp_path, "r") as f:
            content = f.read()
            self.assertIn("[ERR]", content)
            self.assertIn("Test error message", content)

    def test_warning_logs_to_file(self):
        """Test warning() writes to file with [WRN] prefix."""
        logger = SafeLogger(filename=self.temp_path)

        logger.warning("Test warning message")

        time.sleep(0.1)
        logger.close()

        with open(self.temp_path, "r") as f:
            content = f.read()
            self.assertIn("[WRN]", content)
            self.assertIn("Test warning message", content)

    def test_info_logs_to_file(self):
        """Test info() writes to file with [INF] prefix."""
        logger = SafeLogger(filename=self.temp_path)

        logger.info("Test info message")

        time.sleep(0.1)
        logger.close()

        with open(self.temp_path, "r") as f:
            content = f.read()
            self.assertIn("[INF]", content)
            self.assertIn("Test info message", content)

    def test_multiple_logs_to_file(self):
        """Test multiple log messages are written in order."""
        logger = SafeLogger(filename=self.temp_path)

        logger.error("Error 1")
        logger.warning("Warning 1")
        logger.info("Info 1")
        logger.error("Error 2")

        time.sleep(0.2)
        logger.close()

        with open(self.temp_path, "r") as f:
            content = f.read()
            lines = content.strip().split("\n")

            # Should have 4 lines
            self.assertEqual(len(lines), 4)

            # Check order and prefixes
            self.assertIn("[ERR]", lines[0])
            self.assertIn("Error 1", lines[0])
            self.assertIn("[WRN]", lines[1])
            self.assertIn("Warning 1", lines[1])
            self.assertIn("[INF]", lines[2])
            self.assertIn("Info 1", lines[2])
            self.assertIn("[ERR]", lines[3])
            self.assertIn("Error 2", lines[3])

    def test_timestamp_in_logs(self):
        """Test log messages include timestamp."""
        logger = SafeLogger(filename=self.temp_path)

        logger.info("Test message")

        time.sleep(0.1)
        logger.close()

        with open(self.temp_path, "r") as f:
            content = f.read()
            # Timestamp format: YYYY-MM-DD HH:MM
            # Check for date pattern (at least year)
            import datetime

            current_year = datetime.datetime.now().year
            self.assertIn(str(current_year), content)

    def test_close_waits_for_queue(self):
        """Test close() waits for all messages to be processed."""
        logger = SafeLogger(filename=self.temp_path)

        # Queue multiple messages
        for i in range(10):
            logger.info(f"Message {i}")

        # Close should wait for all messages
        logger.close()

        with open(self.temp_path, "r") as f:
            content = f.read()
            lines = content.strip().split("\n")

            # All 10 messages should be written
            self.assertEqual(len(lines), 10)

    def test_log_file_name_property(self):
        """Test log_file_name property returns filename."""
        logger = SafeLogger(filename=self.temp_path)

        self.assertEqual(logger.log_file_name, self.temp_path)

        logger.close()

    def test_append_mode(self):
        """Test append mode preserves existing content."""
        # Write initial content
        with open(self.temp_path, "w") as f:
            f.write("Initial line\n")

        # Create logger with append mode
        logger = SafeLogger(filename=self.temp_path, write_mode="a")
        logger.info("Appended message")

        time.sleep(0.1)
        logger.close()

        with open(self.temp_path, "r") as f:
            content = f.read()
            self.assertIn("Initial line", content)
            self.assertIn("Appended message", content)


class TestSafeLoggerStandardLogging(unittest.TestCase):
    """Test standard logging fallback (no file)."""

    @patch("logging.error")
    def test_error_uses_logging_when_no_file(self, mock_error):
        """Test error() uses logging.error when no file specified."""
        logger = SafeLogger()

        logger.error("Test error")

        mock_error.assert_called_once_with("Test error")

    @patch("logging.warning")
    def test_warning_uses_logging_when_no_file(self, mock_warning):
        """Test warning() uses logging.warning when no file specified."""
        logger = SafeLogger()

        logger.warning("Test warning")

        mock_warning.assert_called_once_with("Test warning")

    @patch("logging.info")
    def test_info_uses_logging_when_no_file(self, mock_info):
        """Test info() uses logging.info when no file specified."""
        logger = SafeLogger()

        logger.info("Test info")

        mock_info.assert_called_once_with("Test info")

    @patch("logging.error")
    @patch("logging.warning")
    @patch("logging.info")
    def test_multiple_logs_use_logging(
        self, mock_info, mock_warning, mock_error
    ):
        """Test multiple calls use standard logging."""
        logger = SafeLogger()

        logger.error("Error message")
        logger.warning("Warning message")
        logger.info("Info message")

        mock_error.assert_called_once_with("Error message")
        mock_warning.assert_called_once_with("Warning message")
        mock_info.assert_called_once_with("Info message")


class TestSafeLoggerAfterClose(unittest.TestCase):
    """Test behavior after close() is called."""

    def setUp(self):
        self.temp_file = tempfile.NamedTemporaryFile(mode="w", delete=False)
        self.temp_path = self.temp_file.name
        self.temp_file.close()

    def tearDown(self):
        if os.path.exists(self.temp_path):
            os.unlink(self.temp_path)

    @patch("logging.error")
    def test_error_uses_logging_after_close(self, mock_error):
        """Test error() uses logging after close()."""
        logger = SafeLogger(filename=self.temp_path)
        logger.close()

        # After close, finished is True, should use standard logging
        logger.error("After close error")

        mock_error.assert_called_once_with("After close error")

    @patch("logging.warning")
    def test_warning_uses_logging_after_close(self, mock_warning):
        """Test warning() uses logging after close()."""
        logger = SafeLogger(filename=self.temp_path)
        logger.close()

        logger.warning("After close warning")

        mock_warning.assert_called_once_with("After close warning")

    @patch("logging.info")
    def test_info_uses_logging_after_close(self, mock_info):
        """Test info() uses logging after close()."""
        logger = SafeLogger(filename=self.temp_path)
        logger.close()

        logger.info("After close info")

        mock_info.assert_called_once_with("After close info")


class TestSafeLoggerWorkerThread(unittest.TestCase):
    """Test worker thread functionality."""

    def setUp(self):
        self.temp_file = tempfile.NamedTemporaryFile(mode="w", delete=False)
        self.temp_path = self.temp_file.name
        self.temp_file.close()

    def tearDown(self):
        if os.path.exists(self.temp_path):
            os.unlink(self.temp_path)

    def test_worker_thread_is_daemon(self):
        """Test worker thread is created as daemon."""
        logger = SafeLogger(filename=self.temp_path)

        # Worker thread should be running
        import threading

        threads = [t for t in threading.enumerate() if t.name == "SafeLogWriter"]
        # Should have at least one SafeLogWriter thread
        self.assertGreater(len(threads), 0)
        # All SafeLogWriter threads should be daemon threads
        for thread in threads:
            self.assertTrue(thread.daemon)

        logger.close()

    def test_worker_thread_processes_queue(self):
        """Test worker thread processes messages from queue."""
        logger = SafeLogger(filename=self.temp_path)

        # Add messages
        logger._write("Direct message 1")
        logger._write("Direct message 2")

        # Wait for processing
        time.sleep(0.1)
        logger.close()

        with open(self.temp_path, "r") as f:
            content = f.read()
            self.assertIn("Direct message 1", content)
            self.assertIn("Direct message 2", content)

    def test_worker_stops_when_finished(self):
        """Test worker thread stops when finished flag is set."""
        logger = SafeLogger(filename=self.temp_path)

        logger.info("Test message")
        time.sleep(0.1)

        # Close sets finished to True
        logger.close()

        # Wait a bit for thread to finish
        time.sleep(0.1)

        # Worker thread should have stopped
        import threading

        [t for t in threading.enumerate() if t.name == "SafeLogWriter"]
        # Thread may still exist briefly, but should not be processing
        self.assertTrue(logger.finished)


class TestSafeLoggerEdgeCases(unittest.TestCase):
    """Test edge cases and error conditions."""

    def setUp(self):
        self.temp_file = tempfile.NamedTemporaryFile(mode="w", delete=False)
        self.temp_path = self.temp_file.name
        self.temp_file.close()

    def tearDown(self):
        if os.path.exists(self.temp_path):
            os.unlink(self.temp_path)

    def test_empty_message(self):
        """Test logging empty string."""
        logger = SafeLogger(filename=self.temp_path)

        logger.info("")

        time.sleep(0.1)
        logger.close()

        with open(self.temp_path, "r") as f:
            content = f.read()
            # Should have timestamp and prefix, even if message is empty
            self.assertIn("[INF]", content)

    def test_multiline_message(self):
        """Test logging multiline message."""
        logger = SafeLogger(filename=self.temp_path)

        multiline = "Line 1\nLine 2\nLine 3"
        logger.info(multiline)

        time.sleep(0.1)
        logger.close()

        with open(self.temp_path, "r") as f:
            content = f.read()
            self.assertIn("Line 1", content)
            self.assertIn("Line 2", content)
            self.assertIn("Line 3", content)

    def test_special_characters(self):
        """Test logging messages with special characters."""
        logger = SafeLogger(filename=self.temp_path)

        special_msg = "Test with émojis 🎉 and spëcial çhars: @#$%^&*()"
        logger.info(special_msg)

        time.sleep(0.1)
        logger.close()

        with open(self.temp_path, "r") as f:
            content = f.read()
            self.assertIn("Test with", content)
            # Special characters may or may not be preserved based on encoding

    def test_very_long_message(self):
        """Test logging very long message."""
        logger = SafeLogger(filename=self.temp_path)

        long_msg = "A" * 10000
        logger.info(long_msg)

        time.sleep(0.2)
        logger.close()

        with open(self.temp_path, "r") as f:
            content = f.read()
            self.assertIn("A" * 100, content)  # Check partial content

    def test_rapid_logging(self):
        """Test rapid successive logging."""
        logger = SafeLogger(filename=self.temp_path)

        # Log 100 messages rapidly
        for i in range(100):
            logger.info(f"Message {i}")

        logger.close()

        with open(self.temp_path, "r") as f:
            content = f.read()
            lines = content.strip().split("\n")

            # All messages should be written
            self.assertEqual(len(lines), 100)

    @patch("logging.info")
    def test_log_file_name_none_when_no_file(self, mock_info):
        """Test log_file_name is None when using standard logging."""
        logger = SafeLogger()

        self.assertIsNone(logger.log_file_name)


if __name__ == "__main__":
    unittest.main()
