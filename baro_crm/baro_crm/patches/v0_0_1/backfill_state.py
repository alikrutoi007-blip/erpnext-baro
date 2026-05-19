"""
Patch: backfill the new `service_state` field on existing Repair Job rows.

Strategy: parse the existing free-text `area` value and map it to one of the
four service states (Texas, Florida, New York, New Jersey). Rows that don't
match any keyword are left blank for a manager to fill in.

Idempotent: only touches rows where service_state is empty.
"""

import frappe


# Lowercase keyword -> state. Order matters when keywords overlap (none here).
CITY_TO_STATE = {
    # New York
    "new york": "New York",
    "ny ": "New York",
    ", ny": "New York",
    "brooklyn": "New York",
    "manhattan": "New York",
    "queens": "New York",
    "bronx": "New York",
    "staten island": "New York",
    "long island": "New York",
    "buffalo": "New York",
    "rochester": "New York",
    # Florida
    "florida": "Florida",
    " fl ": "Florida",
    ", fl": "Florida",
    "tampa": "Florida",
    "miami": "Florida",
    "orlando": "Florida",
    "jacksonville": "Florida",
    "tallahassee": "Florida",
    "fort lauderdale": "Florida",
    "naples": "Florida",
    "sarasota": "Florida",
    "key west": "Florida",
    # Texas
    "texas": "Texas",
    " tx ": "Texas",
    ", tx": "Texas",
    "houston": "Texas",
    "dallas": "Texas",
    "austin": "Texas",
    "san antonio": "Texas",
    "fort worth": "Texas",
    "el paso": "Texas",
    "arlington": "Texas",
    # New Jersey
    "new jersey": "New Jersey",
    " nj ": "New Jersey",
    ", nj": "New Jersey",
    "newark": "New Jersey",
    "jersey city": "New Jersey",
    "paterson": "New Jersey",
    "elizabeth": "New Jersey",
    "trenton": "New Jersey",
    "atlantic city": "New Jersey",
}


def execute():
    if not frappe.db.has_column("tabRepair Job", "service_state"):
        # Custom Field fixture hasn't installed yet — bench migrate will retry.
        print("backfill_state: tabRepair Job.service_state not present yet, skipping")
        return

    rows = frappe.get_all(
        "Repair Job",
        fields=["name", "area"],
        filters=[["service_state", "in", ["", None]]],
    )

    if not rows:
        print("backfill_state: no rows need backfill")
        return

    updated = 0
    unmatched = 0
    for r in rows:
        area = (r.get("area") or "").lower()
        if not area:
            unmatched += 1
            continue

        # Pad with spaces so " ny " keyword matches "USA, NY" after lowercase
        padded = f" {area} "
        state = None
        for keyword, state_name in CITY_TO_STATE.items():
            if keyword in padded:
                state = state_name
                break

        if state:
            frappe.db.set_value(
                "Repair Job",
                r["name"],
                "service_state",
                state,
                update_modified=False,
            )
            updated += 1
        else:
            unmatched += 1

    frappe.db.commit()
    print(
        f"backfill_state: updated {updated} of {len(rows)} Repair Jobs "
        f"({unmatched} left for manager to assign)"
    )
