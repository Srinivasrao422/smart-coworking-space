"""
Database module for Smart Co-Working Space Management.
Implements SQLite with WAL mode, transactions, schema initialization, notifications, and enterprise seed data.
"""

import sqlite3
import os
import json
import uuid
import datetime

DB_FILE = os.path.join("/tmp", "coworking.db") if (os.environ.get("VERCEL") or os.environ.get("AWS_LAMBDA_FUNCTION_NAME")) else os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "coworking.db")

def get_db():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    try:
        conn.execute("PRAGMA journal_mode = WAL;")
    except Exception:
        pass
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()

    # 1. Users Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        salt TEXT NOT NULL,
        full_name TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'USER', -- USER, SPACE_OWNER, ADMIN
        company_name TEXT,
        phone TEXT,
        is_verified INTEGER DEFAULT 1,
        created_at TEXT NOT NULL
    );
    """)

    # 2. Facilities (Co-Working Hubs)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS facilities (
        id TEXT PRIMARY KEY,
        owner_id TEXT NOT NULL,
        name TEXT NOT NULL,
        slug TEXT UNIQUE NOT NULL,
        description TEXT NOT NULL,
        address TEXT NOT NULL,
        city TEXT NOT NULL,
        state TEXT NOT NULL,
        postal_code TEXT,
        latitude REAL,
        longitude REAL,
        total_area_sqft INTEGER NOT NULL,
        opening_time TEXT DEFAULT '08:00',
        closing_time TEXT DEFAULT '22:00',
        is_24x7 INTEGER DEFAULT 0,
        work_style TEXT DEFAULT 'COLLABORATIVE', -- QUIET_FOCUS, COLLABORATIVE, EXECUTIVE
        status TEXT DEFAULT 'ACTIVE', -- PENDING, ACTIVE, SUSPENDED
        image_url TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY (owner_id) REFERENCES users(id) ON DELETE CASCADE
    );
    """)

    # 3. Amenities Catalog
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS amenities (
        id TEXT PRIMARY KEY,
        code TEXT UNIQUE NOT NULL,
        name TEXT NOT NULL,
        category TEXT NOT NULL, -- Tech, Comfort, Facility, Hospitality
        icon TEXT NOT NULL
    );
    """)

    # 4. Facility Amenities Junction
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS facility_amenities (
        facility_id TEXT NOT NULL,
        amenity_id TEXT NOT NULL,
        PRIMARY KEY (facility_id, amenity_id),
        FOREIGN KEY (facility_id) REFERENCES facilities(id) ON DELETE CASCADE,
        FOREIGN KEY (amenity_id) REFERENCES amenities(id) ON DELETE CASCADE
    );
    """)

    # 5. Workspace Units (Atomic bookable items: Desks, Cabins, Rooms)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS workspace_units (
        id TEXT PRIMARY KEY,
        facility_id TEXT NOT NULL,
        unit_identifier TEXT NOT NULL, -- e.g. "Desk-101", "Cabin-A", "Boardroom-1"
        type TEXT NOT NULL, -- HOT_DESK, DEDICATED_DESK, PRIVATE_CABIN, MEETING_ROOM
        capacity INTEGER NOT NULL DEFAULT 1,
        area_sqft INTEGER,
        hourly_price REAL,
        daily_price REAL,
        monthly_price REAL,
        current_status TEXT NOT NULL DEFAULT 'VACANT', -- VACANT, RESERVED, OCCUPIED, MAINTENANCE
        floor_number INTEGER DEFAULT 1,
        zone_name TEXT,
        x_pos INTEGER DEFAULT 0, -- Coordinates for interactive 2D floor-map
        y_pos INTEGER DEFAULT 0,
        created_at TEXT NOT NULL,
        FOREIGN KEY (facility_id) REFERENCES facilities(id) ON DELETE CASCADE,
        UNIQUE(facility_id, unit_identifier)
    );
    """)

    # 6. Bookings
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS bookings (
        id TEXT PRIMARY KEY,
        booking_code TEXT UNIQUE NOT NULL,
        user_id TEXT NOT NULL,
        unit_id TEXT NOT NULL,
        start_time TEXT NOT NULL,
        end_time TEXT NOT NULL,
        total_amount REAL NOT NULL,
        status TEXT NOT NULL DEFAULT 'CONFIRMED', -- PENDING_APPROVAL, CONFIRMED, ACTIVE_CHECKED_IN, COMPLETED, CANCELLED, NO_SHOW_RELEASED
        check_in_time TEXT,
        check_out_time TEXT,
        qr_token TEXT UNIQUE NOT NULL,
        cancellation_reason TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
        FOREIGN KEY (unit_id) REFERENCES workspace_units(id) ON DELETE CASCADE
    );
    """)

    # 7. Telemetry & Occupancy Logs
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS telemetry_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        unit_id TEXT NOT NULL,
        source TEXT NOT NULL, -- QR_SCAN, HOST_MANUAL, IOT_SENSOR, AUTO_RELEASE
        event_state TEXT NOT NULL, -- VACANT, RESERVED, OCCUPIED, MAINTENANCE
        captured_at TEXT NOT NULL,
        metadata TEXT,
        FOREIGN KEY (unit_id) REFERENCES workspace_units(id) ON DELETE CASCADE
    );
    """)

    # 8. Inquiries / Custom Proposals
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS inquiries (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        facility_id TEXT NOT NULL,
        subject TEXT NOT NULL,
        message TEXT NOT NULL,
        team_size INTEGER DEFAULT 1,
        target_date TEXT,
        status TEXT DEFAULT 'OPEN', -- OPEN, RESPONDED, CLOSED
        response_notes TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
        FOREIGN KEY (facility_id) REFERENCES facilities(id) ON DELETE CASCADE
    );
    """)

    # 9. Simulated Email & SMS Notifications
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS notifications (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        type TEXT NOT NULL, -- EMAIL, SMS, SYSTEM
        title TEXT NOT NULL,
        message TEXT NOT NULL,
        channel TEXT NOT NULL,
        created_at TEXT NOT NULL,
        is_read INTEGER DEFAULT 0,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    """)

    # Indexes
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_units_facility ON workspace_units(facility_id, current_status);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_bookings_time ON bookings(unit_id, start_time, end_time);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_bookings_user ON bookings(user_id, status);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_notifications_user ON notifications(user_id, created_at);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_inquiries_facility ON inquiries(facility_id, status);")

    conn.commit()
    conn.close()

def create_notification(user_id: str, notif_type: str, title: str, message: str, channel: str):
    """Logs simulated transactional notification."""
    conn = get_db()
    cursor = conn.cursor()
    notif_id = f"notif-{uuid.uuid4().hex[:8]}"
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    cursor.execute("""
    INSERT INTO notifications (id, user_id, type, title, message, channel, created_at, is_read)
    VALUES (?, ?, ?, ?, ?, ?, ?, 0);
    """, (notif_id, user_id, notif_type, title, message, channel, now))
    conn.commit()
    conn.close()

def seed_or_update_real_users(cursor, now):
    from .auth import hash_password

    real_users = [
        # 1. Primary Administrator (User's real email & corporate admin)
        ("user-admin-real", "kumbhasrinivasarao422@gmail.com", "SmartCoWork@2026!", "Srinivas Rao Kumbha", "ADMIN", "CodeGuard AI Enterprise Operations", "+1-415-890-4220"),
        ("user-admin-corp", "admin@smartcowork.io", "SmartCoWork@2026!", "Executive Admin Team", "ADMIN", "SmartCoWork Global Inc", "+1-800-555-0100"),
        ("user-admin-legacy", "admin@codeguard.ai", "SmartCoWork@2026!", "System Administrator", "ADMIN", "CodeGuard Operations", "+1-800-555-0100"),
        # 2. Real Space Hosts / Facility Managers
        ("host-nexus-01", "vikram.malhotra@nexusworkspaces.com", "NexusHost@2026!", "Vikram Malhotra", "SPACE_OWNER", "Nexus Workspaces Group", "+1-415-555-0101"),
        ("host-nexus-alias", "owner@nexusspaces.com", "NexusHost@2026!", "Vikram Malhotra", "SPACE_OWNER", "Nexus Workspaces Group", "+1-415-555-0101"),
        ("host-apex-02", "sarah.jenkins@apexspaces.io", "ApexHost@2026!", "Sarah Jenkins", "SPACE_OWNER", "Apex Innovation Labs", "+1-415-555-0102"),
        ("host-apex-alias", "sarah@apexspaces.io", "ApexHost@2026!", "Sarah Jenkins", "SPACE_OWNER", "Apex Innovation Labs", "+1-415-555-0102"),
        # 3. Real Space Seekers & Teams
        ("user-freelance-01", "alex.rivera@techventures.io", "AlexSeeker@2026!", "Alex Rivera", "USER", "TechVentures Capital", "+1-212-555-0103"),
        ("user-seeker-alias", "alex.dev@gmail.com", "AlexSeeker@2026!", "Alex Rivera", "USER", "Indie Builder Ltd", "+1-212-555-0103"),
        ("user-startup-02", "elena.rostova@synapseai.tech", "ElenaSynapse@2026!", "Elena Rostova", "USER", "Synapse AI Labs", "+1-512-555-0104"),
        ("user-startup-alias", "elena@synapse.tech", "ElenaSynapse@2026!", "Elena Rostova", "USER", "Synapse AI Labs", "+1-512-555-0104"),
    ]

    for uid, email, raw_pwd, full_name, role, company, phone in real_users:
        p_hash, p_salt = hash_password(raw_pwd)
        cursor.execute("SELECT id FROM users WHERE email = ? OR id = ?;", (email.lower(), uid))
        existing = cursor.fetchone()
        if existing:
            cursor.execute("""
            UPDATE users 
            SET email = ?, password_hash = ?, salt = ?, full_name = ?, role = ?, company_name = ?, phone = ?, is_verified = 1
            WHERE id = ?;
            """, (email.lower(), p_hash, p_salt, full_name, role, company, phone, existing["id"]))
        else:
            cursor.execute("""
            INSERT INTO users (id, email, password_hash, salt, full_name, role, company_name, phone, is_verified, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?);
            """, (uid, email.lower(), p_hash, p_salt, full_name, role, company, phone, now))

def seed_db():
    conn = get_db()
    cursor = conn.cursor()
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()

    # Always ensure real production users exist and are up to date
    seed_or_update_real_users(cursor, now)
    conn.commit()

    cursor.execute("SELECT COUNT(*) FROM facilities;")
    if cursor.fetchone()[0] > 0:
        conn.close()
        return

    # 2. Seed Amenities Catalog
    amenities = [
        ("am-wifi", "GIGABIT_WIFI", "Enterprise Gigabit Wi-Fi (500+ Mbps)", "Tech", "wifi"),
        ("am-power", "POWER_BACKUP", "100% Dual-Grid DG Power Backup", "Tech", "battery-charging"),
        ("am-monitors", "DUAL_MONITORS", "4K Ultra-Wide USB-C Displays", "Tech", "monitor"),
        ("am-ac", "CENTRAL_HVAC", "Climate Controlled Ergonomic Space", "Comfort", "thermometer"),
        ("am-booth", "PHONE_BOOTHS", "Soundproof Acoustic Isolation Pods", "Comfort", "phone-call"),
        ("am-coffee", "ARTISAN_COFFEE", "Unlimited Specialty Barista Coffee & Teas", "Hospitality", "coffee"),
        ("am-cafeteria", "CAFETERIA", "Gourmet Rooftop Cafeteria & Lounge", "Hospitality", "utensils"),
        ("am-parking", "VALET_PARKING", "Reserved Valet Parking & EV Stations", "Facility", "car"),
        ("am-247", "ACCESS_24_7", "24/7 Smart Biometric & NFC Access", "Facility", "lock"),
        ("am-meeting", "SMART_CONFERENCE", "4K Video Conference Suite & Digital Whiteboards", "Tech", "video"),
    ]

    cursor.executemany("""
    INSERT INTO amenities (id, code, name, category, icon)
    VALUES (?, ?, ?, ?, ?);
    """, amenities)

    # 3. Seed 6 Real-World Enterprise Facilities (Inspired by Flexo Spaces, Unified Mentor & Knotel)
    facilities = [
        (
            "fac-01",
            "host-nexus-01",
            "Nexus Horizon Tech Hub",
            "nexus-horizon-tech-hub",
            "Premier high-tech co-working ecosystem engineered for engineering teams, AI startups, and quantitative professionals. Features ultra-low latency fiber, motorized standing desks, modular private team cabins, and acoustic focus pods.",
            "104 Innovation Boulevard, Tech District",
            "San Francisco",
            "CA",
            "94105",
            37.789,
            -122.398,
            18500,
            "07:00",
            "23:00",
            1,
            "COLLABORATIVE",
            "ACTIVE",
            "https://images.unsplash.com/photo-1527192491265-7e15c55b1ed2?auto=format&fit=crop&w=1200&q=80",
            now
        ),
        (
            "fac-02",
            "host-apex-02",
            "Apex Quiet Sanctuary & Labs",
            "apex-quiet-sanctuary",
            "Crafted exclusively for deep work, solo software engineers, researchers, and technical writers. Silent acoustic zones, natural daylight light-wells, Herman Miller Aeron seating, and zero-distraction policy.",
            "450 Market Street, Suite 900",
            "San Francisco",
            "CA",
            "94104",
            37.791,
            -122.401,
            12000,
            "08:00",
            "21:00",
            0,
            "QUIET_FOCUS",
            "ACTIVE",
            "https://images.unsplash.com/photo-1497366216548-37526070297c?auto=format&fit=crop&w=1200&q=80",
            now
        ),
        (
            "fac-03",
            "host-nexus-01",
            "The Executive Loft & Suites",
            "executive-loft-suites",
            "Prestige executive boardrooms and private executive suites designed for enterprise client meetings, VC partner pitches, and strategic advisory summits overlooking Central Park.",
            "720 5th Avenue, Financial Center",
            "New York",
            "NY",
            "10019",
            40.762,
            -73.974,
            24000,
            "08:00",
            "22:00",
            0,
            "EXECUTIVE",
            "ACTIVE",
            "https://images.unsplash.com/photo-1497215728101-856f4ea42174?auto=format&fit=crop&w=1200&q=80",
            now
        ),
        (
            "fac-04",
            "host-apex-02",
            "Meridian Innovation Campus",
            "meridian-innovation-campus",
            "Expansive indoor-outdoor workspace featuring high-ceiling glass atriums, soundproof team cabins, private phone booths, and a vibrant community lounge for scaling engineering teams.",
            "300 Colorado St, Downtown",
            "Austin",
            "TX",
            "78701",
            30.267,
            -97.743,
            21000,
            "07:30",
            "23:00",
            1,
            "COLLABORATIVE",
            "ACTIVE",
            "https://images.unsplash.com/photo-1504384308090-c894fdcc538d?auto=format&fit=crop&w=1200&q=80",
            now
        ),
        (
            "fac-05",
            "host-nexus-01",
            "Flexo Urban Hive & Maker Studio",
            "flexo-urban-hive",
            "Modern biophilic workspace designed for product teams, IoT builders, and designers. Equipped with rapid prototyping hardware lab, dedicated team bays, and acoustic meeting rooms.",
            "1201 3rd Avenue, Central Business District",
            "Seattle",
            "WA",
            "98101",
            47.606,
            -122.332,
            16500,
            "07:00",
            "22:00",
            1,
            "COLLABORATIVE",
            "ACTIVE",
            "https://images.unsplash.com/photo-1517502884422-41eaead166d4?auto=format&fit=crop&w=1200&q=80",
            now
        ),
        (
            "fac-06",
            "host-apex-02",
            "Unified Enterprise Tower",
            "unified-enterprise-tower",
            "High-rise flagship workspace tailored for multinational enterprise branches, finance firms, and legal teams. Offers private keycard-secured suites, auditorium, and dedicated fiber trunks.",
            "100 Federal Street, Financial District",
            "Boston",
            "MA",
            "02110",
            42.355,
            -71.056,
            32000,
            "08:00",
            "22:00",
            1,
            "EXECUTIVE",
            "ACTIVE",
            "https://images.unsplash.com/photo-1486406146926-c627a92ad1ab?auto=format&fit=crop&w=1200&q=80",
            now
        )
    ]

    cursor.executemany("""
    INSERT INTO facilities (id, owner_id, name, slug, description, address, city, state, postal_code, latitude, longitude, total_area_sqft, opening_time, closing_time, is_24x7, work_style, status, image_url, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
    """, facilities)

    # 4. Map Amenities to Facilities
    fac_amenities = [
        # fac-01 (Nexus Horizon - SF)
        ("fac-01", "am-wifi"), ("fac-01", "am-power"), ("fac-01", "am-monitors"), 
        ("fac-01", "am-booth"), ("fac-01", "am-coffee"), ("fac-01", "am-247"), ("fac-01", "am-meeting"),
        # fac-02 (Apex Sanctuary - SF)
        ("fac-02", "am-wifi"), ("fac-02", "am-power"), ("fac-02", "am-ac"), 
        ("fac-02", "am-booth"), ("fac-02", "am-coffee"), ("fac-02", "am-monitors"),
        # fac-03 (Executive Loft - NY)
        ("fac-03", "am-wifi"), ("fac-03", "am-power"), ("fac-03", "am-parking"), 
        ("fac-03", "am-cafeteria"), ("fac-03", "am-meeting"), ("fac-03", "am-coffee"),
        # fac-04 (Meridian Austin - TX)
        ("fac-04", "am-wifi"), ("fac-04", "am-power"), ("fac-04", "am-monitors"),
        ("fac-04", "am-cafeteria"), ("fac-04", "am-247"), ("fac-04", "am-meeting"),
        # fac-05 (Flexo Urban Hive - Seattle)
        ("fac-05", "am-wifi"), ("fac-05", "am-power"), ("fac-05", "am-booth"),
        ("fac-05", "am-coffee"), ("fac-05", "am-247"), ("fac-05", "am-parking"),
        # fac-06 (Unified Enterprise Tower - Boston)
        ("fac-06", "am-wifi"), ("fac-06", "am-power"), ("fac-06", "am-meeting"),
        ("fac-06", "am-cafeteria"), ("fac-06", "am-247"), ("fac-06", "am-parking"), ("fac-06", "am-monitors")
    ]

    cursor.executemany("""
    INSERT INTO facility_amenities (facility_id, amenity_id) VALUES (?, ?);
    """, fac_amenities)

    # 5. Seed Workspace Units with coordinates for live interactive architectural blueprints
    units = [
        # Nexus Horizon (fac-01) Units:
        ("unit-01-d01", "fac-01", "Desk A-1", "HOT_DESK", 1, 45, 12.0, 60.0, 450.0, "VACANT", 1, "Zone A - Open Collab", 70, 75, now),
        ("unit-01-d02", "fac-01", "Desk A-2", "HOT_DESK", 1, 45, 12.0, 60.0, 450.0, "OCCUPIED", 1, "Zone A - Open Collab", 170, 75, now),
        ("unit-01-d03", "fac-01", "Desk A-3", "HOT_DESK", 1, 45, 12.0, 60.0, 450.0, "VACANT", 1, "Zone A - Open Collab", 270, 75, now),
        ("unit-01-d04", "fac-01", "Desk A-4", "HOT_DESK", 1, 45, 12.0, 60.0, 450.0, "RESERVED", 1, "Zone A - Open Collab", 370, 75, now),
        ("unit-01-d05", "fac-01", "Desk A-5", "HOT_DESK", 1, 45, 12.0, 60.0, 450.0, "VACANT", 1, "Zone A - Open Collab", 470, 75, now),
        ("unit-01-dd01", "fac-01", "Ergo-Desk B-1", "DEDICATED_DESK", 1, 60, 18.0, 90.0, 650.0, "OCCUPIED", 1, "Zone B - High Perf", 70, 185, now),
        ("unit-01-dd02", "fac-01", "Ergo-Desk B-2", "DEDICATED_DESK", 1, 60, 18.0, 90.0, 650.0, "VACANT", 1, "Zone B - High Perf", 170, 185, now),
        ("unit-01-dd03", "fac-01", "Ergo-Desk B-3", "DEDICATED_DESK", 1, 60, 18.0, 90.0, 650.0, "MAINTENANCE", 1, "Zone B - High Perf", 270, 185, now),
        ("unit-01-c01", "fac-01", "Private Cabin C-1", "PRIVATE_CABIN", 6, 320, 65.0, 350.0, 2600.0, "VACANT", 1, "Zone C - Suites", 400, 185, now),
        ("unit-01-c02", "fac-01", "Private Cabin C-2", "PRIVATE_CABIN", 10, 550, 95.0, 520.0, 3900.0, "OCCUPIED", 1, "Zone C - Suites", 400, 290, now),
        ("unit-01-m01", "fac-01", "Apollo Boardroom", "MEETING_ROOM", 8, 380, 45.0, 240.0, 0.0, "VACANT", 1, "East Wing", 70, 295, now),
        ("unit-01-m02", "fac-01", "Orion Video Studio", "MEETING_ROOM", 4, 180, 30.0, 160.0, 0.0, "VACANT", 1, "East Wing", 230, 295, now),

        # Apex Sanctuary (fac-02) Units:
        ("unit-02-d01", "fac-02", "Focus Desk 1", "HOT_DESK", 1, 50, 14.0, 70.0, 500.0, "VACANT", 2, "Silent Pod Bay", 80, 80, now),
        ("unit-02-d02", "fac-02", "Focus Desk 2", "HOT_DESK", 1, 50, 14.0, 70.0, 500.0, "VACANT", 2, "Silent Pod Bay", 190, 80, now),
        ("unit-02-c01", "fac-02", "Acoustic Cabin Alpha", "PRIVATE_CABIN", 4, 220, 50.0, 280.0, 2100.0, "VACANT", 2, "North Pod", 330, 80, now),
        ("unit-02-m01", "fac-02", "Zen Meeting Nook", "MEETING_ROOM", 6, 260, 40.0, 200.0, 0.0, "VACANT", 2, "North Pod", 330, 200, now),

        # Executive Loft (fac-03) Units:
        ("unit-03-m01", "fac-03", "Summit Boardroom", "MEETING_ROOM", 16, 850, 120.0, 650.0, 0.0, "VACANT", 3, "Penthouse", 90, 90, now),
        ("unit-03-c01", "fac-03", "Executive Suite 301", "PRIVATE_CABIN", 12, 700, 110.0, 590.0, 4500.0, "OCCUPIED", 3, "Penthouse", 280, 90, now),

        # Meridian Austin (fac-04) Units:
        ("unit-04-d01", "fac-04", "Austin Loft Desk 1", "HOT_DESK", 1, 55, 15.0, 75.0, 520.0, "VACANT", 1, "Atrium Bay", 80, 80, now),
        ("unit-04-d02", "fac-04", "Austin Loft Desk 2", "HOT_DESK", 1, 55, 15.0, 75.0, 520.0, "VACANT", 1, "Atrium Bay", 190, 80, now),
        ("unit-04-c01", "fac-04", "Meridian Cabin M-1", "PRIVATE_CABIN", 8, 420, 75.0, 410.0, 3100.0, "VACANT", 1, "West Wing", 320, 80, now),
        ("unit-04-m01", "fac-04", "Glasshouse Conference", "MEETING_ROOM", 10, 480, 55.0, 290.0, 0.0, "VACANT", 1, "Atrium Center", 150, 220, now),

        # Flexo Urban Hive Seattle (fac-05) Units:
        ("unit-05-d01", "fac-05", "Seattle Hive Desk 1", "HOT_DESK", 1, 50, 14.0, 65.0, 480.0, "VACANT", 1, "Open Studio", 80, 80, now),
        ("unit-05-d02", "fac-05", "Seattle Hive Desk 2", "HOT_DESK", 1, 50, 14.0, 65.0, 480.0, "VACANT", 1, "Open Studio", 190, 80, now),
        ("unit-05-c01", "fac-05", "Maker Team Cabin 5", "PRIVATE_CABIN", 6, 310, 60.0, 320.0, 2400.0, "VACANT", 1, "Lab Bay", 330, 80, now),
        ("unit-05-m01", "fac-05", "Soundview Conference", "MEETING_ROOM", 8, 360, 45.0, 230.0, 0.0, "VACANT", 1, "Waterfront", 150, 220, now),

        # Unified Enterprise Tower Boston (fac-06) Units:
        ("unit-06-d01", "fac-06", "Boston Suite Desk 1", "DEDICATED_DESK", 1, 65, 18.0, 95.0, 680.0, "VACANT", 14, "Tower Floor 14", 80, 80, now),
        ("unit-06-c01", "fac-06", "Executive Floorplate A", "PRIVATE_CABIN", 16, 920, 130.0, 720.0, 5500.0, "VACANT", 14, "Tower Floor 14", 260, 80, now),
        ("unit-06-m01", "fac-06", "Auditorium & Boardroom", "MEETING_ROOM", 24, 1200, 160.0, 890.0, 0.0, "VACANT", 14, "Tower Floor 14", 150, 230, now)
    ]

    cursor.executemany("""
    INSERT INTO workspace_units (id, facility_id, unit_identifier, type, capacity, area_sqft, hourly_price, daily_price, monthly_price, current_status, floor_number, zone_name, x_pos, y_pos, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
    """, units)

    # 6. Seed Sample Active Bookings
    start_slot = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=10)).isoformat()
    end_slot = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=3)).isoformat()

    bookings = [
        (
            "b-nexus-01",
            "CG-2026-NEX1",
            "user-freelance-01",
            "unit-01-d02",
            start_slot,
            end_slot,
            36.0,
            "ACTIVE_CHECKED_IN",
            start_slot,
            None,
            "QR-NEXUS-D02-VALID",
            None,
            now
        )
    ]

    cursor.executemany("""
    INSERT INTO bookings (id, booking_code, user_id, unit_id, start_time, end_time, total_amount, status, check_in_time, check_out_time, qr_token, cancellation_reason, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
    """, bookings)

    # 7. Seed Initial Telemetry Logs
    telemetry = [
        ("unit-01-d02", "QR_SCAN", "OCCUPIED", start_slot, json.dumps({"client": "Mobile Web", "ip": "192.168.1.42"})),
        ("unit-01-dd03", "HOST_MANUAL", "MAINTENANCE", now, json.dumps({"issue": "Standing motor inspection"}))
    ]

    cursor.executemany("""
    INSERT INTO telemetry_logs (unit_id, source, event_state, captured_at, metadata)
    VALUES (?, ?, ?, ?, ?);
    """, telemetry)

    # 8. Seed Initial Notifications
    notifications = [
        ("n-01", "user-freelance-01", "EMAIL", "Welcome to SmartCoWork Platform", "Your account has been verified. You can now discover, inspect live floorplans, and reserve verified co-working spaces.", "Email (alex.dev@gmail.com)", now),
        ("n-02", "user-freelance-01", "SMS", "Reservation Active: Desk A-2", "Your reservation at Nexus Horizon Tech Hub is active. Your Digital Pass QR code is valid until 13:50.", "SMS (+1-800-555-0103)", start_slot)
    ]

    cursor.executemany("""
    INSERT INTO notifications (id, user_id, type, title, message, channel, created_at, is_read)
    VALUES (?, ?, ?, ?, ?, ?, ?, 0);
    """, notifications)

    # 9. Seed Sample Expectation Inquiry
    inquiries = [
        (
            "inq-01",
            "user-startup-02",
            "fac-01",
            "Enterprise Workspace Inquiry (5 persons)",
            "We are a 5-person AI startup looking for a private cabin near the acoustic pods. We need dual 1Gbps drops and dedicated access.",
            5,
            now,
            "OPEN",
            None,
            now
        )
    ]

    cursor.executemany("""
    INSERT INTO inquiries (id, user_id, facility_id, subject, message, team_size, target_date, status, response_notes, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
    """, inquiries)

    conn.commit()
    conn.close()
