from __future__ import annotations

from typing import Any


class DataApi:
    def __init__(
        self,
        *,
        client: Any,
        cluster_arn: str,
        secret_arn: str,
        database_name: str,
    ) -> None:
        self._client = client
        self._cluster_arn = cluster_arn
        self._secret_arn = secret_arn
        self._database_name = database_name

    def execute(self, sql: str, parameters: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "resourceArn": self._cluster_arn,
            "secretArn": self._secret_arn,
            "database": self._database_name,
            "sql": sql,
        }
        if parameters:
            kwargs["parameters"] = parameters
        return self._client.execute_statement(**kwargs)

    def batch_execute(self, statements: list[str]) -> None:
        for statement in statements:
            stripped = statement.strip()
            if stripped:
                self.execute(stripped)


def text_param(name: str, value: str) -> dict[str, Any]:
    return {"name": name, "value": {"stringValue": value}}


def long_param(name: str, value: int) -> dict[str, Any]:
    return {"name": name, "value": {"longValue": value}}
