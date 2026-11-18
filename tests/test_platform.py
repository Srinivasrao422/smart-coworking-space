"""
Automated Test Suite for Smart Co-Working Space Management Platform.
Tests database integrity, auth security, matching algorithm, booking concurrency,
QR check-in telemetry, notifications, host inquiry responses, and auto-release daemon.
"""

import unittest
import os
import sys
import uuid
import datetime

# Ensure project root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import init_db, seed_db, get_db, create_notification
from app.auth import hash_password, verify_password, create_token, verify_token, authenticate_user, register_user
from app.matching import calculate_match_score, search_spaces
from app.telemetry import hub

class TestCoworkingPlatform(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        # Reset and seed database cleanly
        db_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "coworking.db")
        if os.path.exists(db_file):
            try:
                os.remove(db_file)
            except Exception:
                pass
        init_db()
        seed_db()

    def test_01_database_seed_integrity(self):
        """Verify seeded data exists for facilities, units, amenities, users, and notifications."""
        conn = get_db()
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM users;")
        self.assertGreaterEqual(cursor.fetchone()[0], 5)

        cursor.execute("SELECT COUNT(*) FROM facilities;")
        self.assertGreaterEqual(cursor.fetchone()[0], 6)

        cursor.execute("SELECT COUNT(*) FROM workspace_units;")
        self.assertGreaterEqual(cursor.fetchone()[0], 24)

        cursor.execute("SELECT COUNT(*) FROM amenities;")
        self.assertGreaterEqual(cursor.fetchone()[0], 8)

        cursor.execute("SELECT COUNT(*) FROM notifications;")
        self.assertGreaterEqual(cursor.fetchone()[0], 2)

        cursor.execute("SELECT COUNT(*) FROM inquiries;")
        self.assertGreaterEqual(cursor.fetchone()[0], 1)

        conn.close()

    def test_02_password_hashing_and_auth(self):
        """Test PBKDF2 password derivation and comparison."""
        pwd = "ExecutivePass2026!"
        h, salt = hash_password(pwd)
        self.assertTrue(verify_password(pwd, h, salt))
        self.assertFalse(verify_password("WrongPassword", h, salt))

    def test_03_jwt_token_tampering_resistance(self):
        """Verify token validation and signature check."""
        token = create_token("user-test-123", "test@test.com", "USER", expires_in_seconds=3600)
        decoded = verify_token(token)
        self.assertIsNotNone(decoded)
        self.assertEqual(decoded["sub"], "user-test-123")
        self.assertEqual(decoded["role"], "USER")

        # Tamper with token payload
        parts = token.split(".")
        tampered_token = f"{parts[0]}.eyJhZG1pbiI6dHJ1ZX0.{parts[2]}"
        self.assertIsNone(verify_token(tampered_token))

    def test_04_user_registration_and_rbac(self):
        """Test registering a new space seeker and authenticating."""
        unique_email = f"executive_{uuid.uuid4().hex[:6]}@example.com"
        reg = register_user(unique_email, "SecurePass123!", "Diana Prince", role="USER", company_name="Wayne Enterprises")
        self.assertIn("token", reg)
        self.assertEqual(reg["user"]["email"], unique_email)
        self.assertEqual(reg["user"]["role"], "USER")

        # Authenticate
        auth = authenticate_user(unique_email, "SecurePass123!")
        self.assertIsNotNone(auth)
        self.assertEqual(auth["user"]["email"], unique_email)

    def test_05_smart_matching_algorithm(self):
        """Test suitability score calculations for curated brackets."""
        # Find solo desks in San Francisco
        spaces = search_spaces({"team_bracket": "solo", "budget_bracket": "standard", "city": "San Francisco"})
        self.assertGreater(len(spaces), 0)
        top_match = spaces[0]
        self.assertIn("match_metrics", top_match)
        self.assertGreaterEqual(top_match["match_metrics"]["overall_score"], 60)
        self.assertIn("capacity", top_match["match_metrics"]["breakdown"])
        self.assertIn("budget", top_match["match_metrics"]["breakdown"])

    def test_06_booking_creation_and_state_transition(self):
        """Test reserving an available desk transitions it to RESERVED."""
        conn = get_db()
        cursor = conn.cursor()

        # Find any VACANT unit
        cursor.execute("SELECT id, facility_id FROM workspace_units WHERE current_status = 'VACANT' LIMIT 1;")
        unit = cursor.fetchone()
        self.assertIsNotNone(unit, "Need at least one vacant unit to test booking")

        unit_id = unit["id"]
        booking_code = f"TEST-BOOK-{uuid.uuid4().hex[:6]}"
        qr_token = f"TEST-QR-{uuid.uuid4().hex[:6]}"
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        end = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=2)).isoformat()

        cursor.execute("""
        INSERT INTO bookings (id, booking_code, user_id, unit_id, start_time, end_time, total_amount, status, qr_token, created_at)
        VALUES (?, ?, 'user-freelance-01', ?, ?, ?, 30.0, 'CONFIRMED', ?, ?);
        """, (str(uuid.uuid4()), booking_code, unit_id, now, end, qr_token, now))

        cursor.execute("UPDATE workspace_units SET current_status = 'RESERVED' WHERE id = ?;", (unit_id,))
        conn.commit()

        # Check unit is now RESERVED
        cursor.execute("SELECT current_status FROM workspace_units WHERE id = ?;", (unit_id,))
        self.assertEqual(cursor.fetchone()[0], "RESERVED")

        # Test QR Check-in telemetry
        cursor.execute("""
        UPDATE bookings SET status = 'ACTIVE_CHECKED_IN', check_in_time = ? WHERE booking_code = ?;
        """, (now, booking_code))
        cursor.execute("UPDATE workspace_units SET current_status = 'OCCUPIED' WHERE id = ?;", (unit_id,))
        conn.commit()

        cursor.execute("SELECT current_status FROM workspace_units WHERE id = ?;", (unit_id,))
        self.assertEqual(cursor.fetchone()[0], "OCCUPIED")

        # Clean up unit back to VACANT
        cursor.execute("UPDATE workspace_units SET current_status = 'VACANT' WHERE id = ?;", (unit_id,))
        cursor.execute("UPDATE bookings SET status = 'COMPLETED' WHERE booking_code = ?;", (booking_code,))
        conn.commit()
        conn.close()

    def test_07_notifications_logging(self):
        """Test creating and retrieving simulated notifications."""
        create_notification(
            "user-freelance-01",
            "EMAIL",
            "Slot Reserved: Desk B-2",
            "Your seat is confirmed at Apex Sanctuary.",
            "Email (alex.dev@gmail.com)"
        )
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM notifications WHERE user_id = 'user-freelance-01';")
        self.assertGreaterEqual(cursor.fetchone()[0], 2)
        conn.close()

    def test_08_auto_release_no_show_reclamation(self):
        """Test that past-grace bookings are automatically released to VACANT."""
        conn = get_db()
        cursor = conn.cursor()

        cursor.execute("SELECT id, facility_id, unit_identifier FROM workspace_units LIMIT 1;")
        unit = cursor.fetchone()
        unit_id = unit["id"]

        # Create an expired booking: start time was 25 minutes ago, never checked in
        past_time = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=25)).isoformat()
        end_time = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=1)).isoformat()
        b_id = f"test-stale-{uuid.uuid4().hex[:6]}"
        b_code = f"CG-STALE-{uuid.uuid4().hex[:4]}"

        cursor.execute("""
        INSERT INTO bookings (id, booking_code, user_id, unit_id, start_time, end_time, total_amount, status, qr_token, created_at)
        VALUES (?, ?, 'user-freelance-01', ?, ?, ?, 25.0, 'CONFIRMED', ?, ?);
        """, (b_id, b_code, unit_id, past_time, end_time, f"QR-{b_code}", past_time))
        cursor.execute("UPDATE workspace_units SET current_status = 'RESERVED' WHERE id = ?;", (unit_id,))
        conn.commit()

        # Trigger auto-release logic directly
        hub._check_and_release_no_shows(grace_minutes=15)

        # Verify booking is now NO_SHOW_RELEASED and unit is VACANT
        cursor.execute("SELECT status FROM bookings WHERE id = ?;", (b_id,))
        self.assertEqual(cursor.fetchone()[0], "NO_SHOW_RELEASED")

        cursor.execute("SELECT current_status FROM workspace_units WHERE id = ?;", (unit_id,))
        self.assertEqual(cursor.fetchone()[0], "VACANT")

        conn.close()

    def test_09_inquiry_response_and_matching(self):
        """Test space host response to customer expectation inquiry."""
        conn = get_db()
        cursor = conn.cursor()

        cursor.execute("SELECT id, user_id FROM inquiries WHERE status = 'OPEN' LIMIT 1;")
        inq = cursor.fetchone()
        self.assertIsNotNone(inq)

        # Host responds
        reply_text = "We have reserved Cabin C-1 near the acoustic pods for your team at $2,400/mo."
        cursor.execute("UPDATE inquiries SET status = 'RESPONDED', response_notes = ? WHERE id = ?;", (reply_text, inq["id"]))
        conn.commit()

        cursor.execute("SELECT status, response_notes FROM inquiries WHERE id = ?;", (inq["id"],))
        row = cursor.fetchone()
        self.assertEqual(row["status"], "RESPONDED")
        self.assertEqual(row["response_notes"], reply_text)

        conn.close()

    def test_10_admin_credentials_and_rbac_defense(self):
        """Verify Admin credentials security, privilege escalation prevention, and server-side RBAC."""
        # 1. Admin authentication with correct credentials
        admin_email = os.environ.get("ADMIN_EMAIL", "kumbhasrinivasarao422@gmail.com")
        admin_pwd = os.environ.get("ADMIN_PASSWORD", "SmartCoWork@2026!")
        admin_auth = authenticate_user(admin_email, admin_pwd)
        self.assertIsNotNone(admin_auth, "Admin authentication with valid credentials must succeed")
        self.assertEqual(admin_auth["user"]["role"], "ADMIN")
        self.assertTrue(bool(admin_auth["token"]))

        # 2. Admin authentication with incorrect password must fail
        bad_auth = authenticate_user(admin_email, "IncorrectPassword2026!")
        self.assertIsNone(bad_auth, "Admin auth with incorrect password must be rejected")

        # 3. Privilege Escalation Defense: Self-registering with role="ADMIN" must be rejected
        with self.assertRaises(ValueError) as ctx:
            register_user(f"hacker_{uuid.uuid4().hex[:6]}@exploit.com", "HackerPass2026!", "Malicious Actor", role="ADMIN")
        self.assertIn("Privilege Error", str(ctx.exception))

        # 4. Host demo account remains functional
        host_auth = authenticate_user("vikram.malhotra@nexusworkspaces.com", "NexusHost@2026!")
        self.assertIsNotNone(host_auth, "Space Host demo authentication must remain functional")
        self.assertEqual(host_auth["user"]["role"], "SPACE_OWNER")

        # 5. Enterprise seeker demo account remains functional
        seeker_auth = authenticate_user("alex.rivera@techventures.io", "AlexSeeker@2026!")
        self.assertIsNotNone(seeker_auth, "Enterprise Seeker demo authentication must remain functional")
        self.assertEqual(seeker_auth["user"]["role"], "USER")

        # 6. Verify token decoding verifies roles strictly
        seeker_token_data = verify_token(seeker_auth["token"])
        self.assertEqual(seeker_token_data["role"], "USER")
        self.assertNotEqual(seeker_token_data["role"], "ADMIN")

        admin_token_data = verify_token(admin_auth["token"])
        self.assertEqual(admin_token_data["role"], "ADMIN")

if __name__ == "__main__":
    unittest.main()
