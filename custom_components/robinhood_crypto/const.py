"""Constants for the Robinhood Crypto integration."""

from __future__ import annotations

DOMAIN = "robinhood_crypto"

CONF_API_KEY = "api_key"
CONF_PRIVATE_KEY = "private_key"
CONF_SYMBOLS = "symbols"
CONF_POLL_INTERVAL = "poll_interval"
CONF_PRICE_POLL_INTERVAL = "price_poll_interval"
CONF_ENTRY_ID = "entry_id"

DEFAULT_POLL_INTERVAL = 60
DEFAULT_PRICE_POLL_INTERVAL = 30

PLATFORMS = ["sensor"]
