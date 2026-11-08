"""单窗口界面：选报告 → 看懂结果和下一步 → 按需补充结果或保存说明。

三个内容区（目前发现 / 还不能确认 / 下一步）始终在主区域可见；
技术详情和问题历史可折叠。关键错误与未知不进入折叠区。

不含聊天框、账户、模型设置、侧边栏、历史中心、仪表盘、评分或装饰图表。
"""

from __future__ import annotations

import tkinter as tk
from dataclasses import replace
from pathlib import Path
from tkinter import filedialog, font as tkfont, ttk

from .explain import explain_report, unknown_impact
from .export import ExportError, render_markdown, save_markdown
from .guides import (
    FEEDBACK_BLOCKED,
    GUIDE_VERSION,
    MATERIAL_HELP,
    MATERIAL_HELP_FOOTER,
    MATERIALS_VIEW_TITLE,
    PRACTICE_CASES,
    PRACTICE_NOTE,
    current_card,
)
from .issue_panel import IssueDetailFrame
from .reports import SUPPORTED_TYPES, TYPE_LABELS, ReportError, load_report
from .session import Session, new_problem_labels

APP_TITLE = "排查助手"
WINDOW_MIN = (760, 560)
WINDOW_START = (980, 760)

SUPPORTED_TEXT = (
    "本程序目前支持三类报告（按内容和版本识别，不只看扩展名）：\n\n"
    + "\n".join(
        f"• {TYPE_LABELS[name]}：report_type = {name}，schema_version = "
        + "、".join(str(v) for v in sorted(versions))
        for name, versions in SUPPORTED_TYPES.items()
    )
    + "\n\nJSON 内容保存在 .json 或 .txt 文件中都可以。\n"
    "不支持的版本、损坏的 JSON、重复键、缺少必要字段或超出大小限制的文件会被明确拒绝，"
    "并且不会影响已经读到的其他结果。\n\n"
    "报告分别在哪里产生、怎样识别，见首页“报告在哪里 / 我没有报告”。"
)

NO_REPORT_TEXT = (
    "还没有报告时，先确认你手里是哪一类材料。三类材料的来源、识别方法和选择范围：\n\n"
    + "\n\n".join(
        f"【{item.label}】{item.scenario}\n"
        f"• 在哪里找：{item.source}\n"
        f"• 怎样识别：{item.identify}\n"
        f"• 选择范围：{item.scope}"
        for item in MATERIAL_HELP
    )
    + "\n\n" + MATERIAL_HELP_FOOTER
)


class InvestigatorApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(APP_TITLE)
        self.minsize(*WINDOW_MIN)
        self.geometry("{}x{}".format(*WINDOW_START))

        self.session = Session()
        self._notice: str | None = None
        self._view = "welcome"          # welcome | supported | no_report | report
        self._technical_visible = False
        self._selected_issue = None
        self._note_visible = False
        self._pending_addition = None   # (report, explanation) 等待关联回答
        self._pending_question = None   # 待用户回答的那个必要问题
        self._note_draft = ""           # 已输入但尚未“记录说明”的文字
        self._handoff_draft = ""        # 材料帮助页里尚未记录的文字
        self._wrap_labels: list[tk.Label] = []

        self._setup_fonts_and_styles()
        self._build_shell()
        self._bind_keys()
        self._render()

    # ------------------------------------------------ 外观

    def _setup_fonts_and_styles(self) -> None:
        base = tkfont.nametofont("TkDefaultFont")
        base.configure(size=10)
        tkfont.nametofont("TkTextFont").configure(size=10)

        self.font_title = tkfont.Font(family=base.cget("family"), size=16, weight="bold")
        self.font_section = tkfont.Font(family=base.cget("family"), size=12, weight="bold")
        self.font_small = tkfont.Font(family=base.cget("family"), size=9)

        style = ttk.Style(self)
        try:
            style.theme_use("vista")
        except tk.TclError:
            pass

        self.bg = style.lookup("TFrame", "background") or "#f5f5f5"
        self.fg = style.lookup("TLabel", "foreground") or "#1a1a1a"
        self.accent = "#1a5fb4"

        style.configure("Primary.TButton", font=(base.cget("family"), 10, "bold"), padding=(14, 8))
        style.configure("Secondary.TButton", padding=(10, 6))
        style.configure("Link.TButton", padding=(4, 2), relief="flat")
        style.configure("Section.TLabel", font=self.font_section, foreground=self.fg)
        style.configure("Title.TLabel", font=self.font_title, foreground=self.fg)
        style.configure("Muted.TLabel", font=self.font_small, foreground="#5a5a5a")
        style.configure("Notice.TLabel", foreground="#8a3b00", font=(base.cget("family"), 10, "bold"))

    # ------------------------------------------------ 骨架

    def _build_shell(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        header = ttk.Frame(self, padding=(16, 12, 16, 6))
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        self.header_title = ttk.Label(header, text=APP_TITLE, style="Title.TLabel")
        self.header_title.grid(row=0, column=0, sticky="w")
        self.header_sub = ttk.Label(header, text="", style="Muted.TLabel")
        self.header_sub.grid(row=1, column=0, sticky="w", pady=(2, 0))
        self.change_button = ttk.Button(header, text="开始另一件问题",
                                        style="Secondary.TButton",
                                        command=self.choose_report)
        self.change_button.grid(row=0, column=1, rowspan=2, sticky="e")
        self.change_button.grid_remove()
        self.change_hint = ttk.Label(
            header,
            text="将开始一次新调查；当前说明和结果不会带入。需要核对变化请用底部的"
                 "“添加操作后的结果”。",
            style="Muted.TLabel", justify="left", anchor="e",
        )
        self.change_hint.grid(row=2, column=0, columnspan=2, sticky="e", pady=(2, 0))
        self.change_hint.grid_remove()

        container = ttk.Frame(self)
        container.grid(row=1, column=0, sticky="nsew")
        container.columnconfigure(0, weight=1)
        container.rowconfigure(0, weight=1)

        self.canvas = tk.Canvas(container, borderwidth=0, highlightthickness=0,
                                background=self.bg)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        vbar = ttk.Scrollbar(container, orient="vertical", command=self.canvas.yview)
        vbar.grid(row=0, column=1, sticky="ns")
        self.canvas.configure(yscrollcommand=vbar.set)

        self.body = ttk.Frame(self.canvas, padding=(16, 4, 16, 12))
        self._body_id = self.canvas.create_window((0, 0), window=self.body, anchor="nw")
        self.body.columnconfigure(0, weight=1)

        self.body.bind("<Configure>", self._on_body_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self.canvas.bind("<Enter>", lambda _e: self.canvas.bind_all("<MouseWheel>", self._on_wheel))
        self.canvas.bind("<Leave>", lambda _e: self.canvas.unbind_all("<MouseWheel>"))

        footer = ttk.Frame(self, padding=(16, 8, 16, 14))
        footer.grid(row=2, column=0, sticky="ew")
        self.footer = footer

    def _bind_keys(self) -> None:
        self.bind("<Control-o>", lambda _e: self.choose_report())
        self.bind("<Control-s>", lambda _e: self.save_note())
        self.bind("<F5>", lambda _e: self._render())

    def _on_body_configure(self, _event=None) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_configure(self, event) -> None:
        self.canvas.itemconfigure(self._body_id, width=event.width)
        width = max(360, event.width - 60)
        for label in self._wrap_labels:
            try:
                label.configure(wraplength=width)
            except tk.TclError:
                pass

    def _on_wheel(self, event) -> None:
        self.canvas.yview_scroll(int(-event.delta / 120), "units")

    # ------------------------------------------------ 渲染工具

    def _clear_body(self) -> None:
        self._wrap_labels.clear()
        for child in self.body.winfo_children():
            child.destroy()

    def _label(self, parent, text: str, *, style=None, wrap=True, **kwargs) -> ttk.Label:
        label = ttk.Label(parent, text=text, style=style, justify="left", anchor="w")
        if wrap:
            label.configure(wraplength=760)
            self._wrap_labels.append(label)
        label.pack(fill="x", **kwargs)
        return label

    def _section(self, title: str) -> None:
        ttk.Separator(self.body, orient="horizontal").pack(fill="x", pady=(10, 6))
        ttk.Label(self.body, text=title, style="Section.TLabel").pack(fill="x", anchor="w")

    # ------------------------------------------------ 主渲染

    def _capture_drafts(self) -> None:
        """重建控件前保存文字；记录/放弃/新调查显式跳过此步骤。"""
        for widget_name, draft_name in (("note_text", "_note_draft"),
                                       ("handoff_text", "_handoff_draft")):
            widget = getattr(self, widget_name, None)
            if widget is not None and widget.winfo_exists():
                setattr(self, draft_name, widget.get("1.0", "end").strip())

    def _render(self, *, preserve_drafts: bool = True) -> None:
        if preserve_drafts:
            self._capture_drafts()
        self._clear_body()

        if self._view == "supported":
            self._render_info("支持哪些报告", SUPPORTED_TEXT)
            return
        if self._view == "no_report":
            self._render_info(MATERIALS_VIEW_TITLE, NO_REPORT_TEXT)
            self._render_footer()
            self._on_body_configure()
            return
        if self.session.primary is None:
            self._render_welcome()
        else:
            self._render_report()
        self._render_footer()
        self._on_body_configure()

    def _render_info(self, title: str, text: str) -> None:
        self.header_sub.configure(text=title)
        self.change_button.grid_remove()
        self.change_hint.grid_remove()
        self._label(self.body, text, pady=(4, 8))
        if self._view == "no_report":
            self._render_handoff_area()
            self._render_practice_list()
        ttk.Button(self.body, text="返回", style="Secondary.TButton",
                   command=self._go_home).pack(anchor="w", pady=(8, 0))
        self._clear_footer()

    def _render_handoff_area(self) -> None:
        self._section("找不到材料")
        self._label(
            self.body,
            "如果找不到、不能确定是不是这一类材料，可以把情况记下来并保存交接说明；"
            "也可以返回选择已有的合成练习案例。导入报告前不会显示诊断或复验结论。",
            style="Muted.TLabel", pady=(2, 4),
        )
        self.handoff_text = tk.Text(self.body, height=3, wrap="word",
                                    font=tkfont.nametofont("TkTextFont"))
        self.handoff_text.pack(fill="x", pady=(2, 4))
        if self._handoff_draft:
            self.handoff_text.insert("1.0", self._handoff_draft)
        row = ttk.Frame(self.body)
        row.pack(fill="x", anchor="w")
        ttk.Button(row, text="记录找不到 / 不确定", style="Secondary.TButton",
                   command=lambda: self._record_handoff("找不到 / 不确定")).pack(side="left")
        ttk.Button(row, text="记录观察", style="Secondary.TButton",
                   command=lambda: self._record_handoff("观察")).pack(
                       side="left", padx=(8, 0))
        for note in self.session.notes:
            self._label(
                self.body,
                f"• （{note.created_at}）{note.text}（用户声明，未独立验证）",
                style="Muted.TLabel", pady=(2, 0))

    def _record_handoff(self, kind: str) -> None:
        text = self._handoff_text_value()
        if not text:
            self._notice = "请先写一句你找不到的材料或观察到的情况。"
            self._render()
            return
        self.session.add_note(f"{kind}：{text}")
        self._handoff_draft = ""
        self._notice = "已记录（用户声明，未独立验证）。可以用底部“保存交接说明”保存。"
        self._render(preserve_drafts=False)

    def _handoff_text_value(self) -> str:
        widget = getattr(self, "handoff_text", None)
        if widget is None or not widget.winfo_exists():
            return self._handoff_draft
        return widget.get("1.0", "end").strip()

    def _render_practice_list(self) -> None:
        self._section("合成练习案例（可选）")
        self._label(self.body, PRACTICE_NOTE, style="Muted.TLabel", pady=(2, 4))
        for label, filename, description in PRACTICE_CASES:
            self._label(self.body, f"• {label}：{filename} — {description}", pady=(0, 3))
        self._label(
            self.body,
            "这些文件不在本程序中自动生成或扫描；由主持者保存到本地后，用“返回 → "
            "选择报告”导入。合成案例只用于练习识别，不是实拍记录。",
            style="Muted.TLabel", pady=(2, 0),
        )

    def _go_home(self) -> None:
        if self._view == "no_report":
            self._handoff_draft = self._handoff_text_value()
        self._view = "welcome" if self.session.primary is None else "report"
        self._notice = None
        self._render()

    def _render_welcome(self) -> None:
        self.header_sub.configure(text="选择已有报告，了解结果和下一步")
        self.change_button.grid_remove()
        self.change_hint.grid_remove()
        self._label(self.body, "选择已有报告，了解结果和下一步。", pady=(8, 4))
        self._label(
            self.body,
            "本程序只读取你选择的已有文件；不启动摄像头，不重新分析图片，不复算指标。",
            style="Muted.TLabel", pady=(0, 12),
        )
        ttk.Button(self.body, text="选择已有报告", style="Primary.TButton",
                   command=self.choose_report).pack(anchor="w", pady=(0, 10))
        row = ttk.Frame(self.body)
        row.pack(fill="x", anchor="w")
        ttk.Button(row, text=MATERIALS_VIEW_TITLE, style="Link.TButton",
                   command=lambda: self._set_view("no_report")).pack(side="left")
        ttk.Button(row, text="支持哪些报告", style="Link.TButton",
                   command=lambda: self._set_view("supported")).pack(side="left", padx=(12, 0))

    def _set_view(self, view: str) -> None:
        if self._view == "no_report":
            self._handoff_draft = self._handoff_text_value()
        self._view = view
        self._render()

    def _render_report(self) -> None:
        report = self.session.primary
        explanation = self.session.primary_explanation
        self.header_sub.configure(
            text=f"{report.type_label} · 本次先帮你读懂报告"
        )
        self.change_button.grid()
        self.change_hint.grid()

        self._render_notice()

        if report.report_type == "capture_task_review":
            self._section("当前调查")
            state, summary = self.session.investigation_summary()
            problems = self.session.review_problems_by_priority()
            panel = None
            if problems:
                panel = IssueDetailFrame(self.body, self.session, problems, self._selected_issue,
                                         self._select_issue)
            if panel is not None and panel.has_detail:
                self._label(self.body, state, style="Section.TLabel")
                panel.pack(fill="x")
            else:
                if panel is not None:
                    panel.destroy()
                self._label(self.body, f"{state}：{summary}", style="Notice.TLabel")
        # 1. 目前发现
        self._section("原主报告的发现" if report.report_type == "capture_task_review" else "目前发现")
        for item in explanation.findings:
            self._label(self.body, "• " + item, pady=(0, 4))

        # 2. 这份报告还不能说明什么
        self._section("这份报告还不能说明什么")
        if explanation.unknowns:
            for item in explanation.unknowns:
                self._label(self.body, "• " + item, pady=(0, 1))
                self._label(self.body, "  影响：" + unknown_impact(item),
                            style="Muted.TLabel", pady=(0, 5))
        else:
            self._label(self.body, "• 没有额外需要保留的未知项。", style="Muted.TLabel")

        # 3. 当前操作卡（一次只突出一个动作）
        card = current_card(self.session)
        if card is not None:
            self.session.record_suggestion(card)
            self._render_action_card(card)

        # 补充结果后的比较
        if self.session.additions:
            self._section("与之前相比")
            self._label(self.body, "以下为各份补充与原主报告的单次比较；局部结果不替代当前调查结论。",
                        style="Muted.TLabel")
            for index, addition in enumerate(self.session.additions, start=1):
                self._label(
                    self.body,
                    f"补充记录 {index}（{addition.report.type_label}）："
                    f"{addition.recheck_result}",
                    pady=(2, 2),
                )
                self._label(self.body, addition.recheck_reason, style="Muted.TLabel", pady=(0, 2))
                for problem in new_problem_labels(addition):
                    self._label(self.body, "新出现：" + problem, style="Notice.TLabel",
                                pady=(0, 2))
                if addition.comparison_reason != addition.recheck_reason:
                    self._label(self.body, "比较限制：" + addition.comparison_reason,
                                style="Muted.TLabel", pady=(0, 2))
                for change in addition.changes:
                    self._label(self.body, "  - " + change, style="Muted.TLabel", pady=(0, 2))
                if addition.relation.conflict:
                    self._label(self.body, "客观冲突：" + addition.relation.conflict,
                                style="Notice.TLabel", pady=(0, 2))
                self._label(self.body, f"补充记录 {index} 自身的发现：", style="Muted.TLabel")
                for finding in addition.explanation.findings:
                    self._label(self.body, "• " + finding, pady=(0, 2))
                for unknown in addition.explanation.unknowns:
                    self._label(self.body, "仍不能确认：" + unknown,
                                style="Notice.TLabel", pady=(0, 2))

        # 待回答的关联问题
        if self._pending_addition is not None:
            self._render_relation_question()

        # 可选补充说明
        self._render_note_area()

        # 技术详情（折叠）
        self._render_technical(explanation)

    def _select_issue(self, ident: str) -> None:
        self._selected_issue = ident

    def _render_action_card(self, card) -> None:
        self._section("现在做什么")
        self._label(self.body, card.title, pady=(2, 2))
        self._label(
            self.body,
            f"与哪条发现有关（{card.context}）：{card.related}",
            style="Muted.TLabel", pady=(0, 4),
        )
        self._label(self.body, "去哪里：" + card.step.where, pady=(0, 4))
        self._label(self.body, "具体做：", pady=(0, 1))
        for index, action in enumerate(card.step.actions, start=1):
            self._label(self.body, f"  {index}. {action}", pady=(0, 2))
        self._label(self.body, "做完看什么：" + card.step.observe, pady=(2, 4))
        self._label(self.body, "回来后：" + card.step.return_hint, pady=(0, 4))
        self._label(self.body, "做不了、不确定或没有结果时：" + card.step.stop, pady=(0, 4))
        if card.note:
            self._label(self.body, "当前记录：" + card.note, style="Muted.TLabel", pady=(0, 6))

        if card.feedback_choices:
            self._label(self.body, "你做完或尝试后，可以就近记录：",
                        style="Muted.TLabel", pady=(2, 2))
            row = ttk.Frame(self.body)
            row.pack(fill="x", anchor="w", pady=(0, 4))
            for choice, label in card.feedback_choices:
                ttk.Button(
                    row, text=label, style="Secondary.TButton",
                    command=lambda c=choice: self._record_step_feedback(c),
                ).pack(side="left", padx=(0, 8))
        self._label(
            self.body,
            f"指引 {card.guide_id} v{card.guide_version} · 步骤 {card.step_id}。"
            "你的选择只是一条用户声明，不会变成已执行检查或复验通过。",
            style="Muted.TLabel", pady=(2, 4),
        )
        self._label(
            self.body,
            "注意：“我完成了操作”不等于“问题已修好”。需要核对变化时，请补充新的报告。",
            style="Muted.TLabel", pady=(0, 4),
        )

    def _render_notice(self) -> None:
        if not self._notice:
            return
        box = ttk.Frame(self.body)
        box.pack(fill="x", pady=(0, 8))
        ttk.Label(box, text="需要注意", style="Notice.TLabel").pack(anchor="w")
        self._label(box, self._notice, pady=(2, 0))

    def _render_relation_question(self) -> None:
        report, _explanation = self._pending_addition
        self._section("需要确认一件事")
        question = self._pending_question
        self._label(self.body, question, pady=(2, 6))
        row = ttk.Frame(self.body)
        row.pack(fill="x", anchor="w", pady=(0, 8))
        ttk.Button(row, text="是，同一件事", style="Secondary.TButton",
                   command=lambda: self._answer_relation("yes")).pack(side="left")
        ttk.Button(row, text="不是，另一件事", style="Secondary.TButton",
                   command=lambda: self._answer_relation("no")).pack(side="left", padx=(8, 0))
        ttk.Button(row, text="不确定", style="Secondary.TButton",
                   command=lambda: self._answer_relation("unsure")).pack(side="left", padx=(8, 0))

    def _render_note_area(self) -> None:
        self._section("补充说明（可选）")
        self._label(
            self.body,
            "只记录你做过什么、主观上是否改善。它始终算用户反馈，不会变成已执行检查或复验通过。",
            style="Muted.TLabel", pady=(2, 4),
        )
        self._label(
            self.body,
            "当前操作卡已提供简短选择时，用那几个按钮就够了；这里适合写更完整的观察。",
            style="Muted.TLabel", pady=(0, 4),
        )
        if not self._note_visible:
            ttk.Button(self.body, text="▸ 添加我的说明", style="Link.TButton",
                       command=self._show_note).pack(anchor="w")
            if self.session.notes:
                for note in self.session.notes:
                    self._label(self.body, f"• （{note.created_at}）{note.text}",
                                style="Muted.TLabel", pady=(2, 0))
            return

        self.note_text = tk.Text(self.body, height=4, wrap="word", font=tkfont.nametofont("TkTextFont"))
        self.note_text.pack(fill="x", pady=(2, 4))
        if self._note_draft:
            self.note_text.insert("1.0", self._note_draft)
        row = ttk.Frame(self.body)
        row.pack(fill="x", anchor="w")
        ttk.Button(row, text="记录说明", style="Secondary.TButton",
                   command=self._record_note).pack(side="left")
        ttk.Button(row, text="收起", style="Link.TButton",
                   command=self._hide_note).pack(side="left", padx=(8, 0))
        for note in self.session.notes:
            self._label(self.body, f"• （{note.created_at}）{note.text}",
                        style="Muted.TLabel", pady=(2, 0))
        self.note_text.focus_set()

    def _render_technical(self, explanation) -> None:
        self._section("技术详情")
        ttk.Button(
            self.body,
            text=("▾ 收起技术详情" if self._technical_visible else "▸ 查看技术详情"),
            style="Link.TButton",
            command=self._toggle_technical,
        ).pack(anchor="w")
        if not self._technical_visible:
            return
        self._render_explanation_details(explanation, "主报告")
        for index, addition in enumerate(self.session.additions, start=1):
            self._render_explanation_details(addition.explanation, f"补充记录 {index}")

    def _render_explanation_details(self, explanation, context: str) -> None:
        self._label(self.body, context, style="Muted.TLabel", pady=(6, 0))
        frame = ttk.Frame(self.body)
        frame.pack(fill="x", pady=(6, 0))
        frame.columnconfigure(1, weight=1)
        for row, (label, value) in enumerate(explanation.technical):
            ttk.Label(frame, text=label, style="Muted.TLabel").grid(
                row=row, column=0, sticky="nw", padx=(0, 12), pady=1)
            ttk.Label(frame, text=str(value), justify="left", anchor="w",
                      wraplength=560).grid(row=row, column=1, sticky="w", pady=1)

        if explanation.evidence:
            ttk.Label(self.body, text="证据定位", style="Muted.TLabel").pack(
                anchor="w", pady=(10, 2))
            for ident, locator, note in explanation.evidence:
                self._label(self.body, f"{context}/{ident}  {locator}  {note}".rstrip(),
                            style="Muted.TLabel", pady=(0, 1))

    # ------------------------------------------------ 页脚按钮

    def _clear_footer(self) -> None:
        for child in self.footer.winfo_children():
            child.destroy()

    def _render_footer(self) -> None:
        self._clear_footer()
        if self.session.primary is None:
            if self._has_handoff_content():
                row = ttk.Frame(self.footer)
                row.pack(fill="x")
                ttk.Button(row, text="保存交接说明", style="Secondary.TButton",
                           command=self.save_note).pack(side="left")
            return
        row = ttk.Frame(self.footer)
        row.pack(fill="x")
        self.addition_button = ttk.Button(
            row, text="添加操作后的结果", style="Primary.TButton",
            command=self.choose_addition,
        )
        self.addition_button.pack(side="left")
        ttk.Button(row, text="保存说明", style="Secondary.TButton",
                   command=self.save_note).pack(side="left", padx=(10, 0))
        ttk.Button(row, text="报告在哪里 / 我没有报告", style="Link.TButton",
                   command=lambda: self._set_view("no_report")).pack(side="left",
                                                                    padx=(10, 0))
        ttk.Label(row, text="保留原报告并核对变化", style="Muted.TLabel").pack(
            side="left", padx=(8, 0))

    # ------------------------------------------------ 动作

    def choose_report(self) -> None:
        if self.session.primary is not None:
            choice = self._ask_report_or_addition()
            if choice == "addition":
                self.choose_addition()
                return
            if choice != "new":
                return
        if not self._confirm_new_investigation():
            return
        path = filedialog.askopenfilename(
            title="选择一份已有报告（开始新调查；核对变化请用“添加操作后的结果”）",
            filetypes=[("报告文件", "*.json *.txt"), ("JSON", "*.json"), ("文本", "*.txt")],
        )
        if not path:
            return
        self._load(path, as_addition=False)

    def choose_addition(self) -> None:
        if not self._confirm_add_addition():
            return
        path = filedialog.askopenfilename(
            title="添加操作后的结果（保留原报告并核对变化）",
            filetypes=[("报告文件", "*.json *.txt"), ("JSON", "*.json"), ("文本", "*.txt")],
        )
        if not path:
            return
        self._load(path, as_addition=True)

    def _load(self, path: str, *, as_addition: bool) -> None:
        name = Path(path).name
        try:
            report = load_report(path)
            explanation = explain_report(report)
            new_investigation = not as_addition or self.session.primary is None
            relation = None if new_investigation else self.session.assess_relation(report)
            prepared = None
            if new_investigation:
                prepared = Session()
                prepared.load_primary(report, explanation)
            elif not relation.question:
                prepared = replace(self.session, additions=list(self.session.additions),
                                   notes=list(self.session.notes),
                                   suggestions=list(self.session.suggestions),
                                   feedbacks=list(self.session.feedbacks))
                prepared.add_addition(report, explanation)
            if prepared is not None:
                current_card(prepared)
        except ReportError as error:
            self._notice = (
                f"无法读取 {name}：{error.message}（代码：{error.code}）。"
                f"下一步：确认这是受支持的报告文件，或改选另一份。"
            )
            self._render()
            return
        except Exception as error:  # noqa: BLE001 - 任何意外都只提示，不弹堆栈
            self._notice = f"读取 {name} 时出现未预期的问题：{type(error).__name__}。请改选另一份文件。"
            self._render()
            return

        self._notice = None
        if new_investigation:
            self.session = prepared
            self._view = "report"
            self._pending_addition = None
            self._pending_question = None
            self._technical_visible = False
            self._selected_issue = None
            self._note_visible = False
            self._note_draft = ""
            self._handoff_draft = ""
            self._render(preserve_drafts=False)
            return

        if relation.question:
            self._pending_addition = (report, explanation)
            self._pending_question = relation.question
            self._render()
            return
        self.session = prepared
        self._render()

    def _answer_relation(self, answer: str) -> None:
        if self._pending_addition is None:
            return
        report, explanation = self._pending_addition
        self.session.add_addition(report, explanation, relation_answer=answer)
        self._pending_addition = None
        self._pending_question = None
        self._render()

    def _toggle_technical(self) -> None:
        # 重渲染会销毁说明输入框；先保住草稿，避免展开技术详情时丢字。
        self._note_draft = self._note_text_value()
        self._technical_visible = not self._technical_visible
        self._render()

    def _show_note(self) -> None:
        self._note_draft = self._note_text_value()
        self._note_visible = True
        self._render()

    def _hide_note(self) -> None:
        # 收起不等于记录：保留草稿，重新展开时还在。
        self._note_draft = self._note_text_value()
        self._note_visible = False
        self._render()

    def _note_text_value(self) -> str:
        widget = getattr(self, "note_text", None)
        if widget is None or not widget.winfo_exists():
            return self._note_draft
        return widget.get("1.0", "end").strip()

    def _record_step_feedback(self, choice: str) -> None:
        card = current_card(self.session)
        if card is None:
            return
        self.session.record_suggestion(card)
        self.session.add_step_feedback(card, choice)
        self._notice = None
        if choice == FEEDBACK_BLOCKED:
            self._notice = (
                "已记录“做不了或不确定”。当前卡会改为交接出口；"
                "仍然可以保存说明。"
            )
        self._render()

    def _record_note(self) -> None:
        text = self._note_text_value()
        if not text:
            self._notice = "说明内容为空，没有记录。"
            self._render()
            return
        self.session.add_note(text)
        self._note_draft = ""
        self._note_visible = True   # 保持打开：连续记录多条时不用反复展开
        self._render(preserve_drafts=False)

    def preview_and_save(self) -> bool:
        """预览 → 选择位置 → 独占新建。只有写入成功返回 True。

        预览与保存复用同一份 ``payload``；取消或失败都不改未保存状态。
        没有报告时也可以保存交接说明（只含用户声明和“无法判断”）。
        """
        if self.session.primary is None and not self._has_handoff_content():
            self._notice = "还没有可保存的内容：请选择报告，或记录一条交接说明。"
            self._render()
            return False
        payload = render_markdown(self.session)
        preview = ExportPreview(self, payload, on_save=self._save_payload)
        saved_name = preview.show()
        if saved_name is None:
            return False
        self.session.mark_saved()
        self._notice = f"已保存说明：{saved_name}（未附原始文件，技术人员可能仍需另行索取）。"
        self._render()
        return True

    def _save_payload(self, payload: str) -> str | None:
        """在预览窗口里选择目标并写入；返回文件名，取消或失败返回 None。"""
        target = filedialog.asksaveasfilename(
            title="保存说明",
            defaultextension=".md",
            filetypes=[("Markdown", "*.md")],
        )
        if not target:
            return None
        try:
            saved = save_markdown(self.session, target, payload=payload)
        except ExportError as error:
            show_export_error(self, error)
            return None
        return saved.name

    # 保留旧名称，供键盘快捷键与外部调用。
    def save_note(self) -> bool:
        return self.preview_and_save()

    def _has_handoff_content(self) -> bool:
        return bool(self.session.notes or self.session.feedbacks)

    # ------------------------------------------------ 未保存内容

    def _pending_draft(self) -> bool:
        return bool(self._note_text_value() or self._handoff_text_value())

    def _confirm_new_investigation(self) -> bool:
        """选择主报告前：先让用户处理当前调查的内容。只有可以继续才返回 True。"""
        if not self._confirm_discard():
            return False
        if self._pending_draft():
            return self._ask_discard_draft()
        return True

    def _confirm_add_addition(self) -> bool:
        draft = self._note_text_value()
        if not draft:
            return True
        choice = self._ask_draft_choice(keep_option=True)
        if choice == "keep":
            self.session.add_note(draft)
            self._note_draft = ""
        elif choice == "discard":
            self._note_draft = ""
        else:
            return False
        self._render(preserve_drafts=False)
        return True

    def _confirm_discard(self) -> bool:
        if not self.session.has_unsaved_content():
            return True
        return self._ask_unsaved()

    def _ask_unsaved(self) -> bool:
        """返回 True 表示可以继续（已保存成功或用户明确放弃）。"""
        dialog = tk.Toplevel(self)
        dialog.title("还有未保存的内容")
        dialog.transient(self)
        dialog.grab_set()
        result = {"ok": False}
        finish = self._write_guard(dialog, result,
                                   "你还有未保存的用户说明或补充结果。")

        def save_then_maybe_continue() -> None:
            if self.preview_and_save():
                finish(True)
                return
            # 预览抢走了模态；取消或失败后回到本对话框，避免主窗口被误点。
            dialog.grab_set()

        ttk.Label(dialog, text="继续会丢失这些内容。",
                  padding=(14, 0, 14, 10)).pack(anchor="w")
        row = ttk.Frame(dialog, padding=(14, 0, 14, 14))
        row.pack(fill="x")
        ttk.Button(row, text="保存说明", style="Primary.TButton",
                   command=save_then_maybe_continue).pack(side="left")
        ttk.Button(row, text="放弃本次内容", style="Secondary.TButton",
                   command=lambda: finish(True)).pack(side="left", padx=(8, 0))
        ttk.Button(row, text="返回", style="Secondary.TButton",
                   command=lambda: finish(False)).pack(side="left", padx=(8, 0))

        dialog.wait_window()
        return result["ok"]

    def _ask_discard_draft(self) -> bool:
        """关闭或切换时，已输入但未记录的文字会丢失；必须明确选择才能继续。"""
        return self._ask_draft_choice(keep_option=False) == "discard"

    def _ask_report_or_addition(self) -> str:
        """已有调查时点“选择报告”：先分清新调查与补充结果。返回 new/addition/cancel。"""
        if self._note_text_value():
            self._note_draft = self._note_text_value()
        dialog = tk.Toplevel(self)
        dialog.title("开始新调查还是添加结果")
        dialog.transient(self)
        dialog.grab_set()
        result = {"choice": "cancel"}
        finish = self._write_guard_choice(dialog, result)
        ttk.Label(
            dialog,
            text="你现在已经打开了一份调查。要开始另一件问题（新调查），还是继续当前调查、"
                 "添加操作后的新结果？",
            wraplength=440, justify="left", padding=(14, 14, 14, 4),
        ).pack(anchor="w")
        ttk.Label(
            dialog,
            text="新调查不会带入当前说明和结果；添加结果会保留原报告并核对变化。",
            wraplength=440, justify="left", padding=(14, 0, 14, 10),
        ).pack(anchor="w")
        row = ttk.Frame(dialog, padding=(14, 0, 14, 14))
        row.pack(fill="x")
        ttk.Button(row, text="添加操作后的结果", style="Primary.TButton",
                   command=lambda: finish("addition")).pack(side="left")
        ttk.Button(row, text="开始另一件问题", style="Secondary.TButton",
                   command=lambda: finish("new")).pack(side="left", padx=(8, 0))
        ttk.Button(row, text="返回", style="Secondary.TButton",
                   command=lambda: finish("cancel")).pack(side="left", padx=(8, 0))
        dialog.wait_window()
        return result["choice"]

    def _ask_draft_choice(self, *, keep_option: bool) -> str:
        """返回 keep（先记录为说明）、discard（放弃草稿）或 cancel（返回）。"""
        dialog = tk.Toplevel(self)
        dialog.title("还有未记录的说明")
        dialog.transient(self)
        dialog.grab_set()
        result = {"choice": "cancel"}
        finish = self._write_guard_choice(dialog, result)
        ttk.Label(dialog, text="你输入了说明，但还没有点“记录说明”。",
                  padding=(14, 14, 14, 4)).pack(anchor="w")
        ttk.Label(dialog, text="这段文字还没有进入说明，继续会丢失它。",
                  padding=(14, 0, 14, 10)).pack(anchor="w")
        row = ttk.Frame(dialog, padding=(14, 0, 14, 14))
        row.pack(fill="x")
        ttk.Button(row, text="返回填写", style="Primary.TButton",
                   command=lambda: finish("cancel")).pack(side="left")
        if keep_option:
            ttk.Button(row, text="先记录并继续", style="Secondary.TButton",
                       command=lambda: finish("keep")).pack(side="left", padx=(8, 0))
        ttk.Button(row, text="放弃这段文字并继续", style="Secondary.TButton",
                   command=lambda: finish("discard")).pack(side="left", padx=(8, 0))
        dialog.wait_window()
        return result["choice"]

    @staticmethod
    def _write_guard_choice(dialog: tk.Toplevel, result: dict):
        """草稿选择框：返回值写回 result['choice'] 后关窗并恢复主窗口模态。"""
        owner = dialog.master

        def finish(choice: str) -> None:
            result["choice"] = choice
            try:
                dialog.grab_release()
            except tk.TclError:
                pass
            dialog.destroy()
            try:
                owner.grab_set()
            except tk.TclError:
                pass

        dialog.protocol("WM_DELETE_WINDOW", lambda: finish("cancel"))
        return finish

    @staticmethod
    def _write_guard(dialog: tk.Toplevel, result: dict, message: str):
        """把结果写回 ``result`` 并关窗。

        预览窗口也是模态的：关掉本对话框的 grab 再打开预览，结束后恢复，
        否则预览和保存对话框可能被挡在下面、用户无法点击。
        """
        ttk.Label(dialog, text=message, padding=(14, 14, 14, 6)).pack(anchor="w")
        owner = dialog.master

        def finish(value: bool) -> None:
            result["ok"] = value
            try:
                dialog.grab_release()
            except tk.TclError:
                pass
            dialog.destroy()
            try:
                owner.grab_set()
            except tk.TclError:
                pass

        dialog.protocol("WM_DELETE_WINDOW", lambda: finish(False))
        return finish

    def on_close(self) -> None:
        if not self._confirm_new_investigation():
            return
        self.destroy()


class ExportPreview:
    """导出预览：只读展示将写入的完整内容，保存时原样写入。"""

    def __init__(self, app: tk.Tk, payload: str, on_save) -> None:
        self.app = app
        self.payload = payload
        self._on_save = on_save
        self.saved_name: str | None = None
        self.dialog = tk.Toplevel(app)
        self.dialog.title("预览说明")
        self.dialog.transient(app)
        self.dialog.minsize(700, 520)
        self.dialog.geometry("820x680")
        self.dialog.columnconfigure(0, weight=1)
        self.dialog.rowconfigure(1, weight=1)

        ttk.Label(
            self.dialog,
            text="以下是即将保存的完整说明。它只在本地保存，不会上传或发送；"
                 "关闭前请检查是否包含不愿分享的内容。",
            wraplength=760, justify="left", padding=(14, 12, 14, 6),
        ).grid(row=0, column=0, sticky="ew")

        body = ttk.Frame(self.dialog, padding=(14, 0, 14, 8))
        body.grid(row=1, column=0, sticky="nsew")
        body.columnconfigure(0, weight=1)
        body.rowconfigure(0, weight=1)
        self.text = tk.Text(body, wrap="word", height=24, borderwidth=1, relief="solid",
                            font=tkfont.nametofont("TkTextFont"))
        self.text.grid(row=0, column=0, sticky="nsew")
        bar = ttk.Scrollbar(body, orient="vertical", command=self.text.yview)
        bar.grid(row=0, column=1, sticky="ns")
        self.text.insert("1.0", payload)   # 先写入，再把控件设为只读，避免内容为空
        self.text.configure(yscrollcommand=bar.set, state="disabled")

        row = ttk.Frame(self.dialog, padding=(14, 0, 14, 14))
        row.grid(row=2, column=0, sticky="ew")
        self.save_button = ttk.Button(row, text="保存", style="Primary.TButton",
                                      command=self._save)
        self.save_button.pack(side="left")
        ttk.Button(row, text="返回", style="Secondary.TButton",
                   command=self.dialog.destroy).pack(side="left", padx=(8, 0))
        self.dialog.protocol("WM_DELETE_WINDOW", self.dialog.destroy)

    def _save(self) -> None:
        name = self._on_save(self.payload)
        if name is None:
            # 取消或失败：留在预览窗口，内容与未保存状态都不变。
            # 文件对话框/错误提示关闭后会丢失模态，这里恢复。
            self.dialog.lift()
            self.dialog.grab_set()
            return
        self.saved_name = name
        self.dialog.destroy()

    def show(self) -> str | None:
        self.dialog.grab_set()
        self.dialog.wait_window()
        return self.saved_name


def show_export_error(app: tk.Tk, error: ExportError) -> None:
    dialog = tk.Toplevel(app)
    dialog.title("没有保存成功")
    dialog.transient(app)
    dialog.grab_set()
    ttk.Label(dialog, text=f"没有保存成功：{error.message}",
              wraplength=420, justify="left", padding=(14, 14, 14, 6)).pack(anchor="w")
    ttk.Label(dialog, text="本次内容仍在窗口里，可以换个名称重试。",
              wraplength=420, justify="left", padding=(14, 0, 14, 10)).pack(anchor="w")
    ttk.Button(dialog, text="返回", style="Secondary.TButton",
               command=dialog.destroy).pack(anchor="e", padx=14, pady=(0, 14))
    dialog.wait_window()


def main() -> int:
    app = InvestigatorApp()
    app.protocol("WM_DELETE_WINDOW", app.on_close)
    app.mainloop()
    return 0
