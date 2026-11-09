"""配置当前窗口使用的模型连接。密钥只保存在进程内。"""

import tkinter as tk
from tkinter import ttk

from .model_api import ModelConfig, ModelError


def configure_model(parent, on_apply=None):
    dialog = parent.children.get("model_settings")
    if dialog is not None:
        dialog.on_apply = on_apply
        dialog.deiconify()
        dialog.lift()
        dialog.focus_force()
        return dialog

    current = parent.model_config
    dialog = tk.Toplevel(parent, name="model_settings")
    dialog.title("模型 API 设置")
    dialog.on_apply = on_apply
    dialog.protocol("WM_DELETE_WINDOW", dialog.destroy)
    body = ttk.Frame(dialog, padding=14)
    body.pack(fill="both", expand=True)
    body.columnconfigure(1, weight=1)
    entries = []
    for row, (label, value) in enumerate((("API 基础地址", current.base_url), ("模型 ID", current.model),
                                           ("API Key", ""))):
        ttk.Label(body, text=label).grid(row=row, column=0, sticky="w", padx=(0, 8), pady=4)
        entry = ttk.Entry(body, width=43, show="*" if row == 2 else "")
        entry.insert(0, value)
        entry.grid(row=row, column=1, sticky="ew")
        entries.append(entry)
    hint = "本次运行有效。"
    if current.api_key:
        hint += "地址相同且密钥留空时沿用当前密钥。"
    ttk.Label(body, text=hint).grid(row=3, columnspan=2, sticky="w", pady=4)
    error = ttk.Label(body, foreground="#953c00")
    error.grid(row=4, columnspan=2, sticky="w")

    def apply():
        base, model, key = (entry.get().strip() for entry in entries)
        if not key and base.rstrip("/") == current.base_url.strip().rstrip("/"):
            key = current.api_key
        config = ModelConfig(base, model, key)
        try:
            config.endpoint()
        except ModelError as exc:
            error.configure(text=str(exc))
            return
        parent.model_config = config
        callback = dialog.on_apply
        dialog.destroy()
        if callback is not None:
            callback()

    buttons = ttk.Frame(body)
    buttons.grid(row=5, columnspan=2, sticky="e")
    ttk.Button(buttons, text="应用", command=apply).pack(side="left", padx=3)
    ttk.Button(buttons, text="取消", command=dialog.destroy).pack(side="left")
    dialog.bind("<Escape>", lambda _event: dialog.destroy())
    dialog.tk.call("tk::PlaceWindow", dialog._w, "widget", parent._w)
    dialog.lift()
    entries[2].focus_force()
    return dialog
