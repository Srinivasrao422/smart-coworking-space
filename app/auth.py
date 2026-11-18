"""
Authentication and Authorization module using standard library hashlib, hmac, base64, and json.
Implements PBKDF2 password hashing and signed JWT-like bearer tokens.
"""

import hashlib
import hmac
import base64
import json
import time
import os
import uuid
import datetime
from .database import get_db

import re

SECRET_KEY = os.environ.get("COWORKING_SECRET_KEY", "smart_coworking_secret_salt_2026_super_secure")
EMAIL_REGEX = re.compile(r"^[\w\.\+\-]+@[a-zA-Z0-9\.\-]+\.[a-zA-Z]{2,}$")

def validate_email_format(email: str) -> bool:
    """Validate RFC-standard real email format."""
    return bool(EMAIL_REGEX.match(email.strip()))

def validate_password_strength(password: str) -> tuple[bool, str]:
    """Enforce real-world enterprise password security standards."""
    if len(password) < 8:
        return False, "Password must be at least 8 characters long."
    if not any(c.isupper() for c in password):
        return False, "Password must contain at least one uppercase letter."
    if not any(c.islower() for c in password):
        return False, "Password must contain at least one lowercase letter."
    if not any(c.isdigit() or c in "!@#$%^&*()-_=+[]{}|;:,.<>?" for c in password):
        return False, "Password must contain at least one number or special character."
    return True, ""

def hash_password(password: str, salt: str = None) -> tuple[str, str]:
    if not salt:
        salt = os.urandom(16).hex()
    pwd_bytes = password.encode("utf-8")
    salt_bytes = salt.encode("utf-8")
    derived = hashlib.pbkdf2_hmac("sha256", pwd_bytes, salt_bytes, iterations=100000)
    return derived.hex(), salt

def verify_password(password: str, hashed: str, salt: str) -> bool:
    new_hash, _ = hash_password(password, salt)
    return hmac.compare_digest(new_hash, hashed)

def create_token(user_id: str, email: str, role: str, expires_in_seconds: int = 86400 * 7) -> str:
    """Generate a tamper-proof HMAC-SHA256 signed bearer token."""
    payload = {
        "sub": user_id,
        "email": email,
        "role": role,
        "iat": int(time.time()),
        "exp": int(time.time()) + expires_in_seconds
    }
    header = {"alg": "HS256", "typ": "JWT"}
    
    header_b64 = base64.urlsafe_b64encode(json.dumps(header).encode()).decode().rstrip("=")
    payload_b64 = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    
    signature_input = f"{header_b64}.{payload_b64}".encode()
    signature = hmac.new(SECRET_KEY.encode(), signature_input, hashlib.sha256).digest()
    sig_b64 = base64.urlsafe_b64encode(signature).decode().rstrip("=")
    
    return f"{header_b64}.{payload_b64}.{sig_b64}"

def verify_token(token: str) -> dict | None:
    """Validate and decode a bearer token."""
    if not token:
        return None
    try:
        parts = token.strip().split(".")
        if len(parts) != 3:
            return None
        header_b64, payload_b64, sig_b64 = parts
        
        # Verify signature
        sig_input = f"{header_b64}.{payload_b64}".encode()
        expected_sig = hmac.new(SECRET_KEY.encode(), sig_input, hashlib.sha256).digest()
        
        # Add padding back if necessary
        sig_padding = len(sig_b64) % 4
        if sig_padding:
            sig_b64 += "=" * (4 - sig_padding)
        actual_sig = base64.urlsafe_b64decode(sig_b64.encode())
        
        if not hmac.compare_digest(expected_sig, actual_sig):
            return None
            
        # Decode payload
        payload_padding = len(payload_b64) % 4
        if payload_padding:
            payload_b64 += "=" * (4 - payload_padding)
        payload = json.loads(base64.urlsafe_b64decode(payload_b64.encode()).decode())
        
        # Check expiration
        if payload.get("exp", 0) < time.time():
            return None
            
        return payload
    except Exception:
        return None

def authenticate_user(email: str, password: str) -> dict | None:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT id, email, password_hash, salt, full_name, role, company_name, phone, is_verified 
    FROM users WHERE email = ?;
    """, (email.strip().lower(),))
    row = cursor.fetchone()
    conn.close()

    if not row:
        return None

    if verify_password(password, row["password_hash"], row["salt"]):
        token = create_token(row["id"], row["email"], row["role"])
        return {
            "token": token,
            "user": {
                "id": row["id"],
                "email": row["email"],
                "full_name": row["full_name"],
                "role": row["role"],
                "company_name": row["company_name"],
                "phone": row["phone"],
                "is_verified": bool(row["is_verified"])
            }
        }
    return None

def register_user(email: str, password: str, full_name: str, role: str = "USER", company_name: str = "", phone: str = "") -> dict:
    if role == "ADMIN":
        raise ValueError("Privilege Error: Administrative accounts cannot be registered through the public portal.")
    if role not in ["USER", "SPACE_OWNER"]:
        role = "USER"

    email_clean = email.strip().lower()
    if not validate_email_format(email_clean):
        raise ValueError("Please provide a valid corporate or personal email address (e.g. name@company.com).")

    is_strong, pwd_err = validate_password_strength(password)
    if not is_strong:
        raise ValueError(pwd_err)

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM users WHERE email = ?;", (email_clean,))
    if cursor.fetchone():
        conn.close()
        raise ValueError("An account with this email address already exists.")

    p_hash, salt = hash_password(password)
    user_id = str(uuid.uuid4())
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()

    cursor.execute("""
    INSERT INTO users (id, email, password_hash, salt, full_name, role, company_name, phone, is_verified, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?);
    """, (user_id, email_clean, p_hash, salt, full_name.strip(), role, company_name.strip(), phone.strip(), now))

    conn.commit()
    conn.close()

    token = create_token(user_id, email_clean, role)
    return {
        "token": token,
        "user": {
            "id": user_id,
            "email": email_clean,
            "full_name": full_name.strip(),
            "role": role,
            "company_name": company_name.strip(),
            "phone": phone.strip(),
            "is_verified": True
        }
    }
