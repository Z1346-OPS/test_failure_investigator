"""在调查或问题卡中选择固定问题，显示可复制的离线回答。"""

import tkinter as tk
from tkinter import ttk

from .answers import QUESTIONS


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
            if self.copy_controls is not None:
                self.notice.configure(text="")
                self.copy_controls.pack(anchor="w")

    def _copy(self):
        try:
            self.clipboard_clear()
            self.clipboard_append(self.current_text)
        except tk.TclError:
            self.notice.configure(text="复制失败")
        else:
            self.notice.configure(text="已复制")
