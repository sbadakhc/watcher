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
    {
        "username": "eve",
        "email": "eve@example.com",
        "violations": 0,
        "account_age_days": 45,
        "note": "Brand new seller, no history",
    },
]

# ---------------------------------------------------------------------------
# Listings: (seller, title, category, description, price, expected, image_key)
# ---------------------------------------------------------------------------

LISTINGS = [
    # -----------------------------------------------------------------------
    # Clean approvals (30 listings)
    # -----------------------------------------------------------------------
    ("alice", "iPhone 14 Pro 256GB Space Black", "Electronics",
     "Selling my iPhone 14 Pro in excellent condition. Screen protector applied from day one, no scratches. "
     "Battery health 97%. Comes with original box, charger, and unused EarPods. "
     "Unlocked, works with any carrier. Upgraded to iPhone 15, hence selling.",
     749.00, "APPROVE", "iphone"),

    ("alice", "Vintage Levis 501 Jeans Size 32x30", "Clothing",
     "Classic Levi's 501 straight fit jeans in dark indigo wash. Barely worn, excellent condition. "
     "Size 32 waist, 30 inseam. Original shrink-to-fit 100% cotton version. No rips, no fading.",
     45.00, "APPROVE", "jeans"),

    ("bob", "KitchenAid Stand Mixer 5 Qt Artisan", "Home",
     "KitchenAid Artisan 5-quart stand mixer in Empire Red. Used for about a year, works perfectly. "
     "Comes with all original attachments: flat beater, dough hook, wire whip, and pouring shield. "
     "Moving abroad and cannot take it with me. Original retail $450.",
     220.00, "APPROVE", "mixer"),

    ("bob", "Trek FX 3 Disc Hybrid Bike 2022", "Vehicles",
     "Trek FX 3 Disc hybrid bike, 2022 model, size Medium. Used for commuting, approximately 500 miles. "
     "Hydraulic disc brakes, Shimano Altus drivetrain, puncture-resistant tyres. Serviced 2 months ago.",
     580.00, "APPROVE", "bike"),

    ("alice", "Sony WH-1000XM5 Wireless Headphones", "Electronics",
     "Sony WH-1000XM5 noise cancelling headphones. Purchased 6 months ago, in perfect condition. "
     "Comes with original carry case, USB-C cable, and 3.5mm audio cable. 30-hour battery life.",
     249.00, "APPROVE", "headphones"),

    ("alice", "MacBook Pro 14 M3 Pro 18GB 512GB Space Black", "Electronics",
     "MacBook Pro 14-inch with M3 Pro chip, 18GB unified memory, 512GB SSD. "
     "Purchased January 2024, used lightly for development work. Battery cycles under 50. "
     "Comes with 96W USB-C charger and original box. No scratches, immaculate condition.",
     1799.00, "APPROVE", "laptop"),

    ("bob", "PlayStation 5 Disc Edition 1TB", "Electronics",
     "Sony PlayStation 5 disc edition console. Purchased at launch, excellent condition. "
     "Includes original DualSense controller, HDMI cable, and power cord. "
     "No disc drive issues, runs quietly. Upgrading to PS5 Pro.",
     380.00, "APPROVE", "console"),

    ("alice", "DJI Mini 3 Pro Fly More Combo", "Electronics",
     "DJI Mini 3 Pro drone with Fly More Combo. Under 250g, no licence required in the UK. "
     "4K/60fps video, obstacle avoidance, 34-min flight time. Under 5 hours total flight time. "
     "Comes with 3 batteries, charging hub, carrying bag, and ND filter set.",
     649.00, "APPROVE", "drone"),

    ("bob", "Herman Miller Aeron Chair Size B Graphite", "Home",
     "Herman Miller Aeron in graphite, size B (medium). PostureFit SL lumbar support. "
     "Purchased 2021, used daily in home office. All adjustments work perfectly. "
     "No tears, no broken parts. Retail $1,495. Downsizing office.",
     650.00, "APPROVE", "chair"),

    ("carlos", "Fender Player Stratocaster Electric Guitar", "Other",
     "Fender Player Series Stratocaster in Polar White with maple neck. "
     "Purchased 2022, played at home, no gigging. Frets have plenty of life. "
     "Comes with Fender gig bag and strap. Slight buckle rash on back, pictured.",
     449.00, "APPROVE", "guitar"),

    ("alice", "Canon EOS R50 Mirrorless Camera Body", "Electronics",
     "Canon EOS R50 mirrorless camera body, purchased March 2024. "
     "Approximately 1,200 shutter actuations. Compact APS-C sensor, 4K video. "
     "Comes with original box, battery, charger, and body cap. Perfect condition.",
     499.00, "APPROVE", "camera"),

    ("bob", "Garmin Fenix 7 Solar Sapphire GPS Watch", "Electronics",
     "Garmin Fenix 7 Solar Sapphire edition. Titanium bezel with sapphire crystal lens. "
     "Solar charging, 18-day battery life, full multisport tracking. "
     "Purchased June 2023, lightly used for cycling and hiking. Original box and charger included.",
     549.00, "APPROVE", "smartwatch"),

    ("alice", "Patagonia Down Sweater Jacket Size XL Navy", "Clothing",
     "Patagonia Down Sweater in Classic Navy, size XL. 800-fill-power traceable down. "
     "Worn one season, excellent condition. No damage, no pilling. "
     "Stuffs into chest pocket. Great layering piece for hiking or travel.",
     149.00, "APPROVE", "winter-jacket"),

    ("bob", "Nike Air Force 1 Low White Size UK 10", "Clothing",
     "Nike Air Force 1 Low all-white, UK size 10. Worn twice, effectively new. "
     "No creasing, no yellowing on soles. Original box included. "
     "Bought in error, too large for me. Authentic Nike, purchased from JD Sports.",
     75.00, "APPROVE", "trainers"),

    ("alice", "Dyson V15 Detect Absolute Cordless Vacuum", "Home",
     "Dyson V15 Detect Absolute. Laser dust detection, 60-min runtime, HEPA filtration. "
     "Purchased April 2023, used weekly. All attachments included. "
     "No loss of suction. Comes with wall dock and original accessories.",
     349.00, "APPROVE", "vacuum"),

    ("bob", "De'Longhi Magnifica Evo Coffee Machine", "Home",
     "De'Longhi Magnifica Evo automatic bean-to-cup espresso machine. "
     "Integrated grinder, adjustable strength and temperature. Used daily for 18 months. "
     "Recently descaled and serviced. Produces excellent espresso and lungo.",
     299.00, "APPROVE", "coffee-machine"),

    ("alice", "Apple AirPods Pro 2nd Gen MagSafe USB-C", "Electronics",
     "Apple AirPods Pro 2nd generation with MagSafe USB-C charging case. "
     "Purchased October 2023, used lightly. Battery health above 95% on all three units. "
     "Active noise cancellation and transparency mode work perfectly. Original box.",
     189.00, "APPROVE", "earbuds"),

    ("bob", "iPad Pro 12.9 M2 256GB Space Grey WiFi", "Electronics",
     "iPad Pro 12.9-inch M2 chip, 256GB, Space Grey, WiFi model. "
     "Purchased February 2023. Screen is pristine with Paperlike screen protector applied. "
     "Comes with USB-C cable and Apple 20W charger. No dents or scratches.",
     699.00, "APPROVE", "tablet"),

    ("carlos", "Weber Kettle Premium BBQ 57cm Black", "Home",
     "Weber Kettle Premium charcoal BBQ, 57cm diameter, black. "
     "Two seasons old, cleaned after each use. Porcelain-enamelled bowl and lid, no rust. "
     "Comes with grill tools and charcoal chimney starter. Selling as moving to gas.",
     159.00, "APPROVE", "bbq"),

    ("carlos", "Coleman 4-Person Instant Tent", "Other",
     "Coleman Sundome 4-person camping tent. Pre-attached poles for setup in under 2 minutes. "
     "Used on three camping trips, no rips or broken poles. Seams are watertight. "
     "Comes with carry bag and ground stakes.",
     79.00, "APPROVE", "tent"),

    ("alice", "Specialized Allez Road Bike 54cm 2021", "Vehicles",
     "Specialized Allez entry-level road bike, 54cm frame, 2021 model. "
     "Shimano Claris 2x8 groupset, double-butted aluminium frame. "
     "Approximately 800 miles. Tyres replaced last month. Great first road bike.",
     599.00, "APPROVE", "road-bike"),

    ("bob", "Bose SoundLink Revolve+ Portable Speaker", "Electronics",
     "Bose SoundLink Revolve+ II portable Bluetooth speaker in silver. "
     "360-degree sound, IPX4 water resistant, 17-hour battery life. "
     "Purchased August 2023. No scratches. Comes with charging cradle and soft carry case.",
     199.00, "APPROVE", "speaker"),

    ("alice", "Nintendo Switch OLED White 2023", "Electronics",
     "Nintendo Switch OLED model in white. Purchased as gift, barely used. "
     "7-inch OLED screen with vivid colours. Comes with dock, Joy-Cons, HDMI, and power adapter. "
     "No dead pixels, no stick drift. Original box.",
     249.00, "APPROVE", "console"),

    ("bob", "Vitamix E310 Explorian Blender", "Home",
     "Vitamix E310 Explorian blender in black. 2.0 HP motor, 48oz container. "
     "Variable speed control and pulse feature. Used for smoothies and soups for 2 years. "
     "Motor base in perfect condition. Container and blade assembly recently replaced.",
     249.00, "APPROVE", "blender"),

    ("carlos", "Keychron Q1 Pro Wireless Mechanical Keyboard", "Electronics",
     "Keychron Q1 Pro QMK/VIA wireless keyboard in carbon black with Gateron G Pro Red switches. "
     "Full aluminium body, hot-swappable PCB, RGB backlight. "
     "Used at home office for 8 months. No keycap shine, all switches working perfectly.",
     149.00, "APPROVE", "keyboard"),

    ("eve", "Samsung Galaxy S24 Ultra 256GB Titanium", "Electronics",
     "Samsung Galaxy S24 Ultra 256GB in Titanium Black. Purchased at launch. "
     "S Pen included. 200MP camera, 6.8-inch QHD+ display. "
     "Gorilla Glass Armour, no cracks. Comes with box and original charger.",
     899.00, "APPROVE", "android-phone"),

    ("eve", "Brompton C Line Explore Folding Bike", "Vehicles",
     "Brompton C Line Explore 6-speed folding bike in Turkish Green. "
     "2022 model, approximately 200 miles of city commuting. "
     "Comes with original Brompton bag and rear rack. Folds in under 20 seconds.",
     1099.00, "APPROVE", "bike"),

    ("eve", "Brooks Ghost 15 Running Shoes UK 9", "Clothing",
     "Brooks Ghost 15 neutral road running shoes, UK size 9, colour Oyster/Alloy. "
     "Approximately 80 miles on these. Plenty of cushioning life remaining. "
     "No upper tears. Selling after switching to a wider fitting shoe.",
     69.00, "APPROVE", "trainers"),

    ("carlos", "LEGO Technic Porsche 911 42096 Sealed", "Other",
     "LEGO Technic Porsche 911 RSR set (42096). Brand new, factory sealed, never opened. "
     "1,580 pieces, 1:8 scale. Discontinued set, hard to find. "
     "Perfect gift for adults. Stored in smoke-free, dry environment.",
     189.00, "APPROVE", "lego"),

    ("eve", "Kindle Paperwhite 16GB Signature Edition", "Electronics",
     "Kindle Paperwhite Signature Edition, 16GB, without ads. "
     "300 ppi glare-free display, wireless charging, auto-adjusting front light. "
     "Used for 6 months, pristine condition. Comes with USB-C cable and original box.",
     139.00, "APPROVE", "ereader"),

    # -----------------------------------------------------------------------
    # Borderline / REVIEW (10 listings)
    # -----------------------------------------------------------------------
    ("carlos", "Phone Unlocking Service All Networks", "Services",
     "Professional phone unlocking service for all major carriers. Remote unlock within 24 hours. "
     "Works for iPhone and Android. Permanent unlock, no software required. "
     "Over 500 satisfied customers. Contact me with your IMEI number.",
     35.00, "REVIEW", "phone-unlock"),

    ("carlos", "Vintage Military Surplus Jacket US Army M65", "Clothing",
     "Authentic US Army M65 field jacket from 1970s military surplus. "
     "Olive drab, size Large Regular. Some wear consistent with age, all buttons intact. "
     "Collector item, not reproduction. Great for outdoor activities.",
     85.00, "REVIEW", "army-jacket"),

    ("carlos", "Chemistry Set Advanced Home Lab Kit", "Other",
     "Advanced chemistry set for serious hobbyists and home experimenters. "
     "Includes 40+ reagents, glassware, and instruction manual. "
     "Everything you need for titration, crystallisation, and organic synthesis experiments. "
     "Suitable for adults only.",
     120.00, "REVIEW", "chemistry-set"),

    ("bob", "Lockpick Set Professional Grade", "Other",
     "Professional lockpick set with 24 picks and 4 tension wrenches. "
     "Stainless steel, lifetime warranty. Used by locksmiths and security professionals. "
     "Legal in most jurisdictions. Includes carrying case.",
     55.00, "REVIEW", "lockpick"),

    ("carlos", "Airsoft Rifle Full Auto Electric Blowback", "Other",
     "Airsoft AEG rifle with full-auto and semi-auto fire modes. "
     "Electric blowback, 400 FPS with 0.2g BBs. Metal gearbox, polymer body. "
     "Suitable for skirmish use. Site limits apply. Over 18 only. UK legal.",
     120.00, "REVIEW", "airsoft"),

    ("eve", "Pre-Workout Supplement High Stim DMAA Formula", "Other",
     "Importing discontinued high-stimulant pre-workout from US supplier. "
     "Contains DMAA (1,3-dimethylamylamine) and high-dose caffeine. "
     "Not for sale to under 18s. Not evaluated by MHRA. Use at your own risk.",
     45.00, "REVIEW", "supplements"),

    ("bob", "VPN Service Lifetime Subscription All Devices", "Services",
     "Lifetime VPN subscription for unlimited devices. Based offshore, no-logs policy. "
     "Bypasses geo-restrictions on all major streaming platforms. "
     "Includes dedicated IP, P2P optimised servers, and 24/7 support.",
     29.00, "REVIEW", "vpn-service"),

    ("diana", "Replica Rolex Submariner Watch AAA Grade", "Clothing",
     "High-quality Rolex Submariner replica, AAA grade. Sapphire crystal glass. "
     "Automatic movement, keeps accurate time. Looks identical to the genuine article. "
     "Clearly stated as replica. Not a Rolex-authorised product.",
     95.00, "REVIEW", "replica-watch"),

    ("carlos", "Kratom Powder Red Vein Borneo 250g", "Other",
     "Red Vein Borneo kratom powder, 250g resealable pouch. "
     "Sourced from sustainable Indonesian farms. Finely milled, lab tested for purity. "
     "Legal in the UK. Not for human consumption. Sold as botanical specimen only.",
     35.00, "REVIEW", "kratom"),

    ("eve", "Crossbow 80lb Pistol Hunting Legal UK", "Other",
     "80lb pistol crossbow. Legal to own in the UK for adults. "
     "Includes 3 aluminium bolts and a quiver. Suitable for target shooting and small game. "
     "Not a firearm, no licence required. Buyer must be 18+.",
     49.00, "REVIEW", "crossbow"),

    # -----------------------------------------------------------------------
    # Clear violations / REJECT (10 listings)
    # -----------------------------------------------------------------------
    ("diana", "Louis Vuitton Neverfull MM Brand New", "Clothing",
     "Brand new Louis Vuitton Neverfull MM tote bag. Monogram canvas with beige interior. "
     "Gold hardware. Comes with dust bag. Beautiful bag, perfect condition. "
     "Originally purchased from a supplier in Guangzhou. Great quality.",
     180.00, "REJECT", "fake-bag"),

    ("diana", "Tramadol 50mg 100 Tablets No Prescription", "Other",
     "Selling unopened pack of Tramadol 50mg tablets, 100 count. "
     "Prescription not required for purchase. Fast discreet shipping. "
     "Contact me for bulk pricing. Multiple packs available.",
     60.00, "REJECT", "prescription-drugs"),

    ("diana", "Stun Gun 1 Million Volt Self Defence", "Other",
     "High voltage stun gun for personal protection. 1 million volt output. "
     "Rechargeable battery, LED flashlight included. Compact design fits in pocket. "
     "Shipping available to all locations. No questions asked.",
     45.00, "REJECT", "stun-gun"),

    ("diana", "Get 10000 Instagram Followers Guaranteed", "Services",
     "Boost your Instagram instantly! 10,000 real-looking followers delivered within 48 hours. "
     "100% guaranteed or money back. Our bot network ensures rapid growth. "
     "Safe, permanent, and undetectable. DM for bulk packages.",
     25.00, "REJECT", "fake-followers"),

    ("diana", "Oxycodone 30mg 50 Tablets No Script Needed", "Other",
     "Pharmaceutical grade Oxycodone 30mg tablets, 50 count. "
     "No prescription required. Sourced from licensed overseas pharmacy. "
     "Discreet packaging, tracked shipping. Contact for volume discounts.",
     120.00, "REJECT", "prescription-drugs"),

    ("diana", "Fake Nike Air Jordan 1 High OG Chicago", "Clothing",
     "Perfect replica Nike Air Jordan 1 High OG Chicago colourway. "
     "1:1 quality, indistinguishable from retail. Correct box, tissue paper, and tag. "
     "Sourced from same factory as originals. All sizes available.",
     85.00, "REJECT", "counterfeit-shoes"),

    ("diana", "MacBook Pro 16 M2 IMEI Blocked Lost Report", "Electronics",
     "MacBook Pro 16-inch M2, selling for parts or repair. "
     "Activation locked and IMEI flagged as lost. Priced accordingly. "
     "No questions asked, cash on collection preferred.",
     300.00, "REJECT", "stolen-device"),

    ("diana", "Netflix Premium 4K Account 12 Months Access", "Services",
     "Selling access to a shared Netflix Premium 4K account. "
     "Your own profile, no interruptions. Account is not in your name. "
     "Payment via crypto only. Message me for details.",
     18.00, "REJECT", "stolen-account"),

    ("diana", "50000 YouTube Subscribers Real Looking Bots", "Services",
     "Grow your YouTube channel fast. 50,000 subscribers delivered within 72 hours. "
     "Bot traffic that passes YouTube's detection systems. "
     "100% refund if dropped within 30 days. Bulk orders available.",
     49.00, "REJECT", "fake-subscribers"),

    ("diana", "Fake Gucci Marmont Belt 90cm AAA Rep", "Clothing",
     "Gucci Marmont double G belt, 90cm, in black leather with gold hardware. "
     "High-quality replica, purchased from verified supplier. "
     "Looks identical to the retail product. Not an authorised Gucci item.",
     55.00, "REJECT", "counterfeit-belt"),
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


def _draw_laptop(draw: ImageDraw.ImageDraw) -> None:
    cx, cy = _CX, _CY + 10
    silver = _rgb("#6b7280")
    dark = _rgb("#1f2937")
    screen_bg = _rgb("#0f172a")
    accent = _rgb("#3b82f6")
    # Base (keyboard section)
    draw.rounded_rectangle([cx - 140, cy + 20, cx + 140, cy + 80], radius=8, fill=silver)
    # Keyboard rows
    for row in range(3):
        ky = cy + 35 + row * 13
        for col in range(12):
            kx = cx - 120 + col * 21
            draw.rounded_rectangle([kx, ky, kx + 17, ky + 9], radius=2, fill=dark)
    # Touchpad
    draw.rounded_rectangle([cx - 35, cy + 55, cx + 35, cy + 75], radius=4, fill=_rgb("#4b5563"))
    # Lid (screen)
    draw.rounded_rectangle([cx - 140, cy - 100, cx + 140, cy + 22], radius=10, fill=silver)
    draw.rounded_rectangle([cx - 132, cy - 93, cx + 132, cy + 16], radius=6, fill=screen_bg)
    # Screen content
    draw.rectangle([cx - 100, cy - 70, cx + 100, cy - 55], fill=_rgb("#1e3a8a"))
    for i in range(3):
        draw.rounded_rectangle([cx - 100, cy - 48 + i * 18, cx - 10, cy - 38 + i * 18], radius=3, fill=_rgb("#374151"))
        draw.rounded_rectangle([cx, cy - 48 + i * 18, cx + 60, cy - 38 + i * 18], radius=3, fill=accent)
    # Webcam
    draw.ellipse([cx - 4, cy - 96, cx + 4, cy - 88], fill=dark)
    # Hinge
    draw.rectangle([cx - 140, cy + 18, cx + 140, cy + 24], fill=_rgb("#374151"))


def _draw_console(draw: ImageDraw.ImageDraw) -> None:
    cx, cy = _CX, _CY
    white = _rgb("#f8fafc")
    dark = _rgb("#0f172a")
    blue = _rgb("#3b82f6")
    # Main console body (tall vertical unit)
    draw.rounded_rectangle([cx - 55, cy - 110, cx + 55, cy + 95], radius=12, fill=white)
    # Side accent panel
    draw.rounded_rectangle([cx - 55, cy - 110, cx - 25, cy + 95], radius=12, fill=_rgb("#e2e8f0"))
    # Disc slot
    draw.rounded_rectangle([cx - 48, cy - 30, cx + 50, cy - 20], radius=3, fill=_rgb("#cbd5e1"))
    # USB ports
    draw.rounded_rectangle([cx - 20, cy + 20, cx + 20, cy + 32], radius=3, fill=_rgb("#94a3b8"))
    draw.rounded_rectangle([cx - 20, cy + 38, cx + 20, cy + 50], radius=3, fill=_rgb("#94a3b8"))
    # Power button
    draw.ellipse([cx + 30, cy + 60, cx + 50, cy + 80], fill=blue)
    draw.text((cx + 40, cy + 70), "PS", fill=white, font=_font(10), anchor="mm")
    # Logo area
    draw.text((cx - 5, cy - 70), "PS5", fill=dark, font=_font(20), anchor="mm")
    # Curved wing effect
    draw.arc([cx - 90, cy - 130, cx + 0, cy + 10], start=270, end=90, fill=_rgb("#e2e8f0"), width=20)
    draw.arc([cx + 0, cy - 130, cx + 90, cy + 10], start=90, end=270, fill=_rgb("#e2e8f0"), width=20)


def _draw_drone(draw: ImageDraw.ImageDraw) -> None:
    cx, cy = _CX, _CY
    body = _rgb("#1f2937")
    arm = _rgb("#374151")
    prop = _rgb("#6b7280")
    accent = _rgb("#3b82f6")
    # Four arms at 45 degree angles
    for dx, dy in [(-80, -60), (80, -60), (-80, 60), (80, 60)]:
        draw.line([cx, cy, cx + dx, cy + dy], fill=arm, width=8)
        # Motor
        draw.ellipse([cx + dx - 18, cy + dy - 18, cx + dx + 18, cy + dy + 18], fill=body, outline=accent, width=2)
        # Prop blades
        draw.ellipse([cx + dx - 35, cy + dy - 6, cx + dx + 35, cy + dy + 6], fill=prop)
        draw.ellipse([cx + dx - 6, cy + dy - 35, cx + dx + 6, cy + dy + 35], fill=prop)
    # Central body
    draw.rounded_rectangle([cx - 35, cy - 25, cx + 35, cy + 25], radius=8, fill=body)
    # Camera gimbal
    draw.ellipse([cx - 16, cy + 20, cx + 16, cy + 46], fill=_rgb("#0f172a"), outline=accent, width=2)
    draw.ellipse([cx - 10, cy + 25, cx + 10, cy + 41], fill=_rgb("#1e3a8a"))
    # LED indicator
    draw.ellipse([cx - 5, cy - 10, cx + 5, cy], fill=_rgb("#22c55e"))
    # Status lights
    for i, col in enumerate([_rgb("#ef4444"), _rgb("#22c55e"), _rgb("#3b82f6")]):
        draw.ellipse([cx - 12 + i * 12, cy + 5, cx - 5 + i * 12, cy + 12], fill=col)


def _draw_chair(draw: ImageDraw.ImageDraw) -> None:
    cx, cy = _CX, _CY
    black = _rgb("#111827")
    dark = _rgb("#1f2937")
    grey = _rgb("#4b5563")
    mesh = _rgb("#374151")
    # Five-star base (5 legs radiating)
    for angle in range(0, 360, 72):
        ex = cx + int(90 * math.cos(math.radians(angle)))
        ey = cy + 95 + int(30 * math.sin(math.radians(angle)))
        draw.line([cx, cy + 90, ex, ey], fill=black, width=8)
        draw.ellipse([ex - 8, ey - 5, ex + 8, ey + 5], fill=grey)
    # Gas cylinder / stem
    draw.rectangle([cx - 10, cy + 30, cx + 10, cy + 92], fill=grey)
    draw.rectangle([cx - 7, cy + 25, cx + 7, cy + 35], fill=dark)
    # Seat
    draw.ellipse([cx - 70, cy + 5, cx + 70, cy + 35], fill=black)
    # Seat cushion highlight
    draw.ellipse([cx - 60, cy + 8, cx + 60, cy + 28], fill=dark)
    # Armrests
    draw.rounded_rectangle([cx - 85, cy - 20, cx - 60, cy + 20], radius=6, fill=dark)
    draw.rounded_rectangle([cx + 60, cy - 20, cx + 85, cy + 20], radius=6, fill=dark)
    draw.line([cx - 72, cy + 5, cx - 72, cy + 20], fill=grey, width=5)
    draw.line([cx + 72, cy + 5, cx + 72, cy + 20], fill=grey, width=5)
    # Backrest (mesh effect)
    draw.rounded_rectangle([cx - 65, cy - 110, cx + 65, cy + 5], radius=10, fill=mesh)
    for mrow in range(7):
        for mcol in range(5):
            mx = cx - 52 + mcol * 26
            my = cy - 98 + mrow * 17
            draw.rounded_rectangle([mx, my, mx + 20, my + 12], radius=3, fill=dark)
    # Headrest
    draw.rounded_rectangle([cx - 40, cy - 130, cx + 40, cy - 105], radius=8, fill=black)


def _draw_guitar(draw: ImageDraw.ImageDraw) -> None:
    cx, cy = _CX, _CY
    wood = _rgb("#92400e")
    light_wood = _rgb("#b45309")
    dark = _rgb("#1c0a00")
    chrome = _rgb("#9ca3af")
    string = _rgb("#d1d5db")
    # Body lower bout
    draw.ellipse([cx - 85, cy + 10, cx + 85, cy + 120], fill=wood)
    # Body upper bout
    draw.ellipse([cx - 65, cy - 60, cx + 65, cy + 40], fill=wood)
    # Waist cutaway
    draw.ellipse([cx - 40, cy - 20, cx + 40, cy + 40], fill=light_wood)
    # Sound hole
    draw.ellipse([cx - 28, cy + 25, cx + 28, cy + 81], fill=dark)
    draw.ellipse([cx - 22, cy + 31, cx + 22, cy + 75], fill=wood)
    # Neck
    draw.rectangle([cx - 14, cy - 140, cx + 14, cy - 55], fill=light_wood)
    # Fretboard
    draw.rectangle([cx - 10, cy - 138, cx + 10, cy - 55], fill=dark)
    # Frets
    for f in range(6):
        fy = cy - 125 + f * 14
        draw.line([cx - 10, fy, cx + 10, fy], fill=chrome, width=2)
    # Headstock
    draw.rounded_rectangle([cx - 20, cy - 155, cx + 20, cy - 135], radius=5, fill=light_wood)
    # Tuning pegs (3 each side)
    for side, px in [(-1, cx - 25), (1, cx + 25)]:
        for i in range(3):
            py = cy - 152 + i * 10
            draw.ellipse([px - 5, py - 4, px + 5, py + 4], fill=chrome)
    # Strings
    for i, sx in enumerate(range(cx - 8, cx + 10, 4)):
        draw.line([sx, cy - 135, sx, cy + 110], fill=string, width=1)
    # Bridge
    draw.rectangle([cx - 25, cy + 85, cx + 25, cy + 95], fill=dark)
    # Strap button
    draw.ellipse([cx - 5, cy + 116, cx + 5, cy + 124], fill=chrome)


def _draw_camera(draw: ImageDraw.ImageDraw) -> None:
    cx, cy = _CX, _CY
    black = _rgb("#111827")
    dark = _rgb("#1f2937")
    silver = _rgb("#6b7280")
    red = _rgb("#dc2626")
    glass = _rgb("#1e3a8a")
    # Camera body
    draw.rounded_rectangle([cx - 90, cy - 55, cx + 90, cy + 65], radius=10, fill=black)
    # Viewfinder hump
    draw.rounded_rectangle([cx - 30, cy - 80, cx + 30, cy - 50], radius=6, fill=dark)
    # Lens barrel
    draw.ellipse([cx - 55, cy - 50, cx + 55, cy + 50], fill=_rgb("#0f172a"), outline=silver, width=3)
    draw.ellipse([cx - 45, cy - 40, cx + 45, cy + 40], fill=dark, outline=silver, width=2)
    draw.ellipse([cx - 32, cy - 27, cx + 32, cy + 27], fill=glass)
    draw.ellipse([cx - 20, cy - 15, cx + 20, cy + 15], fill=_rgb("#0c1f5e"))
    draw.ellipse([cx - 8, cy - 3, cx + 8, cy + 3], fill=_rgb("#93c5fd"))
    # Shutter button
    draw.ellipse([cx + 55, cy - 62, cx + 75, cy - 46], fill=red)
    # Mode dial
    draw.ellipse([cx + 50, cy - 45, cx + 80, cy - 20], fill=silver)
    draw.text((cx + 65, cy - 32), "P", fill=black, font=_font(12), anchor="mm")
    # Hot shoe
    draw.rectangle([cx - 20, cy - 82, cx + 20, cy - 75], fill=silver)
    # Logo strip
    draw.text((cx - 60, cy + 50), "EOS", fill=red, font=_font(14), anchor="mm")
    # Grip
    draw.rounded_rectangle([cx + 65, cy - 55, cx + 92, cy + 65], radius=8, fill=_rgb("#1c1c1c"))


def _draw_smartwatch(draw: ImageDraw.ImageDraw) -> None:
    cx, cy = _CX, _CY
    case = _rgb("#374151")
    screen = _rgb("#0f172a")
    strap = _rgb("#1f2937")
    accent = _rgb("#22c55e")
    silver = _rgb("#9ca3af")
    # Strap top
    draw.rounded_rectangle([cx - 22, cy - 130, cx + 22, cy - 65], radius=8, fill=strap)
    # Strap bottom
    draw.rounded_rectangle([cx - 22, cy + 60, cx + 22, cy + 130], radius=8, fill=strap)
    # Strap holes
    for hy in range(cy + 75, cy + 120, 12):
        draw.ellipse([cx + 10, hy - 3, cx + 18, hy + 3], fill=_rgb("#374151"))
    # Watch case
    draw.rounded_rectangle([cx - 50, cy - 68, cx + 50, cy + 62], radius=14, fill=case)
    # Screen
    draw.rounded_rectangle([cx - 43, cy - 61, cx + 43, cy + 55], radius=10, fill=screen)
    # Watch face content
    draw.text((cx, cy - 28), "12:45", fill=_rgb("#f8fafc"), font=_font(22), anchor="mm")
    draw.text((cx, cy - 5), "THU 18 JUN", fill=silver, font=_font(10), anchor="mm")
    # Activity ring
    draw.arc([cx - 28, cy + 10, cx + 28, cy + 50], start=270, end=200, fill=accent, width=6)
    draw.arc([cx - 28, cy + 10, cx + 28, cy + 50], start=270, end=160, fill=_rgb("#ef4444"), width=6)
    # Crown
    draw.rounded_rectangle([cx + 48, cy - 15, cx + 56, cy + 15], radius=4, fill=silver)


def _draw_trainers(draw: ImageDraw.ImageDraw) -> None:
    cx, cy = _CX, _CY + 20
    white = _rgb("#f8fafc")
    off_white = _rgb("#e2e8f0")
    sole = _rgb("#9ca3af")
    lace = _rgb("#374151")
    # Sole
    draw.rounded_rectangle([cx - 110, cy + 20, cx + 110, cy + 55], radius=12, fill=sole)
    draw.rounded_rectangle([cx - 105, cy + 15, cx + 105, cy + 30], radius=8, fill=_rgb("#cbd5e1"))
    # Upper body
    draw.polygon([cx - 100, cy + 20, cx + 100, cy + 20, cx + 80, cy - 50, cx - 20, cy - 60], fill=white)
    # Toe box
    draw.ellipse([cx + 60, cy - 30, cx + 115, cy + 22], fill=white)
    # Collar
    draw.arc([cx - 100, cy - 60, cx + 20, cy + 20], start=270, end=180, fill=off_white, width=14)
    # Tongue
    draw.polygon([cx - 40, cy + 20, cx - 10, cy + 20, cx - 5, cy - 55, cx - 35, cy - 55], fill=off_white)
    # Laces (5 pairs)
    for i in range(5):
        ly = cy - 40 + i * 13
        lx_start = cx - 35 + i * 4
        lx_end = cx - 12 + i * 4
        draw.line([lx_start, ly, lx_end, ly - 3], fill=lace, width=2)
    # Swoosh-like stripe
    draw.arc([cx - 30, cy - 20, cx + 90, cy + 40], start=190, end=300, fill=_rgb("#374151"), width=5)
    # Heel tab
    draw.rectangle([cx - 105, cy - 25, cx - 92, cy + 20], fill=off_white)
    draw.text((cx - 98, cy - 5), "N", fill=lace, font=_font(14), anchor="mm")


def _draw_vacuum(draw: ImageDraw.ImageDraw) -> None:
    cx, cy = _CX, _CY
    purple = _rgb("#7c3aed")
    silver = _rgb("#9ca3af")
    dark = _rgb("#1f2937")
    cyclone = _rgb("#a78bfa")
    # Wand / stick (angled slightly)
    draw.polygon([cx - 8, cy - 120, cx + 8, cy - 120, cx + 15, cy + 40, cx - 15, cy + 40], fill=silver)
    # Floor head
    draw.rounded_rectangle([cx - 70, cy + 35, cx + 70, cy + 60], radius=8, fill=dark)
    draw.rounded_rectangle([cx - 65, cy + 40, cx + 65, cy + 55], radius=5, fill=purple)
    # Main body / cyclone unit (attaches to wand top)
    draw.rounded_rectangle([cx - 38, cy - 120, cx + 38, cy - 30], radius=12, fill=purple)
    # Cyclone chambers
    draw.ellipse([cx - 28, cy - 110, cx - 2, cy - 80], fill=cyclone)
    draw.ellipse([cx + 2, cy - 110, cx + 28, cy - 80], fill=cyclone)
    draw.ellipse([cx - 28, cy - 75, cx - 2, cy - 45], fill=cyclone)
    draw.ellipse([cx + 2, cy - 75, cx + 28, cy - 45], fill=cyclone)
    # Handle / trigger area
    draw.rounded_rectangle([cx - 20, cy - 145, cx + 20, cy - 115], radius=8, fill=dark)
    draw.rounded_rectangle([cx - 12, cy - 135, cx + 12, cy - 118], radius=5, fill=purple)
    # Battery indicator
    for i in range(4):
        fill = _rgb("#22c55e") if i < 3 else _rgb("#374151")
        draw.rounded_rectangle([cx - 15 + i * 9, cy - 42, cx - 8 + i * 9, cy - 33], radius=2, fill=fill)


def _draw_coffee_machine(draw: ImageDraw.ImageDraw) -> None:
    cx, cy = _CX, _CY
    silver = _rgb("#9ca3af")
    dark = _rgb("#111827")
    red_btn = _rgb("#dc2626")
    cream = _rgb("#fef3c7")
    chrome = _rgb("#d1d5db")
    # Main body
    draw.rounded_rectangle([cx - 75, cy - 90, cx + 75, cy + 90], radius=12, fill=silver)
    draw.rounded_rectangle([cx - 68, cy - 82, cx + 68, cy + 82], radius=8, fill=dark)
    # Drip tray
    draw.rounded_rectangle([cx - 60, cy + 55, cx + 60, cy + 90], radius=5, fill=chrome)
    draw.rounded_rectangle([cx - 55, cy + 58, cx + 55, cy + 85], radius=3, fill=_rgb("#6b7280"))
    # Cup platform
    draw.rectangle([cx - 50, cy + 50, cx + 50, cy + 60], fill=chrome)
    # Coffee cup
    draw.rounded_rectangle([cx - 18, cy + 15, cx + 18, cy + 52], radius=4, fill=cream)
    draw.ellipse([cx - 16, cy + 13, cx + 16, cy + 23], fill=cream)
    draw.arc([cx + 16, cy + 22, cx + 30, cy + 40], start=270, end=90, fill=chrome, width=4)
    # Steam nozzle
    draw.rectangle([cx + 45, cy - 30, cx + 55, cy + 30], fill=chrome)
    draw.ellipse([cx + 43, cy - 36, cx + 57, cy - 24], fill=chrome)
    # Bean hopper (top)
    draw.rounded_rectangle([cx - 35, cy - 110, cx + 35, cy - 82], radius=8, fill=_rgb("#374151"))
    draw.ellipse([cx - 30, cy - 115, cx + 30, cy - 100], fill=dark)
    draw.ellipse([cx - 24, cy - 113, cx + 24, cy - 103], fill=_rgb("#1c0a00"))
    # Control buttons
    for i, col in enumerate([red_btn, _rgb("#f59e0b"), _rgb("#22c55e")]):
        draw.ellipse([cx - 30 + i * 30, cy - 50, cx - 14 + i * 30, cy - 34], fill=col)
    # Display strip
    draw.rounded_rectangle([cx - 50, cy - 75, cx + 50, cy - 55], radius=4, fill=_rgb("#0f172a"))
    draw.text((cx, cy - 65), "READY", fill=_rgb("#22c55e"), font=_font(11), anchor="mm")


def _draw_earbuds(draw: ImageDraw.ImageDraw) -> None:
    cx, cy = _CX, _CY
    white = _rgb("#f8fafc")
    off_white = _rgb("#e2e8f0")
    dark = _rgb("#1f2937")
    silver = _rgb("#9ca3af")
    # Case body
    draw.rounded_rectangle([cx - 65, cy - 40, cx + 65, cy + 80], radius=20, fill=white)
    draw.rounded_rectangle([cx - 60, cy - 35, cx + 60, cy + 75], radius=16, fill=off_white)
    # Case lid line (open)
    draw.arc([cx - 65, cy - 80, cx + 65, cy + 10], start=200, end=340, fill=white, width=16)
    draw.arc([cx - 58, cy - 72, cx + 58, cy + 5], start=205, end=335, fill=off_white, width=10)
    # Left earbud in case
    lx, ly = cx - 28, cy + 15
    draw.ellipse([lx - 18, ly - 24, lx + 18, ly + 24], fill=white, outline=silver, width=1)
    draw.ellipse([lx - 12, ly - 18, lx + 12, ly + 18], fill=off_white)
    draw.rounded_rectangle([lx - 6, ly + 20, lx + 6, ly + 55], radius=5, fill=white)
    # Right earbud in case
    rx, ry = cx + 28, cy + 15
    draw.ellipse([rx - 18, ry - 24, rx + 18, ry + 24], fill=white, outline=silver, width=1)
    draw.ellipse([rx - 12, ry - 18, rx + 12, ry + 18], fill=off_white)
    draw.rounded_rectangle([rx - 6, ry + 20, rx + 6, ry + 55], radius=5, fill=white)
    # Charging LED
    draw.ellipse([cx - 5, cy + 68, cx + 5, cy + 76], fill=_rgb("#22c55e"))
    # Lightning connector at base
    draw.rounded_rectangle([cx - 8, cy + 78, cx + 8, cy + 88], radius=3, fill=silver)


def _draw_tent(draw: ImageDraw.ImageDraw) -> None:
    cx, cy = _CX, _CY + 20
    green = _rgb("#166534")
    light_green = _rgb("#22c55e")
    grey = _rgb("#9ca3af")
    dark = _rgb("#14532d")
    # Ground / shadow
    draw.ellipse([cx - 130, cy + 45, cx + 130, cy + 65], fill=_rgb("#374151"))
    # Main tent body (large triangle)
    draw.polygon([cx, cy - 110, cx - 130, cy + 50, cx + 130, cy + 50], fill=green)
    # Front face panel (lighter)
    draw.polygon([cx, cy - 110, cx - 30, cy + 50, cx + 30, cy + 50], fill=light_green)
    # Door zip
    draw.arc([cx - 25, cy - 40, cx + 25, cy + 50], start=270, end=90, fill=dark, width=3)
    draw.ellipse([cx - 5, cy + 25, cx + 5, cy + 35], fill=grey)
    # Tent poles (visible at sides)
    draw.line([cx - 130, cy + 50, cx, cy - 110], fill=grey, width=3)
    draw.line([cx + 130, cy + 50, cx, cy - 110], fill=grey, width=3)
    # Guy ropes
    draw.line([cx - 100, cy + 10, cx - 150, cy + 50], fill=_rgb("#f59e0b"), width=2)
    draw.line([cx + 100, cy + 10, cx + 150, cy + 50], fill=_rgb("#f59e0b"), width=2)
    # Pegs
    draw.line([cx - 150, cy + 48, cx - 145, cy + 58], fill=grey, width=3)
    draw.line([cx + 150, cy + 48, cx + 145, cy + 58], fill=grey, width=3)
    # Ventilation window
    draw.polygon([cx, cy - 108, cx - 20, cy - 70, cx + 20, cy - 70], fill=_rgb("#bbf7d0"))


_DRAW_FNS = {
    # Original 13
    "iphone":             _draw_iphone,
    "jeans":              _draw_jeans,
    "mixer":              _draw_mixer,
    "bike":               _draw_bike,
    "headphones":         _draw_headphones,
    "phone-unlock":       _draw_phone_unlock,
    "army-jacket":        _draw_army_jacket,
    "chemistry-set":      _draw_chemistry_set,
    "lockpick":           _draw_lockpick,
    "fake-bag":           _draw_fake_bag,
    "prescription-drugs": _draw_pills,
    "stun-gun":           _draw_stun_gun,
    "fake-followers":     _draw_fake_followers,
    # New product types
    "laptop":             _draw_laptop,
    "console":            _draw_console,
    "drone":              _draw_drone,
    "chair":              _draw_chair,
    "guitar":             _draw_guitar,
    "camera":             _draw_camera,
    "smartwatch":         _draw_smartwatch,
    "trainers":           _draw_trainers,
    "vacuum":             _draw_vacuum,
    "coffee-machine":     _draw_coffee_machine,
    "earbuds":            _draw_earbuds,
    "tent":               _draw_tent,
    # Reused functions for visually similar products
    "road-bike":          _draw_bike,
    "blender":            _draw_mixer,
    "android-phone":      _draw_iphone,
    "speaker":            _draw_headphones,
    "tablet":             _draw_iphone,
    "ereader":            _draw_iphone,
    "bbq":                _draw_mixer,
    "lego":               _draw_chemistry_set,
    "keyboard":           _draw_laptop,
    "winter-jacket":      _draw_army_jacket,
    "running-shoes":      _draw_trainers,
    "airsoft":            _draw_stun_gun,
    "supplements":        _draw_pills,
    "vpn-service":        _draw_phone_unlock,
    "replica-watch":      _draw_smartwatch,
    "kratom":             _draw_pills,
    "crossbow":           _draw_army_jacket,
    "counterfeit-shoes":  _draw_trainers,
    "stolen-device":      _draw_laptop,
    "stolen-account":     _draw_fake_followers,
    "fake-subscribers":   _draw_fake_followers,
    "counterfeit-belt":   _draw_fake_bag,
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
    "laptop":             ("#0a0f1a", "#101828"),
    "console":            ("#080818", "#0e1222"),
    "drone":              ("#060a10", "#0c1018"),
    "chair":              ("#080a0c", "#0f1214"),
    "guitar":             ("#1a0800", "#2a1000"),
    "camera":             ("#060808", "#0c1010"),
    "smartwatch":         ("#080c08", "#101410"),
    "trainers":           ("#0a0c10", "#12141a"),
    "vacuum":             ("#10081a", "#180c28"),
    "coffee-machine":     ("#100808", "#1a1010"),
    "earbuds":            ("#0a0c10", "#12141a"),
    "tent":               ("#04100a", "#081a10"),
    "road-bike":          ("#0e1218", "#141c24"),
    "blender":            ("#160606", "#220a0a"),
    "android-phone":      ("#060a10", "#0c1018"),
    "speaker":            ("#080a0e", "#10121a"),
    "tablet":             ("#080a14", "#0e1020"),
    "ereader":            ("#060606", "#101010"),
    "bbq":                ("#0c0606", "#160a0a"),
    "lego":               ("#0a0808", "#140c0c"),
    "keyboard":           ("#06080c", "#0c1018"),
    "winter-jacket":      ("#080e14", "#101828"),
    "running-shoes":      ("#060a08", "#0c1410"),
    "airsoft":            ("#060606", "#0c0c0c"),
    "supplements":        ("#0a0810", "#14101a"),
    "vpn-service":        ("#060e10", "#0c1418"),
    "replica-watch":      ("#080a08", "#10120e"),
    "kratom":             ("#080c08", "#101410"),
    "crossbow":           ("#080a06", "#10120a"),
    "counterfeit-shoes":  ("#080a0c", "#10121a"),
    "stolen-device":      ("#080808", "#101010"),
    "stolen-account":     ("#0a0820", "#10102c"),
    "fake-subscribers":   ("#0c0820", "#14102c"),
    "counterfeit-belt":   ("#14100a", "#1e180e"),
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
    "laptop":             "#64748b",
    "console":            "#3b82f6",
    "drone":              "#0ea5e9",
    "chair":              "#374151",
    "guitar":             "#b45309",
    "camera":             "#dc2626",
    "smartwatch":         "#22c55e",
    "trainers":           "#6b7280",
    "vacuum":             "#7c3aed",
    "coffee-machine":     "#92400e",
    "earbuds":            "#94a3b8",
    "tent":               "#16a34a",
    "road-bike":          "#ea580c",
    "blender":            "#b91c1c",
    "android-phone":      "#0284c7",
    "speaker":            "#4f46e5",
    "tablet":             "#0891b2",
    "ereader":            "#374151",
    "bbq":                "#9a3412",
    "lego":               "#b91c1c",
    "keyboard":           "#4338ca",
    "winter-jacket":      "#1d4ed8",
    "running-shoes":      "#15803d",
    "airsoft":            "#4b5563",
    "supplements":        "#7c3aed",
    "vpn-service":        "#0e7490",
    "replica-watch":      "#4b5563",
    "kratom":             "#15803d",
    "crossbow":           "#374151",
    "counterfeit-shoes":  "#4b5563",
    "stolen-device":      "#6b7280",
    "stolen-account":     "#6d28d9",
    "fake-subscribers":   "#7e22ce",
    "counterfeit-belt":   "#92400e",
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
