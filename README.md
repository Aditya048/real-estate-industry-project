# [MAST30034] Real Estate Industry Project (Group 4)

## Web Scraping Pipeline - Sprint 1

**Flow:** `url_retrieval` → `html_retrieval` → `html_parser` → `geospatial`

| Module | Owner |
|---|---|
| `url_retrieval.py` | Sean |
| `html_retrieval.py` | Aydin |
| `html_parser.py` | Aditya |
| `geospatial.py` | Ben |

### `url_retrieval.py`

### `html_retrieval.py`
Contains code to take HTML code from every web page specified by a list of URLs.
It is presented as a `WebScraper` class and handles rate limiting and general
error handling. 
**Packages required for this code to work**
- `requests`
- `urllib3`
All other packages (like `sqlite3` and `logging`) are built into Python.
### `html_parser.py`

### `geospatial.py`
