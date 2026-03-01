# Database migrations for schema updates
# This module handles adding new columns/tables to existing databases

from sqlalchemy import text, inspect
from .database import engine
import logging

logger = logging.getLogger(__name__)


def run_migrations():
    """Run all pending migrations"""
    with engine.connect() as conn:
        inspector = inspect(engine)
        existing_tables = inspector.get_table_names()

        # Migration 1: Add accounts table if not exists
        if 'accounts' not in existing_tables:
            logger.info("Migration: Creating accounts table")
            conn.execute(text("""
                CREATE TABLE accounts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    iban VARCHAR(34) UNIQUE,
                    name VARCHAR(100),
                    bank_name VARCHAR(100),
                    account_type VARCHAR(20) DEFAULT 'giro',
                    owner_name VARCHAR(200),
                    is_active BOOLEAN DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
            conn.commit()
            logger.info("Migration: accounts table created")

        # Migration 2: Add account_id column to transactions if not exists
        if 'transactions' in existing_tables:
            columns = [col['name'] for col in inspector.get_columns('transactions')]

            if 'account_id' not in columns:
                logger.info("Migration: Adding account_id to transactions")
                conn.execute(text("""
                    ALTER TABLE transactions ADD COLUMN account_id INTEGER REFERENCES accounts(id)
                """))
                conn.commit()
                logger.info("Migration: account_id column added")

        # Migration 3: Add account_id column to imports if not exists
        if 'imports' in existing_tables:
            columns = [col['name'] for col in inspector.get_columns('imports')]

            if 'account_id' not in columns:
                logger.info("Migration: Adding account_id to imports")
                conn.execute(text("""
                    ALTER TABLE imports ADD COLUMN account_id INTEGER REFERENCES accounts(id)
                """))
                conn.commit()
                logger.info("Migration: account_id column added to imports")

        # Migration 4: Add profiles table and profile support
        if 'profiles' not in existing_tables:
            logger.info("Migration: Creating profiles table")
            conn.execute(text("""
                CREATE TABLE profiles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name VARCHAR(100) UNIQUE NOT NULL,
                    color VARCHAR(20) DEFAULT '#2563eb',
                    is_admin BOOLEAN DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
            conn.commit()
            logger.info("Migration: profiles table created")

            # Refresh inspector to see new table
            inspector = inspect(engine)

        # Ensure default admin profile exists (also handles case where table was created by init_db)
        result = conn.execute(text("SELECT COUNT(*) FROM profiles WHERE is_admin = 1"))
        admin_count = result.scalar()
        if admin_count == 0:
            conn.execute(text("""
                INSERT INTO profiles (name, color, is_admin, created_at) VALUES ('Admin', '#2563eb', 1, CURRENT_TIMESTAMP)
            """))
            conn.commit()
            logger.info("Migration: Default admin profile created")

        # Fix any profiles with NULL created_at
        conn.execute(text("""
            UPDATE profiles SET created_at = CURRENT_TIMESTAMP WHERE created_at IS NULL
        """))
        conn.commit()

        # Migration 5: Add profile_id to accounts
        if 'accounts' in existing_tables:
            columns = [col['name'] for col in inspector.get_columns('accounts')]
            if 'profile_id' not in columns:
                logger.info("Migration: Adding profile_id to accounts")
                conn.execute(text("""
                    ALTER TABLE accounts ADD COLUMN profile_id INTEGER REFERENCES profiles(id)
                """))
                # Assign all existing accounts to the default admin profile
                conn.execute(text("""
                    UPDATE accounts SET profile_id = (SELECT id FROM profiles WHERE is_admin = 1 LIMIT 1)
                """))
                conn.commit()
                logger.info("Migration: profile_id added to accounts")

        # Assign unassigned accounts to admin profile
        if 'accounts' in existing_tables:
            conn.execute(text("""
                UPDATE accounts SET profile_id = (SELECT id FROM profiles WHERE is_admin = 1 LIMIT 1)
                WHERE profile_id IS NULL
            """))
            conn.commit()

        # Migration 6: Add is_shared to transactions
        if 'transactions' in existing_tables:
            columns = [col['name'] for col in inspector.get_columns('transactions')]
            if 'is_shared' not in columns:
                logger.info("Migration: Adding is_shared to transactions")
                conn.execute(text("""
                    ALTER TABLE transactions ADD COLUMN is_shared BOOLEAN DEFAULT 0
                """))
                conn.commit()
                logger.info("Migration: is_shared added to transactions")

        # Migration 7: Add assign_shared to categorization_rules
        if 'categorization_rules' in existing_tables:
            columns = [col['name'] for col in inspector.get_columns('categorization_rules')]
            if 'assign_shared' not in columns:
                logger.info("Migration: Adding assign_shared to categorization_rules")
                conn.execute(text("""
                    ALTER TABLE categorization_rules ADD COLUMN assign_shared BOOLEAN DEFAULT 0
                """))
                conn.commit()
                logger.info("Migration: assign_shared added to categorization_rules")

        # Migration 8: Add users table
        if 'users' not in existing_tables:
            logger.info("Migration: Creating users table")
            conn.execute(text("""
                CREATE TABLE users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email VARCHAR(255) UNIQUE NOT NULL,
                    hashed_password VARCHAR(255) NOT NULL,
                    display_name VARCHAR(100) NOT NULL,
                    is_active BOOLEAN DEFAULT 1,
                    is_admin BOOLEAN DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
            conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_users_email ON users(email)"))
            conn.commit()
            logger.info("Migration: users table created")
            # Refresh inspector
            inspector = inspect(engine)

        # Migration 9: Add user_id to accounts, categories, categorization_rules
        for table_name in ['accounts', 'categories', 'categorization_rules']:
            if table_name in inspector.get_table_names():
                columns = [col['name'] for col in inspector.get_columns(table_name)]
                if 'user_id' not in columns:
                    logger.info(f"Migration: Adding user_id to {table_name}")
                    conn.execute(text(
                        f"ALTER TABLE {table_name} ADD COLUMN user_id INTEGER REFERENCES users(id)"
                    ))
                    conn.commit()
                    logger.info(f"Migration: user_id added to {table_name}")

        # Migration 10: Add user_id to imports
        if 'imports' in inspector.get_table_names():
            columns = [col['name'] for col in inspector.get_columns('imports')]
            if 'user_id' not in columns:
                logger.info("Migration: Adding user_id to imports")
                conn.execute(text(
                    "ALTER TABLE imports ADD COLUMN user_id INTEGER REFERENCES users(id)"
                ))
                conn.commit()
                logger.info("Migration: user_id added to imports")

        # Migration 10a: Link orphaned transactions to accounts by IBAN
        if 'transactions' in existing_tables and 'accounts' in existing_tables:
            tx_cols = [col['name'] for col in inspector.get_columns('transactions')]
            if 'account_id' in tx_cols and 'account_iban' in tx_cols:
                result = conn.execute(text("""
                    UPDATE transactions SET account_id = (
                        SELECT accounts.id FROM accounts WHERE accounts.iban = transactions.account_iban
                    )
                    WHERE transactions.account_id IS NULL AND transactions.account_iban IS NOT NULL
                """))
                if result.rowcount > 0:
                    logger.info(f"Migration: Linked {result.rowcount} orphaned transactions to accounts by IBAN")
                conn.commit()

        # Migration 10b: Assign orphaned accounts/categories/rules to first admin user
        first_admin = conn.execute(text(
            "SELECT id FROM users WHERE is_admin = 1 ORDER BY id LIMIT 1"
        )).fetchone()
        if first_admin:
            admin_id = first_admin[0]
            for table_name in ['accounts', 'categories', 'categorization_rules']:
                if table_name in inspector.get_table_names():
                    columns = [col['name'] for col in inspector.get_columns(table_name)]
                    if 'user_id' in columns:
                        result = conn.execute(text(
                            f"UPDATE {table_name} SET user_id = :admin_id WHERE user_id IS NULL"
                        ), {"admin_id": admin_id})
                        if result.rowcount > 0:
                            logger.info(f"Migration: Assigned {result.rowcount} orphaned {table_name} to admin user {admin_id}")
            conn.commit()

        # Migration 11: Add households table
        if 'households' not in inspector.get_table_names():
            logger.info("Migration: Creating households table")
            conn.execute(text("""
                CREATE TABLE households (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name VARCHAR(200) NOT NULL,
                    created_by INTEGER NOT NULL REFERENCES users(id),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
            conn.commit()
            logger.info("Migration: households table created")
            inspector = inspect(engine)

        # Migration 12: Add household_members table
        if 'household_members' not in inspector.get_table_names():
            logger.info("Migration: Creating household_members table")
            conn.execute(text("""
                CREATE TABLE household_members (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    household_id INTEGER NOT NULL REFERENCES households(id),
                    user_id INTEGER NOT NULL REFERENCES users(id),
                    role VARCHAR(20) DEFAULT 'member',
                    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
            conn.commit()
            logger.info("Migration: household_members table created")
            inspector = inspect(engine)

        # Migration 13: Add household_invites table
        if 'household_invites' not in inspector.get_table_names():
            logger.info("Migration: Creating household_invites table")
            conn.execute(text("""
                CREATE TABLE household_invites (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    household_id INTEGER NOT NULL REFERENCES households(id),
                    invited_by INTEGER NOT NULL REFERENCES users(id),
                    invited_email VARCHAR(255) NOT NULL,
                    status VARCHAR(20) DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
            conn.commit()
            logger.info("Migration: household_invites table created")

        logger.info("All migrations completed")
