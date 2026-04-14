from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "ops" / "src"))

from timer_entry_ops.daily_transaction_import import _normalized_transaction_values


def test_normalized_transaction_values_extracts_account_balance_and_trade_ids() -> None:
    transaction = {
        "id": "1001",
        "accountID": "acct-1",
        "time": "2026-04-14T12:00:01.000000000Z",
        "type": "ORDER_FILL",
        "orderID": "order-1",
        "batchID": "batch-1",
        "instrument": "USD_JPY",
        "units": "-1000",
        "price": "151.234",
        "pl": "120.5",
        "financing": "-1.2",
        "accountBalance": "100119.3",
        "reason": "MARKET_ORDER",
        "tradesClosed": [{"tradeID": "trade-1"}],
        "clientOrderID": "setting-1",
        "clientOrderTag": "timed_entry_sell",
        "clientOrderComment": "tyo09:test",
    }

    values = _normalized_transaction_values(transaction)

    assert values["account_id"] == "acct-1"
    assert values["account_balance"] == "100119.3"
    assert values["trade_id"] == "trade-1"
    assert values["client_ext_id"] == "setting-1"
    assert values["pl"] == "120.5"
