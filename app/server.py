"""
HTTP REST Server & Real-Time SSE Streamer for Smart Co-Working Space Management.
Built using standard library http.server, threading, json, and sqlite3.
"""

import http.server
import socketserver
import urllib.parse
import json
import os
import mimetypes
import uuid
import datetime
from .database import get_db, init_db, seed_db, create_notification
from .auth import authenticate_user, register_user, verify_token
from .matching import search_spaces
from .telemetry import hub

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC_DIR = os.path.join(BASE_DIR, "static")

class CoworkingRequestHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=STATIC_DIR, **kwargs)

    def log_message(self, format, *args):
        # Clean logging
        print(f"[HTTP] {self.command} {self.path} - {args[1] if len(args) > 1 else ''}")

    def send_json(self, status_code: int, data: dict | list):
        payload = json.dumps(data).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, PATCH, DELETE, OPTIONS")
        self.end_headers()
        self.wfile.write(payload)

    def send_error_json(self, status_code: int, message: str):
        self.send_json(status_code, {"error": message, "status": status_code})

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, PATCH, DELETE, OPTIONS")
        self.end_headers()

    def get_auth_user(self) -> dict | None:
        auth_header = self.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return None
        token = auth_header[7:].strip()
        return verify_token(token)

    def read_json_body(self) -> dict:
        content_length = int(self.headers.get("Content-Length", 0))
        if content_length == 0:
            return {}
        raw = self.rfile.read(content_length)
        return json.loads(raw.decode("utf-8"))

    def get_normalized_path(self):
        original = self.headers.get("x-vercel-original-url") or self.headers.get("x-matched-path") or self.headers.get("x-forwarded-uri")
        if original and original.startswith("/api"):
            return urllib.parse.urlparse(original)
        return urllib.parse.urlparse(self.path)

    # ==========================================
    # GET Endpoints
    # ==========================================
    def do_GET(self):
        parsed = self.get_normalized_path()
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        # 1. Real-Time Server-Sent Events (SSE) Stream
        if path == "/api/telemetry/stream":
            self.handle_sse_stream()
            return

        # 2. Auth Profile
        if path == "/api/auth/me":
            user = self.get_auth_user()
            if not user:
                return self.send_error_json(401, "Unauthorized or token expired")
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("SELECT id, email, full_name, role, company_name, phone FROM users WHERE id = ?", (user["sub"],))
            row = cursor.fetchone()
            conn.close()
            if not row:
                return self.send_error_json(404, "User not found")
            return self.send_json(200, dict(row))

        # 3. Search Spaces with Multi-Bracket Filters
        if path == "/api/spaces":
            filters = {}
            if "city" in query:
                filters["city"] = query["city"][0]
            if "team_bracket" in query:
                filters["team_bracket"] = query["team_bracket"][0]
            if "budget_bracket" in query:
                filters["budget_bracket"] = query["budget_bracket"][0]
            if "area_bracket" in query:
                filters["area_bracket"] = query["area_bracket"][0]
            if "work_style" in query:
                filters["work_style"] = query["work_style"][0]
            if "unit_type" in query:
                filters["unit_type"] = query["unit_type"][0]
            if "amenities" in query:
                filters["amenities"] = [a.strip() for a in query["amenities"][0].split(",") if a.strip()]

            spaces = search_spaces(filters)
            return self.send_json(200, spaces)

        # 4. Space Detail
        if path.startswith("/api/spaces/") and not path.endswith("/units") and not path.endswith("/live-status"):
            space_id = path.split("/")[3]
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("""
            SELECT f.*, u.full_name as owner_name, u.email as owner_email, u.company_name as owner_company
            FROM facilities f
            JOIN users u ON f.owner_id = u.id
            WHERE f.id = ?;
            """, (space_id,))
            fac = cursor.fetchone()
            if not fac:
                conn.close()
                return self.send_error_json(404, "Facility not found")
            
            res = dict(fac)
            # Units
            cursor.execute("SELECT * FROM workspace_units WHERE facility_id = ? ORDER BY floor_number, unit_identifier;", (space_id,))
            res["units"] = [dict(u) for u in cursor.fetchall()]
            # Amenities
            cursor.execute("""
            SELECT a.id, a.code, a.name, a.category, a.icon 
            FROM amenities a
            JOIN facility_amenities fa ON a.id = fa.amenity_id
            WHERE fa.facility_id = ?;
            """, (space_id,))
            res["amenities"] = [dict(a) for a in cursor.fetchall()]
            conn.close()
            return self.send_json(200, res)

        # 5. Units for Space
        if path.startswith("/api/spaces/") and path.endswith("/units"):
            parts = path.split("/")
            space_id = parts[3]
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM workspace_units WHERE facility_id = ? ORDER BY floor_number, unit_identifier;", (space_id,))
            units = [dict(u) for u in cursor.fetchall()]
            conn.close()
            return self.send_json(200, units)

        # 6. User's Personal Bookings
        if path == "/api/bookings/my":
            user = self.get_auth_user()
            if not user:
                return self.send_error_json(401, "Authentication required")
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("""
            SELECT b.*, u.unit_identifier, u.type as unit_type, u.hourly_price, f.name as facility_name, f.address as facility_address
            FROM bookings b
            JOIN workspace_units u ON b.unit_id = u.id
            JOIN facilities f ON u.facility_id = f.id
            WHERE b.user_id = ?
            ORDER BY b.start_time DESC;
            """, (user["sub"],))
            bookings = [dict(b) for b in cursor.fetchall()]
            conn.close()
            return self.send_json(200, bookings)

        # 7. Space Owner's Bookings
        if path == "/api/bookings/owner":
            user = self.get_auth_user()
            if not user or user.get("role") not in ["SPACE_OWNER", "ADMIN"]:
                return self.send_error_json(403, "Access restricted to Space Owners and Admins")
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("""
            SELECT b.*, u.unit_identifier, u.type as unit_type, f.name as facility_name, usr.full_name as client_name, usr.email as client_email
            FROM bookings b
            JOIN workspace_units u ON b.unit_id = u.id
            JOIN facilities f ON u.facility_id = f.id
            JOIN users usr ON b.user_id = usr.id
            WHERE f.owner_id = ? OR ? = 'ADMIN'
            ORDER BY b.start_time DESC;
            """, (user["sub"], user.get("role")))
            bookings = [dict(b) for b in cursor.fetchall()]
            conn.close()
            return self.send_json(200, bookings)

        # 8. Amenities Catalog
        if path == "/api/amenities":
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM amenities ORDER BY category, name;")
            amenities = [dict(a) for a in cursor.fetchall()]
            conn.close()
            return self.send_json(200, amenities)

        # 9. Admin Platform Metrics
        if path == "/api/admin/metrics":
            user = self.get_auth_user()
            if not user or user.get("role") != "ADMIN":
                return self.send_error_json(403, "Admin authorization required")
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM users;")
            total_users = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM facilities;")
            total_facilities = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM workspace_units;")
            total_units = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM workspace_units WHERE current_status = 'OCCUPIED';")
            occupied_units = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM bookings WHERE status = 'CONFIRMED' OR status = 'ACTIVE_CHECKED_IN';")
            active_bookings = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM bookings WHERE status = 'NO_SHOW_RELEASED';")
            no_show_released = cursor.fetchone()[0]

            cursor.execute("SELECT COALESCE(SUM(total_amount), 0) FROM bookings WHERE status != 'CANCELLED';")
            total_revenue = cursor.fetchone()[0]

            occupancy_rate = round((occupied_units / float(total_units) * 100), 1) if total_units > 0 else 0.0

            cursor.execute("""
            SELECT t.*, u.unit_identifier, f.name as facility_name
            FROM telemetry_logs t
            JOIN workspace_units u ON t.unit_id = u.id
            JOIN facilities f ON u.facility_id = f.id
            ORDER BY t.captured_at DESC LIMIT 20;
            """)
            recent_telemetry = [dict(r) for r in cursor.fetchall()]

            conn.close()

            return self.send_json(200, {
                "total_users": total_users,
                "total_facilities": total_facilities,
                "total_units": total_units,
                "occupied_units": occupied_units,
                "occupancy_rate_percent": occupancy_rate,
                "active_bookings": active_bookings,
                "no_show_released_count": no_show_released,
                "total_revenue": total_revenue,
                "recent_telemetry": recent_telemetry
            })

        # 10. Inquiries
        if path == "/api/inquiries":
            user = self.get_auth_user()
            if not user:
                return self.send_error_json(401, "Authentication required")
            conn = get_db()
            cursor = conn.cursor()
            if user.get("role") in ["SPACE_OWNER", "ADMIN"]:
                cursor.execute("""
                SELECT i.*, f.name as facility_name, u.full_name as user_name, u.email as user_email
                FROM inquiries i
                JOIN facilities f ON i.facility_id = f.id
                JOIN users u ON i.user_id = u.id
                WHERE f.owner_id = ? OR ? = 'ADMIN'
                ORDER BY i.created_at DESC;
                """, (user["sub"], user.get("role")))
            else:
                cursor.execute("""
                SELECT i.*, f.name as facility_name 
                FROM inquiries i
                JOIN facilities f ON i.facility_id = f.id
                WHERE i.user_id = ?
                ORDER BY i.created_at DESC;
                """, (user["sub"],))
            inquiries = [dict(i) for i in cursor.fetchall()]
            conn.close()
            return self.send_json(200, inquiries)

        # 11. User Notifications (Simulated Email & SMS)
        if path == "/api/notifications":
            user = self.get_auth_user()
            if not user:
                return self.send_error_json(401, "Authentication required")
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("""
            SELECT * FROM notifications 
            WHERE user_id = ? 
            ORDER BY created_at DESC LIMIT 25;
            """, (user["sub"],))
            notifs = [dict(n) for n in cursor.fetchall()]
            conn.close()
            return self.send_json(200, notifs)

        # Fallback to static files
        if path == "/":
            self.path = "/index.html"
        return super().do_GET()

    # ==========================================
    # POST Endpoints
    # ==========================================
    def do_POST(self):
        parsed = self.get_normalized_path()
        path = parsed.path

        # 1. Auth Register
        if path == "/api/auth/register":
            body = self.read_json_body()
            email = body.get("email")
            password = body.get("password")
            full_name = body.get("full_name")
            role = body.get("role", "USER")
            company = body.get("company_name", "")
            phone = body.get("phone", "")

            if not email or not password or not full_name:
                return self.send_error_json(400, "Missing required fields: email, password, and full_name")

            try:
                res = register_user(email, password, full_name, role, company, phone)
                create_notification(
                    res["user"]["id"],
                    "EMAIL",
                    "Welcome to SmartCoWork",
                    f"Hi {full_name}, your account has been verified. You can now discover spaces and view live floorplans.",
                    f"Email ({email})"
                )
                return self.send_json(201, res)
            except ValueError as e:
                return self.send_error_json(409, str(e))

        # 2. Auth Login
        if path == "/api/auth/login":
            body = self.read_json_body()
            email = body.get("email", "")
            password = body.get("password", "")
            auth_res = authenticate_user(email, password)
            if not auth_res:
                return self.send_error_json(401, "Invalid email address or password")
            return self.send_json(200, auth_res)

        # 3. Create Booking
        if path == "/api/bookings":
            user = self.get_auth_user()
            if not user:
                return self.send_error_json(401, "Authentication required to book")

            body = self.read_json_body()
            unit_id = body.get("unit_id")
            hours = int(body.get("hours", 1))
            start_str = body.get("start_time")

            if not unit_id:
                return self.send_error_json(400, "unit_id is required")

            conn = get_db()
            cursor = conn.cursor()

            # Verify Unit exists & check current status
            cursor.execute("""
            SELECT u.*, f.name as facility_name 
            FROM workspace_units u 
            JOIN facilities f ON u.facility_id = f.id 
            WHERE u.id = ?
            """, (unit_id,))
            unit = cursor.fetchone()
            if not unit:
                conn.close()
                return self.send_error_json(404, "Workspace unit not found")

            if unit["current_status"] == "OCCUPIED":
                conn.close()
                return self.send_error_json(409, f"Unit {unit['unit_identifier']} is currently occupied.")

            # Calculate times
            if start_str:
                try:
                    start_dt = datetime.datetime.fromisoformat(start_str)
                except ValueError:
                    start_dt = datetime.datetime.now(datetime.timezone.utc)
            else:
                start_dt = datetime.datetime.now(datetime.timezone.utc)

            end_dt = start_dt + datetime.timedelta(hours=hours)
            total_price = (unit["hourly_price"] or 15.0) * hours

            booking_id = f"book-{uuid.uuid4().hex[:8]}"
            booking_code = f"CG-{datetime.datetime.now().year}-{uuid.uuid4().hex[:4].upper()}"
            qr_token = f"QR-{booking_code}-{uuid.uuid4().hex[:6]}"
            now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

            # Update unit status to RESERVED
            cursor.execute("""
            INSERT INTO bookings (id, booking_code, user_id, unit_id, start_time, end_time, total_amount, status, qr_token, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'CONFIRMED', ?, ?);
            """, (booking_id, booking_code, user["sub"], unit_id, start_dt.isoformat(), end_dt.isoformat(), total_price, qr_token, now_iso))

            cursor.execute("UPDATE workspace_units SET current_status = 'RESERVED' WHERE id = ?;", (unit_id,))

            # Log Telemetry
            cursor.execute("""
            INSERT INTO telemetry_logs (unit_id, source, event_state, captured_at, metadata)
            VALUES (?, 'SYSTEM_BOOKING', 'RESERVED', ?, ?);
            """, (unit_id, now_iso, json.dumps({"booking_code": booking_code, "user_id": user["sub"]})))

            conn.commit()
            conn.close()

            # Broadcast update via SSE
            hub.broadcast("unit_update", {
                "unit_id": unit_id,
                "facility_id": unit["facility_id"],
                "status": "RESERVED",
                "unit_identifier": unit["unit_identifier"],
                "timestamp": now_iso
            })

            # Create transactional notifications
            create_notification(
                user["sub"],
                "EMAIL",
                f"Booking Confirmed: {booking_code}",
                f"Your reservation for {unit['unit_identifier']} at {unit['facility_name']} is confirmed. Total: ${total_price:.2f}. Please check in within 15 mins of arrival.",
                f"Email ({user.get('email', 'tenant')})"
            )
            create_notification(
                user["sub"],
                "SMS",
                f"Pass Ready: {unit['unit_identifier']}",
                f"SmartCoWork Pass: Show QR {booking_code} at scanner to unlock your desk. Grace period ends in 15 mins.",
                "SMS Alert"
            )

            return self.send_json(201, {
                "id": booking_id,
                "booking_code": booking_code,
                "qr_token": qr_token,
                "unit_identifier": unit["unit_identifier"],
                "facility_name": unit["facility_name"],
                "total_amount": total_price,
                "start_time": start_dt.isoformat(),
                "end_time": end_dt.isoformat(),
                "status": "CONFIRMED"
            })

        # 4. QR Telemetry Check-in
        if path == "/api/telemetry/check-in":
            body = self.read_json_body()
            qr_token = body.get("qr_token") or body.get("booking_code")
            if not qr_token:
                return self.send_error_json(400, "qr_token or booking_code is required for check-in")

            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("""
            SELECT b.*, u.facility_id, u.unit_identifier, f.name as facility_name
            FROM bookings b
            JOIN workspace_units u ON b.unit_id = u.id
            JOIN facilities f ON u.facility_id = f.id
            WHERE (b.qr_token = ? OR b.booking_code = ?) AND b.status IN ('CONFIRMED', 'PENDING_APPROVAL');
            """, (qr_token.strip(), qr_token.strip()))
            booking = cursor.fetchone()

            if not booking:
                conn.close()
                return self.send_error_json(404, "Active booking not found or already checked-in/expired")

            now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
            cursor.execute("""
            UPDATE bookings 
            SET status = 'ACTIVE_CHECKED_IN', check_in_time = ?
            WHERE id = ?;
            """, (now_iso, booking["id"]))

            cursor.execute("UPDATE workspace_units SET current_status = 'OCCUPIED' WHERE id = ?;", (booking["unit_id"],))

            cursor.execute("""
            INSERT INTO telemetry_logs (unit_id, source, event_state, captured_at, metadata)
            VALUES (?, 'QR_SCAN', 'OCCUPIED', ?, ?);
            """, (booking["unit_id"], now_iso, json.dumps({"booking_code": booking["booking_code"]})))

            conn.commit()
            conn.close()

            # Broadcast instant status flip to OCCUPIED
            hub.broadcast("unit_update", {
                "unit_id": booking["unit_id"],
                "facility_id": booking["facility_id"],
                "status": "OCCUPIED",
                "unit_identifier": booking["unit_identifier"],
                "timestamp": now_iso
            })

            # Check-in notification
            create_notification(
                booking["user_id"],
                "SMS",
                f"Check-In Verified: {booking['unit_identifier']}",
                f"Welcome to {booking['facility_name']}! Wi-Fi SSID: SmartCoWork-Guest (Pass: FastFiber2026). Enjoy your productive session.",
                "SMS Check-in"
            )

            return self.send_json(200, {
                "message": "Check-in successful! Workspace is activated and live telemetry logged.",
                "booking_code": booking["booking_code"],
                "unit_identifier": booking["unit_identifier"],
                "facility_name": booking["facility_name"],
                "check_in_time": now_iso
            })

        # 5. Create Facility / Space Listing (Space Owner)
        if path == "/api/spaces":
            user = self.get_auth_user()
            if not user or user.get("role") not in ["SPACE_OWNER", "ADMIN"]:
                return self.send_error_json(403, "Only verified Space Owners or Admins can create listings")

            body = self.read_json_body()
            name = body.get("name")
            address = body.get("address")
            city = body.get("city")
            total_area = int(body.get("total_area_sqft", 8000))
            description = body.get("description", "Executive co-working facility.")
            work_style = body.get("work_style", "COLLABORATIVE")
            image_url = body.get("image_url", "https://images.unsplash.com/photo-1497366216548-37526070297c?auto=format&fit=crop&w=1200&q=80")

            if not name or not address or not city:
                return self.send_error_json(400, "Name, address, and city are mandatory")

            fac_id = f"fac-{uuid.uuid4().hex[:8]}"
            slug = f"{name.lower().replace(' ', '-')}-{uuid.uuid4().hex[:4]}"
            now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("""
            INSERT INTO facilities (id, owner_id, name, slug, description, address, city, state, postal_code, latitude, longitude, total_area_sqft, opening_time, closing_time, is_24x7, work_style, status, image_url, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'CA', '94105', 37.78, -122.40, ?, '08:00', '22:00', 1, ?, 'ACTIVE', ?, ?);
            """, (fac_id, user["sub"], name, slug, description, address, city, total_area, work_style, image_url, now_iso))

            # Automatically create 4 starter units
            default_units = [
                (f"u-{uuid.uuid4().hex[:6]}", fac_id, "Desk 1", "HOT_DESK", 1, 45, 14.0, 70.0, 500.0, "VACANT", 1, "Main Floor", 80, 80, now_iso),
                (f"u-{uuid.uuid4().hex[:6]}", fac_id, "Desk 2", "HOT_DESK", 1, 45, 14.0, 70.0, 500.0, "VACANT", 1, "Main Floor", 190, 80, now_iso),
                (f"u-{uuid.uuid4().hex[:6]}", fac_id, "Executive Cabin 1", "PRIVATE_CABIN", 6, 300, 60.0, 320.0, 2400.0, "VACANT", 1, "Suites", 330, 80, now_iso),
                (f"u-{uuid.uuid4().hex[:6]}", fac_id, "Boardroom 1", "MEETING_ROOM", 8, 380, 45.0, 240.0, 0.0, "VACANT", 1, "Conference", 120, 220, now_iso)
            ]
            cursor.executemany("""
            INSERT INTO workspace_units (id, facility_id, unit_identifier, type, capacity, area_sqft, hourly_price, daily_price, monthly_price, current_status, floor_number, zone_name, x_pos, y_pos, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, default_units)

            cursor.execute("INSERT OR IGNORE INTO facility_amenities (facility_id, amenity_id) VALUES (?, 'am-wifi'), (?, 'am-power'), (?, 'am-coffee');", (fac_id, fac_id, fac_id))

            conn.commit()
            conn.close()

            return self.send_json(201, {"id": fac_id, "name": name, "message": "Facility listing created successfully!"})

        # 6. Submit Inquiry
        if path == "/api/inquiries":
            user = self.get_auth_user()
            if not user:
                return self.send_error_json(401, "Authentication required to submit inquiries")

            body = self.read_json_body()
            facility_id = body.get("facility_id")
            subject = body.get("subject", "Enterprise Workspace Inquiry")
            message = body.get("message", "")
            team_size = int(body.get("team_size", 1))

            if not facility_id or not message:
                return self.send_error_json(400, "facility_id and message are required")

            inq_id = f"inq-{uuid.uuid4().hex[:8]}"
            now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("""
            INSERT INTO inquiries (id, user_id, facility_id, subject, message, team_size, target_date, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'OPEN', ?);
            """, (inq_id, user["sub"], facility_id, subject, message, team_size, now_iso, now_iso))
            conn.commit()
            conn.close()

            create_notification(
                user["sub"],
                "EMAIL",
                "Inquiry Dispatched to Space Host",
                f"Your custom proposal inquiry for {team_size} persons has been sent to the facility manager. They will respond within 2 business hours.",
                "Email Notice"
            )

            return self.send_json(201, {"id": inq_id, "message": "Inquiry submitted! Space manager has received your requirements."})

        self.send_error_json(404, "Endpoint not found")

    # ==========================================
    # PATCH Endpoints
    # ==========================================
    def do_PATCH(self):
        parsed = self.get_normalized_path()
        path = parsed.path

        # 1. Update Unit Status (Maintenance / Vacant / Occupied)
        if path.startswith("/api/units/") and path.endswith("/status"):
            user = self.get_auth_user()
            if not user or user.get("role") not in ["SPACE_OWNER", "ADMIN"]:
                return self.send_error_json(403, "Only space hosts or admins can alter unit status")

            parts = path.split("/")
            unit_id = parts[3]
            body = self.read_json_body()
            new_status = body.get("status")

            if new_status not in ["VACANT", "OCCUPIED", "MAINTENANCE", "RESERVED"]:
                return self.send_error_json(400, "Invalid status")

            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("SELECT facility_id, unit_identifier FROM workspace_units WHERE id = ?", (unit_id,))
            unit = cursor.fetchone()
            if not unit:
                conn.close()
                return self.send_error_json(404, "Unit not found")

            now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
            cursor.execute("UPDATE workspace_units SET current_status = ? WHERE id = ?", (new_status, unit_id))
            cursor.execute("""
            INSERT INTO telemetry_logs (unit_id, source, event_state, captured_at, metadata)
            VALUES (?, 'HOST_MANUAL', ?, ?, ?);
            """, (unit_id, new_status, now_iso, json.dumps({"operator_id": user["sub"]})))
            conn.commit()
            conn.close()

            # Broadcast live update
            hub.broadcast("unit_update", {
                "unit_id": unit_id,
                "facility_id": unit["facility_id"],
                "status": new_status,
                "unit_identifier": unit["unit_identifier"],
                "timestamp": now_iso
            })

            return self.send_json(200, {"message": f"Unit status updated to {new_status}"})

        # 2. Cancel Booking
        if path.startswith("/api/bookings/") and path.endswith("/cancel"):
            user = self.get_auth_user()
            if not user:
                return self.send_error_json(401, "Authentication required")

            parts = path.split("/")
            booking_id = parts[3]

            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("""
            SELECT b.*, u.unit_identifier, f.name as facility_name 
            FROM bookings b 
            JOIN workspace_units u ON b.unit_id = u.id 
            JOIN facilities f ON u.facility_id = f.id 
            WHERE b.id = ?
            """, (booking_id,))
            booking = cursor.fetchone()
            if not booking:
                conn.close()
                return self.send_error_json(404, "Booking not found")

            if booking["user_id"] != user["sub"] and user.get("role") not in ["SPACE_OWNER", "ADMIN"]:
                conn.close()
                return self.send_error_json(403, "Cannot cancel another user's booking")

            cursor.execute("UPDATE bookings SET status = 'CANCELLED' WHERE id = ?", (booking_id,))
            cursor.execute("UPDATE workspace_units SET current_status = 'VACANT' WHERE id = ?", (booking["unit_id"],))

            now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
            cursor.execute("""
            INSERT INTO telemetry_logs (unit_id, source, event_state, captured_at, metadata)
            VALUES (?, 'USER_CANCELLATION', 'VACANT', ?, ?);
            """, (booking["unit_id"], now_iso, json.dumps({"booking_id": booking_id})))

            conn.commit()
            conn.close()

            hub.broadcast("unit_update", {
                "unit_id": booking["unit_id"],
                "facility_id": booking["facility_id"],
                "status": "VACANT",
                "unit_identifier": booking["unit_identifier"],
                "timestamp": now_iso
            })

            create_notification(
                booking["user_id"],
                "EMAIL",
                f"Booking Cancelled: {booking['booking_code']}",
                f"Your reservation for {booking['unit_identifier']} at {booking['facility_name']} has been cancelled and the seat released.",
                "Email Notice"
            )

            return self.send_json(200, {"message": "Booking successfully cancelled and unit released"})

        # 3. Host Respond to Customer Inquiry
        if path.startswith("/api/inquiries/") and path.endswith("/respond"):
            user = self.get_auth_user()
            if not user or user.get("role") not in ["SPACE_OWNER", "ADMIN"]:
                return self.send_error_json(403, "Access restricted to Space Owners and Admins")

            parts = path.split("/")
            inquiry_id = parts[3]
            body = self.read_json_body()
            notes = body.get("response_notes", "").strip()
            if not notes:
                return self.send_error_json(400, "response_notes is required")

            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("""
            SELECT i.*, f.name as facility_name 
            FROM inquiries i 
            JOIN facilities f ON i.facility_id = f.id 
            WHERE i.id = ?
            """, (inquiry_id,))
            inq = cursor.fetchone()
            if not inq:
                conn.close()
                return self.send_error_json(404, "Inquiry not found")

            cursor.execute("""
            UPDATE inquiries 
            SET status = 'RESPONDED', response_notes = ? 
            WHERE id = ?;
            """, (notes, inquiry_id))
            conn.commit()
            conn.close()

            # Create notification for the user
            create_notification(
                inq["user_id"],
                "EMAIL",
                f"Facility Manager Response: {inq['facility_name']}",
                f"The space manager for {inq['facility_name']} has responded: \"{notes}\"",
                "Host Direct Response"
            )
            create_notification(
                inq["user_id"],
                "SMS",
                f"Inquiry Reply: {inq['facility_name']}",
                f"Manager reply: \"{notes[:80]}...\". Check your email for full details.",
                "SMS Alert"
            )

            return self.send_json(200, {
                "message": "Response dispatched to space seeker!",
                "inquiry_id": inquiry_id,
                "status": "RESPONDED",
                "response_notes": notes
            })

        self.send_error_json(404, "Endpoint not found")

    # ==========================================
    # Real-Time SSE Stream Handler
    # ==========================================
    def handle_sse_stream(self):
        """Establishes persistent Server-Sent Events (SSE) connection."""
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

        q = hub.subscribe()
        try:
            self.wfile.write(b"event: connected\ndata: {\"status\": \"listening\"}\n\n")
            self.wfile.flush()

            while True:
                try:
                    msg = q.get(timeout=20.0)
                    self.wfile.write(msg.encode("utf-8"))
                    self.wfile.flush()
                except Exception:
                    self.wfile.write(b": ping\n\n")
                    self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            hub.unsubscribe(q)

def run_server(host="127.0.0.1", port=8000):
    init_db()
    seed_db()
    hub.start_auto_release_daemon(interval_seconds=15, grace_minutes=15)

    server_address = (host, port)
    httpd = socketserver.ThreadingTCPServer(server_address, CoworkingRequestHandler)
    httpd.allow_reuse_address = True
    print(f"==================================================================")
    print(f"  Smart Co-Working Space Management | Real-Time Telemetry Hub     ")
    print(f"  Server URL:           http://{host}:{port}/                     ")
    print(f"  Live SSE Stream:      http://{host}:{port}/api/telemetry/stream ")
    print(f"==================================================================")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down server gracefully...")
        httpd.server_close()
