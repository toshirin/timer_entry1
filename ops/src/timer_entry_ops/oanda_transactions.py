from __future__ import annotations

import json
from typing import Any
import urllib.error
import urllib.parse
import urllib.request


class OandaImportError(RuntimeError):
    pass


def oanda_base_url(environment: str) -> str:
    return "https://api-fxpractice.oanda.com" if environment == "practice" else "https://api-fxtrade.oanda.com"


def fetch_transactions_since_id(
    *,
    access_token: str,
    account_id: str,
    environment: str,
    transaction_id: str,
    transaction_type_filter: str | None = None,
) -> dict[str, Any]:
    params = {"id": transaction_id}
    if transaction_type_filter:
        params["type"] = transaction_type_filter
    url = (
        f"{oanda_base_url(environment)}/v3/accounts/{account_id}/transactions/sinceid?"
        f"{urllib.parse.urlencode(params)}"
    )
    req = urllib.request.Request(
        url=url,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8")
        raise OandaImportError(f"Oanda transaction import failed: {exc.code} {body}") from exc
    except urllib.error.URLError as exc:
        raise OandaImportError(f"Oanda transaction import failed: {exc.reason}") from exc


def fetch_latest_transaction_id(
    *,
    access_token: str,
    account_id: str,
    environment: str,
) -> str:
    url = f"{oanda_base_url(environment)}/v3/accounts/{account_id}/transactions?pageSize=1"
    req = urllib.request.Request(
        url=url,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
            return str(payload["lastTransactionID"])
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8")
        raise OandaImportError(f"Oanda latest transaction lookup failed: {exc.code} {body}") from exc
    except urllib.error.URLError as exc:
        raise OandaImportError(f"Oanda latest transaction lookup failed: {exc.reason}") from exc
