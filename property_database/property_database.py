import json
import sqlite3
import logging
from datetime import datetime
from typing import Optional

# Configure logging (reuse if already configured, or set up here)
logger = logging.getLogger(__name__)

# Column name -> SQLite type, derived from the parsed listing dictionary.
# List-valued keys (external_links, top_4_features) are deliberately excluded.
PROPERTY_DETAILS_SCHEMA = {
    'id': 'INTEGER PRIMARY KEY',
    'url': 'TEXT',
    'latitude': 'REAL',
    'longitude': 'REAL',
    'street_address': 'TEXT',
    'suburb': 'TEXT',
    'postcode': 'TEXT',
    'state': 'TEXT',
    'activated_at': 'TEXT',
    'weekly_rent_number': 'INTEGER',
    'property_type': 'TEXT',
    'bedrooms': 'INTEGER',
    'bathrooms': 'INTEGER',
    'ensuites': 'INTEGER',
    'car_spaces': 'INTEGER',
    'furnished': 'INTEGER',
    'partially_furnished': 'INTEGER',
    'pets_allowed': 'INTEGER',
    'long_term_lease': 'INTEGER',
    'is_build_to_rent': 'INTEGER',
    'features': 'TEXT',
    'n_photos': 'INTEGER',
    'walkability_score': 'TEXT',
}


class PropertyDatabase:
    """
    Simple interface for storing parsed property listings in SQLite.
    
    Handles all database setup, encoding, and validation automatically.
    Non-technical users just need to: instantiate once, call save() for each listing.
    """
    
    def __init__(self, db_path: str = 'data/properties_db/properties.db'):
        """
        Initialize the property database
        
        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        self._setup_table()
        logger.info(f"PropertyDatabase initialized at {db_path}")
    
    def _setup_table(self) -> None:
        """Create the property_details table if it doesn't exist"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            columns = ', '.join(
                f'{name} {dtype}' for name, dtype in PROPERTY_DETAILS_SCHEMA.items()
            )
            cursor.execute(f'''
                CREATE TABLE IF NOT EXISTS property_details (
                    {columns},
                    added_at TIMESTAMP
                )
            ''')
            
            conn.commit()
            conn.close()
            logger.info(f"property_details table ready in {self.db_path}")
        except sqlite3.Error as e:
            logger.error(f"Database setup error for property_details: {e}")
            raise
    
    @staticmethod
    def _encode_value(value):
        """Convert a parsed value into something SQLite can store"""
        if isinstance(value, dict):
            return json.dumps(value, sort_keys=True)
        if isinstance(value, bool):
            return int(value)
        return value
    
    @staticmethod
    def _sqlite_type(value) -> str:
        """Best-guess SQLite type for a value not covered by the schema"""
        if isinstance(value, bool) or isinstance(value, int):
            return 'INTEGER'
        if isinstance(value, float):
            return 'REAL'
        return 'TEXT'
    
    def save(self, listing_data: Optional[dict]) -> bool:
        """
        Save a parsed listing to the database.
        
        This is the main method your teammates will use. It handles:
        - Validation (checks for required id field)
        - Encoding (converts bools to ints, dicts to JSON)
        - Schema evolution (auto-adds new columns if needed)
        - Error handling (logs errors, doesn't crash)
        
        Args:
            listing_data: Dictionary returned by parse_html()
            
        Returns:
            True if successful, False otherwise
        """
        if not listing_data or not listing_data.get('id'):
            logger.warning("Skipping listing with no id")
            return False
        
        # Skip list-valued fields (external_links, top_4_features, etc.)
        row = {
            k: self._encode_value(v) 
            for k, v in listing_data.items() 
            if not isinstance(v, list)
        }
        
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Add any new columns this listing has that the table doesn't know about
            # (schema evolution: handles unexpected fields gracefully)
            cursor.execute('PRAGMA table_info(property_details)')
            existing_columns = {info[1] for info in cursor.fetchall()}
            
            for key in row:
                if key not in existing_columns:
                    logger.info(f"Adding new column to property_details: {key}")
                    cursor.execute(
                        f'ALTER TABLE property_details '
                        f'ADD COLUMN {key} {self._sqlite_type(listing_data[key])}'
                    )
            
            # Insert the row
            row['added_at'] = datetime.now()
            columns = ', '.join(row.keys())
            placeholders = ', '.join('?' for _ in row)
            
            cursor.execute(f'''
                INSERT OR REPLACE INTO property_details ({columns})
                VALUES ({placeholders})
            ''', tuple(row.values()))
            
            conn.commit()
            conn.close()
            logger.info(f"Stored property listing: {listing_data['id']}")
            return True
        
        except sqlite3.Error as e:
            logger.error(f"Database error storing property {listing_data.get('id')}: {e}")
            return False
    
    def get_count(self) -> int:
        """Get total number of listings stored"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(*) FROM property_details')
            count = cursor.fetchone()[0]
            conn.close()
            return count
        except sqlite3.Error as e:
            logger.error(f"Error getting count: {e}")
            return 0