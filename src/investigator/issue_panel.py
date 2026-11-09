"""Tk 采集问题详情。选择和历史折叠只改变当前视图。"""

import tkinter as tk
from tkinter import ttk

from .answer_panel import AnswerPanel
from .answers import capture_answer
from .issue_card import format_issue_card, history_source


class IssueDetailFrame(ttk.Frame):
    def __init__(self, parent, session, problems, selected, on_select):
        super().__init__(parent, padding=(0, 4))
        self.session = session
        self.on_select = on_select
        self.selected = None
        ids = [p.ident for p in problems]
        current = selected if selected in ids else ids[0]
        if len(problems) > 1:
            box = ttk.Frame(self)
            box.pack(fill="x")
            self.tree = ttk.Treeview(box, columns=("ident", "label", "state"),
                                     show="headings", selectmode="browse", height=min(len(ids), 4))
            for key, title, width in (("ident", "编号", 68), ("label", "问题摘要", 355),
                                      ("state", "当前状态", 150)):
                self.tree.heading(key, text=title)
                self.tree.column(key, width=width, stretch=key == "label")
            if len(ids) > 4:
                bar = ttk.Scrollbar(box, orient="vertical", command=self.tree.yview)
                self.tree.configure(yscrollcommand=bar.set)
                bar.pack(side="right", fill="y")
            self.tree.pack(side="left", fill="x", expand=True)
            for p in problems:
                state = "范围内关闭" if p.resolved_by else "仍未解决"
                self.tree.insert("", "end", iid=p.ident, values=(p.ident, p.label, state))
            self.tree.selection_set(current)
            self.tree.see(current)
            self.tree.bind("<<TreeviewSelect>>", self._select)
        self.card = ttk.Frame(self)
        self.card.pack(fill="x")
        self._show(current)

    def _select(self, _event):
        selected = self.tree.selection()
        if selected and selected[0] != self.selected:
            self.on_select(selected[0])
            self._show(selected[0])

    def _show(self, ident):
        self.selected = ident
        detail = self.session.get_issue_details(self.session.investigation_id, ident)
        for child in self.card.winfo_children():
            child.destroy()
        self.has_detail = bool(detail)
        if not detail:
            return
        view = format_issue_card(detail)
        self.card.columnconfigure(1, weight=1)
        def label(row, column, text, **options):
            widget = ttk.Label(self.card, text=text, justify="left", **options)
            widget.grid(row=row, column=column, sticky="nw", padx=(4, 8), pady=2)
            return widget
        color = "#dcf1e3" if detail["status"] == "closed_in_scope" else "#fff0cd"
        header = ttk.Label(self.card, text=f"{ident} · {detail['label']}    {view.decision}",
                           background=color, foreground="#172823", padding=(8, 6),
                           font="TkHeadingFont", wraplength=580)
        header.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(4, 4))
        label(1, 0, "判断依据")
        label(1, 1, view.location, font="TkFixedFont", wraplength=525)
        label(2, 1, view.basis, wraplength=525)
        label(3, 0, "待补检查")
        label(3, 1, view.missing, wraplength=525)
        label(4, 0, "交接备注")
        label(4, 1, view.note, wraplength=525)
        if view.repeat_notice:
            label(5, 1, view.repeat_notice, style="Notice.TLabel", wraplength=525)
        controls = ttk.Frame(self.card)
        controls.grid(row=6, column=0, columnspan=2, sticky="w", pady=4)
        history = ttk.Frame(self.card)
        def toggle():
            if history.winfo_manager():
                history.grid_remove()
            else:
                if not history.winfo_children():
                    for line, event in zip(view.history, detail["history"], strict=True):
                        ttk.Label(history, text=line, wraplength=610, justify="left").pack(anchor="w")
                        ttk.Label(history, text=history_source(detail, event), style="Muted.TLabel",
                                  wraplength=610, justify="left").pack(anchor="w", pady=(0, 4))
                history.grid(row=7, column=0, columnspan=2, sticky="w")
            verb = "收起" if history.winfo_manager() else "展开"
            disclosure.configure(text=f"{verb}状态历史（{len(view.history)}）")
        disclosure = ttk.Button(controls, text=f"展开状态历史（{len(view.history)}）", command=toggle)
        disclosure.pack(side="left")
        questions = AnswerPanel(self.card, lambda: capture_answer(detail), show_copy=False)
        questions.grid(row=8, column=0, columnspan=2, sticky="ew", pady=(2, 0))

        def copy():
            try:
                self.clipboard_clear()
                self.clipboard_append(questions.current_text or view.summary)
            except tk.TclError:
                copied.configure(text="复制失败")
            else:
                copied.configure(text="已复制")
        ttk.Button(controls, text="复制交接摘要", command=copy).pack(side="left", padx=6)
        copied = ttk.Label(controls)
        copied.pack(side="left")
