"""模型选择恢复、账号隔离与凭据写入失败。"""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from investigator.model_api import ModelConfig, ModelError
from investigator.model_catalog import BASE, CUSTOM, MODELS, Choice, ModelCatalog


class FakeVault:
    def __init__(self):
        self.keys = {}

    def read(self, target):
        return self.keys.get(target, "")

    def write(self, target, key):
        self.keys[target] = key


class ModelCatalogTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.folder = Path(temp.name)
        self.vault = FakeVault()
        self.custom = ModelConfig("https://example.invalid/v1", "custom", "example-only")
        self.catalog = self.reopen()

    def reopen(self):
        catalog = ModelCatalog(self.folder, lambda: self.vault)
        catalog.load()
        return catalog

    def test_switch_models_accounts_and_reopen(self):
        self.catalog.save_account("个人", list(MODELS), "test-personal")
        self.catalog.save_account("工作", list(MODELS), "test-work")
        model = Choice("个人", "deepseek-v4-pro")
        self.catalog.select(model.label)
        reopened = self.reopen()
        self.assertEqual(reopened.selected, model.label)
        actual = reopened.connection(self.custom)
        self.assertEqual((actual.model, actual.api_key, actual.base_url), (model.model, "test-personal", BASE))
        reopened.save_account("个人", list(MODELS), "test-rotated")
        for model_id in MODELS:
            reopened.select(Choice("个人", model_id).label)
            self.assertEqual(reopened.connection(self.custom).api_key, "test-rotated")
        reopened.select(Choice("工作", "deepseek-flash").label)
        self.assertEqual(reopened.connection(self.custom).api_key, "test-work")
        reopened.select(CUSTOM)
        self.assertIs(reopened.connection(self.custom), self.custom)
        for file in self.folder.glob("*.json"):
            self.assertNotIn("test-", file.read_text("utf-8"))

    def test_subset_and_missing_key(self):
        with self.assertRaises(ModelError):
            self.catalog.save_account("工作", ["deepseek-flash"], "")
        self.catalog.save_account("工作", ["deepseek-v4-pro"], "test-work")
        self.assertNotIn(Choice("工作", "deepseek-flash").label, self.reopen().labels)
        self.vault.keys.clear()
        self.assertFalse(self.reopen().connection(self.custom).api_key)

    def test_stale_selection_falls_back_only_within_its_own_account(self):
        self.catalog.save_account("工作", list(MODELS), "test-work")
        other = self.reopen()
        self.catalog.save_account("工作", ["deepseek-flash"], "")
        with self.assertRaises(ModelError):
            other.select(Choice("工作", "deepseek-v4-pro").label)
        self.assertEqual(self.reopen().selected, Choice("工作", "deepseek-flash").label)

    def test_vault_error_leaves_preferences_intact(self):
        self.catalog.save_account("个人", list(MODELS), "test-initial")
        before = {p.name: p.read_bytes() for p in self.folder.iterdir()}
        with patch.object(self.vault, "write", side_effect=ModelError("不能写入")), self.assertRaises(ModelError):
            self.catalog.save_account("新账号", list(MODELS), "test-other")
        self.assertEqual({p.name: p.read_bytes() for p in self.folder.iterdir()}, before)

    def test_preferences_cannot_redirect_a_saved_credential(self):
        self.catalog.save_account("个人", list(MODELS), "test-only")
        file = next(self.folder.glob("account-*.json"))
        data = json.loads(file.read_bytes())
        data["base_url"] = "https://example.invalid"
        file.write_text(json.dumps(data), encoding="utf-8")
        self.assertEqual(self.reopen().connection(self.custom).base_url, BASE)
