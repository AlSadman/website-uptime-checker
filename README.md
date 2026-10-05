# Website Uptime Checker

A clean, reliable, and professional Python CLI utility for monitoring website availability, HTTP status codes, latency, and handling automatic retries.

Developed as **Project #4 of the Python CLI Portfolio Series**.

---

## Features

- **Single & Multiple URL Checking**: Check a single endpoint via `--url` or batch-verify multiple domains via a text file with `--file`.
- **HTTP Status Detection**: Accurately classifies HTTP responses:
  - **UP**: HTTP status codes 200–399.
  - **DOWN**: Connection errors, DNS failures, timeouts, SSL issues, or HTTP status codes 400+.
- **Precise Latency Measurement**: Measures response time in seconds using Python's high-resolution monotonic timer (`time.perf_counter()`).
- **Configurable Retries**: Automatically retries temporary connection failures or request timeouts before marking a site down.
- **Configurable Timeout**: Set custom timeout thresholds (default: 10s).
- **Report Generation**: Export full inspection logs to structured **JSON** or **CSV** formats.
- **Atomic File Writing**: Safely writes reports via atomic replacement and prevents unintended overwrites unless `--force` is specified.
- **Quiet Mode**: Suppresses detailed output and displays only high-level totals (`--quiet`).
- **Interactive Mode**: Automatically launches an interactive terminal walkthrough when invoked without arguments.
- **Network Safety & Custom User-Agent**: Transmits a non-impersonating identifier (`WebsiteUptimeChecker/1.0`) and avoids downloading large response bodies (`stream=True`).
- **No Live Test Dependencies**: Full suite of unit tests isolated using standard library mocks (`unittest.mock`).

---

## Requirements

- **Python**: 3.10+ (tested on Python 3.14+)
- **Operating System**: Windows (PowerShell or Command Prompt), macOS, or Linux

---

## Installation

Clone the repository and install the single third-party dependency (`requests`):

```powershell
git clone <repository-url>
cd WebsiteUptimeChecker
pip install -r requirements.txt
```

---

## Usage

### 1. Check a Single URL
```powershell
python src/uptime_checker.py --url https://example.com
```

### 2. Check Multiple URLs from a File
```powershell
python src/uptime_checker.py --file demo_data/websites.txt
```

### 3. Custom Timeout & Retries
```powershell
python src/uptime_checker.py --url https://example.com --timeout 5 --retries 3
```

### 4. Export JSON Report
```powershell
python src/uptime_checker.py --file demo_data/websites.txt --output reports/uptime_report.json --format json
```

### 5. Export CSV Report
```powershell
python src/uptime_checker.py --file demo_data/websites.txt --output reports/uptime_report.csv --format csv
```

### 6. Quiet Mode
```powershell
python src/uptime_checker.py --url https://example.com --quiet
```
*Output:*
```text
Checked: 1 | UP: 1 | DOWN: 0
```

### 7. Interactive Mode
Run the tool without arguments to enter guided interactive mode:
```powershell
python src/uptime_checker.py
```

---

## CLI Options Reference

| Option | Short | Description | Default |
| :--- | :--- | :--- | :--- |
| `--url` | `-u` | Website URL to check (can be specified multiple times) | `None` |
| `--file` | `-f` | Path to text file containing URLs (one per line) | `None` |
| `--timeout` | `-t` | Request timeout in seconds | `10.0` |
| `--retries` | `-r` | Additional retry attempts after initial request | `2` |
| `--output` | `-o` | File path to export results (JSON or CSV) | `None` |
| `--format` | | Format of exported report (`json` or `csv`) | `json` |
| `--force` | | Overwrite existing report file if present | `False` |
| `--quiet` | `-q` | Suppress detailed list and show concise summary | `False` |
| `--help` | `-h` | Show help menu and exit | |

---

## Exit Codes

| Exit Code | Meaning |
| :---: | :--- |
| `0` | Command completed successfully and all checked websites were **UP**. |
| `1` | Command completed, but one or more websites were **DOWN**. |
| `2` | Invalid command arguments, validation error, or missing file. |
| `130` | Execution interrupted by user (`Ctrl+C`). |

---

## Testing

Run the automated unit test suite:

```powershell
python -m unittest discover -s tests -v
```

All 29 tests use `unittest.mock` to simulate HTTP responses, timeouts, connection drops, and DNS errors without requiring an active internet connection.

---

## Project Structure

```text
C:\WebsiteUptimeChecker
│
├── src
│   └── uptime_checker.py
│
├── tests
│   └── test_uptime_checker.py
│
├── demo_data
│   ├── README.md
│   └── websites.txt
│
├── reports
│   └── README.md
│
├── screenshots
│   └── README.md
│
├── README.md
├── requirements.txt
├── .gitignore
└── LICENSE
```

---

## Limitations

- **Network Conditions**: Live checks depend on local network quality, DNS resolution, and ISP routing.
- **Bot Mitigation**: Some websites or CDNs block automated requests or return 403 Forbidden to non-browser User-Agents.
- **Monitoring Scope**: This utility is a lightweight on-demand CLI tool; it does not replace distributed, round-the-clock enterprise monitoring services (e.g. Datadog, Pingdom).
- **Security Testing**: Does not perform vulnerability scanning, credential brute-forcing, or security bypass.

---

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.
