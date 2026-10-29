"""Read-only SQL Server to empty MySQL migration with transactional verification.

The source is never modified. The target must already contain the current
Alembic schema and no portal business rows. User sessions and idempotency keys
are intentionally excluded so restored sessions cannot become valid again.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any

import sqlalchemy as sa

from .database import TABLES, database_url, jsonable, make_engine, metadata


EXCLUDED_TABLES = {
    "user_sessions": "Sessions are revoked by omission; every user signs in again.",
    "idempotency_keys": "Request replay cache is environment-local and disposable.",
}

# Revision 0019 changes only MySQL DATETIME precision.  A stopped SQL Server
# source at 0018 is structurally compatible with a repaired MySQL target at
# 0019 and must not be modified just to advance its version marker.
COMPATIBLE_REVISION_PAIRS = {
    ('0018_remove_portal_backup', '0019_mysql_datetime_precision'),
}


def _revisions_compatible(source_revision: str, target_revision: str) -> bool:
    return source_revision == target_revision or (source_revision, target_revision) in COMPATIBLE_REVISION_PAIRS


def _load_config(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Cannot read JSON config: {path}") from exc
    if not isinstance(value, dict) or not isinstance(value.get("database"), dict):
        raise RuntimeError(f"Config must contain a database object: {path}")
    return value


def _revision(connection: sa.Connection) -> str:
    inspector = sa.inspect(connection)
    if not inspector.has_table("alembic_version"):
        raise RuntimeError("Database has no alembic_version table; run Alembic first.")
    value = connection.execute(sa.text("SELECT version_num FROM alembic_version")).scalar_one_or_none()
    if not value:
        raise RuntimeError("Database Alembic revision is empty.")
    return str(value)


def _verify_schema(connection: sa.Connection, label: str) -> None:
    inspector = sa.inspect(connection)
    missing = [name for name in TABLES if not inspector.has_table(name)]
    if missing:
        preview = ", ".join(missing[:8])
        suffix = " ..." if len(missing) > 8 else ""
        raise RuntimeError(f"{label} is missing {len(missing)} tables: {preview}{suffix}")


def _target_nonempty(connection: sa.Connection) -> dict[str, int]:
    populated: dict[str, int] = {}
    for name, table in TABLES.items():
        count = int(connection.execute(sa.select(sa.func.count()).select_from(table)).scalar_one())
        if count:
            populated[name] = count
    return populated


def _canonical(record: dict[str, Any]) -> bytes:
    value = jsonable(record)
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n"


def _table_summary(connection: sa.Connection, table: sa.Table, batch_size: int) -> dict[str, Any]:
    primary_key = table.primary_key.columns.values()[0]
    digest = hashlib.sha256()
    count = 0
    result = connection.execute(sa.select(table).order_by(primary_key)).mappings()
    while True:
        rows = result.fetchmany(batch_size)
        if not rows:
            break
        for record in rows:
            digest.update(_canonical(dict(record)))
            count += 1
    return {"count": count, "sha256": digest.hexdigest()}


def _source_summaries(connection: sa.Connection, batch_size: int) -> dict[str, dict[str, Any]]:
    summaries: dict[str, dict[str, Any]] = {}
    for name, table in TABLES.items():
        summary = _table_summary(connection, table, batch_size)
        if name in EXCLUDED_TABLES:
            summary["transferred_count"] = 0
            summary["excluded_reason"] = EXCLUDED_TABLES[name]
        summaries[name] = summary
    return summaries


def _pending_jobs(connection: sa.Connection) -> int:
    table = TABLES.get("background_jobs")
    if table is None or "job_state" not in table.c:
        return 0
    return int(connection.execute(
        sa.select(sa.func.count()).select_from(table).where(table.c.job_state.in_(("queued", "running")))
    ).scalar_one())


def _transfer(
    source: sa.Connection,
    target: sa.Connection,
    source_summaries: dict[str, dict[str, Any]],
    batch_size: int,
) -> None:
    inserted_tables: set[str] = set()
    deferred: list[tuple[sa.Table, sa.Column, Any, dict[str, Any]]] = []

    for table in metadata.sorted_tables:
        name = table.name
        if name in EXCLUDED_TABLES:
            inserted_tables.add(name)
            continue
        primary_key = table.primary_key.columns.values()[0]
        result = source.execute(sa.select(table).order_by(primary_key)).mappings()
        copied = 0
        digest = hashlib.sha256()
        while True:
            rows = result.fetchmany(batch_size)
            if not rows:
                break
            prepared: list[dict[str, Any]] = []
            for raw in rows:
                original = dict(raw)
                digest.update(_canonical(original))
                values = dict(original)
                restore: dict[str, Any] = {}
                for column in table.c:
                    if not column.foreign_keys or not column.nullable or values.get(column.name) is None:
                        continue
                    referenced = next(iter(column.foreign_keys)).column.table.name
                    if referenced not in inserted_tables:
                        restore[column.name] = values[column.name]
                        values[column.name] = None
                if restore:
                    deferred.append((table, primary_key, values[primary_key.name], restore))
                prepared.append(values)
            if prepared:
                target.execute(table.insert(), prepared)
                copied += len(prepared)
        expected = source_summaries[name]
        if copied != expected["count"] or digest.hexdigest() != expected["sha256"]:
            raise RuntimeError(f"Source changed while reading table {name}; stop the source portal and retry.")
        inserted_tables.add(name)

    for table, primary_key, key, values in deferred:
        target.execute(table.update().where(primary_key == key).values(**values))


def migrate(source_config: Path, target_config: Path, manifest_path: Path, batch_size: int, dry_run: bool) -> dict[str, Any]:
    source_settings = _load_config(source_config)
    target_settings = _load_config(target_config)
    source_engine = make_engine(database_url(source_settings, use_environment=False))
    target_engine = make_engine(database_url(target_settings, use_environment=False))
    started = datetime.now(timezone.utc)

    try:
        if source_engine.dialect.name != "mssql":
            raise RuntimeError(f"Source must be SQL Server/mssql, got {source_engine.dialect.name}.")
        if target_engine.dialect.name != "mysql":
            raise RuntimeError(f"Target must be MySQL, got {target_engine.dialect.name}.")

        with source_engine.connect() as source, target_engine.connect() as target_probe:
            _verify_schema(source, "Source")
            _verify_schema(target_probe, "Target")
            source_revision = _revision(source)
            target_revision = _revision(target_probe)
            if not _revisions_compatible(source_revision, target_revision):
                raise RuntimeError(
                    f"Alembic revision mismatch: source={source_revision}, target={target_revision}. "
                    "Upgrade both schemas to the same release before migrating."
                )
            populated = _target_nonempty(target_probe)
            if populated:
                preview = ", ".join(f"{name}={count}" for name, count in list(populated.items())[:8])
                raise RuntimeError(f"Target contains portal data; migration refused: {preview}")
            if _pending_jobs(source):
                raise RuntimeError("Source contains queued/running background jobs; finish or cancel them before migration.")
            source_summaries = _source_summaries(source, batch_size)

            manifest: dict[str, Any] = {
                "status": "preflight" if dry_run else "running",
                "started_at": started.isoformat(),
                "source_engine": source_engine.dialect.name,
                "target_engine": target_engine.dialect.name,
                "alembic_revision": target_revision,
                "source_alembic_revision": source_revision,
                "target_alembic_revision": target_revision,
                "batch_size": batch_size,
                "excluded_tables": EXCLUDED_TABLES,
                "tables": source_summaries,
            }
            if dry_run:
                manifest["completed_at"] = datetime.now(timezone.utc).isoformat()
                manifest_path.parent.mkdir(parents=True, exist_ok=True)
                manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
                return manifest

            # Recheck emptiness inside the target transaction. Any failure,
            # including post-copy digest mismatch, rolls back the entire import.
            with target_engine.begin() as target:
                populated = _target_nonempty(target)
                if populated:
                    raise RuntimeError("Target changed after preflight; migration transaction refused.")
                _transfer(source, target, source_summaries, batch_size)
                for name, table in TABLES.items():
                    actual = _table_summary(target, table, batch_size)
                    expected = source_summaries[name]
                    expected_count = 0 if name in EXCLUDED_TABLES else expected["count"]
                    expected_hash = hashlib.sha256().hexdigest() if name in EXCLUDED_TABLES else expected["sha256"]
                    if actual["count"] != expected_count or actual["sha256"] != expected_hash:
                        raise RuntimeError(f"Target verification failed for {name}; all imported rows were rolled back.")
                    expected["target_count"] = actual["count"]
                    expected["target_sha256"] = actual["sha256"]

            manifest["status"] = "completed"
            manifest["completed_at"] = datetime.now(timezone.utc).isoformat()
            manifest_path.parent.mkdir(parents=True, exist_ok=True)
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
            return manifest
    finally:
        source_engine.dispose()
        target_engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate an offline IT portal from SQL Server to an empty MySQL database.")
    parser.add_argument("--source-config", type=Path, required=True, help="JSON config containing the SQL Server database object")
    parser.add_argument("--target-config", type=Path, required=True, help="JSON config containing the MySQL database object")
    parser.add_argument("--manifest", type=Path, default=Path("migration-manifest.json"))
    parser.add_argument("--batch-size", type=int, default=250)
    parser.add_argument("--dry-run", action="store_true", help="Validate schemas, target emptiness and source hashes without writing")
    args = parser.parse_args()
    if not 10 <= args.batch_size <= 5000:
        parser.error("--batch-size must be between 10 and 5000")
    try:
        result = migrate(
            args.source_config.resolve(), args.target_config.resolve(), args.manifest.resolve(), args.batch_size, args.dry_run
        )
    except Exception as exc:
        parser.exit(1, f"Migration failed: {exc}\n")
    print(json.dumps({
        "status": result["status"],
        "alembic_revision": result["alembic_revision"],
        "table_count": len(result["tables"]),
        "manifest": str(args.manifest.resolve()),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
