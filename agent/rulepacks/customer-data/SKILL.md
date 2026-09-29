---
name: customer-data
description: Keep agents out of customer data exports unless a person says otherwise.
---

Enable this pack on agents that can see a data or backend folder. Customer exports (CSV, JSON, Parquet or spreadsheet files in an `exports/` folder) hold real people's records, and a coding agent rarely needs them to do its job.

Blocked examples include reading `exports/customers-2026-09.csv` or copying an `exports/*.parquet` file. Allowed examples include reading the exports folder's README, the export script's source, and test fixtures.
