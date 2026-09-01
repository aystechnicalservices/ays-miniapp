"""Verify Telegram Mini App initData so the backend can trust the caller.

See https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
"""

import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl

from . import config

MAX_AGE_SECONDS = 24 * 60 * 60  # a shared day-checklist stays open a full day


def verify_init_data(init_data: str):
    """Return the parsed user dict if init_data is authentic and fresh, else None."""
    if not init_data:
        return None

    pairs = parse_qsl(init_data, strict_parsing=True)
    data = dict(pairs)
    received_hash = data.pop("hash", None)
    if not received_hash:
        return None

    check_string = "\n".join(f"{k}={v}" for k, v in sorted(data.items()))

    secret_key = hmac.new(b"WebAppData", config.BOT_TOKEN.encode(), hashlib.sha256).digest()
    computed_hash = hmac.new(secret_key, check_string.encode(), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(computed_hash, received_hash):
        return None

    auth_date = int(data.get("auth_date", "0"))
    if time.time() - auth_date > MAX_AGE_SECONDS:
        return None

    user_raw = data.get("user")
    if not user_raw:
        return None
    return json.loads(user_raw)
