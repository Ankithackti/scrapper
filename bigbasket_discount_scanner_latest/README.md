# BigBasket Discount Scanner

A controlled-concurrency scanner for publicly accessible BigBasket offer pages.

## What changed

- Async HTTP requests with bounded concurrency.
- Reuses one HTTP connection pool instead of creating a client for every request.
- Scans category pages immediately instead of first crawling a large URL list.
- Skips `/pc/`, `/cl/`, and `/all-offers/.../c/.../` URLs that commonly redirect/fail.
- Handles 403, 404, timeouts and transient HTTP errors without stopping the complete scan.
- Deduplicates products by BigBasket product ID.
- Saves qualifying products incrementally to `output/discount_products.json`.
- Existing JSON results are loaded at startup and retained between scans.

## Install

From the project root:

```powershell
python -m pip install -r requirements.txt
```

## First test

```powershell
python -m scraper.cli discount-monitor --threshold 60 --pages-per-category 2 --concurrency 8 --delay 0.5 --once
```

## Output

The scanner writes:

```text
output/discount_products.json
```

Only products at or above the requested discount threshold are written.

Each result contains:

- product_id
- name
- url
- mrp
- price
- discount_percent
- category_url
- source_page
- pincode
- location
- scanned_at

## Faster scan

After the first test is stable:

```powershell
python -m scraper.cli discount-monitor --threshold 60 --pages-per-category 5 --concurrency 8 --delay 0.25 --once
```

Increase concurrency gradually. Do not use very high concurrency; the goal is a fast and stable public-page scan, not to overwhelm the site.

## Continuous monitoring

Example: scan once every 30 minutes:

```powershell
python -m scraper.cli discount-monitor --threshold 60 --pages-per-category 2 --concurrency 8 --delay 0.5 --interval 30
```

## Important scope

The scanner works with publicly accessible offer pages. It cannot guarantee discovery of private, personalized, location-gated, non-indexed, or access-restricted inventory.
