"""Mint a demo JWT for the gateway. Usage: python infra/mint_token.py [subject] [days]

Paste the output into NEXT_PUBLIC_DEMO_JWT (frontend) or the Authorization header.
"""
import os
import sys
import time

from jose import jwt

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

secret = os.environ.get("JWT_SECRET", "change-me")
subject = sys.argv[1] if len(sys.argv) > 1 else "ops-console"
days = int(sys.argv[2]) if len(sys.argv) > 2 else 30
now = int(time.time())
print(jwt.encode({"sub": subject, "iat": now, "exp": now + days * 86400}, secret, algorithm="HS256"))
