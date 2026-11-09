"""DeepSeek 账号下的模型和当前选择。磁盘 JSON 只包含账号名和模型 ID。"""

from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
import unicodedata

from .model_api import ModelConfig, ModelError
from .windows_vault import WindowsVault


BASE = "https://api.deepseek.com"
MODELS = {"deepseek-flash": "Flash", "deepseek-v4-pro": "V4 Pro"}
CUSTOM = "自定义兼容接口（本次运行）"
DEFAULT_ACCOUNT = "个人"


def has_env_config():
    return any(os.environ.get(v) for v in ("INVESTIGATOR_BASE_URL", "INVESTIGATOR_MODEL", "INVESTIGATOR_API_KEY"))


def account_name(value: str) -> str:
    name = unicodedata.normalize("NFKC", value).strip()
    if not (1 <= len(name) <= 40 and all(c.isalnum() or c in " _-" for c in name)):
        raise ModelError("账号名请用 1～40 个汉字、字母、数字、空格、下划线或短横线。")
    return name


def account_id(name):
    return sha256(account_name(name).casefold().encode("utf-8")).hexdigest()


def credential_target(name):
    return "TestFailureInvestigator/DeepSeek/" + account_id(name)


@dataclass(frozen=True)
class Choice:
    account: str
    model: str

    @property
    def label(self):
        return f"DeepSeek · {MODELS[self.model]}（{self.account}）"


def write_json(path, data):
    tmp = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as file:
            tmp = Path(file.name)
            json.dump(data, file, ensure_ascii=False)
            file.flush()
            os.fsync(file.fileno())
        os.replace(tmp, path)
    except OSError:
        raise ModelError("无法写入本机模型设置，请检查用户目录写入权限。") from None
    finally:
        if tmp is not None:
            tmp.unlink(missing_ok=True)


class ModelCatalog:
    def __init__(self, folder=None, vault_factory=WindowsVault):
        self.folder = folder or (Path(os.environ.get("LOCALAPPDATA") or Path.home()) /
                                 "TestFailureInvestigator" / "models")
        self.vault_factory = vault_factory
        self.profiles = {DEFAULT_ACCOUNT: tuple(MODELS)}
        self.selected = CUSTOM if has_env_config() else Choice(DEFAULT_ACCOUNT, "deepseek-flash").label

    def _read_profiles(self):
        profiles = {}
        try:
            for path in sorted(self.folder.glob("account-*.json")):
                record = json.loads(path.read_text(encoding="utf-8"))
                account = account_name(record["account"])
                models = self.enabled_models(record["models"])
                if path.name != f"account-{account_id(account)}.json":
                    raise ModelError("模型账号文件名与账号不一致。")
                profiles[account] = models
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise ModelError("无法读取本机模型账号，请检查模型配置文件。") from exc
        return profiles or {DEFAULT_ACCOUNT: tuple(MODELS)}

    def load(self):
        self.profiles = self._read_profiles()
        try:
            path = self.folder / "selection.json"
            if path.exists():
                saved = json.loads(path.read_text(encoding="utf-8"))
                selected = saved["selected"]
                if selected != CUSTOM and selected not in self.choices:
                    account = saved.get("account")
                    if account not in self.profiles:
                        raise ModelError("上次选择的模型不存在，请重新选择。")
                    selected = Choice(account, self.profiles[account][0]).label
                self.selected = selected
            elif self.selected not in self.labels:
                self.selected = next(iter(self.choices))
        except (UnicodeError, OSError, ValueError, KeyError, TypeError) as exc:
            raise ModelError("无法读取本机模型列表，请检查模型配置文件。") from exc

    @staticmethod
    def enabled_models(models):
        if not isinstance(models, (tuple, list)) or not models or any(m not in MODELS for m in models):
            raise ModelError("请至少选择一个支持的 DeepSeek 模型。")
        return tuple(m for m in MODELS if m in models)

    @property
    def choices(self):
        choices = {}
        for account, models in self.profiles.items():
            for model in models:
                choice = Choice(account, model)
                choices[choice.label] = choice
        return choices

    @property
    def labels(self):
        return [*self.choices, CUSTOM]

    def select(self, label):
        self.profiles = self._read_profiles()
        if label not in self.labels:
            raise ModelError("请选择列表中的模型。")
        choice = self.choices.get(label)
        write_json(self.folder / "selection.json", {"selected": label, "account": choice.account if choice else None})
        self.selected = label

    def save_account(self, name, models, key):
        name = account_name(name)
        models = self.enabled_models(models)
        self.profiles = self._read_profiles()
        name = next((a for a in self.profiles if a.casefold() == name.casefold()), name)
        target = credential_target(name)
        vault = self.vault_factory()
        api_key = key or vault.read(target)
        if not api_key:
            raise ModelError("此 DeepSeek 账号尚未保存 Key，请先填写一次。")
        ModelConfig(BASE, models[0], api_key).endpoint()
        if key:
            vault.write(target, key)
        try:
            write_json(self.folder / f"account-{account_id(name)}.json", {"account": name, "models": models})
            self.profiles[name] = models
            previous = self.choices.get(self.selected)
            choice = previous if previous and previous.account == name else Choice(name, models[0])
            self.select(choice.label)
        except ModelError as exc:
            raise ModelError("此账号的 Windows 凭据已保存，模型设置写入失败，请留空 Key 后重试。") from exc

    def connection(self, custom):
        if self.selected == CUSTOM:
            return custom
        choice = self.choices.get(self.selected)
        if choice is None:
            raise ModelError("请选择列表中的模型。")
        key = self.vault_factory().read(credential_target(choice.account))
        return ModelConfig(BASE, choice.model, key)
