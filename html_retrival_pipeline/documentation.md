# WebScraper Documentation

**Last Updated:** September 2026

---

## Features

- **Efficient HTTP Requests** - Built-in session management with connection pooling
- **Automatic Retry Logic** - Handles transient failures with exponential backoff
- **Rate Limit Handling** - Respects HTTP 429 responses and Retry-After headers
- **Persistent Storage** - SQLite database for storing scraped content
- **Error Handling** - Comprehensive error logging and recovery
- **Progress Tracking** - Real-time statistics and monitoring
- **Respectful Scraping** - Configurable delays between requests

---

## Installation

### Requirements

- Python 3.7+
- `requests` >= 2.31.0
- `urllib3` >= 2.0.0

### Setup

```bash
pip install requests urllib3
```

Or using requirements.txt:

```bash
pip install -r requirements.txt
```

---

## Quick Start

```python
from web_scraper import WebScraper

# Initialize the scraper
scraper = WebScraper(db_path='webpages.db', timeout=10)

# Define URLs to scrape
urls = [
    'https://example.com',
    'https://python.org',
    'https://github.com'
]

# Scrape all URLs
scraper.scrape_urls(urls, delay_between_requests=2.0)

# View statistics
stats = scraper.get_stats()
print(f"Successful: {stats['successful']}, Failed: {stats['failed']}")

# Retrieve stored content
html = scraper.retrieve_page('https://example.com')
```

---

## API Reference

### Class: `WebScraper`

Main class for managing web scraping operations.

#### Constructor

```python
WebScraper(db_path: str = 'webpages.db', timeout: int = 10)
```

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `db_path` | `str` | `'webpages.db'` | Path to SQLite database file |
| `timeout` | `int` | `10` | Request timeout in seconds |

**Example:**

```python
scraper = WebScraper(db_path='my_pages.db', timeout=15)
```

---

### Methods

#### `scrape_urls()`

Scrapes a list of URLs and stores HTML content in the database.

```python
def scrape_urls(
    url_list: List[str], 
    delay_between_requests: float = 1.0
) -> None
```

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `url_list` | `List[str]` | Required | List of URLs to scrape |
| `delay_between_requests` | `float` | `1.0` | Delay in seconds between requests (respectful scraping) |

**Returns:** `None`

**Raises:**
- No exceptions raised; errors are logged

**Example:**

```python
urls = [
    'https://example.com',
    'https://example.com/page1',
    'https://example.com/page2'
]

scraper.scrape_urls(urls, delay_between_requests=2.0)
```

**Behavior:**
- Validates URL format
- Retries on rate limits (HTTP 429)
- Uses exponential backoff for failed requests
- Logs progress to both console and file
- Stores results in database

---

#### `fetch_page()`

Fetches a single webpage with automatic retry and exponential backoff.

```python
def fetch_page(
    url: str, 
    max_retries: int = 3
) -> Optional[tuple]
```

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `url` | `str` | Required | URL to fetch |
| `max_retries` | `int` | `3` | Maximum retry attempts |

**Returns:** 
- `tuple` - `(html_content: str, status_code: int)` on success
- `None` - on failure

**Raises:** No exceptions; errors are logged

**Example:**

```python
result = scraper.fetch_page('https://example.com')

if result:
    html, status = result
    print(f"Status: {status}")
    print(f"Content length: {len(html)}")
else:
    print("Failed to fetch page")
```

**Retry Strategy:**
- Retries on HTTP 429 (Rate Limited)
- Retries on connection errors
- Exponential backoff: 1s → 2s → 4s → 8s → 16s
- Respects Retry-After header if provided

---

#### `store_page()`

Stores fetched page data in the SQLite database.

```python
def store_page(
    url: str, 
    html: str, 
    status_code: int, 
    error_message: str = None
) -> bool
```

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `url` | `str` | Required | URL of the page |
| `html` | `str` | Required | HTML content (can be None if failed) |
| `status_code` | `int` | Required | HTTP status code |
| `error_message` | `str` | `None` | Error message if fetch failed |

**Returns:** 
- `bool` - `True` if successfully stored, `False` otherwise

**Example:**

```python
success = scraper.store_page(
    url='https://example.com',
    html='<html>...</html>',
    status_code=200,
    error_message=None
)

if success:
    print("Page stored successfully")
else:
    print("Failed to store page")
```

---

#### `retrieve_page()`

Retrieves stored HTML content from the database.

```python
def retrieve_page(url: str) -> Optional[str]
```

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `url` | `str` | URL to retrieve |

**Returns:**
- `str` - HTML content if found
- `None` - if URL not in database

**Example:**

```python
html = scraper.retrieve_page('https://example.com')

if html:
    print(f"Retrieved {len(html)} characters")
    print(html[:500])  # First 500 chars
else:
    print("URL not found in database")
```

---

#### `get_stats()`

Returns statistics about stored pages.

```python
def get_stats() -> dict
```

**Returns:** 
- `dict` with keys:
  - `total_urls` - Total URLs processed
  - `successful` - URLs with successful content
  - `failed` - URLs with errors

**Example:**

```python
stats = scraper.get_stats()
print(f"Total: {stats['total_urls']}")
print(f"Successful: {stats['successful']}")
print(f"Failed: {stats['failed']}")
print(f"Success rate: {stats['successful']/stats['total_urls']*100:.1f}%")
```

---

#### `setup_database()`

Initializes the SQLite database and creates required tables.

```python
def setup_database() -> None
```

**Returns:** `None`

**Raises:**
- `sqlite3.Error` - If database creation fails

**Note:** Called automatically in `__init__`, rarely needs manual invocation.

**Example:**

```python
scraper.setup_database()  # Reinitialize database
```

---

## Database Schema

The WebScraper stores data in a SQLite table with the following structure:

```sql
CREATE TABLE pages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT UNIQUE,
    html TEXT,
    status_code INTEGER,
    retrieved_at TIMESTAMP,
    error_message TEXT
)
```

**Columns:**

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER | Unique identifier |
| `url` | TEXT | URL (unique constraint) |
| `html` | TEXT | Raw HTML content |
| `status_code` | INTEGER | HTTP status code |
| `retrieved_at` | TIMESTAMP | Retrieval timestamp |
| `error_message` | TEXT | Error description (if failed) |

---

## Error Handling

WebScraper handles various error scenarios gracefully:

### Timeout Errors
```python
# Handled automatically; logged and skipped
# Timeout duration configurable via `timeout` parameter
```

### Connection Errors
```python
# Retried with exponential backoff
# Max 3 attempts by default (configurable)
```

### Rate Limiting (HTTP 429)
```python
# Automatically respected
# Waits for Retry-After header or uses backoff
# Exponential backoff: 1s → 2s → 4s → 8s → 16s
```

### Invalid URLs
```python
# Validated before fetching
# Skipped if missing http:// or https://
# Logged as warnings
```

### Database Errors
```python
# Logged with details
# Operation fails gracefully
# No data corruption
```

All errors are logged to:
- Console (stdout)
- File (`scraper.log`)

---

## Logging

WebScraper produces detailed logs at multiple levels:

### Log File Location
```
./scraper.log
```

### Log Format
```
2026-09-06 10:30:45,123 - INFO - Fetching: https://example.com
2026-09-06 10:30:46,456 - INFO - Successfully fetched https://example.com (Status: 200)
2026-09-06 10:30:47,789 - INFO - Stored page: https://example.com
2026-09-06 10:30:48,012 - WARNING - Rate limited (429). Exponential backoff: 2s
2026-09-06 10:30:50,345 - ERROR - Failed to fetch https://bad-url.com after 3 retries
```

### Log Levels

| Level | When Used |
|-------|-----------|
| INFO | Normal operations, successful requests |
| WARNING | Rate limiting, invalid URLs, retries |
| ERROR | Failed requests, database errors |

---

## Advanced Usage

### Custom Timeout

```python
# Longer timeout for slow servers
scraper = WebScraper(timeout=30)
scraper.scrape_urls(urls)
```

### Process Large URL Lists

```python
# Split into batches to monitor progress
urls = ['https://...'] * 1000

batch_size = 100
for i in range(0, len(urls), batch_size):
    batch = urls[i:i+batch_size]
    scraper.scrape_urls(batch, delay_between_requests=1.0)
    stats = scraper.get_stats()
    print(f"Processed {stats['total_urls']} URLs")
```

### Respectful Scraping

```python
# Increase delay to be kind to servers
scraper.scrape_urls(urls, delay_between_requests=5.0)
```

### Process Scraped Data

```python
from bs4 import BeautifulSoup

scraper = WebScraper()
html = scraper.retrieve_page('https://example.com')

if html:
    soup = BeautifulSoup(html, 'html.parser')
    
    # Extract specific elements
    titles = soup.find_all('h1')
    links = soup.find_all('a')
    
    for title in titles:
        print(title.text)
```

---

## Best Practices

### 1. Respect Rate Limits
```python
# Always include delays
scraper.scrape_urls(urls, delay_between_requests=2.0)
```

### 2. Check Statistics
```python
stats = scraper.get_stats()
if stats['failed'] > 0:
    print(f"Warning: {stats['failed']} URLs failed to fetch")
```

### 3. Monitor Logs
```bash
# Watch logs in real-time
tail -f scraper.log
```

### 4. Validate URLs
```python
urls = ['https://example.com', 'not-a-url.com']  # Bad URL
# The scraper will skip the invalid URL and log a warning
```

### 5. Handle Large Datasets
```python
# Process in batches to avoid memory issues
urls = load_urls_from_file('urls.txt')  # 100k URLs

for batch in batch_urls(urls, size=500):
    scraper.scrape_urls(batch)
```

---

## Performance Considerations

### Memory Usage
- HTML content stored in database (not memory)
- Suitable for millions of pages
- Database file grows ~1KB per 1KB of HTML

### Request Speed
- Concurrent requests not supported
- Sequential processing
- Typical: ~1-2 requests per second
- Adjustable via `delay_between_requests`

### Database Size
```python
# Query database size
import os
size_mb = os.path.getsize('webpages.db') / (1024 * 1024)
print(f"Database size: {size_mb:.2f} MB")
```

---

## Troubleshooting

### Issue: All requests timing out

**Solution:** Increase timeout
```python
scraper = WebScraper(timeout=30)
```

### Issue: Getting rate limited frequently

**Solution:** Increase delay between requests
```python
scraper.scrape_urls(urls, delay_between_requests=5.0)
```

### Issue: Database file growing too large

**Solution:** Archive old data or split into multiple databases
```python
import shutil
shutil.copy('webpages.db', f'archive/webpages_{date}.db')
```

### Issue: URL returns 404 but stored as failed

**Solution:** This is correct behavior; check error_message field
```python
conn = sqlite3.connect('webpages.db')
cursor = conn.cursor()
cursor.execute('SELECT url, error_message FROM pages WHERE status_code IS NULL')
print(cursor.fetchall())
```

---

## Examples

### Example 1: Scrape Real Estate Listings

```python
from web_scraper import WebScraper

# URLs of properties to scrape
property_urls = [
    'https://www.rent.com.au/property/123456',
    'https://www.rent.com.au/property/789012',
    'https://www.rent.com.au/property/345678',
]

scraper = WebScraper(db_path='properties.db')
scraper.scrape_urls(property_urls, delay_between_requests=2.0)

stats = scraper.get_stats()
print(f"Scraped {stats['successful']} properties successfully")
```

### Example 2: Extract Data from Stored HTML

```python
from web_scraper import WebScraper
from bs4 import BeautifulSoup

scraper = WebScraper()

# Retrieve and parse
html = scraper.retrieve_page('https://example.com')
soup = BeautifulSoup(html, 'html.parser')

# Extract price
price = soup.find('div', class_='price')
print(f"Price: {price.text if price else 'N/A'}")

# Extract all paragraphs
paragraphs = soup.find_all('p')
for p in paragraphs:
    print(p.text)
```
