"""Sensor platform for Robinhood Crypto."""

from __future__ import annotations

import logging
from typing import Any, Callable, Iterable, List

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity, DataUpdateCoordinator

from .const import CONF_SYMBOLS, DOMAIN

_LOGGER = logging.getLogger(__name__)


def _extract_results(payload: Any) -> list[dict[str, Any]]:
    if not payload:
        return []
    if isinstance(payload, dict) and "results" in payload and isinstance(payload["results"], list):
        return payload["results"]
    if isinstance(payload, list):
        return payload
    return []


async def async_setup_entry(
    hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up sensors for a config entry."""
    runtime = hass.data[DOMAIN][entry.entry_id]
    entities: list[SensorEntity] = [
        AccountStatusSensor(entry.entry_id, runtime.account),
        BuyingPowerSensor(entry.entry_id, runtime.account),
    ]

    holdings = _extract_results(runtime.holdings.data)
    for holding in holdings:
        asset_code = holding.get("asset_code")
        if not asset_code:
            continue
        entities.append(HoldingSensor(entry.entry_id, runtime.holdings, asset_code))
        # Market value sensor assumes USD quote; this will no-op if price data is missing.
        entities.append(
            MarketValueSensor(
                entry.entry_id,
                runtime.holdings,
                runtime.market,
                asset_code,
                f"{asset_code}-USD",
            )
        )

    symbols = entry.options.get(CONF_SYMBOLS, [])
    for symbol in symbols:
        entities.append(MarketPriceSensor(entry.entry_id, runtime.market, symbol))

    async_add_entities(entities)


class RobinhoodEntity(CoordinatorEntity, SensorEntity):
    """Base entity for Robinhood Crypto sensors."""

    _attr_has_entity_name = True

    def __init__(self, entry_id: str, coordinator) -> None:
        super().__init__(coordinator)
        self._entry_id = entry_id
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry_id)},
            name="Robinhood Crypto",
            manufacturer="Robinhood",
            entry_type=None,
        )


class MultiCoordinatorEntity(SensorEntity):
    """Entity that listens to multiple coordinators."""

    _attr_should_poll = False

    def __init__(self, coordinators: Iterable[DataUpdateCoordinator]) -> None:
        super().__init__()
        self._coordinators: List[DataUpdateCoordinator] = list(coordinators)
        self._remove_listeners: list[Callable[[], None]] = []

    @property
    def available(self) -> bool:
        return all(coordinator.last_update_success for coordinator in self._coordinators)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        for coordinator in self._coordinators:
            remove = coordinator.async_add_listener(self.async_write_ha_state)
            self._remove_listeners.append(remove)

    async def async_will_remove_from_hass(self) -> None:
        for remove in self._remove_listeners:
            remove()
        await super().async_will_remove_from_hass()


class AccountStatusSensor(RobinhoodEntity):
    """Reports the crypto account status."""

    _attr_icon = "mdi:shield-check"

    def __init__(self, entry_id: str, coordinator) -> None:
        super().__init__(entry_id, coordinator)
        self._attr_unique_id = f"{entry_id}_account_status"
        self._attr_name = "Account Status"

    @property
    def native_value(self):
        return (self.coordinator.data or {}).get("status")


class BuyingPowerSensor(RobinhoodEntity):
    """Reports the crypto buying power."""

    _attr_icon = "mdi:cash"
    _attr_device_class = SensorDeviceClass.MONETARY

    def __init__(self, entry_id: str, coordinator) -> None:
        super().__init__(entry_id, coordinator)
        self._attr_unique_id = f"{entry_id}_buying_power"
        self._attr_name = "Buying Power"

    @property
    def native_unit_of_measurement(self):
        return (self.coordinator.data or {}).get("buying_power_currency")

    @property
    def native_value(self):
        value = (self.coordinator.data or {}).get("buying_power")
        try:
            return float(value)
        except (TypeError, ValueError):
            return None


class HoldingSensor(RobinhoodEntity):
    """Reports quantity for an individual crypto holding."""

    _attr_icon = "mdi:coin"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, entry_id: str, coordinator, asset_code: str) -> None:
        super().__init__(entry_id, coordinator)
        self._asset_code = asset_code
        self._attr_unique_id = f"{entry_id}_holding_{asset_code.lower()}"
        self._attr_name = f"{asset_code} Holding"

    def _current_holding(self) -> dict[str, Any] | None:
        for item in _extract_results(self.coordinator.data):
            if item.get("asset_code") == self._asset_code:
                return item
        return None

    @property
    def native_value(self):
        holding = self._current_holding()
        if not holding:
            return None
        try:
            return float(holding.get("total_quantity"))
        except (TypeError, ValueError):
            return None

    @property
    def extra_state_attributes(self):
        holding = self._current_holding()
        if not holding:
            return {}
        return {
            "asset_code": holding.get("asset_code"),
            "account_number": holding.get("account_number"),
            "available_to_trade": holding.get("quantity_available_for_trading"),
        }


class MarketPriceSensor(RobinhoodEntity):
    """Reports midpoint price for a trading pair."""

    _attr_icon = "mdi:chart-line"
    _attr_device_class = SensorDeviceClass.MONETARY

    def __init__(self, entry_id: str, coordinator, symbol: str) -> None:
        super().__init__(entry_id, coordinator)
        self._symbol = symbol.upper()
        self._attr_unique_id = f"{entry_id}_price_{self._symbol.replace('-', '_').lower()}"
        self._attr_name = f"{self._symbol} Price"

    def _current_price(self) -> dict[str, Any] | None:
        for item in _extract_results(self.coordinator.data):
            if item.get("symbol") == self._symbol:
                return item
        return None

    @property
    def native_unit_of_measurement(self):
        quote = self._symbol.split("-")[-1] if "-" in self._symbol else None
        return quote

    @property
    def native_value(self):
        price = self._current_price()
        if not price:
            return None
        try:
            return float(price.get("price"))
        except (TypeError, ValueError):
            return None

    @property
    def extra_state_attributes(self):
        price = self._current_price()
        if not price:
            return {}
        return {
            "symbol": price.get("symbol"),
            "bid_inclusive_of_sell_spread": price.get("bid_inclusive_of_sell_spread"),
            "ask_inclusive_of_buy_spread": price.get("ask_inclusive_of_buy_spread"),
            "buy_spread": price.get("buy_spread"),
            "sell_spread": price.get("sell_spread"),
            "timestamp": price.get("timestamp"),
        }


class MarketValueSensor(MultiCoordinatorEntity):
    """Reports total value for a holding using the midpoint price."""

    _attr_icon = "mdi:cash-multiple"
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_has_entity_name = True

    def __init__(
        self,
        entry_id: str,
        holdings_coordinator: DataUpdateCoordinator,
        market_coordinator: DataUpdateCoordinator,
        asset_code: str,
        symbol: str,
    ) -> None:
        super().__init__([holdings_coordinator, market_coordinator])
        self._entry_id = entry_id
        self._holdings = holdings_coordinator
        self._market = market_coordinator
        self._asset_code = asset_code
        self._symbol = symbol.upper()
        self._attr_unique_id = f"{entry_id}_value_{asset_code.lower()}"
        self._attr_name = f"{asset_code} Value"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry_id)},
            name="Robinhood Crypto",
            manufacturer="Robinhood",
            entry_type=None,
        )

    def _current_holding(self) -> dict[str, Any] | None:
        for item in _extract_results(self._holdings.data):
            if item.get("asset_code") == self._asset_code:
                return item
        return None

    def _current_price(self) -> dict[str, Any] | None:
        for item in _extract_results(self._market.data):
            if item.get("symbol") == self._symbol:
                return item
        return None

    @property
    def native_unit_of_measurement(self):
        quote = self._symbol.split("-")[-1] if "-" in self._symbol else None
        return quote

    @property
    def native_value(self):
        holding = self._current_holding()
        price = self._current_price()
        if not holding or not price:
            return None
        try:
            qty = float(holding.get("total_quantity"))
            midpoint = float(price.get("price"))
        except (TypeError, ValueError):
            return None
        return qty * midpoint

    @property
    def extra_state_attributes(self):
        holding = self._current_holding()
        price = self._current_price()
        return {
            "symbol": self._symbol,
            "asset_code": self._asset_code,
            "quantity": holding.get("total_quantity") if holding else None,
            "price": price.get("price") if price else None,
            "bid_inclusive_of_sell_spread": price.get("bid_inclusive_of_sell_spread")
            if price
            else None,
            "ask_inclusive_of_buy_spread": price.get("ask_inclusive_of_buy_spread")
            if price
            else None,
            "timestamp": price.get("timestamp") if price else None,
        }
