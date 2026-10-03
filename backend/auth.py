import hashlib
import os
import secrets
import smtplib
import ssl
from datetime import datetime, timedelta
from email.message import EmailMessage

import bcrypt
from dotenv import load_dotenv

# Look for .env next to the .exe (packaged) or next to main.py (dev).
from backend.paths import app_data_path
load_dotenv(app_data_path(".env"))
load_dotenv()

from database.database import (
    register_user,
    get_user,
    get_user_by_email,
    save_password_reset_otp,
    get_active_password_reset_otp,
    increment_otp_attempts,
    mark_password_reset_otp_used,
    update_password,
)


def hash_password(plain_password: str) -> str:
    """Hash a plain-text password with bcrypt."""
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(plain_password.encode("utf-8"), salt)
    return hashed.decode("utf-8")


def check_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain-text password against a stored bcrypt hash."""
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            hashed_password.encode("utf-8")
        )
    except (ValueError, TypeError):
        return False


def _valid_email(email: str) -> bool:
    email = email.strip()
    return (
        len(email) <= 254
        and "@" in email
        and "." in email.rsplit("@", 1)[-1]
        and " " not in email
    )


def signup(username: str, email: str, password: str):
    """
    Register a new user with an email address so password recovery is possible.
    Returns (True, message) or (False, message).
    """
    username = username.strip()
    email = email.strip().lower()

    if not username or not email or not password:
        return False, "Username, email and password are required."

    if not _valid_email(email):
        return False, "Enter a valid email address."

    if len(password) < 6:
        return False, "Password must be at least 6 characters."

    # Keep email unique even though the DB column remains nullable for older
    # accounts created before this feature was added.
    existing = get_user_by_email(email)
    if existing is not None:
        return False, "Email is already registered."

    password_hash = hash_password(password)
    ok, error = register_user(username, email, password_hash)

    if not ok:
        return False, error

    return True, "Account created successfully."


def login(username: str, password: str):
    """Verify login credentials."""
    username = username.strip()

    if not username or not password:
        return False, "Username and password are required."

    user = get_user(username)

    if user is None:
        return False, "No account found with that username."

    # Current schema: id, username, email, password_hash, created_at.
    _, db_username, _, password_hash, _ = user

    if not check_password(password, password_hash):
        return False, "Incorrect password."

    return True, f"Welcome back, {db_username}!"


def _smtp_config():
    """
    Read SMTP settings from environment variables.

    Required:
      SMTP_USERNAME
      SMTP_PASSWORD

    Optional:
      SMTP_HOST (default: smtp.gmail.com)
      SMTP_PORT (default: 587)
      SMTP_FROM (default: SMTP_USERNAME)
    """
    username = os.getenv("SMTP_USERNAME", "").strip()
    password = os.getenv("SMTP_PASSWORD", "")
    host = os.getenv("SMTP_HOST", "smtp.gmail.com").strip()
    port = int(os.getenv("SMTP_PORT", "587"))
    sender = os.getenv("SMTP_FROM", username).strip()

    return host, port, username, password, sender


def _send_otp_email(recipient: str, otp: str):
    host, port, username, password, sender = _smtp_config()

    if not username or not password:
        raise RuntimeError(
            "Email is not configured. Set SMTP_USERNAME and SMTP_PASSWORD."
        )

    message = EmailMessage()
    message["Subject"] = "VoxTranslate Password Reset OTP"
    message["From"] = sender
    message["To"] = recipient
    message.set_content(
        "VoxTranslate Password Reset\n\n"
        f"Your OTP is: {otp}\n\n"
        "This OTP is valid for 10 minutes and can be used only once.\n"
        "If you did not request a password reset, you can safely ignore this email."
    )

    context = ssl.create_default_context()

    if port == 465:
        with smtplib.SMTP_SSL(host, port, context=context, timeout=20) as smtp:
            smtp.login(username, password)
            smtp.send_message(message)
    else:
        with smtplib.SMTP(host, port, timeout=20) as smtp:
            smtp.ehlo()
            smtp.starttls(context=context)
            smtp.ehlo()
            smtp.login(username, password)
            smtp.send_message(message)


def request_password_reset(email: str):
    """
    Generate a six-digit OTP and send it to the registered email.

    Returns:
      (True, message, user_id)
      (False, message, None)
    """
    email = email.strip().lower()

    if not _valid_email(email):
        return False, "Enter a valid email address.", None

    user = get_user_by_email(email)

    # Do not reveal whether an email exists.
    if user is None:
        return True, "If an account exists for this email, an OTP has been sent.", None

    user_id = user[0]
    otp = f"{secrets.randbelow(1_000_000):06d}"
    otp_hash = hashlib.sha256(otp.encode("utf-8")).hexdigest()
    expires_at = (datetime.now() + timedelta(minutes=10)).isoformat(timespec="seconds")

    try:
        _send_otp_email(email, otp)
    except Exception as exc:
        print("OTP email error:", exc)
        return False, "Could not send the OTP email. Check your email/SMTP settings.", None

    save_password_reset_otp(user_id, otp_hash, expires_at)
    return True, "OTP sent to your email. It is valid for 10 minutes.", user_id


def verify_password_reset_otp(user_id: int, otp: str):
    """
    Verify an OTP. Maximum of 5 attempts per OTP.
    Returns (True, message) or (False, message).
    """
    otp = otp.strip()

    if not otp.isdigit() or len(otp) != 6:
        return False, "Enter the 6-digit OTP."

    record = get_active_password_reset_otp(user_id)
    if record is None:
        return False, "OTP expired or already used. Please request a new OTP."

    otp_id, _, otp_hash, expires_at, attempts, _, _ = record

    if attempts >= 5:
        mark_password_reset_otp_used(otp_id)
        return False, "Too many incorrect attempts. Please request a new OTP."

    if datetime.now() > datetime.fromisoformat(expires_at):
        mark_password_reset_otp_used(otp_id)
        return False, "OTP expired. Please request a new OTP."

    increment_otp_attempts(otp_id)

    candidate_hash = hashlib.sha256(otp.encode("utf-8")).hexdigest()
    if not secrets.compare_digest(candidate_hash, otp_hash):
        remaining = max(0, 4 - attempts)
        return False, f"Incorrect OTP. {remaining} attempts remaining."

    return True, "OTP verified. Set your new password."


def reset_password(user_id: int, new_password: str):
    """Set a new password after successful OTP verification."""
    if len(new_password) < 6:
        return False, "Password must be at least 6 characters."

    record = get_active_password_reset_otp(user_id)
    if record is None:
        return False, "Password reset session expired. Please request a new OTP."

    otp_id = record[0]

    if datetime.now() > datetime.fromisoformat(record[3]):
        mark_password_reset_otp_used(otp_id)
        return False, "Password reset session expired. Please request a new OTP."

    ok = update_password(user_id, hash_password(new_password))
    if not ok:
        return False, "Could not update the password."

    mark_password_reset_otp_used(otp_id)
    return True, "Password reset successfully. You can now login."
