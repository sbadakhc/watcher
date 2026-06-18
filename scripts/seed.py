#!/usr/bin/env python3
"""
Watcher demo seed script.

Creates a realistic set of seller accounts and listings that exercise the
full moderation pipeline:
  - Auto-APPROVE: clean, legitimate listings
  - REVIEW:       ambiguous listings requiring human judgement
  - REJECT:       clear policy violations

Each listing gets a distinct product card image. If scripts/images/<key>.jpg
(or .png) exists, it is used directly. Otherwise a PIL-generated card is
produced. Drop real product photos into scripts/images/ to upgrade the demo.

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
import math
import secrets
import sys
import time
from pathlib import Path

import httpx
import psycopg2
from PIL import Image, ImageDraw, ImageFont

# ---------------------------------------------------------------------------
# Seller profiles
# ---------------------------------------------------------------------------

SELLERS = [
    {
        "username": "alice",
        "email": "alice@example.com",
        "violations": 0,
        "account_age_days": 730,
        "note": "Established seller, clean history",
    },
    {
        "username": "bob",
        "email": "bob@example.com",
        "violations": 0,
        "account_age_days": 180,
        "note": "Newer seller, clean history",
    },
    {
        "username": "carlos",
        "email": "carlos@example.com",
        "violations": 1,
        "account_age_days": 365,
        "note": "Previously flagged once",
    },
    {
        "username": "diana",
        "email": "diana@example.com",
        "violations": 2,
        "account_age_days": 90,
        "note": "Known policy violator",
    },
]

# ---------------------------------------------------------------------------
# Listings: (seller, title, category, description, price, expected, image_key)
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
        "iphone",
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
        "jeans",
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
        "mixer",
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
        "bike",
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
        "headphones",
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
        "phone-unlock",
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
        "army-jacket",
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
        "chemistry-set",
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
        "lockpick",
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
        "fake-bag",
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
        "prescription-drugs",
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
        "stun-gun",
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
        "fake-followers",
    ),
]

# ---------------------------------------------------------------------------
# Password hashing (mirrors auth.py)
# ---------------------------------------------------------------------------


def _hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    hashed = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100000)
    return f"pbkdf2_sha256${salt}${hashed.hex()}"


# ---------------------------------------------------------------------------
# Image generation
# ---------------------------------------------------------------------------

IMAGE_DIR = Path(__file__).parent / "images"

_W, _H = 640, 480
_HEADER = 64
_FOOTER = 110
_IL_Y = _HEADER                        # illustration top
_IL_H = _H - _HEADER - _FOOTER        # illustration height
_CX = _W // 2
_CY = _HEADER + _IL_H // 2            # illustration centre y


def _rgb(h: str) -> tuple:
    h = h.lstrip("#")
    return tuple(int(h[i : i + 2], 16) for i in (0, 2, 4))


def _font(size: int) -> ImageFont.ImageFont:
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


# --- per-product drawing functions -------------------------------------------

def _draw_iphone(draw: ImageDraw.ImageDraw) -> None:
    cx, cy = _CX, _CY
    w, h = 110, 210
    body = _rgb("#1c1c1e")
    screen = _rgb("#0a1628")
    accent = _rgb("#3b82f6")
    draw.rounded_rectangle([cx - w//2, cy - h//2, cx + w//2, cy + h//2], radius=20, fill=body)
    sw, sh = w - 14, h - 36
    draw.rounded_rectangle([cx - sw//2, cy - sh//2, cx + sw//2, cy + sh//2], radius=12, fill=screen)
    # Dynamic Island
    draw.rounded_rectangle([cx - 22, cy - h//2 + 10, cx + 22, cy - h//2 + 24], radius=8, fill=_rgb("#000000"))
    # Home bar
    draw.rounded_rectangle([cx - 28, cy + h//2 - 14, cx + 28, cy + h//2 - 7], radius=4, fill=_rgb("#3a3a3c"))
    # App grid (4x3 dots to simulate home screen)
    for row in range(3):
        for col in range(4):
            ax = cx - 36 + col * 24
            ay = cy - 40 + row * 30
            draw.ellipse([ax - 8, ay - 8, ax + 8, ay + 8], fill=accent)
    # Side button
    draw.rectangle([cx + w//2, cy - 40, cx + w//2 + 5, cy - 10], fill=_rgb("#3a3a3c"))


def _draw_jeans(draw: ImageDraw.ImageDraw) -> None:
    cx, cy = _CX, _CY
    denim = _rgb("#1e40af")
    light = _rgb("#2563eb")
    gold = _rgb("#d97706")
    shadow = _rgb("#1e3a8a")
    # Waistband
    draw.rectangle([cx - 85, cy - 105, cx + 85, cy - 80], fill=gold)
    draw.line([cx - 85, cy - 88, cx + 85, cy - 88], fill=_rgb("#92400e"), width=2)
    # Belt loops
    for bx in [cx - 60, cx - 20, cx + 20, cx + 60]:
        draw.rectangle([bx - 5, cy - 110, bx + 5, cy - 78], fill=_rgb("#92400e"))
    # Left leg
    draw.polygon([cx - 85, cy - 80, cx - 5, cy - 80, cx - 15, cy + 110, cx - 95, cy + 110], fill=denim)
    draw.polygon([cx - 85, cy - 80, cx - 5, cy - 80, cx - 12, cy - 20, cx - 80, cy - 20], fill=light)
    # Right leg
    draw.polygon([cx + 5, cy - 80, cx + 85, cy - 80, cx + 95, cy + 110, cx + 15, cy + 110], fill=denim)
    draw.polygon([cx + 5, cy - 80, cx + 85, cy - 80, cx + 80, cy - 20, cx + 12, cy - 20], fill=light)
    # Centre seam
    draw.line([cx, cy - 80, cx, cy + 20], fill=_rgb("#1d4ed8"), width=3)
    # Stitch lines on waistband
    for x in range(cx - 70, cx + 75, 18):
        draw.line([x, cy - 100, x + 10, cy - 100], fill=_rgb("#92400e"), width=2)
    # Rivet dots
    for rx in [cx - 70, cx + 70]:
        draw.ellipse([rx - 5, cy - 102, rx + 5, cy - 92], fill=gold)


def _draw_mixer(draw: ImageDraw.ImageDraw) -> None:
    cx, cy = _CX, _CY
    red = _rgb("#dc2626")
    chrome = _rgb("#9ca3af")
    bowl_c = _rgb("#e5e7eb")
    dark = _rgb("#1f2937")
    # Base
    draw.rectangle([cx - 75, cy + 65, cx + 75, cy + 90], fill=dark)
    draw.rectangle([cx - 55, cy + 45, cx + 55, cy + 70], fill=chrome)
    # Stand column
    draw.rectangle([cx - 18, cy - 30, cx + 18, cy + 50], fill=chrome)
    # Mixer head
    draw.ellipse([cx - 80, cy - 100, cx + 60, cy + 10], fill=red)
    draw.ellipse([cx - 70, cy - 90, cx + 50, cy + 0], fill=_rgb("#ef4444"))
    # Speed dial
    draw.ellipse([cx - 20, cy - 70, cx + 20, cy - 30], fill=dark)
    draw.ellipse([cx - 14, cy - 64, cx + 14, cy - 36], fill=chrome)
    draw.line([cx, cy - 50, cx + 8, cy - 42], fill=dark, width=3)
    # Bowl
    draw.ellipse([cx - 80, cy + 15, cx + 80, cy + 90], fill=bowl_c, outline=chrome, width=3)
    # Beaters descending into bowl
    draw.line([cx - 15, cy - 20, cx - 20, cy + 50], fill=chrome, width=5)
    draw.line([cx + 15, cy - 20, cx + 20, cy + 50], fill=chrome, width=5)


def _draw_bike(draw: ImageDraw.ImageDraw) -> None:
    cx, cy = _CX, _CY + 20
    r = 80
    frame = _rgb("#374151")
    orange = _rgb("#f97316")
    silver = _rgb("#9ca3af")
    # Left wheel
    lx = cx - 115
    draw.ellipse([lx - r, cy - r, lx + r, cy + r], outline=frame, width=8)
    draw.ellipse([lx - r + 12, cy - r + 12, lx + r - 12, cy + r - 12], outline=silver, width=3)
    draw.ellipse([lx - 10, cy - 10, lx + 10, cy + 10], fill=frame)
    for angle in range(0, 180, 60):
        x1 = lx + int((r - 4) * math.cos(math.radians(angle)))
        y1 = cy + int((r - 4) * math.sin(math.radians(angle)))
        x2 = lx - int((r - 4) * math.cos(math.radians(angle)))
        y2 = cy - int((r - 4) * math.sin(math.radians(angle)))
        draw.line([x1, y1, x2, y2], fill=frame, width=3)
    # Right wheel
    rx = cx + 115
    draw.ellipse([rx - r, cy - r, rx + r, cy + r], outline=frame, width=8)
    draw.ellipse([rx - r + 12, cy - r + 12, rx + r - 12, cy + r - 12], outline=silver, width=3)
    draw.ellipse([rx - 10, cy - 10, rx + 10, cy + 10], fill=frame)
    for angle in range(0, 180, 60):
        x1 = rx + int((r - 4) * math.cos(math.radians(angle)))
        y1 = cy + int((r - 4) * math.sin(math.radians(angle)))
        x2 = rx - int((r - 4) * math.cos(math.radians(angle)))
        y2 = cy - int((r - 4) * math.sin(math.radians(angle)))
        draw.line([x1, y1, x2, y2], fill=frame, width=3)
    # Frame: chain stay (rear) + seat stay
    draw.line([lx, cy, cx - 20, cy - 60], fill=orange, width=7)  # chain stay
    draw.line([cx - 20, cy - 60, rx, cy], fill=orange, width=7)  # seat stay
    draw.line([cx - 20, cy - 60, cx + 20, cy - 60], fill=frame, width=7)  # top tube
    draw.line([cx - 20, cy - 60, cx, cy - 90], fill=frame, width=7)  # seat tube
    draw.line([cx + 20, cy - 60, cx + 40, cy - 95], fill=frame, width=7)  # head tube
    # Handlebars
    draw.line([cx + 40, cy - 95, cx + 20, cy - 110], fill=frame, width=6)
    draw.line([cx + 20, cy - 110, cx + 35, cy - 105], fill=frame, width=6)
    # Saddle
    draw.rounded_rectangle([cx - 30, cy - 98, cx + 10, cy - 88], radius=4, fill=frame)


def _draw_headphones(draw: ImageDraw.ImageDraw) -> None:
    cx, cy = _CX, _CY + 20
    r = 95
    body = _rgb("#1c1c1e")
    silver = _rgb("#6b7280")
    accent = _rgb("#3b82f6")
    cushion = _rgb("#374151")
    # Headband
    draw.arc([cx - r, cy - r, cx + r, cy + r], start=200, end=340, fill=body, width=16)
    # Headband padding
    draw.arc([cx - r + 8, cy - r + 8, cx + r - 8, cy + r - 8], start=205, end=335, fill=silver, width=6)
    # Left earcup
    lx, ly = cx - r - 5, cy + 10
    draw.ellipse([lx - 38, ly - 45, lx + 38, ly + 45], fill=cushion)
    draw.ellipse([lx - 30, ly - 37, lx + 30, ly + 37], fill=body)
    draw.ellipse([lx - 20, ly - 27, lx + 20, ly + 27], fill=accent)
    draw.ellipse([lx - 8, ly - 8, lx + 8, ly + 8], fill=silver)
    # Right earcup
    rx, ry = cx + r + 5, cy + 10
    draw.ellipse([rx - 38, ry - 45, rx + 38, ry + 45], fill=cushion)
    draw.ellipse([rx - 30, ry - 37, rx + 30, ry + 37], fill=body)
    draw.ellipse([rx - 20, ry - 27, rx + 20, ry + 27], fill=accent)
    draw.ellipse([rx - 8, ry - 8, rx + 8, ry + 8], fill=silver)
    # Cable from left cup
    draw.line([lx, ly + 45, lx, ly + 80, lx + 20, ly + 100], fill=silver, width=3)


def _draw_phone_unlock(draw: ImageDraw.ImageDraw) -> None:
    cx, cy = _CX, _CY
    body = _rgb("#1e293b")
    screen = _rgb("#0f172a")
    gold = _rgb("#f59e0b")
    dark = _rgb("#78350f")
    # Phone
    draw.rounded_rectangle([cx - 65, cy - 110, cx + 65, cy + 90], radius=14, fill=body)
    draw.rounded_rectangle([cx - 55, cy - 100, cx + 55, cy + 80], radius=10, fill=screen)
    # Lock body (centred on screen)
    draw.rounded_rectangle([cx - 35, cy - 20, cx + 35, cy + 45], radius=7, fill=gold)
    # Shackle
    draw.arc([cx - 22, cy - 65, cx + 22, cy - 10], start=0, end=180, fill=gold, width=10)
    # Keyhole
    draw.ellipse([cx - 9, cy - 5, cx + 9, cy + 13], fill=dark)
    draw.polygon([cx - 7, cy + 13, cx + 7, cy + 13, cx + 10, cy + 30, cx - 10, cy + 30], fill=dark)
    # Unlock indicator (green tick to the side)
    draw.ellipse([cx + 40, cy - 70, cx + 70, cy - 40], fill=_rgb("#16a34a"))
    draw.line([cx + 48, cy - 55, cx + 54, cy - 48, cx + 63, cy - 62], fill=_rgb("#ffffff"), width=3)


def _draw_army_jacket(draw: ImageDraw.ImageDraw) -> None:
    cx, cy = _CX, _CY
    olive = _rgb("#4a5e2a")
    dark_olive = _rgb("#374520")
    khaki = _rgb("#8b8360")
    button = _rgb("#c4b078")
    # Main jacket body
    draw.polygon([
        cx - 90, cy - 110,
        cx + 90, cy - 110,
        cx + 110, cy + 100,
        cx - 110, cy + 100,
    ], fill=olive)
    # Shading
    draw.polygon([cx - 90, cy - 110, cx, cy - 110, cx, cy + 100, cx - 110, cy + 100], fill=dark_olive)
    # Left lapel
    draw.polygon([cx - 70, cy - 110, cx - 5, cy - 60, cx - 5, cy + 10, cx - 55, cy + 10, cx - 70, cy - 55], fill=_rgb("#3d4f1e"))
    # Right lapel
    draw.polygon([cx + 70, cy - 110, cx + 5, cy - 60, cx + 5, cy + 10, cx + 55, cy + 10, cx + 70, cy - 55], fill=_rgb("#3d4f1e"))
    # Collar
    draw.polygon([cx - 30, cy - 110, cx + 30, cy - 110, cx + 5, cy - 65, cx - 5, cy - 65], fill=dark_olive)
    # Buttons (5 down centre)
    for i, by in enumerate(range(cy - 45, cy + 65, 27)):
        draw.ellipse([cx - 8, by - 7, cx + 8, by + 7], fill=button, outline=khaki, width=1)
    # Chest pocket (left)
    draw.rectangle([cx - 80, cy - 75, cx - 35, cy - 35], outline=khaki, width=2)
    draw.line([cx - 80, cy - 60, cx - 35, cy - 60], fill=khaki, width=2)
    # Chest pocket (right)
    draw.rectangle([cx + 35, cy - 75, cx + 80, cy - 35], outline=khaki, width=2)
    draw.line([cx + 35, cy - 60, cx + 80, cy - 60], fill=khaki, width=2)
    # US Army patch on shoulder
    draw.rectangle([cx + 40, cy - 110, cx + 90, cy - 85], fill=_rgb("#1a1a1a"), outline=khaki, width=1)
    # Sleeve stripes
    for sx in [cx - 110, cx + 90]:
        for oy in [-20, 0, 20]:
            draw.line([sx, cy + oy, sx + 20 * (1 if sx < cx else -1), cy + oy], fill=khaki, width=3)


def _draw_chemistry_set(draw: ImageDraw.ImageDraw) -> None:
    cx, cy = _CX, _CY
    glass = _rgb("#bfdbfe")
    glass_edge = _rgb("#93c5fd")
    green_fluid = _rgb("#22c55e")
    orange_fluid = _rgb("#f97316")
    amber = _rgb("#d97706")
    # Erlenmeyer flask (left)
    fx, fy = cx - 70, cy
    draw.polygon([fx - 12, fy - 80, fx + 12, fy - 80, fx + 50, fy + 60, fx - 50, fy + 60], fill=glass, outline=glass_edge, width=2)
    draw.polygon([fx - 10, fy + 20, fx + 10, fy + 20, fx + 50, fy + 60, fx - 50, fy + 60], fill=green_fluid)
    draw.rectangle([fx - 12, fy - 95, fx + 12, fy - 78], fill=glass, outline=glass_edge, width=2)
    # Cork
    draw.ellipse([fx - 13, fy - 105, fx + 13, fy - 90], fill=amber)
    # Bubbles in flask
    for bx, by in [(fx - 20, fy + 5), (fx + 5, fy - 10), (fx + 20, fy + 25)]:
        draw.ellipse([bx - 6, by - 6, bx + 6, by + 6], outline=glass_edge, width=2)
    # Beaker (right)
    bkx, bky = cx + 60, cy
    draw.rectangle([bkx - 40, bky - 70, bkx + 40, bky + 65], fill=glass, outline=glass_edge, width=2)
    draw.rectangle([bkx - 38, bky + 5, bkx + 38, bky + 63], fill=orange_fluid)
    # Measurement lines on beaker
    for ml in range(-50, 65, 20):
        lx_start = bkx - 38 if ml % 40 == 0 else bkx - 25
        draw.line([lx_start, bky + ml, bkx - 20, bky + ml], fill=glass_edge, width=1)
    # Spout on beaker
    draw.polygon([bkx + 38, bky - 70, bkx + 50, bky - 82, bkx + 52, bky - 68], fill=glass, outline=glass_edge, width=1)
    # Test tube (right side, leaning)
    ttx, tty = cx + 110, cy - 30
    draw.rectangle([ttx - 8, tty - 60, ttx + 8, tty + 40], fill=glass, outline=glass_edge, width=2)
    draw.ellipse([ttx - 8, tty + 32, ttx + 8, tty + 48], fill=glass, outline=glass_edge, width=2)
    draw.rectangle([ttx - 6, tty + 5, ttx + 6, tty + 44], fill=_rgb("#a78bfa"))


def _draw_lockpick(draw: ImageDraw.ImageDraw) -> None:
    cx, cy = _CX, _CY
    metal = _rgb("#9ca3af")
    steel = _rgb("#d1d5db")
    dark = _rgb("#374151")
    gold = _rgb("#d97706")
    # Padlock (right side)
    lx, ly = cx + 80, cy - 10
    draw.rounded_rectangle([lx - 35, ly - 25, lx + 35, ly + 45], radius=5, fill=gold, outline=_rgb("#92400e"), width=2)
    draw.arc([lx - 22, ly - 65, lx + 22, ly - 15], start=0, end=180, fill=gold, width=10)
    draw.ellipse([lx - 8, ly - 5, lx + 8, ly + 13], fill=dark)
    draw.polygon([lx - 6, ly + 13, lx + 6, ly + 13, lx + 9, ly + 28, lx - 9, ly + 28], fill=dark)
    # Pick set (5 picks stacked, left side)
    for i, oy in enumerate(range(-55, 60, 27)):
        tips = [
            [(cx - 20, cy + oy - 3), (cx + 15, cy + oy - 3), (cx + 25, cy + oy)],
            [(cx - 20, cy + oy - 3), (cx + 15, cy + oy - 3), (cx + 15, cy + oy + 3)],
            [(cx - 20, cy + oy - 3), (cx + 20, cy + oy), (cx - 20, cy + oy + 3)],
            [(cx - 20, cy + oy - 3), (cx + 10, cy + oy - 6), (cx + 10, cy + oy + 6), (cx - 20, cy + oy + 3)],
            [(cx - 20, cy + oy - 3), (cx + 25, cy + oy - 3), (cx + 25, cy + oy + 3), (cx - 20, cy + oy + 3)],
        ]
        draw.rounded_rectangle([cx - 90, cy + oy - 5, cx - 20, cy + oy + 5], radius=4, fill=dark)
        draw.rectangle([cx - 22, cy + oy - 3, cx + 10, cy + oy + 3], fill=metal)
        draw.polygon(tips[i], fill=steel)
    # Tension wrench
    draw.rectangle([cx - 90, cy + 80, cx + 5, cy + 87], fill=metal)
    draw.rectangle([cx + 5, cy + 77, cx + 12, cy + 90], fill=metal)


def _draw_fake_bag(draw: ImageDraw.ImageDraw) -> None:
    cx, cy = _CX, _CY
    tan = _rgb("#c8a96e")
    tan_dark = _rgb("#a07848")
    gold = _rgb("#c8a040")
    dark = _rgb("#3d2b10")
    lv_brown = _rgb("#8b5e2a")
    # Handles (two arcs)
    draw.arc([cx - 65, cy - 145, cx - 5, cy - 75], start=0, end=180, fill=dark, width=9)
    draw.arc([cx + 5, cy - 145, cx + 65, cy - 75], start=0, end=180, fill=dark, width=9)
    # Bag body
    draw.polygon([cx - 110, cy - 90, cx + 110, cy - 90, cx + 120, cy + 90, cx - 120, cy + 90], fill=tan)
    # LV monogram grid pattern
    for gx in range(cx - 105, cx + 110, 22):
        draw.line([gx, cy - 90, gx, cy + 90], fill=tan_dark, width=1)
    for gy in range(cy - 85, cy + 90, 22):
        draw.line([cx - 110, gy, cx + 110, gy], fill=tan_dark, width=1)
    # LV flower motifs (simplified diamond shapes at grid intersections)
    for gx in range(cx - 94, cx + 100, 44):
        for gy in range(cy - 74, cy + 80, 44):
            draw.polygon([(gx, gy - 7), (gx + 7, gy), (gx, gy + 7), (gx - 7, gy)], fill=lv_brown)
    # Top border
    draw.rectangle([cx - 112, cy - 92, cx + 112, cy - 82], fill=dark)
    # Zipper
    draw.rectangle([cx - 100, cy - 85, cx + 100, cy - 80], fill=gold)
    draw.ellipse([cx - 8, cy - 90, cx + 8, cy - 76], fill=gold, outline=dark, width=1)
    # Centre clasp
    draw.ellipse([cx - 12, cy - 5, cx + 12, cy + 15], fill=gold, outline=dark, width=2)
    # LV text
    draw.text((cx, cy + 50), "L V", fill=gold, font=_font(24), anchor="mm")
    draw.text((cx, cy + 72), "PARIS", fill=tan_dark, font=_font(12), anchor="mm")


def _draw_pills(draw: ImageDraw.ImageDraw) -> None:
    cx, cy = _CX, _CY
    bottle_body = _rgb("#e2e8f0")
    bottle_outline = _rgb("#94a3b8")
    cap_red = _rgb("#dc2626")
    cap_white = _rgb("#fef2f2")
    pill_white = _rgb("#f1f5f9")
    pill_orange = _rgb("#fb923c")
    # Main pill bottle
    draw.rounded_rectangle([cx - 45, cy - 70, cx + 45, cy + 80], radius=8, fill=bottle_body, outline=bottle_outline, width=2)
    # Child-proof cap
    draw.rounded_rectangle([cx - 52, cy - 110, cx + 52, cy - 65], radius=10, fill=cap_red)
    draw.rounded_rectangle([cx - 44, cy - 104, cx + 44, cy - 72], radius=6, fill=_rgb("#ef4444"))
    # Push arrows on cap
    draw.text((cx, cy - 87), "PUSH", fill=cap_white, font=_font(13), anchor="mm")
    draw.text((cx, cy - 73), "& TURN", fill=cap_white, font=_font(11), anchor="mm")
    # Prescription label
    draw.rounded_rectangle([cx - 38, cy - 55, cx + 38, cy + 35], radius=4, fill=_rgb("#ffffff"), outline=bottle_outline, width=1)
    draw.rectangle([cx - 38, cy - 55, cx + 38, cy - 40], fill=_rgb("#1e3a8a"))
    draw.text((cx, cy - 47), "Rx ONLY", fill=_rgb("#ffffff"), font=_font(10), anchor="mm")
    draw.text((cx, cy - 25), "TRAMADOL", fill=_rgb("#1e293b"), font=_font(12), anchor="mm")
    draw.text((cx, cy - 8), "50 mg", fill=_rgb("#334155"), font=_font(11), anchor="mm")
    draw.text((cx, cy + 10), "100 Tablets", fill=_rgb("#64748b"), font=_font(10), anchor="mm")
    draw.text((cx, cy + 25), "No refills", fill=_rgb("#dc2626"), font=_font(10), anchor="mm")
    # Pills scattered around bottle
    for px, py, col in [
        (cx - 90, cy - 30, pill_orange),
        (cx - 85, cy + 10, pill_white),
        (cx - 95, cy + 50, pill_orange),
        (cx + 70, cy - 20, pill_white),
        (cx + 80, cy + 20, pill_orange),
        (cx + 65, cy + 60, pill_white),
    ]:
        draw.ellipse([px - 14, py - 7, px + 14, py + 7], fill=col, outline=_rgb("#94a3b8"), width=1)
        draw.line([px, py - 7, px, py + 7], fill=_rgb("#94a3b8"), width=1)


def _draw_stun_gun(draw: ImageDraw.ImageDraw) -> None:
    cx, cy = _CX, _CY
    body = _rgb("#1f2937")
    grip_tex = _rgb("#111827")
    yellow = _rgb("#fbbf24")
    red_btn = _rgb("#dc2626")
    silver = _rgb("#6b7280")
    # Grip (handle)
    draw.rounded_rectangle([cx - 28, cy + 30, cx + 28, cy + 110], radius=8, fill=grip_tex)
    # Grip texture lines
    for gy in range(cy + 40, cy + 105, 12):
        draw.line([cx - 24, gy, cx + 24, gy], fill=_rgb("#374151"), width=2)
    # Main body
    draw.rounded_rectangle([cx - 35, cy - 95, cx + 35, cy + 40], radius=10, fill=body)
    # Prongs at top
    draw.rectangle([cx - 28, cy - 145, cx - 14, cy - 92], fill=silver)
    draw.ellipse([cx - 28, cy - 152, cx - 14, cy - 138], fill=yellow)
    draw.rectangle([cx + 14, cy - 145, cx + 28, cy - 92], fill=silver)
    draw.ellipse([cx + 14, cy - 152, cx + 28, cy - 138], fill=yellow)
    # Electric arc between prongs
    draw.line([cx - 21, cy - 140, cx - 5, cy - 128, cx + 5, cy - 140, cx + 21, cy - 128], fill=yellow, width=3)
    # Lightning bolt on body
    draw.polygon([
        (cx + 8, cy - 75),
        (cx - 8, cy - 30),
        (cx + 5, cy - 30),
        (cx - 8, cy + 20),
        (cx + 12, cy - 25),
        (cx - 2, cy - 25),
    ], fill=yellow)
    # Activation button
    draw.ellipse([cx - 13, cy + 5, cx + 13, cy + 31], fill=red_btn, outline=_rgb("#b91c1c"), width=2)
    draw.text((cx, cy + 18), "ON", fill=_rgb("#ffffff"), font=_font(11), anchor="mm")
    # Safety switch
    draw.rounded_rectangle([cx - 28, cy - 10, cx - 15, cy + 4], radius=3, fill=_rgb("#16a34a"))
    # Brand label strip
    draw.rectangle([cx - 32, cy - 55, cx + 32, cy - 40], fill=_rgb("#374151"))
    draw.text((cx, cy - 47), "1,000,000V", fill=yellow, font=_font(11), anchor="mm")


def _draw_fake_followers(draw: ImageDraw.ImageDraw) -> None:
    cx, cy = _CX, _CY
    purple = _rgb("#7c3aed")
    pink = _rgb("#ec4899")
    dark = _rgb("#0f0a1a")
    white = _rgb("#f8fafc")
    # Phone body
    draw.rounded_rectangle([cx - 75, cy - 115, cx + 75, cy + 100], radius=16, fill=_rgb("#1c0c2e"))
    # Screen gradient (simulate with two rectangles)
    draw.rounded_rectangle([cx - 65, cy - 105, cx + 65, cy + 90], radius=10, fill=dark)
    draw.rounded_rectangle([cx - 65, cy - 105, cx + 65, cy - 10], radius=10, fill=_rgb("#1a0838"))
    # Camera notch
    draw.ellipse([cx - 8, cy - 113, cx + 8, cy - 100], fill=_rgb("#0a0010"))
    # Follower count (hero number)
    draw.text((cx, cy - 65), "10,000", fill=white, font=_font(28), anchor="mm")
    draw.text((cx, cy - 38), "FOLLOWERS", fill=purple, font=_font(15), anchor="mm")
    draw.text((cx, cy - 18), "GUARANTEED", fill=pink, font=_font(12), anchor="mm")
    # Instagram-like gradient bar
    draw.rounded_rectangle([cx - 50, cy + 5, cx + 50, cy + 20], radius=7, fill=purple)
    draw.text((cx, cy + 12), "INSTANT DELIVERY", fill=white, font=_font(10), anchor="mm")
    # Person icons (3 silhouettes as "followers")
    for ox in [-45, 0, 45]:
        # Head
        draw.ellipse([cx + ox - 12, cy + 30, cx + ox + 12, cy + 54], fill=_rgb("#4c1d95"))
        # Body arc
        draw.arc([cx + ox - 18, cy + 50, cx + ox + 18, cy + 80], start=0, end=180, fill=_rgb("#4c1d95"), width=5)
    # Money bag icon (top right corner)
    draw.text((cx + 45, cy - 90), "$", fill=_rgb("#fbbf24"), font=_font(22), anchor="mm")
    # Home indicator
    draw.rounded_rectangle([cx - 25, cy + 94, cx + 25, cy + 100], radius=3, fill=_rgb("#374151"))


_DRAW_FNS = {
    "iphone":            _draw_iphone,
    "jeans":             _draw_jeans,
    "mixer":             _draw_mixer,
    "bike":              _draw_bike,
    "headphones":        _draw_headphones,
    "phone-unlock":      _draw_phone_unlock,
    "army-jacket":       _draw_army_jacket,
    "chemistry-set":     _draw_chemistry_set,
    "lockpick":          _draw_lockpick,
    "fake-bag":          _draw_fake_bag,
    "prescription-drugs": _draw_pills,
    "stun-gun":          _draw_stun_gun,
    "fake-followers":    _draw_fake_followers,
}

# Background colours per image key
_BG = {
    "iphone":             ("#0a0a1a", "#111128"),
    "jeans":              ("#0d1a3a", "#122044"),
    "mixer":              ("#1a0505", "#2d0808"),
    "bike":               ("#0d1117", "#1a2030"),
    "headphones":         ("#0a0a0a", "#141414"),
    "phone-unlock":       ("#0a1020", "#0f1a30"),
    "army-jacket":        ("#0c110a", "#131a0e"),
    "chemistry-set":      ("#08101a", "#0d1828"),
    "lockpick":           ("#080808", "#101010"),
    "fake-bag":           ("#1a1208", "#241a0c"),
    "prescription-drugs": ("#08101a", "#0c1828"),
    "stun-gun":           ("#040408", "#080810"),
    "fake-followers":     ("#0d0820", "#140c2c"),
}

# Header accent colours per key
_ACCENT = {
    "iphone":             "#3b82f6",
    "jeans":              "#1d4ed8",
    "mixer":              "#dc2626",
    "bike":               "#f97316",
    "headphones":         "#6366f1",
    "phone-unlock":       "#0ea5e9",
    "army-jacket":        "#65a30d",
    "chemistry-set":      "#22c55e",
    "lockpick":           "#6b7280",
    "fake-bag":           "#d97706",
    "prescription-drugs": "#dc2626",
    "stun-gun":           "#fbbf24",
    "fake-followers":     "#7c3aed",
}


def _load_real_image(key: str) -> bytes | None:
    for ext in (".jpg", ".jpeg", ".png", ".webp"):
        path = IMAGE_DIR / f"{key}{ext}"
        if path.exists():
            img = Image.open(path).convert("RGB")
            img.thumbnail((_W, _H), Image.LANCZOS)
            canvas = Image.new("RGB", (_W, _H), (245, 245, 245))
            x = (_W - img.width) // 2
            y = (_H - img.height) // 2
            canvas.paste(img, (x, y))
            buf = io.BytesIO()
            canvas.save(buf, format="JPEG", quality=90)
            return buf.getvalue()
    return None


def _wrap_text(text: str, max_chars: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current: list[str] = []
    for word in words:
        if len(" ".join(current + [word])) <= max_chars:
            current.append(word)
        else:
            if current:
                lines.append(" ".join(current))
            current = [word]
    if current:
        lines.append(" ".join(current))
    return lines


def make_image(title: str, category: str, key: str, price: float = 0.0) -> bytes:
    """Return JPEG bytes for a listing.

    Checks scripts/images/<key>.jpg first; falls back to a PIL product card.
    """
    real = _load_real_image(key)
    if real:
        return real

    bg1_hex, bg2_hex = _BG.get(key, ("#0d0d1a", "#12122a"))
    accent_hex = _ACCENT.get(key, "#6366f1")
    bg1 = _rgb(bg1_hex)
    bg2 = _rgb(bg2_hex)
    accent = _rgb(accent_hex)
    white = (248, 250, 252)
    mid = (156, 163, 175)

    img = Image.new("RGB", (_W, _H), bg1)
    draw = ImageDraw.Draw(img)

    # Subtle two-tone background split
    draw.rectangle([0, _IL_Y, _W, _IL_Y + _IL_H], fill=bg2)

    # Illustration
    fn = _DRAW_FNS.get(key)
    if fn:
        fn(draw)

    # Header bar
    draw.rectangle([0, 0, _W, _HEADER], fill=accent)
    # Category tag (left)
    tag_text = category.upper()
    draw.text((20, _HEADER // 2), tag_text, fill=white, font=_font(16), anchor="lm")
    # Price badge (right)
    price_text = f"${price:,.0f}" if price >= 1 else f"${price:.2f}"
    draw.text((_W - 20, _HEADER // 2), price_text, fill=white, font=_font(18), anchor="rm")

    # Footer
    footer_y = _H - _FOOTER
    draw.rectangle([0, footer_y, _W, _H], fill=bg1)
    draw.line([0, footer_y, _W, footer_y], fill=accent, width=2)

    # Title text (wrapped)
    lines = _wrap_text(title, 42)
    line_h = 24
    title_block_h = len(lines) * line_h
    title_start_y = footer_y + (_FOOTER - title_block_h - 20) // 2
    for i, line in enumerate(lines[:3]):
        draw.text((_W // 2, title_start_y + i * line_h), line, fill=white, font=_font(18), anchor="mm")

    # Branding
    draw.text((_W // 2, _H - 14), "CASHI SHOP", fill=mid, font=_font(11), anchor="mm")

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=88)
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
                   category: str, description: str,
                   price: float, image_key: str) -> str | None:
    image_bytes = make_image(title, category, image_key, price)
    data = {
        "user_id": seller,
        "title": title,
        "category": category,
        "description": description,
        "price": str(price),
    }
    files = {"images": (f"{image_key}.jpg", image_bytes, "image/jpeg")}

    with httpx.Client(base_url=api, timeout=30) as client:
        r = client.post("/api/submit", data=data, files=files)
        if r.status_code != 200:
            print(f"    ERROR {r.status_code}: {r.text[:120]}", file=sys.stderr)
            return None
        return r.json().get("listing_id")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
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
                    help="Seconds to wait for background moderation (default: 30)")
    args = ap.parse_args()

    print("\nWatcher Demo Seed")
    print("=" * 60)

    if IMAGE_DIR.exists():
        real_count = sum(1 for k in _DRAW_FNS if any((IMAGE_DIR / f"{k}{e}").exists() for e in (".jpg", ".jpeg", ".png", ".webp")))
        print(f"\n  Image directory: {IMAGE_DIR}")
        print(f"  Real images found: {real_count}/{len(_DRAW_FNS)}")
        if real_count < len(_DRAW_FNS):
            print(f"  Missing keys will use generated product cards.")
    else:
        print(f"\n  No scripts/images/ directory found -- using generated product cards.")
        print(f"  Drop real images (e.g. iphone.jpg) into scripts/images/ to upgrade.")

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
    for seller, title, category, description, price, expected, image_key in LISTINGS:
        listing_id = submit_listing(
            api=args.api,
            seller=seller,
            title=title,
            category=category,
            description=description,
            price=price,
            image_key=image_key,
        )
        if listing_id:
            submitted.append((listing_id, title, expected))
            src = "real img" if _load_real_image(image_key) else "generated"
            print(f"    queued  {title[:46]:<46}  [{src}]  (expected {expected})")
        else:
            errors += 1
        if args.delay > 0:
            time.sleep(args.delay)

    # 3. Wait then print stats
    if submitted and args.wait > 0:
        print(f"\n[3/3] Waiting {args.wait}s for Ollama moderation to complete...")
        time.sleep(args.wait)

        try:
            with httpx.Client(base_url=args.api, timeout=10) as client:
                r = client.get("/api/stats")
                if r.status_code == 200:
                    s = r.json()
                    print(f"\n  Stats from /api/stats:")
                    print(f"    total moderated  : {s.get('total_moderated', 0)}")
                    print(f"    auto approved    : {s.get('auto_approved', 0)}")
                    print(f"    auto rejected    : {s.get('auto_rejected', 0)}")
                    print(f"    sent to review   : {s.get('sent_to_review', 0)}")
                    print(f"    queue depth      : {s.get('queue_depth', 0)}")
        except Exception as e:
            print(f"  (could not fetch stats: {e})")

    print(f"\n{'=' * 60}")
    print(f"Done. {len(submitted)}/{len(LISTINGS)} listings submitted, {errors} error(s).")
    print(f"  Storefront  : {args.api}/")
    print(f"  Review queue: {args.api}/#/review  (log in as admin)")
    print(f"  Dashboard   : {args.api}/#/dashboard")
    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
