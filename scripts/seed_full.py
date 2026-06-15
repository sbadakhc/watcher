#!/usr/bin/env python3
"""
Watcher full demo seed -- 50 listings with real images from picsum.photos.

Downloads 50 royalty-free photos (Creative Commons) then submits them as
marketplace listings. The corpus deliberately exercises all three moderation
outcomes so every pipeline path is tested in a single run:

  - APPROVE (~22)  legitimate product listings, clean text + safe images
  - REVIEW  (~15)  ambiguous items or services requiring human judgement
  - REJECT  (~13)  clear policy violations (counterfeit, drugs, weapons, fraud)

NOTE on timing
  The vision model (qwen2.5vl:3b) takes approximately 5 minutes per image
  when cold. Moderating 50 listings back-to-back can therefore take several
  hours. Check progress at http://localhost:9104?moderator=admin -- listings
  arrive in the review queue as they are moderated, not all at once.

Usage:
    python3 scripts/seed_full.py \\
        --db-password <pw> \\
        --user-password <seller-pw>

    # Run once to download images, then again without re-downloading:
    python3 scripts/seed_full.py --db-password <pw> --user-password <pw> --skip-download

Get passwords from:
    ./aixcl app secrets watcher

Dependencies (all in watcher/requirements.txt):
    pip install httpx psycopg2-binary
"""

import argparse
import hashlib
import os
import secrets
import sys
import time
from pathlib import Path

import httpx
import psycopg2

# ---------------------------------------------------------------------------
# Seller profiles (10 accounts with varied risk profiles)
# ---------------------------------------------------------------------------

SELLERS = [
    {
        "username": "alice",
        "email": "alice@example.com",
        "violations": 0,
        "account_age_days": 730,
        "note": "Established seller, 2 years, clean history",
    },
    {
        "username": "bob",
        "email": "bob@example.com",
        "violations": 0,
        "account_age_days": 180,
        "note": "6-month seller, clean",
    },
    {
        "username": "carlos",
        "email": "carlos@example.com",
        "violations": 1,
        "account_age_days": 365,
        "note": "1-year account, one prior flag",
    },
    {
        "username": "diana",
        "email": "diana@example.com",
        "violations": 2,
        "account_age_days": 90,
        "note": "Known repeat policy violator",
    },
    {
        "username": "emma",
        "email": "emma@example.com",
        "violations": 0,
        "account_age_days": 400,
        "note": "Long-standing seller, clean",
    },
    {
        "username": "frank",
        "email": "frank@example.com",
        "violations": 0,
        "account_age_days": 240,
        "note": "Mid-tenure, clean",
    },
    {
        "username": "grace",
        "email": "grace@example.com",
        "violations": 0,
        "account_age_days": 30,
        "note": "Brand new seller",
    },
    {
        "username": "henry",
        "email": "henry@example.com",
        "violations": 3,
        "account_age_days": 120,
        "note": "High-risk flagged account",
    },
    {
        "username": "iris",
        "email": "iris@example.com",
        "violations": 0,
        "account_age_days": 900,
        "note": "Trusted veteran seller",
    },
    {
        "username": "jack",
        "email": "jack@example.com",
        "violations": 0,
        "account_age_days": 14,
        "note": "Two-week-old account",
    },
]

# ---------------------------------------------------------------------------
# 50 Listings
# Each entry: (seller, title, category, description, price, expected_outcome,
#              picsum_seed)
# picsum_seed is any string; picsum.photos uses it to pick a consistent photo.
# ---------------------------------------------------------------------------

LISTINGS = [

    # ===== AUTO-APPROVE (22) ================================================

    # -- Electronics (5) --
    (
        "alice",
        "MacBook Air M2 13-inch 256GB Space Grey",
        "Electronics",
        "MacBook Air M2, 2022, 8GB RAM, 256GB SSD in Space Grey. "
        "In excellent condition with only light use. "
        "Battery cycles: 42. Runs macOS Sonoma, no issues. "
        "All ports clean, keyboard and screen perfect. "
        "Comes with original charger and box. Upgrading to M3, hence selling.",
        849.00,
        "APPROVE",
        "laptop-desk",
    ),
    (
        "iris",
        "Sony WH-1000XM5 Wireless Noise Cancelling Headphones",
        "Electronics",
        "Sony WH-1000XM5 in Midnight Black. Purchased 8 months ago, "
        "barely used. Industry-leading ANC, 30-hour battery, "
        "USB-C charging. Original carry case and cables included. "
        "No scratches, earpads in mint condition.",
        240.00,
        "APPROVE",
        "headphones-music",
    ),
    (
        "emma",
        "Apple iPad Pro 12.9-inch M2 WiFi 256GB",
        "Electronics",
        "iPad Pro 12.9-inch 5th gen, M2 chip, 256GB, WiFi only, Space Grey. "
        "In excellent condition. Always used with official Apple case. "
        "Screen has no scratches. Apple Pencil 2 not included. "
        "Battery health great, charges normally.",
        720.00,
        "APPROVE",
        "tablet-ipad",
    ),
    (
        "iris",
        "Nintendo Switch OLED White 2023",
        "Electronics",
        "Nintendo Switch OLED model in white. Purchased new in 2023. "
        "Console, dock, Joy-Cons and all cables in original box. "
        "Screen unmarked -- always used with screen protector. "
        "Selling as I no longer have time to play.",
        280.00,
        "APPROVE",
        "gaming-console",
    ),
    (
        "frank",
        "Canon EOS R50 Mirrorless Camera Body Only",
        "Electronics",
        "Canon EOS R50 body in black. Shutter count: 1,840. "
        "In immaculate condition, used for portrait work. "
        "Sensor cleaned professionally. Includes original charger, "
        "battery, strap, and body cap. No lens included. "
        "Great entry into RF system.",
        490.00,
        "APPROVE",
        "camera-photo",
    ),

    # -- Clothing (4) --
    (
        "alice",
        "Vintage Levis 501 Jeans 32x30 Dark Indigo",
        "Clothing",
        "Classic Levi's 501 straight-fit jeans in dark indigo wash. "
        "Barely worn, excellent condition. 100% cotton shrink-to-fit. "
        "Size 32 waist, 30 inseam. No rips, no fading, "
        "original red tab intact. Great addition to any wardrobe.",
        45.00,
        "APPROVE",
        "jeans-denim",
    ),
    (
        "bob",
        "Nike Air Max 270 React Trainers UK10",
        "Clothing",
        "Nike Air Max 270 React in black and white, UK size 10. "
        "Worn twice, as new condition. Full Air unit in heel, "
        "React foam midsole. Comes with original box. "
        "No creasing, sole clean.",
        65.00,
        "APPROVE",
        "trainers-shoes",
    ),
    (
        "emma",
        "Barbour International Ariel Quilted Jacket Size 14",
        "Clothing",
        "Barbour International Ariel quilted jacket in black, ladies size 14. "
        "Excellent condition, worn only a handful of times. "
        "Lightweight, warm, water-resistant. Original bag included. "
        "RRP GBP220.",
        95.00,
        "APPROVE",
        "jacket-fashion",
    ),
    (
        "iris",
        "100% Cashmere Roll Neck Jumper Camel XL",
        "Clothing",
        "Pure cashmere roll-neck jumper in camel, size XL. "
        "Hand-washed once, no pilling. Incredibly soft. "
        "From a premium Scottish knitwear brand. "
        "Perfect for winter, layers well under coats.",
        85.00,
        "APPROVE",
        "knit-sweater",
    ),

    # -- Home & Garden (4) --
    (
        "bob",
        "KitchenAid Artisan 5Qt Stand Mixer Empire Red",
        "Home",
        "KitchenAid Artisan 5-quart stand mixer in Empire Red. "
        "Used approximately once a week for a year. Works perfectly. "
        "All original attachments: flat beater, dough hook, wire whip, "
        "pouring shield. Moving abroad, cannot take. Original RRP GBP499.",
        220.00,
        "APPROVE",
        "kitchen-mixer",
    ),
    (
        "frank",
        "Dyson V15 Detect Cordless Vacuum Cleaner",
        "Home",
        "Dyson V15 Detect in yellow and nickel. 18 months old, "
        "excellent condition. Laser dust detection and particle counting. "
        "Comes with all attachments and two batteries. "
        "Filters washed monthly. Full 60-minute runtime.",
        380.00,
        "APPROVE",
        "vacuum-appliance",
    ),
    (
        "frank",
        "Weber Spirit II E-310 3 Burner Gas BBQ",
        "Home",
        "Weber Spirit II E-310 propane BBQ grill. Used two summers. "
        "In good condition, cleaned after every use. "
        "Three stainless burners, porcelain grates, side tables. "
        "No rust. Regulator included, hose not included. "
        "Selling as upgrading to Weber Genesis.",
        290.00,
        "APPROVE",
        "bbq-grill",
    ),
    (
        "grace",
        "Philips Hue White and Colour Ambiance Starter Kit",
        "Home",
        "Philips Hue starter kit: 3x E27 White and Colour Ambiance bulbs "
        "plus Hue Bridge v2. All bulbs working perfectly. "
        "Full 16 million colour support. Works with Alexa, Google Home, "
        "Apple HomeKit. Everything in original box.",
        75.00,
        "APPROVE",
        "smart-home",
    ),

    # -- Vehicles (2) --
    (
        "alice",
        "Trek FX 3 Disc Hybrid Bike 2022 Medium",
        "Vehicles",
        "Trek FX 3 Disc hybrid, 2022, size Medium, matte navy. "
        "Approx 600 miles of commute use. "
        "Hydraulic disc brakes, Shimano Altus drivetrain, "
        "puncture-resistant tyres. Serviced 3 months ago. "
        "Selling because I moved closer to work.",
        575.00,
        "APPROVE",
        "bicycle-cycling",
    ),
    (
        "emma",
        "Volkswagen Golf Mk7 1.4 TSI SE Manual 2015",
        "Vehicles",
        "2015 VW Golf Mk7 1.4 TSI SE, 5-door, manual, 78k miles. "
        "Full service history, cambelt done at 60k. "
        "12 months MOT, no advisories. "
        "Bluetooth, heated seats, parking sensors. "
        "One previous keeper. HPI clear.",
        9200.00,
        "APPROVE",
        "car-vehicle",
    ),

    # -- Books & Media (2) --
    (
        "grace",
        "Harry Potter Complete Hardback Box Set 7 Books",
        "Books",
        "Complete Harry Potter hardback collection, books 1-7. "
        "UK Bloomsbury editions. All in very good condition, "
        "minimal shelf wear, spines intact, no writing inside. "
        "Perfect for a first-time reader or gift.",
        65.00,
        "APPROVE",
        "books-library",
    ),
    (
        "iris",
        "Vinyl Record Collection 1970s Classic Rock 40 LPs",
        "Books",
        "Collection of 40 classic rock LPs, all from the 1970s: "
        "Led Zeppelin, Fleetwood Mac, Jethro Tull, Thin Lizzy, ELO and more. "
        "Grades: VG to EX. All have original sleeves. "
        "Full list available on request. Selling due to downsizing.",
        220.00,
        "APPROVE",
        "vinyl-records",
    ),

    # -- Sports & Outdoors (3) --
    (
        "alice",
        "Patagonia Nano Puff Jacket Mens Large Black",
        "Sports",
        "Patagonia Nano Puff Insulated Jacket, mens large, black. "
        "Used for one ski season, excellent condition. "
        "PrimaLoft Gold insulation, DWR treated shell. "
        "Packs into its own pocket. No tears, zips work perfectly.",
        145.00,
        "APPROVE",
        "outdoor-jacket",
    ),
    (
        "emma",
        "YETI Rambler 30oz Tumbler Set of 4 Assorted Colours",
        "Sports",
        "Set of 4 YETI Rambler 30oz stainless tumblers. "
        "Used, cleaned thoroughly. Minor surface scuffs only. "
        "Magnetic slider lids, dishwasher safe. "
        "Keeps drinks cold 24h, hot 8h.",
        90.00,
        "APPROVE",
        "outdoor-gear",
    ),
    (
        "bob",
        "Osprey Atmos AG 65L Hiking Backpack Medium Blue",
        "Sports",
        "Osprey Atmos AG 65 backpack, medium, Rigby Blue. "
        "Used for two multi-day hikes, very good condition. "
        "Anti-gravity suspension, rain cover included. "
        "Hip belt pockets, sleeping bag compartment. "
        "Fits torso 18-20 inches.",
        155.00,
        "APPROVE",
        "hiking-backpack",
    ),

    # -- Collectibles (2) --
    (
        "frank",
        "LEGO Star Wars Millennium Falcon 75257 Complete",
        "Collectibles",
        "LEGO Star Wars Millennium Falcon set 75257, 100% complete "
        "with all 1,351 pieces. All minifigs present. "
        "Built once, immediately disassembled. "
        "Instructions included, original box included but has shelf wear.",
        125.00,
        "APPROVE",
        "lego-toys",
    ),
    (
        "emma",
        "Pokemon Cards Base Set Unlimited Collection Near Mint",
        "Collectibles",
        "Selection of 45 Base Set unlimited Pokemon cards, predominantly "
        "commons and uncommons, several holos including Charizard and Blastoise. "
        "All individually sleeved. "
        "Near mint to mint condition, no creases or marks. "
        "From smoke-free home.",
        280.00,
        "APPROVE",
        "pokemon-cards",
    ),

    # ===== HUMAN REVIEW (15) ================================================

    (
        "carlos",
        "Phone Unlocking Service All Networks 24 Hours",
        "Services",
        "Professional remote phone unlocking for any carrier worldwide. "
        "Permanent unlock within 24 hours -- no software required. "
        "Compatible with all iPhone and Android models. "
        "Over 1,000 satisfied customers. Send IMEI via message.",
        35.00,
        "REVIEW",
        "phone-service",
    ),
    (
        "carlos",
        "Vintage US Army M65 Field Jacket 1970s Large",
        "Clothing",
        "Authentic US Army M65 field jacket from 1970s military surplus. "
        "Olive drab, size Large Regular. "
        "Light wear consistent with age. All buttons intact, no tears. "
        "Collector piece, not a reproduction. "
        "Great for outdoor activities or fashion layering.",
        88.00,
        "REVIEW",
        "military-jacket",
    ),
    (
        "carlos",
        "Advanced Home Chemistry Lab Kit 40 Reagents",
        "Other",
        "Advanced chemistry set for serious hobbyists and home experimenters. "
        "Includes 40+ reagents, Pyrex glassware, separating funnel, "
        "and 60-page instruction manual. "
        "Everything needed for titration, crystallisation, and "
        "organic synthesis experiments. Adults only.",
        120.00,
        "REVIEW",
        "science-lab",
    ),
    (
        "bob",
        "Professional Lockpick Set 24 Picks Stainless Steel",
        "Other",
        "Professional-grade lockpick set with 24 picks and 4 tension wrenches. "
        "High-carbon stainless steel, lifetime warranty. "
        "Used by locksmiths and physical security testers. "
        "Includes zip case. Legal where authorised locksport activities permitted.",
        55.00,
        "REVIEW",
        "tools-metal",
    ),
    (
        "carlos",
        "Airsoft MP5 Submachine Gun Full Metal Replica",
        "Sports",
        "Full-metal airsoft MP5 SMG replica, 6mm BB. "
        "Firing velocity 320 fps, semi and full auto. "
        "Two 200-round high-cap magazines included. "
        "Suitable for skirmish use, bright orange tip fitted. "
        "UK legal, F1 site rated. Buyer must confirm 18+.",
        185.00,
        "REVIEW",
        "airsoft-gun",
    ),
    (
        "frank",
        "Car Key Programming and Cutting Service Mobile",
        "Services",
        "Mobile car key cutting and programming for most European and "
        "Asian vehicles including lost-key situations. "
        "AUTEL and Lonsdor equipment. "
        "Registered locksmith, fully insured. "
        "Can attend your home or workplace. Call to check compatibility.",
        90.00,
        "REVIEW",
        "car-keys",
    ),
    (
        "grace",
        "Taxidermy Red Deer Antlers Stag Wall Mount",
        "Collectibles",
        "Professionally mounted set of red deer antlers on oak shield. "
        "Approx 10-point rack. Legally sourced from a Scottish estate. "
        "Certificate of lawful harvest included. "
        "Some minor discolouration on left tine. "
        "Dimensions: 70cm wide, 55cm high.",
        175.00,
        "REVIEW",
        "antlers-nature",
    ),
    (
        "henry",
        "Cryptocurrency Mining Rig 6x RX6600 160 MH/s",
        "Electronics",
        "Complete ETH mining rig: 6x AMD RX6600 GPUs, "
        "Asrock H110 Pro BTC motherboard, "
        "1600W Platinum PSU, aluminium open frame, "
        "16GB RAM, 240GB SSD. "
        "Ran for 10 months before merge, very low wear. "
        "Hashrate validated at 160 MH/s Ethereum classic.",
        1400.00,
        "REVIEW",
        "mining-rig",
    ),
    (
        "henry",
        "Modded PS5 Disc Edition Custom Firmware Homebrew",
        "Electronics",
        "PS5 disc edition with exploited firmware enabling homebrew. "
        "Can run backups from external drive. "
        "Firmware version 4.51 (do not update). "
        "Two controllers included. "
        "Jailbreak may void manufacturer warranty.",
        480.00,
        "REVIEW",
        "console-gaming",
    ),
    (
        "grace",
        "Reading Glasses Bulk Job Lot 50 Pairs Assorted Strengths",
        "Health",
        "Bulk lot of 50 pairs of over-the-counter reading glasses, "
        "strengths from +1.0 to +3.5. "
        "Various frame styles and colours. "
        "Ideal for resale, hospitality, or office use. "
        "Sealed packaging, no prescription required. "
        "No returns on bulk lots.",
        40.00,
        "REVIEW",
        "glasses-eyewear",
    ),
    (
        "carlos",
        "Used Patek Philippe Aquanaut 5168G Watch",
        "Collectibles",
        "Patek Philippe Aquanaut Ref. 5168G in white gold. "
        "Purchased 2019 from secondary market dealer in Geneva. "
        "Serviced 2022, papers from service included. "
        "Original box not available. "
        "Hands and indices perfect. See photos for condition.",
        32000.00,
        "REVIEW",
        "watch-luxury",
    ),
    (
        "henry",
        "Lifetime VPN Service Anonymous No-Log Account",
        "Services",
        "Lifetime subscription to anonymous VPN service. "
        "No-log policy, offshore servers, accepts crypto payment. "
        "Account transferable. "
        "Useful for privacy-conscious users. "
        "Works on Windows, Mac, iOS, Android.",
        45.00,
        "REVIEW",
        "vpn-network",
    ),
    (
        "carlos",
        "Surplus Hospital Portable Suction Unit Medical Grade",
        "Health",
        "Portable medical suction unit from hospital clearance. "
        "Laerdal Suction Unit LSU, 2018, fully functional. "
        "Cleaned and tested. "
        "Suitable for first-responder, veterinary, or training use. "
        "No warranty, sold as-is.",
        220.00,
        "REVIEW",
        "medical-device",
    ),
    (
        "carlos",
        "IMEI Blacklist Check and Removal Service iPhone",
        "Services",
        "IMEI blacklist removal and carrier unlock for iPhones. "
        "Works for lost, stolen or carrier-blocked devices. "
        "Turnaround 2-7 business days. "
        "Send IMEI and network via message. "
        "Over 300 successful removals in past year.",
        70.00,
        "REVIEW",
        "imei-service",
    ),
    (
        "jack",
        "Surplus Teargas Grenades Training Inert Props Set of 4",
        "Other",
        "Set of 4 inert (dummy) CS gas grenade training props "
        "for film, stage, or tactical training use. "
        "Steel construction, painted safety blue. "
        "No explosive compound, pins pull freely. "
        "Used by security training company. No live agent inside.",
        60.00,
        "REVIEW",
        "training-props",
    ),

    # ===== AUTO-REJECT (13) =================================================

    (
        "diana",
        "Louis Vuitton Neverfull MM New Monogram Canvas",
        "Clothing",
        "Brand new Louis Vuitton Neverfull MM tote in signature monogram. "
        "Comes with LV dust bag and receipt from supplier. "
        "Beautiful construction, nearly indistinguishable from retail. "
        "Purchased wholesale from Guangzhou manufacturer. "
        "Several colours available.",
        180.00,
        "REJECT",
        "handbag-fake",
    ),
    (
        "diana",
        "Tramadol 50mg 100 Tablets No Prescription Needed",
        "Health",
        "Selling unopened pack of Tramadol 50mg, 100 count. "
        "No prescription required for purchase here. "
        "Fast and discreet shipping, plain packaging. "
        "Bulk pricing available for multiple packs. "
        "Contact for details.",
        60.00,
        "REJECT",
        "pills-capsules",
    ),
    (
        "diana",
        "Stun Gun 1 Million Volt Personal Defence Device",
        "Other",
        "High-voltage stun gun for personal protection. "
        "1,000,000 volt output, rechargeable battery, "
        "built-in LED torch. Compact enough for pocket carry. "
        "Shipping available to all UK and EU postcodes. "
        "No ID check required.",
        45.00,
        "REJECT",
        "stun-device",
    ),
    (
        "diana",
        "10000 Instagram Followers Delivered 48 Hours Guaranteed",
        "Services",
        "Boost your Instagram instantly with 10,000 followers "
        "delivered within 48 hours. "
        "Real-looking accounts, 100% money-back guarantee. "
        "Bot network ensures rapid delivery, undetectable. "
        "DM for bulk packages or other platforms.",
        25.00,
        "REJECT",
        "social-fraud",
    ),
    (
        "henry",
        "Fake UK Driving Licence ID Card Novelty Prop",
        "Other",
        "High quality novelty UK driving licence prop for film and stage. "
        "Your name, photo and details printed on request. "
        "PVC card, holographic overlay, feels like real document. "
        "Turnaround 3 days, posted discreetly. "
        "Many repeat customers.",
        65.00,
        "REJECT",
        "fake-id",
    ),
    (
        "diana",
        "Complete Hacking Tutorial Bundle 80 Hours Video Course",
        "Books",
        "80-hour video tutorial series covering SQL injection, "
        "XSS, network enumeration, password cracking, "
        "and remote access trojans. "
        "Includes working exploit scripts and cracking wordlists. "
        "Learn to gain unauthorised access to systems. "
        "Beginner to advanced. Lifetime access.",
        40.00,
        "REJECT",
        "hacking-tutorial",
    ),
    (
        "diana",
        "Stolen Credit Card Checker Validator Tool Premium",
        "Services",
        "Premium CC checker tool for validating stolen card details. "
        "Checks balance, BIN lookup, and card validity. "
        "High success rate, low detection. "
        "Works for Visa, Mastercard, Amex. "
        "Subscription plans available.",
        30.00,
        "REJECT",
        "fraud-tool",
    ),
    (
        "henry",
        "Rolex Submariner Replica Swiss ETA Movement",
        "Collectibles",
        "Replica Rolex Submariner with Swiss ETA 2836 movement. "
        "Sapphire crystal, 904L steel case, ceramic bezel. "
        "Keeps excellent time. "
        "Comes in Rolex presentation box with fake papers. "
        "Ships from Hong Kong warehouse.",
        280.00,
        "REJECT",
        "fake-watch",
    ),
    (
        "henry",
        "Bulk Email Marketing Service Send 1 Million Emails",
        "Services",
        "Bulk email sending service -- blast 1 million emails "
        "from rotating IPs for high deliverability. "
        "Bypasses spam filters. "
        "Templates for phishing, newsletter, and product promotions. "
        "Unsubscribe link optional. 72-hour delivery window.",
        75.00,
        "REJECT",
        "spam-service",
    ),
    (
        "diana",
        "Darknet Marketplace Beginner Access and Vendor Guide",
        "Books",
        "Complete beginner's guide to accessing darknet markets: "
        "Tor setup, PGP encryption, cryptocurrency payment methods, "
        "vendor ratings, and how to receive parcels safely. "
        "Includes links to active markets and escrow guides. "
        "PDF delivered by email.",
        20.00,
        "REJECT",
        "darknet-guide",
    ),
    (
        "henry",
        "Cloned SIM Cards 10 Pack UK Numbers Active",
        "Electronics",
        "Pack of 10 pre-cloned UK SIM cards with active numbers. "
        "Useful for anonymous calling, SMS verification bypass, "
        "or reselling. "
        "No contracts, no ID required. "
        "Ships within 48 hours. Bulk discounts available.",
        120.00,
        "REJECT",
        "cloned-sims",
    ),
    (
        "diana",
        "Remote Access Trojan Full Feature Panel and Builder",
        "Services",
        "Professional RAT builder and control panel. "
        "Features: keylogger, webcam capture, file manager, "
        "clipboard monitor, persistence across reboots. "
        "Bypasses major AV vendors. FUD guaranteed at time of sale. "
        "Source code included, Python and C2 panel.",
        150.00,
        "REJECT",
        "malware-rat",
    ),
    (
        "diana",
        "Verified PayPal Accounts with Balance Aged Accounts",
        "Services",
        "Selling aged PayPal accounts pre-loaded with balance "
        "from $200 to $2000. All accounts verified with real SSN. "
        "Includes login, backup email, and security questions. "
        "Change details immediately after purchase. "
        "Cashout methods guide included.",
        90.00,
        "REJECT",
        "stolen-accounts",
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
# Image download
# ---------------------------------------------------------------------------

def download_images(listings: list, images_dir: Path, delay: float) -> dict:
    """
    Download one image per listing from picsum.photos.

    Returns a dict mapping picsum_seed -> local Path.
    Uses seed-based URLs so the same seed always fetches the same photo.
    Skips seeds whose file already exists on disk.
    """
    images_dir.mkdir(parents=True, exist_ok=True)
    image_map = {}
    to_download = []

    for entry in listings:
        seed = entry[6]
        dest = images_dir / f"{seed}.jpg"
        if dest.exists():
            image_map[seed] = dest
        else:
            to_download.append((seed, dest))

    if to_download:
        print(f"  Downloading {len(to_download)} image(s) "
              f"(skipping {len(image_map)} cached)...")
    else:
        print(f"  All {len(listings)} images already cached.")
        for entry in listings:
            image_map[entry[6]] = images_dir / f"{entry[6]}.jpg"
        return image_map

    for i, (seed, dest) in enumerate(to_download, 1):
        url = f"https://picsum.photos/seed/{seed}/640/480"
        try:
            with httpx.Client(timeout=30, follow_redirects=True) as client:
                r = client.get(url)
                if r.status_code == 200:
                    dest.write_bytes(r.content)
                    image_map[seed] = dest
                    print(f"    [{i:02d}/{len(to_download):02d}] {seed}.jpg  "
                          f"({len(r.content):,} bytes)")
                else:
                    print(f"    [{i:02d}/{len(to_download):02d}] FAILED {seed} "
                          f"-- HTTP {r.status_code}", file=sys.stderr)
        except Exception as e:
            print(f"    [{i:02d}/{len(to_download):02d}] FAILED {seed} -- {e}",
                  file=sys.stderr)

        if i < len(to_download) and delay > 0:
            time.sleep(delay)

    return image_map


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
                created_at = datetime.now(timezone.utc) - timedelta(
                    days=s.get("account_age_days", 0)
                )
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
                """, (
                    s["username"], s["email"], pw_hash,
                    s["violations"], created_at,
                ))
                print(f"    {s['username']:10s}  {s['note']}")
    conn.close()


# ---------------------------------------------------------------------------
# API: submit a listing
# ---------------------------------------------------------------------------

def submit_listing(api: str, seller: str, title: str, category: str,
                   description: str, price: float,
                   image_path: Path | None) -> str | None:
    data = {
        "user_id": seller,
        "title": title,
        "category": category,
        "description": description,
        "price": str(price),
    }
    files = None
    if image_path and image_path.exists():
        files = {"images": (image_path.name, image_path.read_bytes(), "image/jpeg")}

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
    ap = argparse.ArgumentParser(
        description="Seed watcher with 50 demo listings and real images"
    )
    ap.add_argument("--api",            default="http://localhost:9104")
    ap.add_argument("--db-host",        default="localhost")
    ap.add_argument("--db-port",        type=int, default=5432)
    ap.add_argument("--db-name",        default="watcher")
    ap.add_argument("--db-user",        default="watcher")
    ap.add_argument("--db-password",    required=True)
    ap.add_argument("--user-password",  required=True,
                    help="Password all seller accounts will share")
    ap.add_argument("--images-dir",     default=os.path.expanduser("~/.cache/watcher-images"),
                    help="Local cache dir for downloaded images (default: ~/.cache/watcher-images)")
    ap.add_argument("--download-delay", type=float, default=2.0,
                    help="Seconds between image downloads (default: 2.0 -- polite rate)")
    ap.add_argument("--submit-delay",   type=float, default=1.0,
                    help="Seconds between listing submissions (default: 1.0)")
    ap.add_argument("--skip-download",  action="store_true",
                    help="Skip download phase; use whatever images exist in --images-dir")
    ap.add_argument("--wait",           type=int, default=60,
                    help="Seconds to wait after seeding before printing stats (default: 60)")
    args = ap.parse_args()

    images_dir = Path(args.images_dir)

    print("\nWatcher Full Demo Seed  --  50 Listings")
    print("=" * 60)
    print(f"  API         : {args.api}")
    print(f"  Images dir  : {images_dir}")
    print(f"  Listings    : {len(LISTINGS)} total "
          f"(22 approve / 15 review / 13 reject expected)")
    print()

    # 1. Download images
    print("[1/4] Downloading images from picsum.photos...")
    if args.skip_download:
        print("  --skip-download set; using cached files only.")
        image_map = {
            e[6]: images_dir / f"{e[6]}.jpg" for e in LISTINGS
        }
    else:
        image_map = download_images(
            listings=LISTINGS,
            images_dir=images_dir,
            delay=args.download_delay,
        )

    missing = sum(
        1 for e in LISTINGS
        if not (images_dir / f"{e[6]}.jpg").exists()
    )
    if missing:
        print(f"  WARNING: {missing} image(s) missing -- those listings will "
              f"submit without an image.")

    # 2. Create seller accounts
    print("\n[2/4] Creating seller accounts...")
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

    # 3. Submit listings
    print(f"\n[3/4] Submitting {len(LISTINGS)} listings...")
    submitted, errors = [], 0
    for seller, title, category, description, price, expected, seed in LISTINGS:
        image_path = images_dir / f"{seed}.jpg"
        listing_id = submit_listing(
            api=args.api,
            seller=seller,
            title=title,
            category=category,
            description=description,
            price=price,
            image_path=image_path if image_path.exists() else None,
        )
        img_tag = "img" if image_path.exists() else "txt"
        if listing_id:
            submitted.append((listing_id, title, expected))
            print(f"  [{img_tag}] {expected:6s}  {title[:55]}")
        else:
            errors += 1
            print(f"  [{img_tag}] ERROR   {title[:55]}")

        if args.submit_delay > 0:
            time.sleep(args.submit_delay)

    # 4. Wait for stats
    if submitted and args.wait > 0:
        print(f"\n[4/4] Waiting {args.wait}s for Ollama moderation "
              f"(text pass only -- vision is much slower)...")
        time.sleep(args.wait)

    try:
        with httpx.Client(base_url=args.api, timeout=10) as client:
            r = client.get("/api/stats")
            if r.status_code == 200:
                s = r.json()
                print("\n  Stats from /api/stats:")
                print(f"    total listings  : {s.get('total_listings', 0)}")
                print(f"    published       : {s.get('published_listings', 0)}")
                print(f"    pending review  : {s.get('pending_review', 0)}")
                print(f"    rejected        : {s.get('rejected_listings', 0)}")
    except Exception as e:
        print(f"  (could not fetch stats: {e})")

    print(f"\n{'=' * 60}")
    print(f"Done. {len(submitted)}/{len(LISTINGS)} submitted, {errors} error(s).")
    print()
    print(f"  Storefront    : {args.api}/")
    print(f"  Review queue  : {args.api}/?moderator=admin")
    print()
    print("  NOTE: Vision moderation (qwen2.5vl:3b) runs per image in the")
    print("  background. Each image takes ~5 min. Allow several hours for")
    print("  all 50 listings to complete vision analysis.")
    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
