import requests
import sqlite3
import time
import logging
from datetime import datetime
from typing import List, Optional
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('scraper.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class WebScraper:
    """Web scraper with SQLite storage and exponential backoff"""
    
    def __init__(self, db_path: str = 'webpages.db', timeout: int = 10):
        """
        Initialize the scraper
        
        Args:
            db_path: Path to SQLite database
            timeout: Request timeout in seconds
        """
        self.db_path = db_path
        self.timeout = timeout
        self.session = self._create_session()
        self.setup_database()
    
    def _create_session(self) -> requests.Session:
        """Create a requests session with retry strategy"""
        session = requests.Session()
        
        # Configure retry strategy with exponential backoff
        retry_strategy = Retry(
            total=5,  # Total number of retries
            status_forcelist=[429, 500, 502, 503, 504],  # HTTP codes to retry on
            allowed_methods=["HEAD", "GET", "OPTIONS"],  # Methods to retry
            backoff_factor=1  # Exponential backoff: {backoff factor} * (2 ** ({number of total retries} - 1))
        )
        
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        
        # Set user agent to avoid being blocked
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        
        return session
    
    def setup_database(self) -> None:
        """Create SQLite database and table if they don't exist"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS pages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url TEXT UNIQUE,
                    html TEXT,
                    status_code INTEGER,
                    retrieved_at TIMESTAMP,
                    error_message TEXT
                )
            ''')
            
            conn.commit()
            conn.close()
            logger.info(f"Database initialized at {self.db_path}")
        except sqlite3.Error as e:
            logger.error(f"Database setup error: {e}")
            raise
    
    def fetch_page(self, url: str, max_retries: int = 3) -> Optional[tuple]:
        """
        Fetch a webpage with exponential backoff for rate limiting
        
        Args:
            url: URL to fetch
            max_retries: Maximum number of retries with exponential backoff
            
        Returns:
            Tuple of (html_content, status_code) or None if failed
        """
        retry_count = 0
        backoff_time = 1  # Start with 1 second
        
        while retry_count < max_retries:
            try:
                logger.info(f"Fetching: {url}")
                response = self.session.get(url, timeout=self.timeout)
                
                # Check for rate limiting (429) or server errors
                if response.status_code == 429:
                    # Extract retry-after header if available
                    retry_after = response.headers.get('Retry-After')
                    if retry_after:
                        wait_time = int(retry_after)
                        logger.warning(f"Rate limited. Waiting {wait_time} seconds...")
                        time.sleep(wait_time)
                    else:
                        # Use exponential backoff
                        logger.warning(f"Rate limited (429). Exponential backoff: {backoff_time}s")
                        time.sleep(backoff_time)
                        backoff_time *= 2  # Exponential increase
                    
                    retry_count += 1
                    continue
                
                # Success
                response.raise_for_status()
                logger.info(f"Successfully fetched {url} (Status: {response.status_code})")
                return (response.text, response.status_code)
            
            except requests.exceptions.Timeout:
                logger.error(f"Timeout error for {url}")
                return None
            
            except requests.exceptions.ConnectionError:
                logger.error(f"Connection error for {url}. Retrying with backoff...")
                time.sleep(backoff_time)
                backoff_time *= 2
                retry_count += 1
            
            except requests.exceptions.HTTPError as e:
                logger.error(f"HTTP error for {url}: {e}")
                return None
            
            except requests.exceptions.RequestException as e:
                logger.error(f"Request error for {url}: {e}")
                return None
        
        logger.error(f"Failed to fetch {url} after {max_retries} retries")
        return None
    
    def store_page(self, url: str, html: str, status_code: int, error_message: str = None) -> bool:
        """
        Store fetched page in database
        
        Args:
            url: The URL
            html: HTML content
            status_code: HTTP status code
            error_message: Error message if fetch failed
            
        Returns:
            True if successful, False otherwise
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT OR REPLACE INTO pages 
                (url, html, status_code, retrieved_at, error_message)
                VALUES (?, ?, ?, ?, ?)
            ''', (url, html, status_code, datetime.now(), error_message))
            
            conn.commit()
            conn.close()
            logger.info(f"Stored page: {url}")
            return True
        
        except sqlite3.Error as e:
            logger.error(f"Database error storing {url}: {e}")
            return False
    
    def scrape_urls(self, url_list: List[str], delay_between_requests: float = 1.0) -> None:
        """
        Scrape a list of URLs and store in database
        
        Args:
            url_list: List of URLs to scrape
            delay_between_requests: Delay in seconds between requests (respect robots.txt)
        """
        total_urls = len(url_list)
        successful = 0
        failed = 0
        
        logger.info(f"Starting to scrape {total_urls} URLs")
        
        for index, url in enumerate(url_list, 1):
            try:
                # Validate URL
                if not url.startswith(('http://', 'https://')):
                    logger.error(f"INVALID: {url} - URL must start with http:// or https://")
                    self.store_page(url, None, None, error_message="Invalid URL format")
                    failed += 1
                    continue
                
                # Fetch the page
                result = self.fetch_page(url)
                
                if result:
                    html_content, status_code = result
                    self.store_page(url, html_content, status_code)
                    successful += 1
                else:
                    logger.error(f"FAILED: {url} - Could not retrieve content after retries")
                    self.store_page(url, None, None, error_message="Failed to fetch")
                    failed += 1
                
                # Progress update
                logger.info(f"Progress: {index}/{total_urls} ({successful} successful, {failed} failed)")
                
                # Add delay between requests to be respectful
                if index < total_urls:
                    time.sleep(delay_between_requests)
            
            except Exception as e:
                logger.error(f"Unexpected error processing {url}: {e}")
                self.store_page(url, None, None, error_message=str(e))
                failed += 1
        
        logger.info(f"Scraping complete. Successful: {successful}, Failed: {failed}")
    
    def retrieve_page(self, url: str) -> Optional[str]:
        """
        Retrieve stored HTML for a URL from database
        
        Args:
            url: The URL to retrieve
            
        Returns:
            HTML content or None if not found
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('SELECT html FROM pages WHERE url = ?', (url,))
            result = cursor.fetchone()
            conn.close()
            
            if result:
                return result[0]
            else:
                logger.warning(f"No stored page found for {url}")
                return None
        
        except sqlite3.Error as e:
            logger.error(f"Database error retrieving {url}: {e}")
            return None
    
    def get_stats(self) -> dict:
        """Get statistics about stored pages"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('SELECT COUNT(*) FROM pages')
            total = cursor.fetchone()[0]
            
            cursor.execute('SELECT COUNT(*) FROM pages WHERE html IS NOT NULL')
            successful = cursor.fetchone()[0]
            
            cursor.execute('SELECT COUNT(*) FROM pages WHERE html IS NULL')
            failed = cursor.fetchone()[0]
            
            conn.close()
            
            return {
                'total_urls': total,
                'successful': successful,
                'failed': failed
            }
        
        except sqlite3.Error as e:
            logger.error(f"Error getting stats: {e}")
            return {}


# Example usage
if __name__ == "__main__":
    # List of URLs to scrape
    url_list = [
        'https://example.com',
        'https://www.python.org',
        'https://www.github.com',
        'https://www.stackoverflow.com',
        'https://www.wikipedia.org'
    ]
    
    # Create scraper instance
    scraper = WebScraper(db_path='webpages.db', timeout=10)
    
    # Scrape all URLs with 2-second delay between requests
    scraper.scrape_urls(url_list, delay_between_requests=2.0)
    
    # Print statistics
    stats = scraper.get_stats()
    print(f"\nStatistics:")
    print(f"Total URLs: {stats['total_urls']}")
    print(f"Successful: {stats['successful']}")
    print(f"Failed: {stats['failed']}")
    
    # Retrieve a stored page
    retrieved_html = scraper.retrieve_page('https://example.com')
    if retrieved_html:
        print(f"\nRetrieved HTML length: {len(retrieved_html)} characters")