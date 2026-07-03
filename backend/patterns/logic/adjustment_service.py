"""Persistence for temporary, occasion-driven pattern adjustments (the overlay).

Stored in their OWN table so the learned patterns are never touched. Each item is
scoped to an ``occasion_date`` and can be listed, added, or removed — a fully
reversible layer on top of the deterministic routines.

Self-healing: DynamoDB-Local runs in-memory, so its tables vanish on restart and
are only recreated when the patterns service (re)starts. To avoid a mid-demo
"non-existent table" 500, every operation lazily (re)creates the table if it's
missing and retries once.
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

from patterns.app.config import get_settings
from patterns.dynamodb.client import get_table
from patterns.models.context_note import ProposedAdjustment, StoredAdjustment


def _table():
    return get_table(get_settings().adjustments_table)


def _missing_table(e: Exception) -> bool:
    return (
        isinstance(e, ClientError)
        and e.response.get("Error", {}).get("Code") == "ResourceNotFoundException"
    )


def _ensure_table() -> None:
    from patterns.dynamodb.tables import create_tables
    create_tables()  # idempotent — creates only what's missing


def _with_table(fn, default=None):
    """Run a DynamoDB op; if the table is missing, create it and retry once."""
    try:
        return fn()
    except ClientError as e:
        if _missing_table(e):
            _ensure_table()
            try:
                return fn()
            except ClientError as e2:
                if _missing_table(e2) and default is not None:
                    return default
                raise
        raise


def add_many(
    household_id: str,
    adjustments: list[ProposedAdjustment],
    *,
    occasion: str = "",
    occasion_date: str = "",
) -> list[StoredAdjustment]:
    """Persist a confirmed plan's adjustments; returns the stored records."""
    created_at = datetime.now(timezone.utc).isoformat()
    stored: list[StoredAdjustment] = [
        StoredAdjustment(
            id=str(uuid4()), household_id=household_id, occasion=occasion,
            occasion_date=occasion_date, created_at=created_at, **adj.model_dump(),
        )
        for adj in adjustments
    ]

    def _write():
        table = _table()
        with table.batch_writer() as batch:
            for rec in stored:
                batch.put_item(Item={k: v for k, v in rec.model_dump().items() if v is not None})
        return stored

    return _with_table(_write)


def list_active(household_id: str, *, on_or_after: str | None = None) -> list[StoredAdjustment]:
    """All stored adjustments for a home, optionally only those still upcoming
    (``occasion_date >= on_or_after``). Sorted by occasion date then creation."""
    def _read():
        table = _table()
        resp = table.query(KeyConditionExpression=Key("household_id").eq(household_id))
        items = resp.get("Items", [])
        while "LastEvaluatedKey" in resp:
            resp = table.query(
                KeyConditionExpression=Key("household_id").eq(household_id),
                ExclusiveStartKey=resp["LastEvaluatedKey"],
            )
            items.extend(resp.get("Items", []))
        return items

    items = _with_table(_read, default=[])
    out = [StoredAdjustment(**it) for it in items]
    if on_or_after:
        out = [a for a in out if (a.occasion_date or "9999") >= on_or_after]
    out.sort(key=lambda a: (a.occasion_date or "", a.created_at))
    return out


def delete(household_id: str, adjustment_id: str) -> bool:
    _with_table(lambda: _table().delete_item(
        Key={"household_id": household_id, "id": adjustment_id}
    ), default=True)
    return True


def clear(household_id: str) -> int:
    def _do():
        table = _table()
        resp = table.query(KeyConditionExpression=Key("household_id").eq(household_id))
        items = resp.get("Items", [])
        with table.batch_writer() as batch:
            for it in items:
                batch.delete_item(Key={"household_id": household_id, "id": it["id"]})
        return len(items)

    return _with_table(_do, default=0)
