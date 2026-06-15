#!/usr/bin/env python3
"""
Watcher demo seed script.

Creates a realistic set of seller accounts and listings that exercise the
full moderation pipeline:
  - Auto-APPROVE: clean, legitimate listings
  - REVIEW:       ambiguous listings requiring human judgement
  - REJECT:       clear policy violations

The submit endpoint is async -- moderation runs in the background via Ollama.
After all submissions, the script polls /api/stats and prints a summary.

Usage:
    python3 scripts/seed.py \\
        --db-password <pw> \\
        --user-password <seller-password>

Passwords from:
    ./aixcl app secrets watcher

Dependencies (all in watcher/requirements.txt):
    pip install httpx psycopg2-binary pillow
"""

import argparse
import hashlib
import io
import random
import secrets
import sys
import time

import httpx
import psycopg2
from PIL import Image, ImageDraw

# ---------------------------------------------------------------------------
# Seller profiles
# ---------------------------------------------------------------------------

SELLERS = [
    {
        "username": "alice",
        "email": "alice@example.com",
        "violations": 0,
        "account_age_days": 730,   # 2-year established seller
        "note": "Established seller, clean history",
    },
    {
        "username": "bob",
        "email": "bob@example.com",
        "violations": 0,
        "account_age_days": 180,   # 6-month seller, newer but clean
        "note": "Newer seller, clean history",
    },
    {
        "username": "carlos",
        "email": "carlos@example.com",
        "violations": 1,
        "account_age_days": 365,   # 1-year account, one prior flag
        "note": "Previously flagged once",
    },
    {
        "username": "diana",
        "email": "diana@example.com",
        "violations": 2,
        "account_age_days": 90,    # 3-month account, repeat offender
        "note": "Known policy violator",
    },
]

# ---------------------------------------------------------------------------
# Listings: (seller, title, category, description, price, expected_outcome)
# ---------------------------------------------------------------------------

LISTINGS = [
    # --- Clean approvals ---
    (
        "alice",
        "iPhone 14 Pro 256GB Space Black",
        "Electronics",
        "Selling my iPhone 14 Pro in excellent condition. Screen protector applied from day one, no scratches. "
        "Battery health 97%. Comes with original box, charger, and unused EarPods. "
        "Unlocked, works with any carrier. Upgraded to iPhone 15, hence selling.",
        749.00,
        "APPROVE",
    ),
    (
        "alice",
        "Vintage Levis 501 Jeans Size 32x30",
        "Clothing",
        "Classic Levi's 501 straight fit jeans in dark indigo wash. Barely worn, excellent condition. "
        "Size 32 waist, 30 inseam. Original shrink-to-fit 100% cotton version. "
        "No rips, no fading. Great addition to any wardrobe.",
        45.00,
        "APPROVE",
    ),
    (
        "bob",
        "KitchenAid Stand Mixer 5 Qt Artisan",
        "Home",
        "KitchenAid Artisan 5-quart stand mixer in Empire Red. Used for about a year, works perfectly. "
        "Comes with all original attachments: flat beater, dough hook, wire whip, and pouring shield. "
        "Moving abroad and cannot take it with me. Original retail $450.",
        220.00,
        "APPROVE",
    ),
    (
        "bob",
        "Trek FX 3 Disc Hybrid Bike 2022",
        "Vehicles",
        "Trek FX 3 Disc hybrid bike, 2022 model, size Medium. Used for commuting, approximately 500 miles. "
        "Hydraulic disc brakes, Shimano Altus drivetrain, puncture-resistant tyres. "
        "Serviced 2 months ago. Selling because I moved closer to work.",
        580.00,
        "APPROVE",
    ),
    (
        "alice",
        "Sony WH-1000XM5 Wireless Headphones",
        "Electronics",
        "Sony WH-1000XM5 noise cancelling headphones. Purchased 6 months ago, in perfect condition. "
        "Comes with original carry case, USB-C cable, and 3.5mm audio cable. "
        "Industry-leading noise cancellation, 30-hour battery life. No scratches or marks.",
        249.00,
        "APPROVE",
    ),
    # --- Borderline / REVIEW ---
    (
        "carlos",
        "Phone Unlocking Service All Networks",
        "Services",
        "Professional phone unlocking service for all major carriers. Remote unlock within 24 hours. "
        "Works for iPhone and Android. Permanent unlock, no software required. "
        "Over 500 satisfied customers. Contact me with your IMEI number.",
        35.00,
        "REVIEW",
    ),
    (
        "carlos",
        "Vintage Military Surplus Jacket US Army M65",
        "Clothing",
        "Authentic US Army M65 field jacket from 1970s military surplus. "
        "Olive drab, size Large Regular. Some wear consistent with age, all buttons intact. "
        "Collector item, not reproduction. Great for outdoor activities.",
        85.00,
        "REVIEW",
    ),
    (
        "carlos",
        "Chemistry Set Advanced Home Lab Kit",
        "Other",
        "Advanced chemistry set for serious hobbyists and home experimenters. "
        "Includes 40+ reagents, glassware, and instruction manual. "
        "Everything you need for titration, crystallisation, and organic synthesis experiments. "
        "Suitable for adults only.",
        120.00,
        "REVIEW",
    ),
    (
        "bob",
        "Lockpick Set Professional Grade",
        "Other",
        "Professional lockpick set with 24 picks and 4 tension wrenches. "
        "Stainless steel, lifetime warranty. Used by locksmiths and security professionals. "
        "Legal in most jurisdictions. Includes carrying case.",
        55.00,
        "REVIEW",
    ),
    # --- Clear violations / REJECT ---
    (
        "diana",
        "Louis Vuitton Neverfull MM Brand New",
        "Clothing",
        "Brand new Louis Vuitton Neverfull MM tote bag. Monogram canvas with beige interior. "
        "Gold hardware. Comes with dust bag. Beautiful bag, perfect condition. "
        "Originally purchased from a supplier in Guangzhou. Great quality.",
        180.00,
        "REJECT",
    ),
    (
        "diana",
        "Tramadol 50mg 100 Tablets No Prescription",
        "Other",
        "Selling unopened pack of Tramadol 50mg tablets, 100 count. "
        "Prescription not required for purchase. Fast discreet shipping. "
        "Contact me for bulk pricing. Multiple packs available.",
        60.00,
        "REJECT",
    ),
    (
        "diana",
        "Stun Gun 1 Million Volt Self Defence",
        "Other",
        "High voltage stun gun for personal protection. 1 million volt output. "
        "Rechargeable battery, LED flashlight included. Compact design fits in pocket. "
        "Shipping available to all locations. No questions asked.",
        45.00,
        "REJECT",
    ),
    (
        "diana",
        "Get 10000 Instagram Followers Guaranteed",
        "Services",
        "Boost your Instagram instantly! 10,000 real-looking followers delivered within 48 hours. "
        "100% guaranteed or money back. Our bot network ensures rapid growth. "
        "Safe, permanent, and undetectable. DM for bulk packages.",
        25.00,
        "REJECT",
    ),
]

# ---------------------------------------------------------------------------
# Password hashing (mirrors auth.py -- no external dependencies)
# ---------------------------------------------------------------------------

def _hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    hashed = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100000)
    return f"pbkdf2_sha256${salt}${hashed.hex()}"


# ---------------------------------------------------------------------------
# Image generation (PIL only, no network)
# ---------------------------------------------------------------------------

PALETTE = [
    ("#6366f1", "#ffffff"),
    ("#22c55e", "#ffffff"),
    ("#f59e0b", "#1f2937"),
    ("#06b6d4", "#ffffff"),
    ("#8b5cf6", "#ffffff"),
    ("#ef4444", "#ffffff"),
    ("#0f172a", "#f1f5f9"),
    ("#64748b", "#ffffff"),
]


def _hex_rgb(h: str) -> tuple:
    h = h.lstrip("#")
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))


def make_image(title: str, category: str) -> bytes:
    bg_hex, fg_hex = random.choice(PALETTE)
    bg, fg = _hex_rgb(bg_hex), _hex_rgb(fg_hex)

    img = Image.new("RGB", (640, 480), bg)
    draw = ImageDraw.Draw(img)

    # Category bar
    bar_fill = fg if fg != (255, 255, 255) else (200, 200, 200)
    draw.rectangle([0, 0, 640, 60], fill=bar_fill)
    draw.text((20, 18), category.upper(), fill=bg)

    # Wrapped title
    words = title.split()
    lines, current = [], []
    for word in words:
        if len(" ".join(current + [word])) <= 28:
            current.append(word)
        else:
            lines.append(" ".join(current))
            current = [word]
    if current:
        lines.append(" ".join(current))

    y = 200 - len(lines) * 20
    for line in lines:
        draw.text((320, y), line, fill=fg, anchor="mm")
        y += 40

    draw.rectangle([40, 390, 600, 440], outline=fg, width=2)
    draw.text((320, 415), "CASHI SHOP", fill=fg, anchor="mm")

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Database: create seller accounts
# ---------------------------------------------------------------------------

def create_sellers(sellers: list, db_host: str, db_port: int,
                   db_name: str, db_user: str, db_password: str,
                   user_password: str) -> None:
    from datetime import datetime, timedelta, timezone

    conn = psycopg2.connect(
        host=db_host, port=db_port, dbname=db_name,
        user=db_user, password=db_password,
    )
    with conn:
        with conn.cursor() as cur:
            for s in sellers:
                pw_hash = _hash_password(user_password)
                age_days = s.get("account_age_days", 0)
                created_at = datetime.now(timezone.utc) - timedelta(days=age_days)
                cur.execute("""
                    INSERT INTO watcher.users
                        (username, email, password_hash, is_admin,
                         previous_violation_count, created_at)
                    VALUES (%s, %s, %s, FALSE, %s, %s)
                    ON CONFLICT (username) DO UPDATE
                        SET previous_violation_count = EXCLUDED.previous_violation_count,
                            email = EXCLUDED.email,
                            password_hash = EXCLUDED.password_hash,
                            created_at = EXCLUDED.created_at
                """, (s["username"], s["email"], pw_hash, s["violations"], created_at))
                print(f"    {s['username']:10s}  {s['note']}  (account age: {age_days}d)")
    conn.close()


# ---------------------------------------------------------------------------
# API: submit a listing
# ---------------------------------------------------------------------------

def submit_listing(api: str, seller: str, title: str,
                   category: str, description: str, price: float) -> str | None:
    """Submit a listing and return the listing_id, or None on error."""
    image_bytes = make_image(title, category)
    data = {
        "user_id": seller,
        "title": title,
        "category": category,
        "description": description,
        "price": str(price),
    }
    files = {"images": (f"{seller}.jpg", image_bytes, "image/jpeg")}

    with httpx.Client(base_url=api, timeout=30) as client:
        r = client.post("/api/submit", data=data, files=files)
        if r.status_code != 200:
            print(f"    ERROR {r.status_code}: {r.text[:120]}", file=sys.stderr)
            return None
        return r.json().get("listing_id")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="Seed watcher with demo listings")
    ap.add_argument("--api",           default="http://localhost:9104")
    ap.add_argument("--db-host",       default="localhost")
    ap.add_argument("--db-port",       type=int, default=5432)
    ap.add_argument("--db-name",       default="watcher")
    ap.add_argument("--db-user",       default="watcher")
    ap.add_argument("--db-password",   required=True)
    ap.add_argument("--user-password", required=True,
                    help="Password all seller accounts will share")
    ap.add_argument("--delay",         type=float, default=0.5,
                    help="Seconds between submissions (default: 0.5)")
    ap.add_argument("--wait",          type=int, default=30,
                    help="Seconds to wait for background moderation before printing stats (default: 30)")
    args = ap.parse_args()

    print("\nWatcher Demo Seed")
    print("=" * 60)

    # 1. Create seller accounts
    print("\n[1/3] Creating seller accounts...")
    try:
        create_sellers(
            sellers=SELLERS,
            db_host=args.db_host,
            db_port=args.db_port,
            db_name=args.db_name,
            db_user=args.db_user,
            db_password=args.db_password,
            user_password=args.user_password,
        )
    except Exception as e:
        print(f"  ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    # 2. Submit listings
    print(f"\n[2/3] Submitting {len(LISTINGS)} listings (moderation is async)...")
    submitted, errors = [], 0
    for seller, title, category, description, price, expected in LISTINGS:
        listing_id = submit_listing(
            api=args.api,
            seller=seller,
            title=title,
            category=category,
            description=description,
            price=price,
        )
        if listing_id:
            submitted.append((listing_id, title, expected))
            print(f"    queued  {title[:50]:<50}  (expected {expected})")
        else:
            errors += 1
        if args.delay > 0:
            time.sleep(args.delay)

    # 3. Wait for Ollama to process, then print stats
    if submitted and args.wait > 0:
        print(f"\n[3/3] Waiting {args.wait}s for Ollama moderation to complete...")
        time.sleep(args.wait)

        try:
            with httpx.Client(base_url=args.api, timeout=10) as client:
                r = client.get("/api/stats")
                if r.status_code == 200:
                    s = r.json()
                    print(f"\n  Stats from /api/stats:")
                    print(f"    total listings   : {s.get('total_listings', 0)}")
                    print(f"    published        : {s.get('published_listings', 0)}")
                    print(f"    pending review   : {s.get('pending_review', 0)}")
                    print(f"    rejected         : {s.get('rejected_listings', 0)}")
        except Exception as e:
            print(f"  (could not fetch stats: {e})")

    print(f"\n{'=' * 60}")
    print(f"Done. {len(submitted)}/{len(LISTINGS)} listings submitted, {errors} error(s).")
    print(f"Storefront  : {args.api}/")
    print(f"Review queue: {args.api}/#/review  (log in as admin)")
    print(f"Dashboard   : {args.api}/#/dashboard")
    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
