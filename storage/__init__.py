"""Data store factory — PostgreSQL in production, SQLite locally."""

from __future__ import annotations

from config import USE_POSTGRES
from user_data import UserDataStore


def get_data_store(retention_hours: int | None = None) -> UserDataStore:
    if USE_POSTGRES:
        from storage.postgres_store import PostgresUserDataStore

        store = PostgresUserDataStore(retention_hours=retention_hours)
        return store
    store = UserDataStore()
    if retention_hours is not None:
        import config

        config.DATA_RETENTION_HOURS = retention_hours
    return store
