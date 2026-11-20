"""Environment configuration. Reads the root .env when python-dotenv is present
(it ships with uvicorn[standard]); real environment variables always win."""
import os
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # pragma: no cover
    pass


def normalize_db_url(url: str) -> str:
    """Accept Neon/Supabase style URLs and return a SQLAlchemy asyncpg URL.

    - postgres:// and postgresql:// become postgresql+asyncpg://
    - sslmode=require becomes ssl=require (asyncpg's spelling)
    - channel_binding is dropped (asyncpg does not accept it)
    """
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            url = "postgresql+asyncpg://" + url[len(prefix):]
            break
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query))
    sslmode = query.pop("sslmode", None)
    if sslmode in ("require", "verify-ca", "verify-full"):
        query["ssl"] = "require"
    query.pop("channel_binding", None)
    return urlunsplit(parts._replace(query=urlencode(query)))


DATABASE_URL = normalize_db_url(
    os.environ.get(
        "DATABASE_URL",
        "postgresql+asyncpg://sentinel:sentinel@localhost:5432/sentinelpay",
    )
)
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
JWT_SECRET = os.environ.get("JWT_SECRET", "change-me")
LLM_API_KEY = os.environ.get("LLM_API_KEY", "")
LEDGER_URL = os.environ.get("LEDGER_URL", "http://localhost:8002")
ALLOWED_ORIGINS = [
    o.strip()
    for o in os.environ.get("ALLOWED_ORIGINS", "http://localhost:3000").split(",")
    if o.strip()
]

# Blueprint Workflow A step 5: transfers of $500+ are FLAGGED.
FLAG_THRESHOLD_CENTS = 50_000
