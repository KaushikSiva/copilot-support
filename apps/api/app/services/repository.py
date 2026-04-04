from __future__ import annotations

from app.config import Settings
from app.services.insforge import InsforgeDataStore
from app.services.local_store import LocalDataStore


def build_repository(settings: Settings):
    if settings.data_mode == "insforge":
        return InsforgeDataStore(settings)
    return LocalDataStore(settings)

