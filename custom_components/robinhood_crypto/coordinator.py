"""Data update coordinators for Robinhood Crypto."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
import logging
from typing import Iterable

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .client import RobinhoodCryptoClient, RobinhoodCryptoError
from .const import DEFAULT_POLL_INTERVAL, DEFAULT_PRICE_POLL_INTERVAL

_LOGGER = logging.getLogger(__name__)


@dataclass
class RobinhoodRuntimeData:
    """Container for integration runtime objects."""

    client: RobinhoodCryptoClient
    account: DataUpdateCoordinator
    holdings: DataUpdateCoordinator
    market: DataUpdateCoordinator


def _wrap_update(error_context: str, coro_factory):
    async def _async_update():
        try:
            return await coro_factory()
        except RobinhoodCryptoError as err:
            raise UpdateFailed(f"{error_context}: {err}") from err

    return _async_update


def create_coordinators(
    hass: HomeAssistant,
    client: RobinhoodCryptoClient,
    *,
    symbols: Iterable[str] | None,
    account_interval: int = DEFAULT_POLL_INTERVAL,
    price_interval: int = DEFAULT_PRICE_POLL_INTERVAL,
) -> RobinhoodRuntimeData:
    """Build all coordinators for a config entry."""

    account_coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name="robinhood_crypto_account",
        update_method=_wrap_update("Failed to refresh account", client.get_account),
        update_interval=timedelta(seconds=account_interval),
    )

    holdings_coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name="robinhood_crypto_holdings",
        update_method=_wrap_update("Failed to refresh holdings", client.get_holdings),
        update_interval=timedelta(seconds=account_interval),
    )

    async def _async_market_update():
        try:
            return await client.get_best_bid_ask(symbols)
        except RobinhoodCryptoError as err:
            raise UpdateFailed(f"Failed to refresh market data: {err}") from err

    market_coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name="robinhood_crypto_market",
        update_method=_async_market_update,
        update_interval=timedelta(seconds=price_interval),
    )

    return RobinhoodRuntimeData(
        client=client,
        account=account_coordinator,
        holdings=holdings_coordinator,
        market=market_coordinator,
    )
