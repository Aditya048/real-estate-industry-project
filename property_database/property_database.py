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
    """SQLite store for parsed property listings."""
    
    def __init__(self, db_path: str = 'data/properties_db/properties.db'):
        """Create or open the property database.

        Args:
            db_path: Path to the SQLite database file.
        """
        self.db_path = db_path
        self._setup_table()
        logger.info(f"PropertyDatabase initialized at {db_path}")
    
    def _setup_table(self) -> None:
        """Create the property_details table if it does not exist."""
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
        """Convert a parsed value into a SQLite-storable form."""
        if isinstance(value, dict):
            return json.dumps(value, sort_keys=True)
        if isinstance(value, bool):
            return int(value)
        return value
    
    @staticmethod
    def _sqlite_type(value) -> str:
        """Infer a SQLite type for a value outside the fixed schema."""
        if isinstance(value, bool) or isinstance(value, int):
            return 'INTEGER'
        if isinstance(value, float):
            return 'REAL'
        return 'TEXT'
    
    def save(self, listing_data: Optional[dict]) -> bool:
        """Save a parsed listing, adding columns if needed.

        Args:
            listing_data: Dictionary from parse_html().

        Returns:
            True on success, False otherwise.
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
        """Return the number of stored listings."""
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

    def export_csv(self, csv_path: str = 'data/properties_db/properties.csv') -> str:
        """Export property_details to a CSV file.

        Args:
            csv_path: Destination CSV path.

        Returns:
            Path string of the written file.
        """
        import csv
        from pathlib import Path

        path = Path(csv_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM property_details')
            rows = cursor.fetchall()
            conn.close()
        except sqlite3.Error as e:
            logger.error(f"Error exporting CSV: {e}")
            raise

        if not rows:
            path.write_text('')
            logger.warning(f"No rows to export; wrote empty file at {path}")
            return str(path)

        fieldnames = list(rows[0].keys())
        with open(path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                writer.writerow(dict(row))

        logger.info(f"Exported {len(rows)} listings to {path}")
        return str(path)