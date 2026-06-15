"""
Database layer for Watcher.

Uses psycopg2 with connection pooling. All queries are parameterized.
Schema is auto-created on startup via init_schema().
"""

import json
import logging
from contextlib import contextmanager
from typing import Any, List, Optional

import psycopg2
from psycopg2 import pool as psycopg2_pool
from psycopg2.extras import RealDictCursor

from config import DB_HOST, DB_NAME, DB_PASSWORD, DB_PORT, DB_USER

logger = logging.getLogger("watcher")

# ---------------------------------------------------------------------------
# Connection pool
# ---------------------------------------------------------------------------

_pool: Optional[Any] = None


def _get_pool():
    global _pool
    if _pool is None:
        _pool = psycopg2_pool.ThreadedConnectionPool(
            minconn=2,
            maxconn=10,
            host=DB_HOST,
            port=DB_PORT,
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
            options="-csearch_path=watcher",
        )
    return _pool


@contextmanager
def _get_conn():
    pool = _get_pool()
    conn = pool.getconn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)


# ---------------------------------------------------------------------------
# Schema initialization
# ---------------------------------------------------------------------------


def init_schema() -> None:
    """Create watcher schema and tables if they do not exist."""
    ddl = """
    CREATE SCHEMA IF NOT EXISTS watcher;

    CREATE TABLE IF NOT EXISTS watcher.users (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        username VARCHAR(50) UNIQUE NOT NULL,
        email VARCHAR(255) UNIQUE,
        password_hash VARCHAR(255) NOT NULL,
        is_admin BOOLEAN DEFAULT FALSE,
        is_banned BOOLEAN DEFAULT FALSE,
        previous_violation_count INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT NOW()
    );

    CREATE TABLE IF NOT EXISTS watcher.listings (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        listing_id VARCHAR(128) UNIQUE NOT NULL,
        user_id UUID REFERENCES watcher.users(id),
        title VARCHAR(255) NOT NULL,
        category VARCHAR(50) DEFAULT 'Other',
        description TEXT NOT NULL,
        price DECIMAL(10,2) NOT NULL,
        status VARCHAR(20) DEFAULT 'pending',
        is_published BOOLEAN DEFAULT FALSE,
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW()
    );

    CREATE TABLE IF NOT EXISTS watcher.listing_images (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        listing_id UUID REFERENCES watcher.listings(id) ON DELETE CASCADE,
        image_data BYTEA NOT NULL,
        mime_type VARCHAR(50) NOT NULL,
        file_name VARCHAR(255),
        created_at TIMESTAMP DEFAULT NOW()
    );

    CREATE TABLE IF NOT EXISTS watcher.listing_moderation (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        listing_id UUID REFERENCES watcher.listings(id) ON DELETE CASCADE,
        text_model VARCHAR,
        vision_model VARCHAR,
        text_decision VARCHAR(10),
        text_confidence DECIMAL(3,2),
        text_reasons JSONB,
        image_decision VARCHAR(10),
        image_confidence DECIMAL(3,2),
        image_caption TEXT,
        image_reasons JSONB,
        final_decision VARCHAR(10) NOT NULL,
        final_confidence DECIMAL(3,2),
        risk_score INTEGER,
        evidence JSONB,
        summary TEXT,
        flags JSONB,
        latency_seconds DECIMAL(8,3),
        created_at TIMESTAMP DEFAULT NOW(),
        processed_at TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS watcher.human_review_queue (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        listing_id UUID REFERENCES watcher.listings(id) ON DELETE CASCADE,
        status VARCHAR(20) DEFAULT 'pending',
        priority VARCHAR(10) DEFAULT 'normal',
        assigned_to VARCHAR,
        moderator_notes TEXT,
        ai_decision VARCHAR(10),
        ai_confidence DECIMAL(3,2),
        ai_reasons JSONB,
        created_at TIMESTAMP DEFAULT NOW(),
        reviewed_at TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS watcher.listing_publish_log (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        listing_id UUID REFERENCES watcher.listings(id) ON DELETE CASCADE,
        action VARCHAR(20) NOT NULL,
        source VARCHAR(20) NOT NULL,
        performed_by VARCHAR,
        notes TEXT,
        created_at TIMESTAMP DEFAULT NOW()
    );

    CREATE INDEX IF NOT EXISTS idx_users_username ON watcher.users(username);
    CREATE INDEX IF NOT EXISTS idx_listings_listing_id ON watcher.listings(listing_id);
    CREATE INDEX IF NOT EXISTS idx_listings_status ON watcher.listings(status);
    CREATE INDEX IF NOT EXISTS idx_listing_images_listing ON watcher.listing_images(listing_id);
    CREATE INDEX IF NOT EXISTS idx_moderation_listing ON watcher.listing_moderation(listing_id);
    CREATE INDEX IF NOT EXISTS idx_moderation_decision ON watcher.listing_moderation(final_decision, created_at DESC);
    CREATE INDEX IF NOT EXISTS idx_queue_status ON watcher.human_review_queue(status, created_at ASC);
    CREATE INDEX IF NOT EXISTS idx_queue_priority ON watcher.human_review_queue(priority DESC, created_at ASC);
    CREATE INDEX IF NOT EXISTS idx_publish_log_listing ON watcher.listing_publish_log(listing_id);
    """
    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(ddl)
            # Idempotent migration for existing installs
            cur.execute(
                "ALTER TABLE watcher.listing_moderation ADD COLUMN IF NOT EXISTS latency_seconds DECIMAL(8,3)"
            )
    logger.info("Database schema initialized.")


# ---------------------------------------------------------------------------
# CRUD helpers
# ---------------------------------------------------------------------------


def create_user(username: str, email: Optional[str], password_hash: str) -> str:
    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO watcher.users (username, email, password_hash)
                VALUES (%s, %s, %s)
                ON CONFLICT (username) DO NOTHING
                RETURNING id
                """,
                (username, email, password_hash),
            )
            result = cur.fetchone()
            if result is None:
                raise ValueError(f"Username '{username}' already exists")
            return str(result[0])


def get_user_by_username(username: str) -> Optional[dict]:
    with _get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT id, username, email, password_hash, is_admin, created_at FROM watcher.users WHERE username = %s",
                (username,),
            )
            return cur.fetchone()


def create_listing(listing_id: str, user_id: str, title: str, category: str, description: str, price: float) -> str:
    """Create a new listing with category. Returns UUID."""
    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO watcher.listings (listing_id, user_id, title, category, description, price)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (listing_id, user_id, title, category, description, price),
            )
            return str(cur.fetchone()[0])


def store_image(listing_id: str, image_data: bytes, mime_type: str, file_name: str) -> str:
    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO watcher.listing_images (listing_id, image_data, mime_type, file_name)
                VALUES (%s, %s, %s, %s)
                RETURNING id
                """,
                (listing_id, image_data, mime_type, file_name),
            )
            return str(cur.fetchone()[0])


def get_images_for_listing(listing_id: str) -> List[dict]:
    with _get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT id, image_data, mime_type, file_name, created_at FROM watcher.listing_images WHERE listing_id = %s",
                (listing_id,),
            )
            return cur.fetchall()


def store_moderation(
    listing_id: str,
    text_model: str,
    vision_model: str,
    text_result: dict,
    image_result: Optional[dict],
    final_result: dict,
    latency_seconds: Optional[float] = None,
) -> None:
    """Store moderation result with full evidence, risk score, flags, and measured latency."""
    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO watcher.listing_moderation
                    (listing_id, text_model, vision_model,
                     text_decision, text_confidence, text_reasons,
                     image_decision, image_confidence, image_caption, image_reasons,
                     final_decision, final_confidence, risk_score, evidence, summary, flags,
                     latency_seconds, processed_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                """,
                (
                    listing_id,
                    text_model,
                    vision_model,
                    text_result.get("decision"),
                    text_result.get("confidence"),
                    json.dumps(text_result.get("reasons", [])),
                    image_result.get("decision") if image_result else None,
                    image_result.get("confidence") if image_result else None,
                    image_result.get("image_summary") if image_result else None,
                    json.dumps(image_result.get("reasons", [])) if image_result else None,
                    final_result.get("decision"),
                    final_result.get("confidence"),
                    final_result.get("risk_score"),
                    json.dumps(final_result.get("evidence", [])),
                    final_result.get("summary"),
                    json.dumps(final_result.get("flags", [])),
                    round(latency_seconds, 3) if latency_seconds is not None else None,
                ),
            )


def enqueue_review(listing_id: str, final_result: dict) -> None:
    """Add listing to human review queue with priority based on risk."""
    risk_score = final_result.get("risk_score", 50)
    if risk_score >= 80:
        priority = "high"
    elif risk_score >= 50:
        priority = "normal"
    else:
        priority = "low"

    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO watcher.human_review_queue
                    (listing_id, status, priority, ai_decision, ai_confidence, ai_reasons)
                VALUES (%s, 'pending', %s, %s, %s, %s)
                ON CONFLICT DO NOTHING
                """,
                (
                    listing_id,
                    priority,
                    final_result.get("decision"),
                    final_result.get("confidence"),
                    json.dumps(final_result.get("reasons", [])),
                ),
            )


def get_review_queue(status: str = "pending", limit: int = 50) -> List[dict]:
    """Return review queue with listing details and submitter username."""
    with _get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT q.id, q.listing_id, l.title, l.category, l.description, l.price,
                       q.status, q.priority, q.ai_decision, q.ai_confidence, q.ai_reasons, q.created_at,
                       u.username as submitter,
                       (SELECT i.id FROM watcher.listing_images i WHERE i.listing_id = l.id LIMIT 1) AS image_id
                FROM watcher.human_review_queue q
                JOIN watcher.listings l ON l.id = q.listing_id
                JOIN watcher.users u ON u.id = l.user_id
                WHERE q.status = %s
                ORDER BY q.priority DESC, q.created_at ASC
                LIMIT %s
                """,
                (status, limit),
            )
            return cur.fetchall()


def review_item(listing_id: str, action: str, moderator: Optional[str], notes: Optional[str]) -> bool:
    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE watcher.human_review_queue
                SET status = %s, assigned_to = %s, moderator_notes = %s, reviewed_at = NOW()
                WHERE listing_id = %s AND status = 'pending'
                RETURNING id
                """,
                (action, moderator, notes, listing_id),
            )
            updated = cur.fetchone()
            if not updated:
                return False

            cur.execute(
                """
                UPDATE watcher.listings SET status = %s, updated_at = NOW() WHERE id = %s
                """,
                (action, listing_id),
            )

            cur.execute(
                """
                INSERT INTO watcher.listing_publish_log (listing_id, action, source, performed_by, notes)
                VALUES (%s, %s, 'human', %s, %s)
                """,
                (listing_id, action, moderator, notes),
            )
            return True


def get_stats() -> dict:
    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM watcher.listing_moderation")
            total = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM watcher.listing_moderation WHERE final_decision = 'APPROVE'")
            approved = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM watcher.listing_moderation WHERE final_decision = 'REJECT'")
            rejected = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM watcher.listing_moderation WHERE final_decision = 'REVIEW'")
            reviewed = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM watcher.human_review_queue WHERE status = 'pending'")
            queue_depth = cur.fetchone()[0]
            cur.execute(
                "SELECT AVG(latency_seconds) FROM watcher.listing_moderation WHERE latency_seconds IS NOT NULL"
            )
            avg_latency = cur.fetchone()[0]
            return {
                "total_moderated": total,
                "auto_approved": approved,
                "auto_rejected": rejected,
                "sent_to_review": reviewed,
                "queue_depth": queue_depth,
                "avg_latency_seconds": round(float(avg_latency or 0), 2),
            }


def seed_users() -> None:
    """Seed pre-defined user and admin accounts from Vault secrets (for demo, no registration)."""
    from pathlib import Path
    from auth import hash_password

    user_pass = ""
    admin_pass = ""
    user_path = Path("/run/secrets/watcher-user-password")
    admin_path = Path("/run/secrets/watcher-admin-password")
    if user_path.exists():
        user_pass = user_path.read_text().strip()
    if admin_path.exists():
        admin_pass = admin_path.read_text().strip()

    if not user_pass or not admin_pass:
        logger.warning("User/admin password secrets not found — skipping seed.")
        return

    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO watcher.users (username, email, password_hash, is_admin)
                VALUES ('user', 'user@test.com', %s, FALSE)
                ON CONFLICT (username) DO NOTHING
                """,
                (hash_password(user_pass),),
            )
            cur.execute(
                """
                INSERT INTO watcher.users (username, email, password_hash, is_admin)
                VALUES ('admin', 'admin@example.com', %s, TRUE)
                ON CONFLICT (username) DO NOTHING
                """,
                (hash_password(admin_pass),),
            )
    logger.info("User accounts seeded (user, admin).")


def get_published_listings(limit: int = 3) -> List[dict]:
    """Return published, approved listings for the storefront."""
    with _get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT l.id, l.listing_id, l.title, l.category, l.description, l.price, l.created_at,
                       (SELECT i.id FROM watcher.listing_images i WHERE i.listing_id = l.id LIMIT 1) AS image_id
                FROM watcher.listings l
                WHERE l.status = 'published' AND l.is_published = TRUE
                ORDER BY l.created_at DESC
                LIMIT %s
                """,
                (limit,),
            )
            return cur.fetchall()


def get_image_by_id(image_id: str) -> Optional[dict]:
    """Fetch a single image by ID for storefront display."""
    with _get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT id, image_data, mime_type, file_name FROM watcher.listing_images WHERE id = %s",
                (image_id,),
            )
            return cur.fetchone()


def publish_listing(listing_id: str, moderator: Optional[str], notes: Optional[str]) -> bool:
    """Moderator publishes a listing: set status=published, is_published=TRUE."""
    return review_item(listing_id, 'published', moderator, notes)


def ban_listing(listing_id: str, moderator: Optional[str], notes: Optional[str]) -> bool:
    """Moderator bans a listing: set status=rejected, is_published=FALSE."""
    return review_item(listing_id, 'rejected', moderator, notes)


def auto_publish_listing(listing_id: str, notes: Optional[str] = None) -> bool:
    """Auto-publish a listing that was approved by AI moderation.

    Does NOT require the listing to be in the human review queue.
    Directly updates the listings table and logs the action.
    """
    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE watcher.listings SET status = 'published', is_published = TRUE, updated_at = NOW()
                WHERE id = %s
                RETURNING id
                """,
                (listing_id,),
            )
            updated = cur.fetchone()
            if not updated:
                return False

            cur.execute(
                """
                INSERT INTO watcher.listing_publish_log (listing_id, action, source, performed_by, notes)
                VALUES (%s, 'published', 'auto', 'system', %s)
                """,
                (listing_id, notes),
            )
            return True


def auto_reject_listing(listing_id: str, notes: Optional[str] = None) -> bool:
    """Auto-reject a listing that was confidently flagged by AI moderation.

    Marks the listing as rejected and increments the seller's violation count.
    No human review required — the LLM was confident enough.
    """
    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE watcher.listings SET status = 'rejected', is_published = FALSE, updated_at = NOW()
                WHERE id = %s
                RETURNING id, user_id
                """,
                (listing_id,),
            )
            updated = cur.fetchone()
            if not updated:
                return False

            # Increment violation count for the seller
            cur.execute(
                "UPDATE watcher.users SET previous_violation_count = previous_violation_count + 1 WHERE id = %s",
                (updated[1],),
            )

            cur.execute(
                """
                INSERT INTO watcher.listing_publish_log (listing_id, action, source, performed_by, notes)
                VALUES (%s, 'rejected', 'auto', 'system', %s)
                """,
                (listing_id, notes),
            )
            return True


def ban_user(username: str) -> bool:
    """Ban a user by username and increment their violation count."""
    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE watcher.users
                SET is_banned = TRUE, previous_violation_count = previous_violation_count + 1
                WHERE username = %s
                RETURNING id
                """,
                (username,),
            )
            return cur.fetchone() is not None


def increment_violation_count(username: str) -> bool:
    """Increment a user's violation count (used when listing is rejected)."""
    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE watcher.users
                SET previous_violation_count = previous_violation_count + 1
                WHERE username = %s
                RETURNING id
                """,
                (username,),
            )
            return cur.fetchone() is not None


def get_seller_stats(user_id: str) -> dict:
    """Return seller statistics for moderation context.

    Returns dict with:
    - account_age_days: int
    - previous_listing_count: int
    - previous_violation_count: int
    """
    with _get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT
                    u.created_at,
                    u.previous_violation_count,
                    COUNT(l.id) AS previous_listing_count
                FROM watcher.users u
                LEFT JOIN watcher.listings l ON l.user_id = u.id
                WHERE u.id = %s
                GROUP BY u.id, u.created_at, u.previous_violation_count
                """,
                (user_id,),
            )
            row = cur.fetchone()
            if not row:
                return {
                    "account_age_days": 0,
                    "previous_listing_count": 0,
                    "previous_violation_count": 0,
                }
            from datetime import datetime, timezone
            created = row["created_at"]
            if created:
                if created.tzinfo is None:
                    created = created.replace(tzinfo=timezone.utc)
                age = datetime.now(timezone.utc) - created
                age_days = max(0, age.days)
            else:
                age_days = 0
            return {
                "account_age_days": age_days,
                "previous_listing_count": row.get("previous_listing_count", 0),
                "previous_violation_count": row.get("previous_violation_count", 0),
            }


def get_user_listings(username: str) -> List[dict]:
    """Return all listings for a user with moderation status."""
    with _get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT l.id, l.listing_id, l.title, l.category, l.description, l.price, l.status, l.is_published,
                       l.created_at, l.updated_at,
                       (SELECT i.id FROM watcher.listing_images i WHERE i.listing_id = l.id LIMIT 1) AS image_id,
                       m.final_decision, m.final_confidence, m.text_reasons, m.image_reasons
                FROM watcher.listings l
                LEFT JOIN watcher.listing_moderation m ON m.listing_id = l.id
                WHERE l.user_id = (SELECT id FROM watcher.users WHERE username = %s)
                ORDER BY l.created_at DESC
                """,
                (username,),
            )
            return cur.fetchall()


def update_listing(listing_id: str, title: str, category: str, description: str, price: float) -> bool:
    """Update a listing's content and reset status for resubmission."""
    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE watcher.listings
                SET title = %s, category = %s, description = %s, price = %s, status = 'pending', is_published = FALSE, updated_at = NOW()
                WHERE id = %s
                RETURNING id
                """,
                (title, category, description, price, listing_id),
            )
            return cur.fetchone() is not None


def is_user_banned(username: str) -> bool:
    """Check if a user is banned."""
    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT is_banned FROM watcher.users WHERE username = %s",
                (username,),
            )
            row = cur.fetchone()
            return bool(row[0]) if row else False


def delete_listing(listing_id: str, username: str, is_admin: bool = False) -> bool:
    """Delete a listing and all related data (images, moderation, queue, logs).

    Security:
    - Users can only delete their own listings.
    - Admins can delete any listing.
    Returns True if deleted, False if not found or not authorized.
    """
    with _get_conn() as conn:
        with conn.cursor() as cur:
            # Verify ownership unless admin
            if not is_admin:
                cur.execute(
                    """
                    SELECT id FROM watcher.listings
                    WHERE id = %s AND user_id = (SELECT id FROM watcher.users WHERE username = %s)
                    """,
                    (listing_id, username),
                )
                if not cur.fetchone():
                    return False

            # Cascade delete handled by FK constraints, but be explicit for clarity
            cur.execute("DELETE FROM watcher.listing_images WHERE listing_id = %s", (listing_id,))
            cur.execute("DELETE FROM watcher.listing_moderation WHERE listing_id = %s", (listing_id,))
            cur.execute("DELETE FROM watcher.human_review_queue WHERE listing_id = %s", (listing_id,))
            cur.execute("DELETE FROM watcher.listing_publish_log WHERE listing_id = %s", (listing_id,))
            cur.execute(
                "DELETE FROM watcher.listings WHERE id = %s RETURNING id",
                (listing_id,),
            )
            return cur.fetchone() is not None
