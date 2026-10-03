import sqlite3
import sys
from pathlib import Path
from datetime import datetime

# Adds the project root to sys.path so `from backend.paths import ...` works
# whether this file is imported as `database.database` (dev mode) or loaded
# directly by a frozen .exe.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backend.paths import app_data_path

DB_PATH = app_data_path("voxtranslate.db")


def create_database():
    connection = sqlite3.connect(DB_PATH, timeout=30)
    cursor = connection.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS translations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_language TEXT NOT NULL,
            target_language TEXT NOT NULL,
            original_text TEXT NOT NULL,
            translated_text TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    # Per-user history (older rows keep username NULL and stay private).
    cursor.execute("PRAGMA table_info(translations)")
    if "username" not in [c[1] for c in cursor.fetchall()]:
        try:
            cursor.execute("ALTER TABLE translations ADD COLUMN username TEXT")
        except sqlite3.OperationalError:
            pass  # another server worker added it at the same moment

    # Login/Register users. Email is used for password recovery.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            email TEXT,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    # Upgrade older VoxTranslate databases that were created before
    # email-based password recovery was added.
    columns = [row[1] for row in cursor.execute("PRAGMA table_info(users)").fetchall()]
    if "email" not in columns:
        cursor.execute("ALTER TABLE users ADD COLUMN email TEXT")

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_users_email
        ON users(email)
    """)

    # Password-reset OTPs are stored hashed and expire after a short period.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS password_reset_otps (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            otp_hash TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            attempts INTEGER NOT NULL DEFAULT 0,
            used INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    """)

    connection.commit()
    connection.close()

    print("Database created successfully!")


# ---------------- Auth functions ----------------

def register_user(username, email, password_hash):
    """
    Insert a new user. password_hash must already be hashed.
    Returns (True, "") on success or (False, error_message) on failure.
    """
    connection = sqlite3.connect(DB_PATH, timeout=30)
    cursor = connection.cursor()

    created_at = datetime.now().strftime("%d-%m-%Y %I:%M:%S %p")

    try:
        cursor.execute("""
            INSERT INTO users (username, email, password_hash, created_at)
            VALUES (?, ?, ?, ?)
        """, (username, email, password_hash, created_at))

        connection.commit()
        return True, ""

    except sqlite3.IntegrityError as exc:
        message = str(exc).lower()
        if "username" in message:
            return False, "Username already exists."
        return False, "An account with these details already exists."

    finally:
        connection.close()


def get_user(username):
    """
    Returns (id, username, email, password_hash, created_at) or None.
    """
    connection = sqlite3.connect(DB_PATH, timeout=30)
    cursor = connection.cursor()

    cursor.execute("""
        SELECT id, username, email, password_hash, created_at
        FROM users
        WHERE username = ?
    """, (username,))

    row = cursor.fetchone()
    connection.close()

    return row


def get_user_by_email(email):
    """
    Returns (id, username, email, password_hash, created_at) or None.
    Email matching is case-insensitive.
    """
    connection = sqlite3.connect(DB_PATH, timeout=30)
    cursor = connection.cursor()

    cursor.execute("""
        SELECT id, username, email, password_hash, created_at
        FROM users
        WHERE lower(email) = lower(?)
        LIMIT 1
    """, (email.strip(),))

    row = cursor.fetchone()
    connection.close()

    return row


def save_password_reset_otp(user_id, otp_hash, expires_at):
    """Invalidate previous OTPs for the user and store a new hashed OTP."""
    connection = sqlite3.connect(DB_PATH, timeout=30)
    cursor = connection.cursor()

    created_at = datetime.now().strftime("%d-%m-%Y %I:%M:%S %p")

    cursor.execute("""
        UPDATE password_reset_otps
        SET used = 1
        WHERE user_id = ? AND used = 0
    """, (user_id,))

    cursor.execute("""
        INSERT INTO password_reset_otps
        (user_id, otp_hash, expires_at, attempts, used, created_at)
        VALUES (?, ?, ?, 0, 0, ?)
    """, (user_id, otp_hash, expires_at, created_at))

    connection.commit()
    connection.close()


def get_active_password_reset_otp(user_id):
    """Return the newest unused OTP row for a user."""
    connection = sqlite3.connect(DB_PATH, timeout=30)
    cursor = connection.cursor()

    cursor.execute("""
        SELECT id, user_id, otp_hash, expires_at, attempts, used, created_at
        FROM password_reset_otps
        WHERE user_id = ? AND used = 0
        ORDER BY id DESC
        LIMIT 1
    """, (user_id,))

    row = cursor.fetchone()
    connection.close()

    return row


def increment_otp_attempts(otp_id):
    connection = sqlite3.connect(DB_PATH, timeout=30)
    cursor = connection.cursor()
    cursor.execute("""
        UPDATE password_reset_otps
        SET attempts = attempts + 1
        WHERE id = ?
    """, (otp_id,))
    connection.commit()
    connection.close()


def mark_password_reset_otp_used(otp_id):
    connection = sqlite3.connect(DB_PATH, timeout=30)
    cursor = connection.cursor()
    cursor.execute("""
        UPDATE password_reset_otps
        SET used = 1
        WHERE id = ?
    """, (otp_id,))
    connection.commit()
    connection.close()


def update_password(user_id, password_hash):
    """Replace a user's password with a new bcrypt hash."""
    connection = sqlite3.connect(DB_PATH, timeout=30)
    cursor = connection.cursor()

    cursor.execute("""
        UPDATE users
        SET password_hash = ?
        WHERE id = ?
    """, (password_hash, user_id))

    connection.commit()
    changed = cursor.rowcount > 0
    connection.close()

    return changed


def save_translation(source_language, target_language, original_text, translated_text, username=None):
    connection = sqlite3.connect(DB_PATH, timeout=30)
    cursor = connection.cursor()

    created_at = datetime.now().strftime("%d-%m-%Y %I:%M:%S %p")

    cursor.execute("""
        INSERT INTO translations
        (source_language, target_language, original_text, translated_text, created_at, username)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        source_language,
        target_language,
        original_text,
        translated_text,
        created_at,
        username
    ))

    connection.commit()
    connection.close()


def get_history(username=None):
    connection = sqlite3.connect(DB_PATH, timeout=30)
    cursor = connection.cursor()

    query = """
        SELECT id, source_language, target_language,
               original_text, translated_text, created_at
        FROM translations
    """
    if username is not None:
        cursor.execute(query + " WHERE username = ? ORDER BY id DESC", (username,))
    else:
        cursor.execute(query + " ORDER BY id DESC")

    history = cursor.fetchall()
    connection.close()
    return history


def clear_history(username=None):
    connection = sqlite3.connect(DB_PATH, timeout=30)
    cursor = connection.cursor()
    if username is not None:
        cursor.execute("DELETE FROM translations WHERE username = ?", (username,))
    else:
        cursor.execute("DELETE FROM translations")
    connection.commit()
    connection.close()


if __name__ == "__main__":
    create_database()
