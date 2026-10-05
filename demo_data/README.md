# Demo Websites

This file contains a list of demonstration URLs for testing the Website Uptime Checker CLI tool.

## Included URLs

- `https://example.com` - Standard reliable example website (expected UP, HTTP 200).
- `https://httpbin.org/status/200` - Reliable test endpoint returning HTTP 200 (expected UP).
- `https://httpbin.org/status/404` - Reliable test endpoint returning HTTP 404 (expected DOWN).
- `https://nonexistent-domain-for-testing-12345.org` - Intentional non-resolvable domain to verify DNS failure handling (expected DOWN).

## Running the Checker

You can run the checker against this file:

```powershell
python src/uptime_checker.py --file demo_data/websites.txt
```

## Note on Automated Unit Tests

Live network availability, DNS, and remote server states can fluctuate. Therefore, all automated unit tests in the `tests/` directory use mock HTTP requests (`unittest.mock`) and do **not** depend on live internet connectivity or remote servers.
