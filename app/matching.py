"""
Smart Search, Filtering, and Multi-Criteria Matching Engine.
Calculates dynamic suitability scores based on team size, budget, area, amenities, work style,
and real-time live availability.
"""

import math
from .database import get_db

def calculate_match_score(facility: dict, criteria: dict) -> dict:
    """
    Computes a normalized suitability match score (0 to 100) and breakdown
    for a given facility against user-specified requirements.
    """
    scores = {}
    weights = {
        "capacity": 0.30,
        "budget": 0.25,
        "amenities": 0.25,
        "work_style": 0.10,
        "live_availability": 0.10
    }

    team_bracket = criteria.get("team_bracket", "all")
    budget_bracket = criteria.get("budget_bracket", "all")
    req_amenities = criteria.get("amenities", [])
    req_work_style = criteria.get("work_style", None)

    # Resolve target team size from bracket
    if team_bracket == "solo":
        req_persons = 1
    elif team_bracket == "small":
        req_persons = 4
    elif team_bracket == "growth":
        req_persons = 8
    elif team_bracket == "enterprise":
        req_persons = 16
    else:
        req_persons = int(criteria.get("team_size", 1) or 1)

    # 1. Capacity Score
    matching_units = [u for u in facility.get("units", []) if u["capacity"] >= req_persons]
    if matching_units:
        best_capacity = min(u["capacity"] for u in matching_units)
        diff = best_capacity - req_persons
        capacity_score = math.exp(-((diff / 4.0) ** 2))
    else:
        max_cap = max([u["capacity"] for u in facility.get("units", [])], default=1)
        capacity_score = max(0.15, max_cap / float(req_persons))
    scores["capacity"] = round(capacity_score, 2)

    # 2. Budget Score
    budget_caps = {
        "economy": 25.0,
        "standard": 50.0,
        "executive": 90.0,
        "premium": 150.0
    }
    max_budget = budget_caps.get(budget_bracket, criteria.get("max_budget"))

    if max_budget and max_budget > 0:
        prices = [u["hourly_price"] for u in facility.get("units", []) if u.get("hourly_price")]
        if prices:
            min_price = min(prices)
            if min_price <= max_budget:
                budget_score = 1.0
            else:
                over = min_price - max_budget
                budget_score = max(0.0, 1.0 - (over / float(max_budget)))
        else:
            budget_score = 0.5
    else:
        budget_score = 1.0
    scores["budget"] = round(budget_score, 2)

    # 3. Amenity Overlap Score
    facility_amenity_codes = set(a["code"] for a in facility.get("amenities", []))
    if req_amenities and len(req_amenities) > 0:
        matched = set(req_amenities).intersection(facility_amenity_codes)
        amenity_score = len(matched) / float(len(req_amenities))
    else:
        amenity_score = 1.0
    scores["amenities"] = round(amenity_score, 2)

    # 4. Work Style & Atmosphere Expectation
    if req_work_style and req_work_style != "all":
        if facility.get("work_style") == req_work_style:
            work_style_score = 1.0
        else:
            work_style_score = 0.35
    else:
        work_style_score = 1.0
    scores["work_style"] = round(work_style_score, 2)

    # 5. Live Availability Bonus
    vacant_count = facility.get("vacant_units_count", 0)
    total_units = facility.get("total_units_count", 1) or 1
    availability_ratio = vacant_count / float(total_units)
    scores["live_availability"] = round(availability_ratio, 2)

    # Composite Weighted Score (0 to 100)
    total_score = (
        weights["capacity"] * scores["capacity"] +
        weights["budget"] * scores["budget"] +
        weights["amenities"] * scores["amenities"] +
        weights["work_style"] * scores["work_style"] +
        weights["live_availability"] * scores["live_availability"]
    ) * 100.0

    return {
        "overall_score": int(round(total_score)),
        "breakdown": scores,
        "is_recommended": total_score >= 70
    }

def search_spaces(filters: dict) -> list[dict]:
    """
    Search and rank co-working spaces with dynamic filtering and smart scoring.
    """
    conn = get_db()
    cursor = conn.cursor()

    query = """
    SELECT f.*, u.full_name as owner_name, u.email as owner_email, u.company_name as owner_company
    FROM facilities f
    JOIN users u ON f.owner_id = u.id
    WHERE f.status = 'ACTIVE'
    """
    params = []

    # City filter
    city = filters.get("city")
    if city and city.lower() != "all":
        query += " AND LOWER(f.city) LIKE ?"
        params.append(f"%{city.strip().lower()}%")

    # Work Style filter
    work_style = filters.get("work_style")
    if work_style and work_style.lower() != "all":
        query += " AND f.work_style = ?"
        params.append(work_style)

    # Area size bracket filter
    area_bracket = filters.get("area_bracket")
    if area_bracket == "compact":
        query += " AND f.total_area_sqft <= 14000"
    elif area_bracket == "medium":
        query += " AND f.total_area_sqft > 14000 AND f.total_area_sqft <= 20000"
    elif area_bracket == "large":
        query += " AND f.total_area_sqft > 20000"

    cursor.execute(query, params)
    facility_rows = cursor.fetchall()

    results = []
    for f in facility_rows:
        fac = dict(f)

        # Fetch units
        cursor.execute("""
        SELECT * FROM workspace_units WHERE facility_id = ? ORDER BY floor_number, unit_identifier;
        """, (fac["id"],))
        units = [dict(u) for u in cursor.fetchall()]
        fac["units"] = units

        # Compute unit counts by status
        fac["total_units_count"] = len(units)
        fac["vacant_units_count"] = sum(1 for u in units if u["current_status"] == "VACANT")
        fac["occupied_units_count"] = sum(1 for u in units if u["current_status"] == "OCCUPIED")
        fac["reserved_units_count"] = sum(1 for u in units if u["current_status"] == "RESERVED")
        fac["maintenance_units_count"] = sum(1 for u in units if u["current_status"] == "MAINTENANCE")

        # Fetch amenities
        cursor.execute("""
        SELECT a.id, a.code, a.name, a.category, a.icon 
        FROM amenities a
        JOIN facility_amenities fa ON a.id = fa.amenity_id
        WHERE fa.facility_id = ?;
        """, (fac["id"],))
        fac["amenities"] = [dict(a) for a in cursor.fetchall()]

        # Filter: Required Unit Type
        req_type = filters.get("unit_type")
        if req_type and req_type.lower() != "all":
            has_type = any(u["type"] == req_type for u in units)
            if not has_type:
                continue

        # Filter: Team bracket matching
        team_bracket = filters.get("team_bracket")
        if team_bracket == "solo":
            if not any(u["capacity"] == 1 for u in units):
                continue
        elif team_bracket == "small":
            if not any(2 <= u["capacity"] <= 5 for u in units):
                continue
        elif team_bracket == "growth":
            if not any(6 <= u["capacity"] <= 15 for u in units):
                continue
        elif team_bracket == "enterprise":
            if not any(u["capacity"] >= 16 for u in units):
                continue

        # Calculate Smart Match Score
        fac["match_metrics"] = calculate_match_score(fac, filters)
        results.append(fac)

    conn.close()

    # Sort primarily by Smart Match Score descending, secondarily by vacant units
    results.sort(key=lambda x: (x["match_metrics"]["overall_score"], x["vacant_units_count"]), reverse=True)
    return results
