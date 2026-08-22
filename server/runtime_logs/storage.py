from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Iterable

from sqlalchemy import Engine, delete, func, or_, select
from sqlalchemy.orm import Session

from models import ClientRuntimeLog

from .domain import LogEvent


def ensure_client_log_schema(engine: Engine) -> None:
    ClientRuntimeLog.__table__.create(bind=engine, checkfirst=True)


def persist_client_events(db: Session, events: Iterable[LogEvent]) -> list[ClientRuntimeLog]:
    rows: list[ClientRuntimeLog] = []
    for event in events:
        context = dict(event.context)
        rows.append(
            ClientRuntimeLog(
                occurred_at=event.occurred_at,
                received_at=event.received_at,
                level=event.level,
                category=event.category,
                message=event.message,
                session_id=str(context.pop("_session_id", "")),
                app_version=str(context.pop("_app_version", "")),
                platform=str(context.pop("_platform", "")),
                source=event.source,
                context_json=context,
                truncated=event.truncated,
            )
        )
    db.add_all(rows)
    db.flush()
    return rows


def row_to_event(row: ClientRuntimeLog) -> LogEvent:
    return LogEvent(
        cursor=str(row.id),
        occurred_at=row.occurred_at,
        received_at=row.received_at,
        source_type="client",
        source=row.source,
        level=row.level,  # type: ignore[arg-type]
        category=row.category,
        message=row.message,
        context={
            **(row.context_json or {}),
            "session_id": row.session_id,
            "app_version": row.app_version,
            "platform": row.platform,
        },
        truncated=row.truncated,
    )


def query_client_events(
    db: Session,
    *,
    after_cursor: int | None = None,
    before_cursor: int | None = None,
    levels: set[str] | None = None,
    keyword: str = "",
    session_id: str = "",
    source: str = "",
    limit: int = 200,
) -> list[LogEvent]:
    statement = select(ClientRuntimeLog)
    if after_cursor is not None:
        statement = statement.where(ClientRuntimeLog.id > after_cursor)
    if before_cursor is not None:
        statement = statement.where(ClientRuntimeLog.id < before_cursor)
    if levels:
        statement = statement.where(ClientRuntimeLog.level.in_(levels))
    if keyword:
        pattern = f"%{keyword}%"
        statement = statement.where(
            or_(ClientRuntimeLog.message.like(pattern), ClientRuntimeLog.category.like(pattern))
        )
    if session_id:
        statement = statement.where(ClientRuntimeLog.session_id == session_id)
    if source:
        statement = statement.where(ClientRuntimeLog.source == source)

    if after_cursor is None:
        rows = list(db.scalars(statement.order_by(ClientRuntimeLog.id.desc()).limit(limit)))
        rows.reverse()
    else:
        rows = list(db.scalars(statement.order_by(ClientRuntimeLog.id.asc()).limit(limit)))
    return [row_to_event(row) for row in rows]


def cleanup_client_logs(
    db: Session,
    *,
    retention_days: int,
    max_rows: int,
    batch_size: int,
    now: datetime | None = None,
) -> int:
    removed = 0
    cutoff = (now or datetime.now(UTC)) - timedelta(days=retention_days)
    expired_ids = list(
        db.scalars(
            select(ClientRuntimeLog.id)
            .where(ClientRuntimeLog.received_at < cutoff)
            .order_by(ClientRuntimeLog.id)
            .limit(batch_size)
        )
    )
    if expired_ids:
        db.execute(delete(ClientRuntimeLog).where(ClientRuntimeLog.id.in_(expired_ids)))
        removed += len(expired_ids)

    current_count = db.scalar(select(func.count()).select_from(ClientRuntimeLog)) or 0
    excess = max(0, current_count - max_rows)
    if excess:
        trim_ids = list(
            db.scalars(
                select(ClientRuntimeLog.id)
                .order_by(ClientRuntimeLog.id)
                .limit(min(excess, batch_size))
            )
        )
        if trim_ids:
            db.execute(delete(ClientRuntimeLog).where(ClientRuntimeLog.id.in_(trim_ids)))
            removed += len(trim_ids)
    return removed
