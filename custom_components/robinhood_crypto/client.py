"""Async client for the Robinhood Crypto Trading API."""

from __future__ import annotations

import base64
import json
import time
from typing import Any, Iterable, Mapping
from urllib.parse import urlencode

from aiohttp import ClientResponseError, ClientSession
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

API_HOST = "https://trading.robinhood.com"


class RobinhoodCryptoError(Exception):
    """Base exception for Robinhood Crypto failures."""


class RobinhoodRequestError(RobinhoodCryptoError):
    """Raised when the API returns an error response."""

    def __init__(self, status: int, message: str, payload: Any | None = None) -> None:
        super().__init__(message)
        self.status = status
        self.payload = payload


class RobinhoodCryptoClient:
    """Client that signs and sends requests to the Robinhood Crypto Trading API."""

    def __init__(self, session: ClientSession, api_key: str, private_key: str) -> None:
        self._session = session
        self._api_key = api_key
        self._signing_key = Ed25519PrivateKey.from_private_bytes(
            base64.b64decode(private_key)
        )

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, str] | list[tuple[str, str]] | None = None,
        json_body: Any | None = None,
        timeout: int = 15,
    ) -> Any:
        method = method.upper()
        query_string = ""
        if params:
            query_string = f"?{urlencode(params, doseq=True)}"

        body_text = ""
        if json_body is not None:
            body_text = json.dumps(json_body, separators=(",", ":"))

        timestamp = int(time.time())
        path_for_signature = f"{path}{query_string}"
        message = f"{self._api_key}{timestamp}{path_for_signature}{method}{body_text}"
        signed = self._signing_key.sign(message.encode("utf-8"))
        signature = base64.b64encode(signed).decode("utf-8")

        headers = {
            "x-api-key": self._api_key,
            "x-signature": signature,
            "x-timestamp": str(timestamp),
            "Content-Type": "application/json; charset=utf-8",
        }

        url = f"{API_HOST}{path_for_signature}"

        try:
            async with self._session.request(
                method,
                url,
                headers=headers,
                data=body_text if body_text else None,
                timeout=timeout,
            ) as response:
                text = await response.text()
                try:
                    data = await response.json()
                except Exception:
                    data = text

                if response.status >= 400:
                    message = "Unknown error"
                    if isinstance(data, dict):
                        if "errors" in data:
                            message = "; ".join(
                                err.get("detail", "Unknown error") for err in data["errors"]
                            )
                        elif "detail" in data:
                            message = str(data["detail"])
                    raise RobinhoodRequestError(response.status, message, payload=data)

                return data
        except ClientResponseError as err:
            raise RobinhoodCryptoError(f"Request failed: {err}") from err
        except Exception as err:  # pragma: no cover - network/transport errors
            raise RobinhoodCryptoError(f"Request error: {err}") from err

    async def get_account(self) -> Any:
        """Return crypto trading account details."""
        return await self._request("GET", "/api/v1/crypto/trading/accounts/")

    async def get_trading_pairs(
        self, symbols: Iterable[str] | None = None, limit: int | None = None, cursor: str | None = None
    ) -> Any:
        params: list[tuple[str, str]] = []
        if symbols:
            params.extend([("symbol", symbol.upper()) for symbol in symbols])
        if limit is not None:
            params.append(("limit", str(limit)))
        if cursor:
            params.append(("cursor", cursor))

        return await self._request("GET", "/api/v1/crypto/trading/trading_pairs/", params=params)

    async def get_holdings(self, asset_codes: Iterable[str] | None = None) -> Any:
        params: list[tuple[str, str]] = []
        if asset_codes:
            params.extend([("asset_code", asset.upper()) for asset in asset_codes])
        return await self._request("GET", "/api/v1/crypto/trading/holdings/", params=params)

    async def get_best_bid_ask(self, symbols: Iterable[str] | None = None) -> Any:
        params: list[tuple[str, str]] = []
        if symbols:
            params.extend([("symbol", symbol.upper()) for symbol in symbols])
        return await self._request("GET", "/api/v1/crypto/marketdata/best_bid_ask/", params=params)

    async def get_estimated_price(self, symbol: str, side: str, quantity: str) -> Any:
        params: list[tuple[str, str]] = [
            ("symbol", symbol.upper()),
            ("side", side),
            ("quantity", quantity),
        ]
        return await self._request("GET", "/api/v1/crypto/marketdata/estimated_price/", params=params)

    async def place_order(
        self,
        *,
        client_order_id: str,
        side: str,
        order_type: str,
        symbol: str,
        order_config: dict[str, Any],
    ) -> Any:
        payload = {
            "client_order_id": client_order_id,
            "side": side,
            "type": order_type,
            "symbol": symbol.upper(),
            f"{order_type}_order_config": order_config,
        }
        return await self._request(
            "POST", "/api/v1/crypto/trading/orders/", json_body=payload
        )

    async def cancel_order(self, order_id: str) -> Any:
        return await self._request(
            "POST", f"/api/v1/crypto/trading/orders/{order_id}/cancel/"
        )

    async def get_order(self, order_id: str) -> Any:
        return await self._request("GET", f"/api/v1/crypto/trading/orders/{order_id}/")

    async def get_orders(self) -> Any:
        return await self._request("GET", "/api/v1/crypto/trading/orders/")
