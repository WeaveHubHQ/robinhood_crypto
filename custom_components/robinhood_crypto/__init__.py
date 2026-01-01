"""Home Assistant integration for Robinhood Crypto."""

from __future__ import annotations

import asyncio
import logging
import uuid

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryNotReady, HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.service import async_register_admin_service

from .client import RobinhoodCryptoClient
from .const import (
    CONF_API_KEY,
    CONF_POLL_INTERVAL,
    CONF_PRICE_POLL_INTERVAL,
    CONF_PRIVATE_KEY,
    CONF_SYMBOLS,
    DEFAULT_POLL_INTERVAL,
    DEFAULT_PRICE_POLL_INTERVAL,
    DOMAIN,
    PLATFORMS,
    CONF_ENTRY_ID,
)
from .coordinator import RobinhoodRuntimeData, create_coordinators

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the integration via YAML (not supported)."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Robinhood Crypto from a config entry."""
    session = async_get_clientsession(hass)
    client = RobinhoodCryptoClient(
        session, entry.data[CONF_API_KEY], entry.data[CONF_PRIVATE_KEY]
    )

    symbols = entry.options.get(CONF_SYMBOLS) or None
    account_interval = entry.options.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL)
    price_interval = entry.options.get(
        CONF_PRICE_POLL_INTERVAL, DEFAULT_PRICE_POLL_INTERVAL
    )

    runtime = create_coordinators(
        hass,
        client,
        symbols=symbols,
        account_interval=account_interval,
        price_interval=price_interval,
    )

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = runtime

    try:
        await asyncio.gather(
            runtime.account.async_config_entry_first_refresh(),
            runtime.holdings.async_config_entry_first_refresh(),
            runtime.market.async_config_entry_first_refresh(),
        )
    except Exception as err:
        raise ConfigEntryNotReady(f"Failed to connect: {err}") from err

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await _async_register_services(hass)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
        if not hass.data.get(DOMAIN):
            hass.services.async_remove(DOMAIN, "place_order")
            hass.services.async_remove(DOMAIN, "cancel_order")
    return unload_ok


async def _async_register_services(hass: HomeAssistant) -> None:
    """Register admin services for trading actions."""
    if hass.services.has_service(DOMAIN, "place_order"):
        return

    place_schema = vol.Schema(
        {
            vol.Optional(CONF_ENTRY_ID): cv.string,
            vol.Required("symbol"): cv.string,
            vol.Required("side"): vol.In(["buy", "sell"]),
            vol.Required("order_type"): vol.In(
                ["market", "limit", "stop_limit", "stop_loss"]
            ),
            vol.Optional("client_order_id"): cv.string,
            vol.Optional("asset_quantity"): vol.Any(cv.positive_float, cv.string),
            vol.Optional("quote_amount"): vol.Any(cv.positive_float, cv.string),
            vol.Optional("limit_price"): vol.Any(cv.positive_float, cv.string),
            vol.Optional("stop_price"): vol.Any(cv.positive_float, cv.string),
            vol.Optional("time_in_force", default="gtc"): vol.In(
                ["gtc", "gfd", "gfw", "gfm"]
            ),
        }
    )

    cancel_schema = vol.Schema(
        {
            vol.Optional(CONF_ENTRY_ID): cv.string,
            vol.Required("order_id"): cv.string,
        }
    )

    async def _async_get_runtime(entry_id: str | None) -> RobinhoodRuntimeData:
        entries = hass.data.get(DOMAIN) or {}
        if not entries:
            raise HomeAssistantError("Robinhood Crypto is not set up")
        if entry_id:
            runtime = entries.get(entry_id)
            if not runtime:
                raise HomeAssistantError(f"Entry id {entry_id} not found")
            return runtime
        return next(iter(entries.values()))

    async def _async_place_order(call: ServiceCall) -> None:
        runtime = await _async_get_runtime(call.data.get(CONF_ENTRY_ID))
        data = call.data
        order_type = data["order_type"]
        side = data["side"]
        symbol = data["symbol"]
        client_order_id = data.get("client_order_id") or str(uuid.uuid4())
        order_config: dict[str, str] = {}

        if data.get("asset_quantity") is not None:
            order_config["asset_quantity"] = str(data["asset_quantity"])
        if data.get("quote_amount") is not None:
            order_config["quote_amount"] = str(data["quote_amount"])
        if data.get("limit_price") is not None:
            order_config["limit_price"] = str(data["limit_price"])
        if data.get("stop_price") is not None:
            order_config["stop_price"] = str(data["stop_price"])
        if "time_in_force" in data:
            order_config["time_in_force"] = data["time_in_force"]

        if not order_config:
            raise HomeAssistantError(
                "Provide at least one order parameter (asset_quantity, quote_amount, limit_price, stop_price)"
            )

        await runtime.client.place_order(
            client_order_id=client_order_id,
            side=side,
            order_type=order_type,
            symbol=symbol,
            order_config=order_config,
        )

    async def _async_cancel_order(call: ServiceCall) -> None:
        runtime = await _async_get_runtime(call.data.get(CONF_ENTRY_ID))
        await runtime.client.cancel_order(call.data["order_id"])

    async_register_admin_service(
        hass, DOMAIN, "place_order", _async_place_order, schema=place_schema
    )
    async_register_admin_service(
        hass, DOMAIN, "cancel_order", _async_cancel_order, schema=cancel_schema
    )
