"""Comprehensive Unit Tests for Website Uptime Checker.

All tests use mocks (`unittest.mock`) to avoid any dependency on live network
connectivity or remote web servers.
"""

from __future__ import annotations

import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import requests

from src.uptime_checker import (
    DEFAULT_RETRIES,
    DEFAULT_TIMEOUT,
    EXIT_ALL_UP,
    EXIT_INTERRUPTED,
    EXIT_INVALID_INPUT,
    EXIT_ONE_OR_MORE_DOWN,
    STATUS_DOWN,
    STATUS_UP,
    USER_AGENT,
    CheckResult,
    calculate_summary,
    check_url,
    format_terminal_output,
    main,
    normalize_url,
    parse_url_file,
    write_report,
)


class TestWebsiteUptimeChecker(unittest.TestCase):
    """Unit test suite for Website Uptime Checker CLI."""

    # 1. URL Normalization
    def test_01_url_normalization_missing_scheme(self):
        result = normalize_url("example.com")
        self.assertEqual(result, "https://example.com")

    # 2. Valid HTTPS URL
    def test_02_url_normalization_https(self):
        result = normalize_url("https://example.com/api/test?query=1")
        self.assertEqual(result, "https://example.com/api/test?query=1")

    # 3. Valid HTTP URL
    def test_03_url_normalization_http(self):
        result = normalize_url("http://insecure-site.org")
        self.assertEqual(result, "http://insecure-site.org")

    # 4. Invalid URL Handling (empty, invalid schemes, missing host)
    def test_04_url_normalization_invalid(self):
        with self.assertRaises(ValueError):
            normalize_url("")
        with self.assertRaises(ValueError):
            normalize_url("   ")
        with self.assertRaises(ValueError):
            normalize_url("ftp://example.com")
        with self.assertRaises(ValueError):
            normalize_url("https://")

    # 5. Basic successful HTTP response
    @patch("requests.Session.get")
    def test_05_basic_successful_response(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_get.return_value = mock_resp

        result = check_url("https://example.com")
        self.assertEqual(result.status, STATUS_UP)
        self.assertEqual(result.http_status, 200)
        self.assertIsNone(result.error)
        self.assertIsNotNone(result.response_time)

    # 6. 2xx status classified as UP
    @patch("requests.Session.get")
    def test_06_status_2xx_classified_as_up(self, mock_get):
        for code in (200, 201, 204):
            mock_resp = MagicMock()
            mock_resp.status_code = code
            mock_get.return_value = mock_resp

            result = check_url("https://example.com")
            self.assertEqual(result.status, STATUS_UP, f"Expected UP for status {code}")
            self.assertEqual(result.http_status, code)

    # 7. 3xx status classified as UP
    @patch("requests.Session.get")
    def test_07_status_3xx_classified_as_up(self, mock_get):
        for code in (301, 302, 307, 308):
            mock_resp = MagicMock()
            mock_resp.status_code = code
            mock_get.return_value = mock_resp

            result = check_url("https://example.com")
            self.assertEqual(result.status, STATUS_UP, f"Expected UP for status {code}")
            self.assertEqual(result.http_status, code)

    # 8. 4xx status classified as DOWN
    @patch("requests.Session.get")
    def test_08_status_4xx_classified_as_down(self, mock_get):
        for code, reason in ((400, "Bad Request"), (404, "Not Found"), (403, "Forbidden")):
            mock_resp = MagicMock()
            mock_resp.status_code = code
            mock_resp.reason = reason
            mock_get.return_value = mock_resp

            result = check_url("https://example.com", retries=0)
            self.assertEqual(result.status, STATUS_DOWN, f"Expected DOWN for status {code}")
            self.assertEqual(result.http_status, code)
            self.assertIn(str(code), result.error)

    # 9. 5xx status classified as DOWN
    @patch("requests.Session.get")
    def test_09_status_5xx_classified_as_down(self, mock_get):
        for code, reason in ((500, "Internal Server Error"), (503, "Service Unavailable")):
            mock_resp = MagicMock()
            mock_resp.status_code = code
            mock_resp.reason = reason
            mock_get.return_value = mock_resp

            result = check_url("https://example.com", retries=0)
            self.assertEqual(result.status, STATUS_DOWN, f"Expected DOWN for status {code}")
            self.assertEqual(result.http_status, code)
            self.assertIn(str(code), result.error)

    # 10. Timeout handling
    @patch("requests.Session.get")
    def test_10_timeout_handling(self, mock_get):
        mock_get.side_effect = requests.exceptions.Timeout("Connection timed out")
        result = check_url("https://example.com", timeout=3.5, retries=1)

        self.assertEqual(result.status, STATUS_DOWN)
        self.assertIsNone(result.http_status)
        self.assertIn("timed out after 3.5s", result.error)
        self.assertEqual(mock_get.call_count, 2)  # initial + 1 retry

    # 11. Connection error handling (DNS failure & generic)
    @patch("requests.Session.get")
    def test_11_connection_error_handling(self, mock_get):
        mock_get.side_effect = requests.exceptions.ConnectionError(
            "Failed to resolve: [Errno 11001] getaddrinfo failed"
        )
        result = check_url("https://nonexistent-host-test.org", retries=0)

        self.assertEqual(result.status, STATUS_DOWN)
        self.assertEqual(result.error, "DNS resolution failed")

    # 12. Retry behavior
    @patch("requests.Session.get")
    def test_12_retry_behavior(self, mock_get):
        # First 2 fail, 3rd succeeds
        mock_fail = requests.exceptions.Timeout("Timed out")
        mock_success = MagicMock(status_code=200)
        mock_get.side_effect = [mock_fail, mock_fail, mock_success]

        result = check_url("https://example.com", retries=2)
        self.assertEqual(result.status, STATUS_UP)
        self.assertEqual(result.http_status, 200)
        self.assertEqual(mock_get.call_count, 3)

    # 13. Response-time measurement logic
    @patch("time.perf_counter")
    @patch("requests.Session.get")
    def test_13_response_time_measurement(self, mock_get, mock_time):
        mock_time.side_effect = [10.0, 10.424]  # difference 0.424s -> 0.42s
        mock_get.return_value = MagicMock(status_code=200)

        result = check_url("https://example.com", retries=0)
        self.assertEqual(result.response_time, 0.42)

    # 14. URL file parsing
    def test_14_url_file_parsing(self):
        content = "https://example.com\nhttp://test.org/path\nexample.net\n"
        with tempfile.NamedTemporaryFile("w+", delete=False, encoding="utf-8") as tf:
            tf.write(content)
            tf.flush()
            temp_path = tf.name

        try:
            urls = parse_url_file(temp_path)
            self.assertEqual(
                urls,
                ["https://example.com", "http://test.org/path", "https://example.net"],
            )
        finally:
            Path(temp_path).unlink(missing_ok=True)

    # 15. Blank-line handling in file
    def test_15_blank_line_handling(self):
        content = "\n\n   \nhttps://example.com\n\n\n"
        with tempfile.NamedTemporaryFile("w+", delete=False, encoding="utf-8") as tf:
            tf.write(content)
            tf.flush()
            temp_path = tf.name

        try:
            urls = parse_url_file(temp_path)
            self.assertEqual(urls, ["https://example.com"])
        finally:
            Path(temp_path).unlink(missing_ok=True)

    # 16. Comment-line handling in file
    def test_16_comment_line_handling(self):
        content = "# Header comment\nhttps://example.com\n# Another comment\n"
        with tempfile.NamedTemporaryFile("w+", delete=False, encoding="utf-8") as tf:
            tf.write(content)
            tf.flush()
            temp_path = tf.name

        try:
            urls = parse_url_file(temp_path)
            self.assertEqual(urls, ["https://example.com"])
        finally:
            Path(temp_path).unlink(missing_ok=True)

    # 17. Missing input file
    def test_17_missing_input_file(self):
        with self.assertRaises(FileNotFoundError):
            parse_url_file("nonexistent_directory/nonexistent_file_xyz.txt")

    # 18. Invalid timeout CLI validation
    def test_18_invalid_timeout(self):
        exit_code = main(["--url", "https://example.com", "--timeout", "0"])
        self.assertEqual(exit_code, EXIT_INVALID_INPUT)

        exit_code_neg = main(["--url", "https://example.com", "--timeout", "-5"])
        self.assertEqual(exit_code_neg, EXIT_INVALID_INPUT)

    # 19. Invalid retry count CLI validation
    def test_19_invalid_retry_count(self):
        exit_code = main(["--url", "https://example.com", "--retries", "-1"])
        self.assertEqual(exit_code, EXIT_INVALID_INPUT)

    # 20. JSON report generation
    def test_20_json_report_generation(self):
        results = [
            CheckResult(
                url="https://example.com",
                status=STATUS_UP,
                http_status=200,
                response_time=0.42,
                error=None,
            )
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            out_file = Path(tmpdir) / "report.json"
            write_report(results, out_file, output_format="json")

            self.assertTrue(out_file.exists())
            with open(out_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.assertEqual(len(data), 1)
            self.assertEqual(data[0]["url"], "https://example.com")
            self.assertEqual(data[0]["status"], "UP")
            self.assertEqual(data[0]["http_status"], 200)

    # 21. CSV report generation
    def test_21_csv_report_generation(self):
        results = [
            CheckResult(
                url="https://example.com",
                status=STATUS_UP,
                http_status=200,
                response_time=0.35,
                error=None,
            ),
            CheckResult(
                url="https://down.site",
                status=STATUS_DOWN,
                http_status=None,
                response_time=None,
                error="DNS resolution failed",
            ),
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            out_file = Path(tmpdir) / "report.csv"
            write_report(results, out_file, output_format="csv")

            self.assertTrue(out_file.exists())
            with open(out_file, "r", encoding="utf-8") as f:
                lines = [line.strip() for line in f.readlines() if line.strip()]
            self.assertEqual(lines[0], "url,status,http_status,response_time,error")
            self.assertIn("https://example.com,UP,200,0.35,", lines[1])
            self.assertIn("https://down.site,DOWN,,,DNS resolution failed", lines[2])

    # 22. Existing output protection
    def test_22_existing_output_protection(self):
        results = [
            CheckResult("https://example.com", STATUS_UP, 200, 0.2, None)
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            out_file = Path(tmpdir) / "existing.json"
            out_file.write_text("existing content", encoding="utf-8")

            # Must raise FileExistsError without force
            with self.assertRaises(FileExistsError):
                write_report(results, out_file, output_format="json", force=False)

            self.assertEqual(out_file.read_text(encoding="utf-8"), "existing content")

            # Must succeed with force=True
            write_report(results, out_file, output_format="json", force=True)
            self.assertIn('"https://example.com"', out_file.read_text(encoding="utf-8"))

    # 23. Quiet mode behavior
    def test_23_quiet_mode_behavior(self):
        results = [
            CheckResult("https://example.com", STATUS_UP, 200, 0.2, None),
            CheckResult("https://down.site", STATUS_DOWN, None, None, "DNS failed"),
        ]
        output = format_terminal_output(results, quiet=True)
        self.assertEqual(output, "Checked: 2 | UP: 1 | DOWN: 1")

    # 24. Multiple URL checking
    @patch("requests.Session.get")
    def test_24_multiple_url_checking(self, mock_get):
        resp_up = MagicMock(status_code=200)
        resp_down = MagicMock(status_code=404, reason="Not Found")
        mock_get.side_effect = [resp_up, resp_down]

        with patch("sys.stdout", new=io.StringIO()) as fake_stdout:
            exit_code = main([
                "--url", "https://site1.com",
                "--url", "https://site2.com",
                "--retries", "0",
            ])
            output = fake_stdout.getvalue()

        self.assertEqual(exit_code, EXIT_ONE_OR_MORE_DOWN)
        self.assertIn("[UP]    https://site1.com", output)
        self.assertIn("[DOWN]  https://site2.com", output)
        self.assertIn("Total Checked: 2", output)
        self.assertIn("UP:            1", output)
        self.assertIn("DOWN:          1", output)

    # 25. Summary calculation
    def test_25_summary_calculation(self):
        results = [
            CheckResult("https://a.com", STATUS_UP, 200, 0.40, None),
            CheckResult("https://b.com", STATUS_UP, 200, 0.60, None),
            CheckResult("https://c.com", STATUS_DOWN, None, None, "Failed"),
        ]
        total, up, down, avg = calculate_summary(results)
        self.assertEqual(total, 3)
        self.assertEqual(up, 2)
        self.assertEqual(down, 1)
        self.assertEqual(avg, 0.50)

    # 26. Exit code logic (all up -> 0, any down -> 1)
    @patch("requests.Session.get")
    def test_26_exit_code_logic(self, mock_get):
        # All UP
        mock_get.return_value = MagicMock(status_code=200)
        code_all_up = main(["--url", "https://example.com"])
        self.assertEqual(code_all_up, EXIT_ALL_UP)

        # One DOWN
        mock_get.return_value = MagicMock(status_code=500, reason="Error")
        code_down = main(["--url", "https://example.com", "--retries", "0"])
        self.assertEqual(code_down, EXIT_ONE_OR_MORE_DOWN)

    # 27. Ctrl+C handling
    @patch("requests.Session.get")
    def test_27_keyboard_interrupt_handling(self, mock_get):
        mock_get.side_effect = KeyboardInterrupt()
        with patch("sys.stderr", new=io.StringIO()) as fake_stderr:
            exit_code = main(["--url", "https://example.com"])
            err_output = fake_stderr.getvalue()

        self.assertEqual(exit_code, EXIT_INTERRUPTED)
        self.assertIn("Operation cancelled by user.", err_output)

    # 28. User-Agent header validation
    @patch("requests.Session.get")
    def test_28_user_agent_header(self, mock_get):
        mock_get.return_value = MagicMock(status_code=200)
        check_url("https://example.com", retries=0)

        mock_get.assert_called_once()
        headers = mock_get.call_args[1].get("headers", {})
        self.assertEqual(headers.get("User-Agent"), USER_AGENT)

    # 29. Temporary output cleanup on failure
    def test_29_temporary_output_cleanup(self):
        results = [CheckResult("https://example.com", STATUS_UP, 200, 0.2, None)]
        with tempfile.TemporaryDirectory() as tmpdir:
            out_file = Path(tmpdir) / "report.json"
            # Force write failure by patching json.dump to raise an error
            with patch("json.dump", side_effect=RuntimeError("Disk write simulated failure")):
                with self.assertRaises(RuntimeError):
                    write_report(results, out_file, output_format="json")

            # Check that no leftover temporary files remain
            leftovers = list(Path(tmpdir).glob(".uptime_tmp_*"))
            self.assertEqual(leftovers, [])
            self.assertFalse(out_file.exists())


if __name__ == "__main__":
    unittest.main()
