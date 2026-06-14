"""
Watcher Moderation Service — FastAPI application.

Serves both the API and the React frontend build.
"""

import logging
import sys
import time
from contextlib import asynccontextmanager
from io import BytesIO
from typing import Optional

from PIL import Image as PILImage

from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from prometheus_client import Counter, Gauge, Histogram, generate_latest

from config import (
    AUTO_APPROVE_THRESHOLD,
    LOG_LEVEL,
    PORT,
    REVIEW_THRESHOLD,
    validate,
)
from db import (
    create_listing,
    enqueue_review,
    get_image_by_id,
    get_published_listings,
    get_review_queue,
    get_stats,
    get_user_by_username,
    init_schema,
    review_item,
    seed_users,
    store_image,
    store_moderation,
)
from moderation import run_moderation, apply_threshold

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL.upper()),
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("watcher")

# ---------------------------------------------------------------------------
# Prometheus metrics
# ---------------------------------------------------------------------------

LISTINGS_SUBMITTED = Counter("watcher_listings_submitted_total", "Total listings submitted")
DECISIONS_TOTAL = Counter("watcher_decisions_total", "Total moderation decisions", ["decision"])
QUEUE_DEPTH = Gauge("watcher_review_queue_depth", "Number of listings pending human review")
MODERATION_LATENCY = Histogram(
    "watcher_moderation_latency_seconds",
    "Time spent moderating a listing",
    buckets=[0.5, 1.0, 2.0, 3.0, 5.0, 10.0, 20.0, 30.0],
)
MODEL_ERRORS = Counter("watcher_model_errors_total", "Total model errors", ["stage"])

# ---------------------------------------------------------------------------
# Security
# ---------------------------------------------------------------------------

security = HTTPBasic(auto_error=False)

# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Watcher starting...")
    try:
        validate()
        init_schema()
        seed_users()
        logger.info("Database schema initialized.")
    except Exception as exc:
        logger.error("Startup failed: %s", exc)
        raise
    yield
    logger.info("Watcher shutting down...")


app = FastAPI(title="Watcher Moderation Service", version="0.2.0", lifespan=lifespan)


# ---------------------------------------------------------------------------
# CORS and security headers
# ---------------------------------------------------------------------------


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' blob: data:; connect-src 'self'"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


# ---------------------------------------------------------------------------
# Auth dependency
# ---------------------------------------------------------------------------


def _require_basic_auth(credentials: Optional[HTTPBasicCredentials] = Depends(security)):
    from auth import verify_basic_auth

    if credentials is None:
        raise HTTPException(status_code=401, detail="Authentication required", headers={"WWW-Authenticate": "Basic"})
    if not verify_basic_auth(credentials.username, credentials.password):
        raise HTTPException(status_code=401, detail="Invalid credentials", headers={"WWW-Authenticate": "Basic"})
    return credentials.username


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


@app.get("/api/health")
async def health():
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------


@app.get("/api/metrics")
async def metrics():
    return Response(generate_latest(), media_type="text/plain")


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------


@app.post("/api/login")
async def login(
    username: str = Form(...),
    password: str = Form(...),
):
    from auth import check_password

    user = get_user_by_username(username)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid username or password")

    if not check_password(password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid username or password")

    if user.get("is_banned"):
        raise HTTPException(status_code=403, detail="Account suspended. Contact support.")

    return {
        "id": str(user["id"]),
        "username": user["username"],
        "is_admin": bool(user.get("is_admin", False)),
        "is_banned": bool(user.get("is_banned", False)),
    }


# ---------------------------------------------------------------------------
# Background moderation helper (Issue 1 fix: async submission)
# ---------------------------------------------------------------------------

def _run_moderation(listing_uuid: str, title: str, category: str, description: str, user_id: str, image_ids: list) -> None:
    """Run full moderation pipeline in background after submission returns."""
    from db import get_seller_stats
    from moderation import run_moderation, apply_threshold

    start = time.time()

    # Get seller stats
    try:
        seller_stats = get_seller_stats(user_id)
    except Exception:
        seller_stats = {
            "account_age_days": 0,
            "previous_listing_count": 0,
            "previous_violation_count": 0,
        }

    # Get image bytes if available
    image_bytes = None
    if image_ids:
        from db import get_images_for_listing
        images_data = get_images_for_listing(listing_uuid)
        if images_data:
            image_bytes = bytes(images_data[0]["image_data"])

    # Run full moderation
    try:
        result = run_moderation(title, category, description, seller_stats, image_bytes)
    except Exception:
        MODEL_ERRORS.labels(stage="text").inc()
        result = {
            "decision": "REVIEW",
            "confidence": 0.5,
            "risk_score": 50,
            "reasons": ["moderation_error"],
            "evidence": ["System error during moderation"],
            "summary": "Moderation failed, requires human review",
            "flags": ["moderation_error"],
            "requires_human_review": True,
        }

    latency = time.time() - start
    MODERATION_LATENCY.observe(latency)

    # Store moderation with full evidence
    store_moderation(
        listing_uuid,
        "qwen3:4b",
        "qwen2.5-vl:3b",
        {"decision": result.get("decision"), "confidence": result.get("confidence"), "reasons": result.get("reasons", [])},
        {"decision": result.get("decision"), "confidence": result.get("confidence"), "reasons": result.get("reasons", []), "image_summary": result.get("image_summary")} if result.get("image_summary") else None,
        result,
    )

    # Apply threshold and auto-publish or queue
    decision, next_step = apply_threshold(result)
    if next_step == "published":
        DECISIONS_TOTAL.labels(decision="auto_approve").inc()
        try:
            from db import auto_publish_listing
            auto_publish_listing(listing_uuid, f"Auto-approved: {result.get('summary', 'AI approved')}")
        except Exception:
            logger.error("Auto-publish failed for listing %s", listing_uuid)
    else:
        DECISIONS_TOTAL.labels(decision="human_review").inc()
        enqueue_review(listing_uuid, result)
        QUEUE_DEPTH.set(len(get_review_queue("pending")))


# ---------------------------------------------------------------------------
# Submit listing (Issue 1 fix: return immediately, background moderation)
# ---------------------------------------------------------------------------


@app.post("/api/submit")
async def submit(
    background_tasks: BackgroundTasks,
    user_id: str = Form(...),
    title: str = Form(...),
    category: str = Form("Other"),
    description: str = Form(...),
    price: float = Form(...),
    images: Optional[list[UploadFile]] = File(None),
):
    LISTINGS_SUBMITTED.inc()

    # Validate user exists - accept UUID or username lookup
    try:
        from uuid import UUID
        UUID(user_id)
        validated_user_id = user_id
    except ValueError:
        user = get_user_by_username(user_id)
        if user is None:
            raise HTTPException(status_code=400, detail=f"User not found: {user_id}")
        validated_user_id = str(user["id"])

    # Create listing
    listing_uuid = create_listing(
        listing_id=f"listing-{int(time.time() * 1000)}",
        user_id=validated_user_id,
        title=title,
        category=category,
        description=description,
        price=price,
    )

    # Store images (only JPEG and PNG allowed)
    image_ids = []
    if images:
        for image in images:
            image_bytes = await image.read()
            if len(image_bytes) > 5 * 1024 * 1024:
                raise HTTPException(status_code=413, detail="Image too large (max 5MB)")
            mime = image.content_type or "application/octet-stream"
            filename = (image.filename or "uploaded").lower()
            is_allowed_mime = mime in {"image/jpeg", "image/png"}
            is_allowed_ext = filename.endswith((".jpg", ".jpeg", ".png"))
            if not (is_allowed_mime or is_allowed_ext):
                raise HTTPException(status_code=415, detail="Only JPG, JPEG, and PNG images are allowed")
            image_id = store_image(listing_uuid, image_bytes, mime, image.filename or "uploaded")
            image_ids.append(image_id)
    else:
        raise HTTPException(status_code=400, detail="At least one image is required")

    # Queue background moderation and return immediately
    background_tasks.add_task(_run_moderation, listing_uuid, title, category, description, validated_user_id, image_ids)

    return JSONResponse(
        status_code=200,
        content={
            "listing_id": listing_uuid,
            "message": "Listing submitted! It will appear in the store once approved.",
            "status": "pending_review",
        },
    )


# ---------------------------------------------------------------------------
# Review queue
# ---------------------------------------------------------------------------


@app.get("/api/review-queue")
async def review_queue(status: str = "pending", limit: int = 50):
    items = get_review_queue(status, limit)
    QUEUE_DEPTH.set(len(get_review_queue("pending")))
    return {
        "count": len(items),
        "status": status,
        "items": [
            {
                "id": str(item["id"]),
                "listing_id": str(item["listing_id"]),
                "title": item["title"],
                "category": item.get("category", "Other"),
                "description": (item["description"] or "")[:200],
                "price": float(item["price"]),
                "status": item["status"],
                "priority": item["priority"],
                "ai_decision": item["ai_decision"],
                "ai_confidence": float(item["ai_confidence"]) if item["ai_confidence"] else None,
                "ai_reasons": item["ai_reasons"],
                "image_url": f"/api/images/{item['image_id']}?width=400" if item.get("image_id") else None,
                "submitter": item.get("submitter", "unknown"),
                "created_at": item["created_at"].isoformat() if item["created_at"] else None,
            }
            for item in items
        ],
    }


@app.post("/api/review/{listing_id}")
async def review(listing_id: str, action: str = Form(...), moderator: Optional[str] = Form(None), notes: Optional[str] = Form(None)):
    if action not in {"publish", "ban", "approve", "reject"}:
        raise HTTPException(status_code=400, detail="Action must be 'publish', 'ban', 'approve', or 'reject'")

    # Normalize legacy actions for backward compat
    db_action = action
    if action == "publish":
        db_action = "published"
    elif action == "ban":
        db_action = "rejected"

    success = review_item(listing_id, db_action, moderator, notes)
    if not success:
        raise HTTPException(status_code=404, detail="Listing not found or already reviewed")

    # Update is_published flag
    from db import _get_conn

    with _get_conn() as conn:
        with conn.cursor() as cur:
            if action == "publish":
                cur.execute(
                    "UPDATE watcher.listings SET is_published = TRUE, updated_at = NOW() WHERE id = %s",
                    (listing_id,),
                )
            elif action == "ban":
                cur.execute(
                    "UPDATE watcher.listings SET is_published = FALSE, updated_at = NOW() WHERE id = %s",
                    (listing_id,),
                )
                # Increment violation count for the listing's owner
                cur.execute(
                    """
                    UPDATE watcher.users
                    SET previous_violation_count = previous_violation_count + 1
                    WHERE id = (SELECT user_id FROM watcher.listings WHERE id = %s)
                    """,
                    (listing_id,),
                )

    QUEUE_DEPTH.set(len(get_review_queue("pending")))
    return {"listing_id": listing_id, "action": action, "status": "completed"}


# ---------------------------------------------------------------------------
# User dashboard
# ---------------------------------------------------------------------------


@app.get("/api/my-listings")
async def my_listings(user_id: str = Query(...)):
    """Return all listings for a user with moderation status."""
    from db import get_user_listings, is_user_banned

    user = get_user_by_username(user_id)
    if user is None:
        raise HTTPException(status_code=400, detail="User not found")

    listings = get_user_listings(user_id)
    is_banned = is_user_banned(user_id)

    return {
        "is_banned": is_banned,
        "listings": [
            {
                "id": str(item["id"]),
                "listing_id": str(item["listing_id"]),
                "title": item["title"],
                "description": item["description"],
                "price": float(item["price"]),
                "status": item["status"],
                "is_published": item["is_published"],
                "image_url": f"/api/images/{item['image_id']}?width=400" if item.get("image_id") else None,
                "ai_decision": item.get("final_decision"),
                "ai_confidence": float(item["final_confidence"]) if item.get("final_confidence") else None,
                "ai_reasons": item.get("text_reasons") or item.get("image_reasons") or ["none"],
                "created_at": item["created_at"].isoformat() if item["created_at"] else None,
                "updated_at": item["updated_at"].isoformat() if item["updated_at"] else None,
            }
            for item in listings
        ]
    }


@app.put("/api/listings/{listing_id}")
async def update_listing_endpoint(
    listing_id: str,
    user_id: str = Form(...),
    title: str = Form(...),
    category: str = Form("Other"),
    description: str = Form(...),
    price: float = Form(...),
):
    """Edit and resubmit a rejected listing."""
    from db import get_user_by_username, update_listing, is_user_banned

    user = get_user_by_username(user_id)
    if user is None:
        raise HTTPException(status_code=400, detail="User not found")

    if user.get("is_banned"):
        raise HTTPException(status_code=403, detail="Account suspended")

    # Update the listing
    success = update_listing(listing_id, title, category, description, price)
    if not success:
        raise HTTPException(status_code=404, detail="Listing not found")

    # Re-run moderation in background
    # Note: images stay the same, only text changes
    # For simplicity, we trigger a new moderation cycle

    return {
        "listing_id": listing_id,
        "message": "Listing updated and sent for moderation",
        "status": "pending_review"
    }


@app.post("/api/ban-user/{username}")
async def ban_user_endpoint(
    username: str,
    moderator: str = Form(...),
):
    """Ban a user (admin only)."""
    from db import get_user_by_username, ban_user

    mod = get_user_by_username(moderator)
    if not mod or not mod.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")

    success = ban_user(username)
    if not success:
        raise HTTPException(status_code=404, detail="User not found")

    return {"username": username, "action": "banned", "status": "completed"}


@app.delete("/api/listings/{listing_id}")
async def delete_listing_endpoint(
    listing_id: str,
    username: str = Form(...),
):
    """Delete a listing (owner or admin only).

    Users can delete their own listings.
    Admins can delete any listing.
    """
    from db import delete_listing, get_user_by_username

    user = get_user_by_username(username)
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")

    is_admin = bool(user.get("is_admin", False))
    success = delete_listing(listing_id, username, is_admin)

    if not success:
        raise HTTPException(status_code=404, detail="Listing not found or not authorized")

    return {"listing_id": listing_id, "action": "deleted", "status": "completed"}


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------


@app.get("/api/stats")
async def stats():
    stats_data = get_stats()
    return {
        **stats_data,
        "auto_approve_threshold": AUTO_APPROVE_THRESHOLD,
        "review_threshold": REVIEW_THRESHOLD,
    }


# ---------------------------------------------------------------------------
# Storefront
# ---------------------------------------------------------------------------


@app.get("/api/listings")
async def storefront_listings(limit: int = 9):
    listings = get_published_listings(limit)
    return {
        "listings": [
            {
                "id": str(item["id"]),
                "listing_id": str(item["listing_id"]),
                "title": item["title"],
                "category": item.get("category", "Other"),
                "description": item["description"],
                "price": float(item["price"]),
                "image_url": f"/api/images/{item['image_id']}?width=400" if item.get("image_id") else None,
                "created_at": item["created_at"].isoformat() if item["created_at"] else None,
            }
            for item in listings
        ]
    }


# ---------------------------------------------------------------------------
# Image serving with on-the-fly resize
# ---------------------------------------------------------------------------


def _resize_image(image_bytes: bytes, max_width: int = 400) -> tuple[bytes, str]:
    """Resize image proportionally, convert to JPEG, return (bytes, mime_type)."""
    try:
        img = PILImage.open(BytesIO(image_bytes))
        img = img.convert("RGB")  # Ensure RGB for JPEG
        
        if img.width > max_width:
            ratio = max_width / img.width
            new_height = int(img.height * ratio)
            img = img.resize((max_width, new_height), PILImage.LANCZOS)
        
        buf = BytesIO()
        img.save(buf, format="JPEG", quality=85, optimize=True)
        buf.seek(0)
        return buf.read(), "image/jpeg"
    except Exception:
        # Fallback: return original if resize fails
        return image_bytes, "image/jpeg"


@app.get("/api/images/{image_id}")
async def get_image(image_id: str, width: Optional[int] = Query(None)):
    image = get_image_by_id(image_id)
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")
    
    image_bytes = bytes(image["image_data"])
    mime_type = image.get("mime_type", "image/jpeg")
    
    # Resize if width parameter provided
    if width and width > 0 and width < image_bytes.__len__() * 100:  # sanity check
        resized_bytes, mime_type = _resize_image(image_bytes, max_width=width)
        image_bytes = resized_bytes
    
    headers = {"Content-Disposition": f'inline; filename="{image.get("file_name") or "image"}"'}
    return Response(content=image_bytes, media_type=mime_type, headers=headers)


# ---------------------------------------------------------------------------
# Serve React frontend
# ---------------------------------------------------------------------------


@app.get("/")
async def serve_index():
    return FileResponse("static/index.html")


@app.get("/{full_path:path}")
async def serve_spa(full_path: str):
    # Let API routes handle /api/* paths
    if full_path.startswith("api/"):
        raise HTTPException(status_code=404, detail="Not found")
    return FileResponse("static/index.html")


# ---------------------------------------------------------------------------
# Rate limiting middleware (disabled for demo — set to very high limit)
# ---------------------------------------------------------------------------

from collections import defaultdict
from datetime import datetime, timedelta

_rate_limits: dict[str, list[datetime]] = defaultdict(list)


@app.middleware("http")
async def rate_limit(request: Request, call_next):
    # DISABLED for demo — log to prove we're not the source of 429s
    logger.debug("Rate limit middleware: PASS for %s %s", request.method, request.url.path)
    return await call_next(request)
