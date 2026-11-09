"""设置 DeepSeek 账号或本次运行的自定义连接。"""

import tkinter as tk
from tkinter import ttk

from .model_api import ModelConfig, ModelError
from .model_catalog import CUSTOM, DEFAULT_ACCOUNT, MODELS


def configure_model(parent, on_apply=None):
    dialog = parent.children.get("model_settings")
    if dialog is not None:
        dialog.on_apply = on_apply
        dialog.deiconify()
        dialog.lift()
        dialog.focus_force()
        return dialog

    catalog = parent.model_catalog
    custom = catalog.selected == CUSTOM
    current = parent.model_config
    dialog = tk.Toplevel(parent, name="model_settings")
    dialog.title("模型 API 设置")
    dialog.on_apply = on_apply
    dialog.protocol("WM_DELETE_WINDOW", dialog.destroy)
    body = ttk.Frame(dialog, padding=14)
    body.pack(fill="both", expand=True)
    body.columnconfigure(1, weight=1)

    def entry(row, label, value="", *, masked=False):
        ttk.Label(body, text=label).grid(row=row, column=0, sticky="w", padx=(0, 8), pady=4)
        widget = ttk.Entry(body, width=43, show="*" if masked else "")
        widget.insert(0, value)
        widget.grid(row=row, column=1, sticky="ew")
        return widget

    if custom:
        base = entry(0, "API 基础地址", current.base_url)
        model = entry(1, "模型 ID", current.model)
        hint = "自定义接口仅在本次运行有效。相同地址可留空沿用当前密钥。"
    else:
        choice = catalog.choices.get(catalog.selected)
        account = entry(0, "DeepSeek 账号名", choice.account if choice else DEFAULT_ACCOUNT)
        ttk.Label(body, text="列入模型列表").grid(row=1, column=0, sticky="w")
        options = ttk.Frame(body)
        options.grid(row=1, column=1, sticky="w")
        enabled = catalog.profiles.get(account.get(), MODELS)
        flags = {m: tk.BooleanVar(body, value=m in enabled) for m in MODELS}
        for m, label in MODELS.items():
            ttk.Checkbutton(options, text=label, variable=flags[m]).pack(side="left")
        hint = "Key 保存在此用户的 Windows 凭据管理器。已有账号可留空沿用；填写新 Key 即更新。"
    key_entry = entry(2, "API Key", masked=True)
    ttk.Label(body, text=hint, wraplength=390).grid(row=3, columnspan=2, sticky="w", pady=4)
    error = ttk.Label(body, foreground="#953c00", wraplength=390)
    error.grid(row=4, columnspan=2, sticky="w")

    def apply():
        key = key_entry.get().strip()
        try:
            if custom:
                address = base.get().strip()
                if not key and address.rstrip("/") == current.base_url.strip().rstrip("/"):
                    key = current.api_key
                config = ModelConfig(address, model.get().strip(), key)
                config.endpoint()
                catalog.select(CUSTOM)
                parent.model_config = config
            else:
                catalog.save_account(account.get(), [m for m in flags if flags[m].get()], key)
        except ModelError as exc:
            error.configure(text=str(exc))
            return
        parent.model_selection.set(catalog.selected)
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
    key_entry.focus_force()
    return dialog
