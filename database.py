"""
Database Module for Account Information Storage

This module manages the SQLite database for storing account signup data,
including credentials, seed phrases, and session information.

Database: ACC_INFO.db
Tables:
    - accounts: Main account information
    - seed_phrases: Encrypted seed phrase storage
    - signup_logs: Audit trail for signup attempts
"""

import sqlite3
import os
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, asdict
import logging
import hashlib

logger = logging.getLogger(__name__)

# Database path
DB_PATH = Path(__file__).parent / "ACC_INFO.db"


@dataclass
class AccountRecord:
    """Represents a stored account."""
    id: Optional[int] = None
    email: str = ""
    password: str = ""
    first_name: str = ""
    last_name: str = ""
    birth_month: str = ""
    birth_day: int = 0
    birth_year: int = 0
    gender: str = ""
    seed_phrase: str = ""
    platform: str = ""
    status: str = "pending"  # pending, active, blocked, failed
    session_file: str = ""
    created_at: str = ""
    updated_at: str = ""
    notes: str = ""


class Database:
    """
    SQLite database manager for account storage.
    
    Usage:
        db = Database()
        db.initialize()
        
        # Save account
        account_id = db.save_account(
            email="test@atomicmail.io",
            password="SecurePass123!",
            first_name="John",
            last_name="Doe",
            seed_phrase="word1 word2 word3...",
            platform="atomicmail"
        )
        
        # Get account
        account = db.get_account(account_id)
    """
    
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = Path(db_path) if db_path else DB_PATH
        self._connection: Optional[sqlite3.Connection] = None
    
    def connect(self) -> sqlite3.Connection:
        """Get or create database connection."""
        if self._connection is None:
            self._connection = sqlite3.connect(
                str(self.db_path),
                check_same_thread=False
            )
            self._connection.row_factory = sqlite3.Row
        return self._connection
    
    def close(self):
        """Close database connection."""
        if self._connection:
            self._connection.close()
            self._connection = None
    
    def initialize(self):
        """Create database tables if they don't exist."""
        conn = self.connect()
        cursor = conn.cursor()
        
        # Main accounts table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                first_name TEXT,
                last_name TEXT,
                birth_month TEXT,
                birth_day INTEGER,
                birth_year INTEGER,
                gender TEXT,
                seed_phrase TEXT,
                platform TEXT DEFAULT 'unknown',
                status TEXT DEFAULT 'pending',
                session_file TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                notes TEXT
            )
        """)
        
        # Signup logs table for audit trail
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS signup_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id INTEGER,
                event_type TEXT NOT NULL,
                event_data TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (account_id) REFERENCES accounts(id)
            )
        """)
        
        # Index for faster lookups
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_accounts_email 
            ON accounts(email)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_accounts_platform 
            ON accounts(platform)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_accounts_status 
            ON accounts(status)
        """)
        
        conn.commit()
        logger.info(f"Database initialized at {self.db_path}")
    
    def save_account(
        self,
        email: str,
        password: str,
        first_name: str = "",
        last_name: str = "",
        birth_month: str = "",
        birth_day: int = 0,
        birth_year: int = 0,
        gender: str = "",
        seed_phrase: str = "",
        platform: str = "unknown",
        status: str = "pending",
        session_file: str = "",
        notes: str = ""
    ) -> int:
        """
        Save a new account to the database.
        
        Returns:
            The account ID of the inserted record.
        """
        conn = self.connect()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                INSERT INTO accounts (
                    email, password, first_name, last_name,
                    birth_month, birth_day, birth_year, gender,
                    seed_phrase, platform, status, session_file, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                email, password, first_name, last_name,
                birth_month, birth_day, birth_year, gender,
                seed_phrase, platform, status, session_file, notes
            ))
            
            conn.commit()
            account_id = cursor.lastrowid
            
            # Log the creation
            self._log_event(account_id, "created", {"email": email, "platform": platform})
            
            logger.info(f"Saved account: {email} (ID: {account_id})")
            return account_id
            
        except sqlite3.IntegrityError as e:
            logger.error(f"Account already exists: {email}")
            raise ValueError(f"Account with email {email} already exists") from e
    
    def update_account(
        self,
        account_id: int,
        **kwargs
    ):
        """
        Update an existing account.
        
        Args:
            account_id: The ID of the account to update
            **kwargs: Fields to update (email, password, status, seed_phrase, etc.)
        """
        if not kwargs:
            return
        
        conn = self.connect()
        cursor = conn.cursor()
        
        # Build update query
        set_clause = ", ".join([f"{key} = ?" for key in kwargs.keys()])
        values = list(kwargs.values()) + [account_id]
        
        cursor.execute(f"""
            UPDATE accounts 
            SET {set_clause}, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, values)
        
        conn.commit()
        
        # Log the update
        self._log_event(account_id, "updated", kwargs)
        
        logger.info(f"Updated account ID {account_id}: {list(kwargs.keys())}")
    
    def get_account(self, account_id: int) -> Optional[AccountRecord]:
        """Get an account by ID."""
        conn = self.connect()
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM accounts WHERE id = ?", (account_id,))
        row = cursor.fetchone()
        
        if row:
            return AccountRecord(**dict(row))
        return None
    
    def get_account_by_email(self, email: str) -> Optional[AccountRecord]:
        """Get an account by email."""
        conn = self.connect()
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM accounts WHERE email = ?", (email,))
        row = cursor.fetchone()
        
        if row:
            return AccountRecord(**dict(row))
        return None
    
    def get_all_accounts(
        self,
        platform: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100
    ) -> List[AccountRecord]:
        """Get all accounts with optional filtering."""
        conn = self.connect()
        cursor = conn.cursor()
        
        query = "SELECT * FROM accounts WHERE 1=1"
        params = []
        
        if platform:
            query += " AND platform = ?"
            params.append(platform)
        
        if status:
            query += " AND status = ?"
            params.append(status)
        
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        
        return [AccountRecord(**dict(row)) for row in rows]
    
    def delete_account(self, account_id: int):
        """Delete an account by ID."""
        conn = self.connect()
        cursor = conn.cursor()
        
        cursor.execute("DELETE FROM accounts WHERE id = ?", (account_id,))
        conn.commit()
        
        logger.info(f"Deleted account ID {account_id}")
    
    def _log_event(self, account_id: int, event_type: str, event_data: dict):
        """Log an event for audit trail."""
        conn = self.connect()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO signup_logs (account_id, event_type, event_data)
            VALUES (?, ?, ?)
        """, (account_id, event_type, json.dumps(event_data)))
        
        conn.commit()
    
    def get_logs(self, account_id: int) -> List[Dict[str, Any]]:
        """Get all logs for an account."""
        conn = self.connect()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT * FROM signup_logs 
            WHERE account_id = ? 
            ORDER BY timestamp DESC
        """, (account_id,))
        
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    
    def get_stats(self) -> Dict[str, Any]:
        """Get database statistics."""
        conn = self.connect()
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM accounts")
        total = cursor.fetchone()[0]
        
        cursor.execute("SELECT status, COUNT(*) FROM accounts GROUP BY status")
        by_status = dict(cursor.fetchall())
        
        cursor.execute("SELECT platform, COUNT(*) FROM accounts GROUP BY platform")
        by_platform = dict(cursor.fetchall())
        
        return {
            "total_accounts": total,
            "by_status": by_status,
            "by_platform": by_platform,
        }


# Singleton instance
_db_instance: Optional[Database] = None


def get_database() -> Database:
    """Get the singleton database instance."""
    global _db_instance
    if _db_instance is None:
        _db_instance = Database()
        _db_instance.initialize()
    return _db_instance


# =============================================================================
# CLI for database management
# =============================================================================

def main():
    """CLI for database management."""
    import sys
    
    db = get_database()
    
    if len(sys.argv) < 2:
        print("Usage: python database.py <command>")
        print("Commands:")
        print("  init     - Initialize database")
        print("  stats    - Show statistics")
        print("  list     - List all accounts")
        print("  export   - Export accounts to JSON")
        return
    
    command = sys.argv[1]
    
    if command == "init":
        db.initialize()
        print(f"Database initialized at {db.db_path}")
    
    elif command == "stats":
        stats = db.get_stats()
        print(f"Total accounts: {stats['total_accounts']}")
        print(f"By status: {stats['by_status']}")
        print(f"By platform: {stats['by_platform']}")
    
    elif command == "list":
        accounts = db.get_all_accounts()
        for acc in accounts:
            print(f"[{acc.id}] {acc.email} ({acc.platform}) - {acc.status}")
    
    elif command == "export":
        accounts = db.get_all_accounts()
        data = [asdict(acc) for acc in accounts]
        output_file = "accounts_export.json"
        with open(output_file, 'w') as f:
            json.dump(data, f, indent=2)
        print(f"Exported {len(accounts)} accounts to {output_file}")
    
    else:
        print(f"Unknown command: {command}")


if __name__ == "__main__":
    main()
