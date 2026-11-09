"""在调查或问题卡中选择固定问题，显示可复制的离线回答。"""

from queue import Empty, Queue
from threading import Thread
import tkinter as tk
from tkinter import ttk

from .answers import QUESTIONS
from .model_api import ModelError, explain_with_model
from .model_settings import configure_model


class AnswerPanel(ttk.Frame):
    def __init__(self, parent, get_answer, *, show_copy=True):
        super().__init__(parent)
        self.get_answer = get_answer
        self.current_text = None
        bar = ttk.Frame(self)
        bar.pack(anchor="w")
        for question in QUESTIONS:
            ttk.Button(bar, text=question, command=lambda q=question: self.show(q)).pack(side="left", padx=2)
        entry_row = ttk.Frame(self)
        entry_row.pack(fill="x", pady=(4, 0))
        ttk.Label(entry_row, text="我的问题").pack(side="left")
        self.entry = ttk.Entry(entry_row)
        self.entry.pack(side="left", fill="x", expand=True, padx=4)
        ttk.Button(entry_row, text="提问", command=self._submit).pack(side="left")
        self.entry.bind("<Return>", self._submit)
        app = self.winfo_toplevel()
        models = ttk.Frame(self)
        models.pack(fill="x", pady=(3, 0))
        ttk.Label(models, text="当前模型").pack(side="left")
        self.model_list = ttk.Combobox(models, state="readonly", width=32)
        self.model_list.pack(side="left", padx=4)
        self.model_list.bind("<<ComboboxSelected>>", self._select_model)
        ttk.Button(models, text="模型设置", command=self._settings).pack(side="left")
        self.model_button = ttk.Button(self, command=self._send_to_model)
        self.model_note = ttk.Label(self, justify="left", wraplength=630)
        self._generation = 0
        self._busy = False
        self._timer = None
        self._selection = app.model_selection
        self._trace = self._selection.trace_add("write", self._sync_models)
        self._sync_models()
        self.bind("<Destroy>", self._destroyed)
        self.result = ttk.Label(self, justify="left", wraplength=630)
        self.copy_controls = None
        if show_copy:
            self.copy_controls = ttk.Frame(self)
            ttk.Button(self.copy_controls, text="复制交接摘要", command=self._copy).pack(side="left")
            self.notice = ttk.Label(self.copy_controls)
            self.notice.pack(side="left", padx=4)

    def _submit(self, _event=None):
        self.show(self.entry.get())
        return "break"

    def show(self, question):
        self._generation += 1
        self.model_note.pack_forget()
        self.model_button.pack_forget()
        self.result.pack(anchor="w", pady=(5, 2))
        try:
            self.current_text = self.get_answer(question)
        except ValueError as exc:
            self.current_text = ""
            self.result.configure(text=str(exc))
            if self.copy_controls is not None:
                self.copy_controls.pack_forget()
        else:
            self.result.configure(text=self.current_text)
            self.model_button.pack(anchor="w")
            if self.copy_controls is not None:
                self.notice.configure(text="")
                self.copy_controls.pack(anchor="w")

    def _sync_models(self, *_):
        catalog = self.winfo_toplevel().model_catalog
        self.model_list.configure(values=catalog.labels)
        self.model_list.set(catalog.selected)
        self.model_button.configure(text=f"用{catalog.selected or '所选模型'}生成说明")
        self._generation += 1
        self.model_note.pack_forget()

    def _select_model(self, _event=None):
        app = self.winfo_toplevel()
        try:
            app.model_catalog.select(self.model_list.get())
        except ModelError as exc:
            self.model_list.set(app.model_catalog.selected)
            self.model_note.configure(text=str(exc))
            self.model_note.pack(anchor="w")
            return
        app.model_selection.set(app.model_catalog.selected)

    def _settings(self):
        app = self.winfo_toplevel()
        return configure_model(app, self._settings_applied)

    def _settings_applied(self):
        if self.winfo_exists():
            self._generation += 1
            self.model_note.pack_forget()

    def _send_to_model(self):
        if self._busy or not self.current_text:
            return
        app = self.winfo_toplevel()
        target = app.model_catalog.selected
        answer = self.current_text
        try:
            config = app.model_catalog.connection(app.model_config)
        except ModelError as exc:
            self.model_note.configure(text=str(exc))
            self.model_note.pack(anchor="w")
            return
        if not config.api_key:
            generation = self._generation

            def send_after_apply():
                # 成功保存设置会触发一次列表刷新，其他问题或模型切换使这次发送失效。
                if (self.winfo_exists() and self._generation == generation + 1
                        and self.current_text == answer and app.model_catalog.selected == target):
                    self._send_to_model()

            configure_model(app, send_after_apply)
            return
        generation = self._generation
        messages = Queue()
        self._busy = True
        self.model_button.state(["disabled"])
        self.model_note.configure(text="正在生成模型说明…")
        self.model_note.pack(anchor="w")

        def request():
            try:
                note = "模型补充说明（供参考）\n" + explain_with_model(config, answer)
            except ModelError as exc:
                note = f"模型说明未生成：{exc} 已保留规则回答。"
            messages.put(note)

        def poll():
            self._timer = None
            try:
                note = messages.get_nowait()
            except Empty:
                self._timer = self.after(100, poll)
                return
            self._busy = False
            self.model_button.state(["!disabled"])
            if self._generation == generation and app.model_catalog.selected == target:
                self.model_note.configure(text=note)

        Thread(target=request, daemon=True).start()
        self._timer = self.after(100, poll)

    def _destroyed(self, event):
        if event.widget is self:
            self._selection.trace_remove("write", self._trace)
            if self._timer is not None:
                self.after_cancel(self._timer)
                self._timer = None

    def _copy(self):
        try:
            self.clipboard_clear()
            self.clipboard_append(self.current_text)
        except tk.TclError:
            self.notice.configure(text="复制失败")
        else:
            self.notice.configure(text="已复制")
