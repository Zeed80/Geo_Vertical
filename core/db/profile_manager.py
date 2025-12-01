import sqlite3
import logging
from typing import List, Dict, Optional, Any
from pathlib import Path

logger = logging.getLogger(__name__)

class ProfileManager:
    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            # Default to profiles.db in the same directory
            db_path = str(Path(__file__).parent / "profiles.db")
        # print(f"Using database at: {db_path}")
        self.db_path = db_path
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def _init_db(self):
        """Initialize the database schema."""
        create_table_sql = """
        CREATE TABLE IF NOT EXISTS profiles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            standard TEXT NOT NULL,
            type TEXT NOT NULL,
            designation TEXT NOT NULL,
            A REAL,          -- Area, cm2
            Ix REAL,         -- Moment of inertia X, cm4
            Iy REAL,         -- Moment of inertia Y, cm4
            Wx REAL,         -- Section modulus X, cm3
            Wy REAL,         -- Section modulus Y, cm3
            i_x REAL,        -- Radius of gyration X, cm
            i_y REAL,        -- Radius of gyration Y, cm
            mass_per_m REAL, -- kg/m
            d REAL,          -- Diameter or height, mm
            t REAL,          -- Thickness, mm
            b REAL,          -- Width, mm
            r REAL,          -- Radius (inner), mm
            UNIQUE(standard, designation)
        );
        """
        try:
            with self._get_connection() as conn:
                conn.execute(create_table_sql)
                
            # Check if empty and populate
            self._check_and_populate()
        except sqlite3.Error as e:
            logger.error(f"Failed to initialize database: {e}")

    def _check_and_populate(self):
        if not self.get_profiles_by_type("pipe"):
            # Import here to avoid circular dep if moved
            try:
                from core.db.init_db import populate_gost_8732, populate_gost_8509, populate_gost_8240
                populate_gost_8732(self)
                populate_gost_8509(self)
                populate_gost_8240(self)
            except ImportError:
                logger.warning("Could not auto-populate database: init_db module not found")

    def add_profile(self, profile_data: Dict[str, Any]) -> bool:
        """Add a new profile to the database."""
        keys = [
            "standard", "type", "designation", "A", "Ix", "Iy", "Wx", "Wy",
            "i_x", "i_y", "mass_per_m", "d", "t", "b", "r"
        ]
        columns = ", ".join(keys)
        placeholders = ", ".join(["?"] * len(keys))
        values = [profile_data.get(k) for k in keys]
        
        sql = f"INSERT OR REPLACE INTO profiles ({columns}) VALUES ({placeholders})"
        
        try:
            with self._get_connection() as conn:
                conn.execute(sql, values)
            return True
        except sqlite3.Error as e:
            logger.error(f"Failed to add profile {profile_data.get('designation')}: {e}")
            return False

    def get_profiles_by_type(self, profile_type: str) -> List[Dict[str, Any]]:
        """Get all profiles of a specific type."""
        sql = "SELECT * FROM profiles WHERE type = ? ORDER BY designation"
        try:
            with self._get_connection() as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute(sql, (profile_type,))
                return [dict(row) for row in cursor.fetchall()]
        except sqlite3.Error as e:
            logger.error(f"Failed to get profiles by type {profile_type}: {e}")
            return []

    def get_profile_by_designation(self, standard: str, designation: str) -> Optional[Dict[str, Any]]:
        """Get a specific profile."""
        sql = "SELECT * FROM profiles WHERE standard = ? AND designation = ?"
        try:
            with self._get_connection() as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute(sql, (standard, designation))
                row = cursor.fetchone()
                return dict(row) if row else None
        except sqlite3.Error as e:
            logger.error(f"Failed to get profile {designation}: {e}")
            return None

    def get_all_standards(self) -> List[str]:
        """Get list of available standards."""
        sql = "SELECT DISTINCT standard FROM profiles ORDER BY standard"
        try:
            with self._get_connection() as conn:
                cursor = conn.execute(sql)
                return [row[0] for row in cursor.fetchall()]
        except sqlite3.Error as e:
            logger.error(f"Failed to get standards: {e}")
            return []
