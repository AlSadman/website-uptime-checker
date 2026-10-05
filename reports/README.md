# Reports Directory

This directory stores generated uptime reports from the Website Uptime Checker CLI tool.

## Report Formats Supported

The CLI tool supports exporting results in:
- **JSON**: Structured list of objects with fields `url`, `status`, `http_status`, `response_time`, and `error`.
- **CSV**: Standard comma-separated format with headers `url,status,http_status,response_time,error`.

## Examples

Generating a JSON report:
```powershell
python src/uptime_checker.py --file demo_data/websites.txt --output reports/uptime_report.json --format json
```

Generating a CSV report:
```powershell
python src/uptime_checker.py --file demo_data/websites.txt --output reports/uptime_report.csv --format csv
```

## Git Policy

Generated `.json` and `.csv` files inside this directory are ignored by Git (via `.gitignore`) to prevent committing temporary or local check data.
