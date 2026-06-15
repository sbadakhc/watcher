"""
Watcher Moderation Service — FastAPI application.

Serves both the API and the vanilla JS frontend (static/index.html).
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
    AUTO_APPROVE_CONFIDENCE,
    AUTO_APPROVE_RISK_MAX,
    AUTO_REJECT_CONFIDENCE,
    LOG_LEVEL,
    OLLAMA_URL,
    PORT,
    TEXT_MODEL,
    VISION_MODEL,
    WEBHOOK_URL,
    validate,
)
from db import (
    create_listing,
    create_user_account,
    delete_user_account,
    enqueue_review,
    get_all_listings,
    get_all_sellers,
    get_audit_log,
    get_db_health,
    get_image_by_id,
    get_insights,
    get_published_listings,
    get_review_queue,
    get_stats,
    get_user_by_username,
    init_schema,
    replace_listing_images,
    review_item,
    rollback_listing,
    seed_users,
    store_image,
    store_moderation,
    unban_user,
    update_user_password,
)
from moderation import run_moderation

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
    buckets=[30, 60, 90, 120, 180, 240, 300, 360, 420, 480, 600],
)
MODEL_ERRORS = Counter("watcher_model_errors_total", "Total model errors", ["stage"])

# Pre-initialise label combinations so series appear at 0 before first event.
for _d in ("auto_approve", "auto_reject", "human_review"):
    DECISIONS_TOTAL.labels(decision=_d)
for _s in ("text", "vision"):
    MODEL_ERRORS.labels(stage=_s)

# DB-backed summary gauges -- survive process restarts by reading from DB.
TOTAL_MODERATED = Gauge("watcher_total_moderated", "Total listings moderated (DB-backed)")
TOTAL_PUBLISHED = Gauge("watcher_total_published", "Total listings auto-approved and published (DB-backed)")
TOTAL_REJECTED = Gauge("watcher_total_rejected", "Total listings auto-rejected (DB-backed)")
TOTAL_IN_REVIEW = Gauge("watcher_total_sent_to_review", "Total listings sent to human review (DB-backed)")
AVG_LATENCY_DB = Gauge("watcher_avg_latency_seconds_db", "Average moderation latency in seconds (DB-backed)")
AUTO_RESOLVE_RATE = Gauge("watcher_auto_resolve_rate", "Percentage of listings auto-resolved without human review (DB-backed)")


def _sync_db_stats() -> None:
    """Refresh DB-backed Prometheus gauges from persistent storage."""
    try:
        s = get_stats()
        TOTAL_MODERATED.set(s["total_moderated"])
        TOTAL_PUBLISHED.set(s["auto_approved"])
        TOTAL_REJECTED.set(s["auto_rejected"])
        TOTAL_IN_REVIEW.set(s["sent_to_review"])
        QUEUE_DEPTH.set(s["queue_depth"])
        if s["avg_latency_seconds"] is not None:
            AVG_LATENCY_DB.set(s["avg_latency_seconds"])
        if s["total_moderated"] > 0:
            AUTO_RESOLVE_RATE.set(
                round((s["auto_approved"] + s["auto_rejected"]) / s["total_moderated"] * 100, 1)
            )
    except Exception as exc:
        logger.warning("Failed to sync DB stats to Prometheus: %s", exc)


# ---------------------------------------------------------------------------
# Runtime-mutable thresholds (update via PUT /api/config/thresholds)
# ---------------------------------------------------------------------------

_runtime_thresholds: dict = {
    "auto_approve_confidence": AUTO_APPROVE_CONFIDENCE,
    "auto_approve_risk_max": AUTO_APPROVE_RISK_MAX,
    "auto_reject_confidence": AUTO_REJECT_CONFIDENCE,
}

_webhook_status: dict = {
    "configured": bool(WEBHOOK_URL),
    "last_sent_at": None,
    "last_status": "never",
    "last_error": None,
}


def _apply_runtime_thresholds(result: dict) -> tuple:
    """Apply current runtime thresholds to a moderation result."""
    if result.get("requires_human_review"):
        return "REVIEW", "human_review"
    conf = float(result.get("confidence") or 0)
    risk = int(result.get("risk_score") or 100)
    if conf >= _runtime_thresholds["auto_approve_confidence"] and risk <= _runtime_thresholds["auto_approve_risk_max"]:
        return "APPROVE", "published"
    if conf >= _runtime_thresholds["auto_reject_confidence"]:
        return "REJECT", "auto_rejected"
    return "REVIEW", "human_review"


def _fire_webhook(payload: dict) -> None:
    """POST a JSON payload to WEBHOOK_URL if configured (called from background thread)."""
    if not WEBHOOK_URL:
        return
    import json as _json
    import urllib.request
    from datetime import datetime, timezone
    try:
        body = _json.dumps(payload).encode()
        req = urllib.request.Request(
            WEBHOOK_URL, data=body,
            headers={"Content-Type": "application/json"}, method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            logger.debug("Webhook delivered: HTTP %s", resp.status)
        _webhook_status["last_sent_at"] = datetime.now(timezone.utc).isoformat()
        _webhook_status["last_status"] = "ok"
        _webhook_status["last_error"] = None
    except Exception as exc:
        logger.warning("Webhook delivery failed (%s): %s", WEBHOOK_URL, exc)
        _webhook_status["last_status"] = "error"
        _webhook_status["last_error"] = str(exc)


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
        _sync_db_stats()
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
    from moderation import run_moderation

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

    # Store moderation with full evidence and measured latency
    store_moderation(
        listing_uuid,
        TEXT_MODEL,
        VISION_MODEL,
        {"decision": result.get("decision"), "confidence": result.get("confidence"), "reasons": result.get("reasons", [])},
        {"decision": result.get("decision"), "confidence": result.get("confidence"), "reasons": result.get("reasons", []), "image_summary": result.get("image_summary")} if result.get("image_summary") else None,
        result,
        latency_seconds=latency,
    )

    # Apply threshold and route accordingly
    decision, next_step = _apply_runtime_thresholds(result)
    if next_step == "published":
        DECISIONS_TOTAL.labels(decision="auto_approve").inc()
        try:
            from db import auto_publish_listing
            auto_publish_listing(listing_uuid, f"Auto-approved: {result.get('summary', 'AI approved')}")
        except Exception:
            logger.error("Auto-publish failed for listing %s", listing_uuid)
    elif next_step == "auto_rejected":
        DECISIONS_TOTAL.labels(decision="auto_reject").inc()
        try:
            from db import auto_reject_listing
            auto_reject_listing(listing_uuid, f"Auto-rejected: {result.get('summary', 'AI rejected')}")
        except Exception:
            logger.error("Auto-reject failed for listing %s", listing_uuid)
    else:
        DECISIONS_TOTAL.labels(decision="human_review").inc()
        enqueue_review(listing_uuid, result)

    _sync_db_stats()
    _fire_webhook({
        "listing_id": listing_uuid,
        "decision": decision,
        "next_step": next_step,
        "confidence": result.get("confidence"),
        "risk_score": result.get("risk_score"),
        "reasons": result.get("reasons", []),
        "latency_seconds": round(latency, 2),
    })


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
    background_tasks: BackgroundTasks,
    user_id: str = Form(...),
    title: str = Form(...),
    category: str = Form("Other"),
    description: str = Form(...),
    price: float = Form(...),
):
    """Edit and resubmit a rejected listing. Re-runs full moderation pipeline."""
    from db import get_user_by_username, update_listing, is_user_banned, get_images_for_listing

    user = get_user_by_username(user_id)
    if user is None:
        raise HTTPException(status_code=400, detail="User not found")

    if user.get("is_banned"):
        raise HTTPException(status_code=403, detail="Account suspended")

    success = update_listing(listing_id, title, category, description, price)
    if not success:
        raise HTTPException(status_code=404, detail="Listing not found")

    # Re-run moderation with existing images; text changes take effect immediately
    images_data = get_images_for_listing(listing_id)
    image_ids = [str(img["id"]) for img in images_data]
    background_tasks.add_task(_run_moderation, listing_id, title, category, description, str(user["id"]), image_ids)

    return {
        "listing_id": listing_id,
        "message": "Listing updated and resubmitted for moderation",
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
        "auto_approve_confidence": AUTO_APPROVE_CONFIDENCE,
        "auto_approve_risk_max": AUTO_APPROVE_RISK_MAX,
        "auto_reject_confidence": AUTO_REJECT_CONFIDENCE,
    }


# ---------------------------------------------------------------------------
# Sellers management (admin only)
# ---------------------------------------------------------------------------


@app.get("/api/sellers")
async def list_sellers(moderator: str = Query(...)):
    mod = get_user_by_username(moderator)
    if not mod or not mod.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")

    sellers = get_all_sellers()
    return {
        "sellers": [
            {
                "id": str(s["id"]),
                "username": s["username"],
                "is_banned": bool(s["is_banned"]),
                "violation_count": int(s["previous_violation_count"]),
                "published_count": int(s["published_count"] or 0),
                "rejected_count": int(s["rejected_count"] or 0),
                "pending_count": int(s["pending_count"] or 0),
                "total_listings": int(s["total_listings"] or 0),
                "created_at": s["created_at"].isoformat() if s["created_at"] else None,
            }
            for s in sellers
        ]
    }


@app.post("/api/unban-user/{username}")
async def unban_user_endpoint(username: str, moderator: str = Form(...)):
    """Lift a ban from a user account (admin only)."""
    mod = get_user_by_username(moderator)
    if not mod or not mod.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")

    success = unban_user(username)
    if not success:
        raise HTTPException(status_code=404, detail="User not found")

    return {"username": username, "action": "unbanned", "status": "completed"}


# ---------------------------------------------------------------------------
# Audit log (admin only)
# ---------------------------------------------------------------------------


@app.get("/api/audit")
async def audit_log(moderator: str = Query(...), limit: int = Query(100)):
    mod = get_user_by_username(moderator)
    if not mod or not mod.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")

    entries = get_audit_log(min(limit, 500))
    return {
        "entries": [
            {
                "id": str(e["id"]),
                "listing_id": str(e["listing_id"]),
                "title": e.get("title") or "(deleted)",
                "category": e.get("category") or "",
                "seller": e.get("seller") or "unknown",
                "action": e["action"],
                "source": e["source"],
                "performed_by": e.get("performed_by") or "system",
                "notes": e.get("notes") or "",
                "created_at": e["created_at"].isoformat() if e["created_at"] else None,
            }
            for e in entries
        ]
    }


# ---------------------------------------------------------------------------
# Rollback a decision (admin only)
# ---------------------------------------------------------------------------


@app.post("/api/listings/{listing_id}/rollback")
async def rollback_listing_endpoint(
    listing_id: str,
    moderator: str = Form(...),
    notes: Optional[str] = Form(None),
):
    """Send any listing back to the review queue for re-evaluation."""
    mod = get_user_by_username(moderator)
    if not mod or not mod.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")

    success = rollback_listing(listing_id, moderator, notes or "")
    if not success:
        raise HTTPException(status_code=404, detail="Listing not found")

    _sync_db_stats()
    return {"listing_id": listing_id, "action": "rollback", "status": "pending_review"}


# ---------------------------------------------------------------------------
# Threshold configuration
# ---------------------------------------------------------------------------


@app.get("/api/config/thresholds")
async def get_thresholds():
    return {
        "auto_approve_confidence": _runtime_thresholds["auto_approve_confidence"],
        "auto_approve_risk_max": _runtime_thresholds["auto_approve_risk_max"],
        "auto_reject_confidence": _runtime_thresholds["auto_reject_confidence"],
        "defaults": {
            "auto_approve_confidence": AUTO_APPROVE_CONFIDENCE,
            "auto_approve_risk_max": AUTO_APPROVE_RISK_MAX,
            "auto_reject_confidence": AUTO_REJECT_CONFIDENCE,
        },
    }


@app.put("/api/config/thresholds")
async def update_thresholds(
    moderator: str = Form(...),
    auto_approve_confidence: Optional[float] = Form(None),
    auto_approve_risk_max: Optional[int] = Form(None),
    auto_reject_confidence: Optional[float] = Form(None),
):
    """Update runtime moderation thresholds (admin only, in-memory)."""
    mod = get_user_by_username(moderator)
    if not mod or not mod.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")

    if auto_approve_confidence is not None:
        if not 0 < auto_approve_confidence <= 1:
            raise HTTPException(status_code=400, detail="auto_approve_confidence must be 0-1")
        _runtime_thresholds["auto_approve_confidence"] = auto_approve_confidence

    if auto_approve_risk_max is not None:
        if not 0 <= auto_approve_risk_max <= 100:
            raise HTTPException(status_code=400, detail="auto_approve_risk_max must be 0-100")
        _runtime_thresholds["auto_approve_risk_max"] = auto_approve_risk_max

    if auto_reject_confidence is not None:
        if not 0 < auto_reject_confidence <= 1:
            raise HTTPException(status_code=400, detail="auto_reject_confidence must be 0-1")
        _runtime_thresholds["auto_reject_confidence"] = auto_reject_confidence

    return {"status": "updated", "thresholds": _runtime_thresholds}


# ---------------------------------------------------------------------------
# Model health check
# ---------------------------------------------------------------------------


def _check_ollama_models():
    """Check Ollama availability and return status dict."""
    import json as _json
    import urllib.request
    try:
        req = urllib.request.Request(f"{OLLAMA_URL}/api/tags")
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = _json.loads(resp.read())
        available = {m["name"] for m in data.get("models", [])}
        return {
            "status": "ok" if (TEXT_MODEL in available and VISION_MODEL in available) else "degraded",
            "ollama_url": OLLAMA_URL,
            "text_model": {"name": TEXT_MODEL, "available": TEXT_MODEL in available},
            "vision_model": {"name": VISION_MODEL, "available": VISION_MODEL in available},
        }
    except Exception as exc:
        return {
            "status": "error", "ollama_url": OLLAMA_URL, "error": str(exc),
            "text_model": {"name": TEXT_MODEL, "available": False},
            "vision_model": {"name": VISION_MODEL, "available": False},
        }


@app.get("/api/health/models")
async def model_health():
    """Check that configured Ollama models are available."""
    import json as _json
    import urllib.request

    result = _check_ollama_models()
    try:
        req = urllib.request.Request(f"{OLLAMA_URL}/api/tags")
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = _json.loads(resp.read())
        available = {m["name"] for m in data.get("models", [])}
        result["available_models"] = sorted(available)
    except Exception:
        result["available_models"] = []
    return result


# ---------------------------------------------------------------------------
# Admin: All Listings
# ---------------------------------------------------------------------------


@app.get("/api/all-listings")
async def all_listings_endpoint(
    moderator: str = Query(...),
    status: Optional[str] = Query(None),
    seller: Optional[str] = Query(None),
    limit: int = Query(200),
):
    """All listings across all sellers (admin view)."""
    mod = get_user_by_username(moderator)
    if not mod or not mod.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")

    listings = get_all_listings(status=status or None, seller=seller or None, limit=min(limit, 500))
    return {
        "listings": [
            {
                "id": str(item["id"]),
                "listing_id": str(item["listing_id"]),
                "title": item["title"],
                "category": item.get("category", "Other"),
                "description": (item["description"] or "")[:300],
                "price": float(item["price"]),
                "status": item["status"],
                "is_published": bool(item["is_published"]),
                "seller": item.get("seller", "unknown"),
                "seller_banned": bool(item.get("seller_banned", False)),
                "final_decision": item.get("final_decision"),
                "final_confidence": float(item["final_confidence"]) if item.get("final_confidence") else None,
                "risk_score": item.get("risk_score"),
                "image_url": f"/api/images/{item['image_id']}?width=100" if item.get("image_id") else None,
                "created_at": item["created_at"].isoformat() if item["created_at"] else None,
                "updated_at": item["updated_at"].isoformat() if item["updated_at"] else None,
            }
            for item in listings
        ]
    }


# ---------------------------------------------------------------------------
# Admin: Insights
# ---------------------------------------------------------------------------


@app.get("/api/insights")
async def insights_endpoint(moderator: str = Query(...)):
    """Analytics for the admin insights panel."""
    mod = get_user_by_username(moderator)
    if not mod or not mod.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")
    return get_insights()


# ---------------------------------------------------------------------------
# Admin: System health
# ---------------------------------------------------------------------------


@app.get("/api/health/system")
async def system_health(moderator: str = Query(...)):
    """Full system health (admin only)."""
    mod = get_user_by_username(moderator)
    if not mod or not mod.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")

    models = _check_ollama_models()
    db = get_db_health()
    return {
        "service": {"version": "0.3.0", "port": PORT},
        "models": models,
        "database": db,
        "webhook": {**_webhook_status, "url_configured": bool(WEBHOOK_URL)},
        "thresholds": _runtime_thresholds,
    }


# ---------------------------------------------------------------------------
# Admin: User management
# ---------------------------------------------------------------------------


@app.post("/api/users")
async def create_user_endpoint(
    moderator: str = Form(...),
    username: str = Form(...),
    password: str = Form(...),
    is_admin: bool = Form(False),
):
    mod = get_user_by_username(moderator)
    if not mod or not mod.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")

    from auth import hash_password
    success = create_user_account(username, hash_password(password), is_admin)
    if not success:
        raise HTTPException(status_code=409, detail="Username already exists")
    return {"username": username, "is_admin": is_admin, "status": "created"}


@app.delete("/api/users/{username}")
async def delete_user_endpoint(username: str, moderator: str = Form(...)):
    mod = get_user_by_username(moderator)
    if not mod or not mod.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")

    if username == moderator:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")

    success = delete_user_account(username)
    if not success:
        raise HTTPException(status_code=404, detail="User not found or is an admin account")
    return {"username": username, "status": "deleted"}


@app.put("/api/users/{username}/password")
async def reset_password_endpoint(
    username: str,
    moderator: str = Form(...),
    password: str = Form(...),
):
    mod = get_user_by_username(moderator)
    if not mod or not mod.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")

    from auth import hash_password
    success = update_user_password(username, hash_password(password))
    if not success:
        raise HTTPException(status_code=404, detail="User not found")
    return {"username": username, "status": "password_updated"}


# ---------------------------------------------------------------------------
# Admin: Edit listing
# ---------------------------------------------------------------------------


@app.patch("/api/listings/{listing_id}/admin")
async def admin_edit_listing(
    listing_id: str,
    background_tasks: BackgroundTasks,
    moderator: str = Form(...),
    title: Optional[str] = Form(None),
    category: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    price: Optional[float] = Form(None),
    direct_publish: bool = Form(False),
    images: Optional[list[UploadFile]] = File(None),
):
    """Admin edit: update fields, optionally replace images, optionally publish directly."""
    from db import _get_conn, get_images_for_listing, auto_publish_listing

    mod = get_user_by_username(moderator)
    if not mod or not mod.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")

    # Fetch current listing
    with _get_conn() as conn:
        with conn.cursor() as cur:
            from psycopg2.extras import RealDictCursor as _RDC
            cur = conn.cursor(cursor_factory=_RDC)
            cur.execute(
                """
                SELECT l.id, l.title, l.category, l.description, l.price, l.status,
                       l.user_id, u.username
                FROM watcher.listings l
                JOIN watcher.users u ON u.id = l.user_id
                WHERE l.id = %s
                """,
                (listing_id,),
            )
            current = cur.fetchone()

    if not current:
        raise HTTPException(status_code=404, detail="Listing not found")

    new_title = title if title is not None else current["title"]
    new_category = category if category is not None else current["category"]
    new_description = description if description is not None else current["description"]
    new_price = price if price is not None else float(current["price"])

    text_changed = (
        title is not None or category is not None or description is not None or price is not None
    )

    # Update text fields if any changed
    if text_changed:
        with _get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE watcher.listings
                    SET title = %s, category = %s, description = %s, price = %s, updated_at = NOW()
                    WHERE id = %s
                    """,
                    (new_title, new_category, new_description, new_price, listing_id),
                )

    images_changed = False
    if images:
        validated_images = []
        for img in images:
            img_bytes = await img.read()
            if len(img_bytes) > 5 * 1024 * 1024:
                raise HTTPException(status_code=413, detail=f"Image {img.filename} too large (max 5MB)")
            mime = img.content_type or "application/octet-stream"
            fname = (img.filename or "uploaded").lower()
            if not (mime in {"image/jpeg", "image/png"} or fname.endswith((".jpg", ".jpeg", ".png"))):
                raise HTTPException(status_code=415, detail="Only JPG, JPEG, and PNG images are allowed")
            validated_images.append({"data": img_bytes, "mime_type": mime, "file_name": img.filename or "uploaded"})
        replace_listing_images(listing_id, validated_images)
        images_changed = True

    if direct_publish:
        # Remove from review queue if present
        with _get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM watcher.human_review_queue WHERE listing_id = %s", (listing_id,))
        auto_publish_listing(listing_id, f"Admin direct publish by {moderator}")
        _sync_db_stats()
        return {"listing_id": listing_id, "status": "published"}

    if text_changed or images_changed:
        # Reset to pending and re-run moderation
        with _get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE watcher.listings SET status = 'pending', is_published = FALSE, updated_at = NOW() WHERE id = %s",
                    (listing_id,),
                )
        images_data = get_images_for_listing(listing_id)
        image_ids = [str(img["id"]) for img in images_data]
        background_tasks.add_task(
            _run_moderation, listing_id, new_title, new_category, new_description,
            str(current["user_id"]), image_ids,
        )
        return {"listing_id": listing_id, "status": "pending_review"}

    return {"listing_id": listing_id, "status": "no_changes"}


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
    
    # Resize if a valid width is requested (cap at 2048px)
    if width and 0 < width <= 2048:
        resized_bytes, mime_type = _resize_image(image_bytes, max_width=width)
        image_bytes = resized_bytes
    
    headers = {"Content-Disposition": f'inline; filename="{image.get("file_name") or "image"}"'}
    return Response(content=image_bytes, media_type=mime_type, headers=headers)


# ---------------------------------------------------------------------------
# Serve vanilla JS frontend
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
