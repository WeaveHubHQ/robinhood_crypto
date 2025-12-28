"""Config flow for the Robinhood Crypto integration."""

from __future__ import annotations

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback

from .const import (
    CONF_API_KEY,
    CONF_POLL_INTERVAL,
    CONF_PRICE_POLL_INTERVAL,
    CONF_PRIVATE_KEY,
    CONF_SYMBOLS,
    DEFAULT_POLL_INTERVAL,
    DEFAULT_PRICE_POLL_INTERVAL,
    DOMAIN,
)


def _parse_symbols(raw: str) -> list[str]:
    return [symbol.strip().upper() for symbol in raw.split(",") if symbol.strip()]


class RobinhoodCryptoConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Robinhood Crypto."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            api_key = user_input[CONF_API_KEY].strip()
            private_key = user_input[CONF_PRIVATE_KEY].strip()
            symbols = _parse_symbols(user_input.get(CONF_SYMBOLS, ""))

            await self.async_set_unique_id(api_key)
            self._abort_if_unique_id_configured()

            return self.async_create_entry(
                title="Robinhood Crypto",
                data={CONF_API_KEY: api_key, CONF_PRIVATE_KEY: private_key},
                options={
                    CONF_SYMBOLS: symbols,
                    CONF_POLL_INTERVAL: DEFAULT_POLL_INTERVAL,
                    CONF_PRICE_POLL_INTERVAL: DEFAULT_PRICE_POLL_INTERVAL,
                },
            )

        schema = vol.Schema(
            {
                vol.Required(CONF_API_KEY): str,
                vol.Required(CONF_PRIVATE_KEY): str,
                vol.Optional(CONF_SYMBOLS, default="BTC-USD,ETH-USD"): str,
            }
        )

        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return RobinhoodOptionsFlow(config_entry)


class RobinhoodOptionsFlow(config_entries.OptionsFlow):
    """Handle options for Robinhood Crypto."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._config_entry = config_entry

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            symbols = _parse_symbols(user_input.get(CONF_SYMBOLS, ""))
            return self.async_create_entry(
                data={
                    CONF_SYMBOLS: symbols,
                    CONF_POLL_INTERVAL: user_input[CONF_POLL_INTERVAL],
                    CONF_PRICE_POLL_INTERVAL: user_input[CONF_PRICE_POLL_INTERVAL],
                }
            )

        current = self.config_entry.options
        symbols = ",".join(current.get(CONF_SYMBOLS, []))
        poll_interval = current.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL)
        price_poll_interval = current.get(
            CONF_PRICE_POLL_INTERVAL, DEFAULT_PRICE_POLL_INTERVAL
        )

        schema = vol.Schema(
            {
                vol.Optional(CONF_SYMBOLS, default=symbols): str,
                vol.Optional(
                    CONF_POLL_INTERVAL,
                    default=poll_interval,
                ): vol.All(vol.Coerce(int), vol.Range(min=15, max=600)),
                vol.Optional(
                    CONF_PRICE_POLL_INTERVAL,
                    default=price_poll_interval,
                ): vol.All(vol.Coerce(int), vol.Range(min=5, max=300)),
            }
        )

        return self.async_show_form(step_id="init", data_schema=schema)
