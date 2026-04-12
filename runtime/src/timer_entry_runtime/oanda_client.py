from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any

from .models import AccountSnapshot, Candle, CloseResult, OandaSecret, OrderResult, PriceSnapshot, ProtectionOrderResult
from .order_builder import market_order_body, trade_protection_order_body
from .time_utils import parse_oanda_time


class OandaApiError(RuntimeError):
    pass


class OandaClient:
    def __init__(self, secret: OandaSecret) -> None:
        self._secret = secret
        self._base_url = "https://api-fxpractice.oanda.com" if secret.environment == "practice" else "https://api-fxtrade.oanda.com"

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        url = self._base_url + path
        if params:
            url = f"{url}?{urllib.parse.urlencode(params)}"
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(
            url=url,
            data=data,
            headers={
                "Authorization": f"Bearer {self._secret.access_token}",
                "Content-Type": "application/json",
            },
            method=method,
        )
        try:
            with urllib.request.urlopen(req, timeout=20) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            response_body = exc.read().decode("utf-8")
            raise OandaApiError(f"{method} {path} failed: {exc.code} {response_body}") from exc
        except urllib.error.URLError as exc:
            raise OandaApiError(f"{method} {path} failed: {exc.reason}") from exc

    def get_price_snapshot(self, instrument: str) -> PriceSnapshot:
        payload = self._request(
            "GET",
            f"/v3/accounts/{self._secret.account_id}/pricing",
            params={"instruments": instrument},
        )
        price = payload["prices"][0]
        return PriceSnapshot(
            instrument=instrument,
            bid=float(price["bids"][0]["price"]),
            ask=float(price["asks"][0]["price"]),
            time_utc=parse_oanda_time(price["time"]),
        )

    def get_account_snapshot(self) -> AccountSnapshot:
        payload = self._request("GET", f"/v3/accounts/{self._secret.account_id}/summary")
        account = payload["account"]
        return AccountSnapshot(account_id=str(account["id"]), balance=float(account["balance"]))

    def get_recent_bid_candles(self, instrument: str, count: int = 120) -> list[Candle]:
        payload = self._request(
            "GET",
            f"/v3/instruments/{instrument}/candles",
            params={"price": "B", "granularity": "M1", "count": count},
        )
        return [Candle.from_oanda(item) for item in payload.get("candles", []) if item.get("complete", False)]

    def create_market_order(
        self,
        *,
        setting: Any,
        units: int,
        client_id: str,
        client_tag: str,
        client_comment: str,
    ) -> OrderResult:
        body = market_order_body(
            setting=setting,
            units=units,
            client_id=client_id,
            client_tag=client_tag,
            client_comment=client_comment,
        )
        payload = self._request("POST", f"/v3/accounts/{self._secret.account_id}/orders", body=body)
        fill = payload.get("orderFillTransaction", {})
        trade_opened = fill.get("tradeOpened", {})
        return OrderResult(
            order_id=str(payload.get("orderCreateTransaction", {}).get("id")) if payload.get("orderCreateTransaction") else None,
            trade_id=str(trade_opened.get("tradeID")) if trade_opened.get("tradeID") else None,
            fill_price=float(fill["price"]) if fill.get("price") is not None else None,
            client_id=client_id,
            raw_response=payload,
        )

    def set_trade_protection_orders(self, *, trade_id: str, setting: Any, entry_fill_price: float) -> ProtectionOrderResult:
        body = trade_protection_order_body(setting, entry_fill_price=entry_fill_price)
        payload = self._request(
            "PUT",
            f"/v3/accounts/{self._secret.account_id}/trades/{trade_id}/orders",
            body=body,
        )
        take_profit_tx = payload.get("takeProfitOrderTransaction", {})
        stop_loss_tx = payload.get("stopLossOrderTransaction", {})
        return ProtectionOrderResult(
            take_profit_order_id=str(take_profit_tx.get("id")) if take_profit_tx.get("id") else None,
            stop_loss_order_id=str(stop_loss_tx.get("id")) if stop_loss_tx.get("id") else None,
            raw_response=payload,
        )

    def close_trade(self, trade_id: str) -> CloseResult:
        payload = self._request(
            "PUT",
            f"/v3/accounts/{self._secret.account_id}/trades/{trade_id}/close",
            body={"units": "ALL"},
        )
        fill = payload.get("orderFillTransaction", {})
        return CloseResult(
            order_id=str(payload.get("orderCreateTransaction", {}).get("id")) if payload.get("orderCreateTransaction") else None,
            fill_price=float(fill["price"]) if fill.get("price") is not None else None,
            raw_response=payload,
        )

    def get_trade(self, trade_id: str) -> dict[str, Any]:
        payload = self._request("GET", f"/v3/accounts/{self._secret.account_id}/trades/{trade_id}")
        return payload.get("trade", {})

    def get_open_trades(self, instrument: str | None = None) -> list[dict[str, Any]]:
        params = {"instrument": instrument} if instrument else None
        payload = self._request("GET", f"/v3/accounts/{self._secret.account_id}/openTrades", params=params)
        return payload.get("trades", [])

    @staticmethod
    def is_market_open(price_time_utc: datetime, now_utc: datetime, threshold_seconds: int) -> bool:
        if price_time_utc.tzinfo is None:
            price_time_utc = price_time_utc.replace(tzinfo=timezone.utc)
        if now_utc.tzinfo is None:
            now_utc = now_utc.replace(tzinfo=timezone.utc)
        return abs((now_utc - price_time_utc).total_seconds()) <= threshold_seconds

