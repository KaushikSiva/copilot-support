from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from app.config import get_settings


class ConfigTests(unittest.TestCase):
    def tearDown(self) -> None:
        get_settings.cache_clear()

    def test_public_and_internal_api_base_urls_can_diverge(self) -> None:
        overrides = {
            "API_BASE_URL": "https://public.example.test",
            "PUBLIC_API_BASE_URL": "https://public.example.test",
            "INTERNAL_API_BASE_URL": "http://127.0.0.1:8787",
        }
        with patch.dict(os.environ, overrides, clear=False):
            get_settings.cache_clear()
            settings = get_settings()

        self.assertEqual(settings.api_base_url, "https://public.example.test")
        self.assertEqual(settings.public_api_base_url, "https://public.example.test")
        self.assertEqual(settings.internal_api_base_url, "http://127.0.0.1:8787")
