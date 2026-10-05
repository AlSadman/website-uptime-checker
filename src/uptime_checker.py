"""Website Uptime Checker CLI

A professional, modular Windows command-line utility for monitoring website
availability, measuring response time, retrying temporary failures, and
exporting detailed JSON/CSV reports.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import List, Optional, Tuple
from urllib.parse import urlparse

import requests

# Constants
DEFAULT_TIMEOUT = 10.0
DEFAULT_RETRIES = 2
USER_AGENT = "WebsiteUptimeChecker/1.0"
STATUS_UP = "UP"
STATUS_DOWN = "DOWN"

# Exit codes
EXIT_ALL_UP = 0
EXIT_ONE_OR_MORE_DOWN = 1
EXIT_INVALID_INPUT = 2
EXIT_INTERRUPTED = 130


@dataclass
class CheckResult:
    """Stores the result of an uptime check for a single URL."""
    url: str
    status: str  # 'UP' or 'DOWN'
    http_status: Optional[int]
    response_time: Optional[float]  # in seconds, rounded to 2 decimal places
    error: Optional[str]

    def to_dict(self) -> dict:
        return asdict(self)


def normalize_url(url: str) -> str:
    """Normalize input URL by stripping whitespace and ensuring scheme exists.
    
    If no scheme is provided (e.g. 'example.com'), defaults to 'https://'.
    Validates that the scheme is http or https.
    """
    cleaned = url.strip()
    if not cleaned:
        raise ValueError("URL cannot be empty.")

    parsed = urlparse(cleaned)
    if not parsed.scheme:
        # Default scheme to https://
        cleaned = f"https://{cleaned}"
        parsed = urlparse(cleaned)

    if parsed.scheme.lower() not in ("http", "https"):
        raise ValueError(
            f"Unsupported URL scheme '{parsed.scheme}'. Only 'http://' and 'https://' are supported."
        )

    if not parsed.netloc:
        raise ValueError(f"Invalid URL structure: '{url}'. Missing domain/host.")

    return cleaned


def parse_url_file(filepath: Path | str) -> List[str]:
    """Parse a text file containing URLs, one per line.
    
    Ignores empty lines and comment lines starting with '#'.
    Validates and normalizes each URL.
    """
    path = Path(filepath)
    if not path.is_file():
        raise FileNotFoundError(f"Input file not found: {filepath}")

    urls: List[str] = []
    try:
        with open(path, mode="r", encoding="utf-8") as f:
            for line_no, raw_line in enumerate(f, start=1):
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue
                try:
                    norm = normalize_url(line)
                    urls.append(norm)
                except ValueError as ve:
                    raise ValueError(f"Line {line_no} in '{filepath}': {ve}") from ve
    except (UnicodeDecodeError, OSError) as e:
        if isinstance(e, FileNotFoundError):
            raise
        raise OSError(f"Could not read input file '{filepath}': {e}") from e

    return urls


def check_url(
    url: str,
    timeout: float = DEFAULT_TIMEOUT,
    retries: int = DEFAULT_RETRIES,
    session: Optional[requests.Session] = None,
) -> CheckResult:
    """Check a single URL's availability with configurable timeout and retries.
    
    Uses stream=True to avoid downloading large response bodies unnecessarily.
    Uses monotonic time.perf_counter() for accurate latency measurement.
    """
    total_attempts = 1 + max(0, retries)
    last_error: Optional[str] = None
    last_http_status: Optional[int] = None
    last_response_time: Optional[float] = None

    headers = {"User-Agent": USER_AGENT}
    req_session = session or requests.Session()

    for attempt in range(total_attempts):
        start_time = time.perf_counter()
        try:
            # stream=True ensures we only read the response headers and do not
            # pull large response bodies into memory.
            response = req_session.get(
                url,
                timeout=timeout,
                headers=headers,
                allow_redirects=True,
                stream=True,
            )
            elapsed = time.perf_counter() - start_time
            response_time = round(elapsed, 2)
            http_status = response.status_code

            # UP: 200 to 399
            if 200 <= http_status <= 399:
                return CheckResult(
                    url=url,
                    status=STATUS_UP,
                    http_status=http_status,
                    response_time=response_time,
                    error=None,
                )

            # DOWN: 400 or higher
            last_http_status = http_status
            last_response_time = response_time
            last_error = f"HTTP Error {http_status}: {response.reason}"

        except requests.exceptions.Timeout:
            last_error = f"Request timed out after {timeout}s"
            last_http_status = None
            last_response_time = None
        except requests.exceptions.SSLError as ssl_err:
            last_error = f"SSL error: {ssl_err}"
            last_http_status = None
            last_response_time = None
        except requests.exceptions.ConnectionError as conn_err:
            # Common DNS or connection failure
            err_str = str(conn_err)
            if "getaddrinfo failed" in err_str or "NameResolutionError" in err_str:
                last_error = "DNS resolution failed"
            else:
                last_error = f"Connection failed: {conn_err}"
            last_http_status = None
            last_response_time = None
        except requests.exceptions.RequestException as req_err:
            last_error = f"Request error: {req_err}"
            last_http_status = None
            last_response_time = None
        except Exception as ex:
            last_error = f"Unexpected error: {ex}"
            last_http_status = None
            last_response_time = None

    # If all attempts failed
    return CheckResult(
        url=url,
        status=STATUS_DOWN,
        http_status=last_http_status,
        response_time=last_response_time,
        error=last_error or "Unknown failure",
    )


def calculate_summary(results: List[CheckResult]) -> Tuple[int, int, int, Optional[float]]:
    """Calculate total, up count, down count, and average response time.
    
    Average response time considers only successful or measured attempts.
    """
    total = len(results)
    up_count = sum(1 for r in results if r.status == STATUS_UP)
    down_count = total - up_count

    times = [r.response_time for r in results if r.response_time is not None]
    avg_time = round(sum(times) / len(times), 2) if times else None
    return total, up_count, down_count, avg_time


def format_terminal_output(results: List[CheckResult], quiet: bool = False) -> str:
    """Format check results and summary for terminal display."""
    total, up_count, down_count, avg_time = calculate_summary(results)

    if quiet:
        return f"Checked: {total} | UP: {up_count} | DOWN: {down_count}"

    lines: List[str] = [
        "Website Uptime Check",
        "====================",
        "",
    ]

    for r in results:
        status_tag = f"[{r.status}]".ljust(7)
        lines.append(f"{status_tag} {r.url}")
        status_code_str = str(r.http_status) if r.http_status is not None else "N/A"
        lines.append(f"       Status: {status_code_str}")
        resp_time_str = f"{r.response_time:.2f}s" if r.response_time is not None else "N/A"
        lines.append(f"       Response Time: {resp_time_str}")
        if r.error:
            lines.append(f"       Error: {r.error}")
        lines.append("")

    lines.extend([
        "Summary",
        "=======",
        "",
        f"Total Checked: {total}",
        f"UP:            {up_count}",
        f"DOWN:          {down_count}",
        f"Average Time:  {avg_time:.2f}s" if avg_time is not None else "Average Time:  N/A",
        "",
    ])

    if down_count == 0 and total > 0:
        lines.append("Result: ALL WEBSITES UP")
    else:
        lines.append("Result: ONE OR MORE WEBSITES DOWN")

    return "\n".join(lines)


def write_report(
    results: List[CheckResult],
    output_path: Path | str,
    output_format: str = "json",
    force: bool = False,
) -> None:
    """Safely write check results to a report file (JSON or CSV).
    
    Protects against overwriting existing files unless force=True.
    Uses atomic write via temporary file replacement.
    """
    target = Path(output_path).resolve()
    target_format = output_format.lower()

    if target_format not in ("json", "csv"):
        raise ValueError(f"Invalid format '{output_format}'. Supported formats: json, csv.")

    if target.exists() and not force:
        raise FileExistsError(
            f"Output file already exists: '{target}'. Use --force to overwrite."
        )

    # Ensure parent directory exists
    target.parent.mkdir(parents=True, exist_ok=True)

    # Create temporary file in same directory for atomic rename
    tmp_fd, tmp_path_str = tempfile.mkstemp(
        prefix=".uptime_tmp_",
        suffix=f".{target_format}",
        dir=str(target.parent),
    )
    tmp_path = Path(tmp_path_str)

    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8", newline="") as f:
            if target_format == "json":
                data = [r.to_dict() for r in results]
                json.dump(data, f, indent=4)
                f.write("\n")
            elif target_format == "csv":
                writer = csv.writer(f)
                writer.writerow(["url", "status", "http_status", "response_time", "error"])
                for r in results:
                    writer.writerow([
                        r.url,
                        r.status,
                        r.http_status if r.http_status is not None else "",
                        r.response_time if r.response_time is not None else "",
                        r.error if r.error is not None else "",
                    ])

        # Atomically replace target
        tmp_path.replace(target)
    except Exception:
        # Clean up temporary file on failure
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass
        raise


def run_interactive() -> Tuple[List[str], float, int, Optional[str], str]:
    """Run an interactive console prompt when arguments are omitted."""
    print("Website Uptime Checker")
    print("=====================")
    print()

    raw_url = input("Enter a website URL: ").strip()
    if not raw_url:
        raise ValueError("URL cannot be empty.")
    url = normalize_url(raw_url)

    raw_timeout = input(f"Enter timeout in seconds (default {DEFAULT_TIMEOUT}s): ").strip()
    timeout = float(raw_timeout) if raw_timeout else DEFAULT_TIMEOUT
    if timeout <= 0:
        raise ValueError("Timeout must be greater than 0.")

    raw_retries = input(f"Enter retry count (default {DEFAULT_RETRIES}): ").strip()
    retries = int(raw_retries) if raw_retries else DEFAULT_RETRIES
    if retries < 0:
        raise ValueError("Retry count cannot be negative.")

    save_report = input("Save report to file? (y/N): ").strip().lower()
    output_path = None
    output_format = "json"
    if save_report in ("y", "yes"):
        output_path = input("Enter output path (e.g., reports/uptime_report.json): ").strip()
        if not output_path:
            output_path = None
        else:
            fmt = input("Format (json/csv, default: json): ").strip().lower()
            if fmt in ("json", "csv"):
                output_format = fmt

    return [url], timeout, retries, output_path, output_format


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line argument parser."""
    parser = argparse.ArgumentParser(
        prog="uptime_checker.py",
        description="Website Uptime Checker - Monitor website availability, latency, and status.",
    )
    parser.add_argument(
        "-u",
        "--url",
        action="append",
        dest="urls",
        help="Website URL to check (can be specified multiple times).",
    )
    parser.add_argument(
        "-f",
        "--file",
        dest="file",
        help="Path to text file containing URLs to check (one per line).",
    )
    parser.add_argument(
        "-t",
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT,
        help=f"Request timeout in seconds (default: {DEFAULT_TIMEOUT}s).",
    )
    parser.add_argument(
        "-r",
        "--retries",
        type=int,
        default=DEFAULT_RETRIES,
        help=f"Additional retry attempts after initial request (default: {DEFAULT_RETRIES}).",
    )
    parser.add_argument(
        "-o",
        "--output",
        dest="output",
        help="Path to save results report file (JSON or CSV).",
    )
    parser.add_argument(
        "--format",
        dest="format",
        choices=["json", "csv"],
        default=None,
        help="Output report format (json or csv). Defaults to JSON or inferred from extension.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing output report file if it already exists.",
    )
    parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="Suppress detailed URL output and show only concise summary.",
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    """Main CLI entry point."""
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        # Validate timeout and retries
        if args.timeout <= 0:
            print(f"Error: Timeout must be greater than 0 (got {args.timeout}).", file=sys.stderr)
            return EXIT_INVALID_INPUT

        if args.retries < 0:
            print(f"Error: Retry count cannot be negative (got {args.retries}).", file=sys.stderr)
            return EXIT_INVALID_INPUT

        urls: List[str] = []

        if args.urls:
            for u in args.urls:
                try:
                    urls.append(normalize_url(u))
                except ValueError as e:
                    print(f"Error: {e}", file=sys.stderr)
                    return EXIT_INVALID_INPUT

        if args.file:
            try:
                file_urls = parse_url_file(args.file)
                urls.extend(file_urls)
            except (FileNotFoundError, ValueError, OSError) as e:
                print(f"Error: {e}", file=sys.stderr)
                return EXIT_INVALID_INPUT

        output_path = args.output
        output_format = args.format or "json"
        if output_path and args.format is None:
            # Infer from file extension if provided
            ext = Path(output_path).suffix.lower()
            if ext == ".csv":
                output_format = "csv"
            elif ext == ".json":
                output_format = "json"

        # Interactive mode if neither URL nor file is provided
        if not urls:
            try:
                urls, timeout, retries, int_output, int_fmt = run_interactive()
                args.timeout = timeout
                args.retries = retries
                if int_output:
                    output_path = int_output
                    output_format = int_fmt
            except ValueError as e:
                print(f"Error: {e}", file=sys.stderr)
                return EXIT_INVALID_INPUT

        if not urls:
            print("Error: No URLs to check.", file=sys.stderr)
            return EXIT_INVALID_INPUT

        # Execute uptime checks
        results: List[CheckResult] = []
        with requests.Session() as session:
            for url in urls:
                res = check_url(
                    url=url,
                    timeout=args.timeout,
                    retries=args.retries,
                    session=session,
                )
                results.append(res)

        # Output terminal summary
        terminal_text = format_terminal_output(results, quiet=args.quiet)
        print(terminal_text)

        # Save report if requested
        if output_path:
            try:
                write_report(
                    results=results,
                    output_path=output_path,
                    output_format=output_format,
                    force=args.force,
                )
                if not args.quiet:
                    print(f"\nReport saved to: {output_path}")
            except (FileExistsError, ValueError, OSError) as e:
                print(f"Error saving report: {e}", file=sys.stderr)
                return EXIT_INVALID_INPUT

        # Determine exit code: 0 if all UP, 1 if any DOWN
        has_down = any(r.status == STATUS_DOWN for r in results)
        return EXIT_ONE_OR_MORE_DOWN if has_down else EXIT_ALL_UP

    except KeyboardInterrupt:
        print("\nOperation cancelled by user.", file=sys.stderr)
        return EXIT_INTERRUPTED


if __name__ == "__main__":
    sys.exit(main())
