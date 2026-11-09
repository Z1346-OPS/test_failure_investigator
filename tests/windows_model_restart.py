"""Windows 专项：以两个真实 Tk 进程验证凭据保存、模型选择和重启后发送。"""

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from unittest.mock import patch
from uuid import uuid4

PROJECT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(PROJECT / "src"), str(PROJECT)]
from investigator.answer_panel import AnswerPanel
from investigator.model_catalog import BASE, Choice, credential_target
from investigator.model_settings import configure_model
from investigator.ui import InvestigatorApp
from investigator.windows_vault import WindowsVault
from tests import synthetic
from tests.gui_closeout_regressions import widgets, button


def run_window(mode, account, report):
    app = InvestigatorApp()
    try:
        app._load(report, as_addition=False)
        app.update()
        panel = next(w for w in widgets(app) if isinstance(w, AnswerPanel))
        target = Choice(account, "deepseek-v4-pro").label
        if mode == "save":
            dialog = configure_model(app)
            app.update()
            name, key = [w for w in widgets(dialog) if w.winfo_class() == "TEntry"]
            name.delete(0, "end")
            name.insert(0, account)
            assert key.cget("show") == "*" and key.get() == ""
            key.insert(0, "test-only-" + account)
            button(dialog, "应用").invoke()
            app.update()
            assert not dialog.winfo_exists(), "Windows 凭据或模型信息写入失败"
            panel.model_list.set(target)
            panel.model_list.event_generate("<<ComboboxSelected>>")
            app.update()
            assert app.model_catalog.selected == target
        else:
            assert panel.model_list.get() == target
            panel.show("依据在哪里？")
            received = []
            def simulated_service(config, answer):
                received.append((config.base_url == BASE, config.model == "deepseek-v4-pro",
                                 config.api_key == "test-only-" + account, "整图" in answer))
                return "模拟服务已收到请求"
            with patch("investigator.answer_panel.explain_with_model", side_effect=simulated_service):
                button(panel, f"用{target}生成说明").invoke()
                end = time.monotonic() + 4
                while panel._busy and time.monotonic() < end:
                    app.update()
                    time.sleep(0.01)
            assert received == [(True, True, True, True)]
            assert "模拟服务已收到请求" in panel.model_note.cget("text")
            assert "model_settings" not in app.children
    finally:
        app.destroy()


def check_restart():
    account = "qa-" + uuid4().hex
    target = credential_target(account)
    vault = WindowsVault()
    assert not vault.read(target), "测试凭据目标已被占用"
    try:
        with tempfile.TemporaryDirectory() as temp:
            env = {k: v for k, v in os.environ.items() if not k.startswith("INVESTIGATOR_")}
            env["LOCALAPPDATA"] = temp
            report = synthetic.write_report(Path(temp) / "qr.json", synthetic.label_baseline_report())
            for mode in ("save", "restart"):
                subprocess.run([sys.executable, "-B", "-X", "utf8", __file__, mode, account, report],
                               env=env, cwd=PROJECT, timeout=25, check=True)
            for path in Path(temp).rglob("*.json"):
                assert "test-only-" + account not in path.read_text(encoding="utf-8")
    finally:
        vault.delete(target)
    assert not vault.read(target)
    print("通过：首次填写、切换模型、重启恢复、读取 Windows 凭据并发送给模拟服务，测试凭据已清理。")


if __name__ == "__main__":
    if len(sys.argv) == 1:
        check_restart()
    else:
        run_window(*sys.argv[1:])
