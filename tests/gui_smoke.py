"""真实图形界面冒烟：启动窗口 → 选报告 → 看解释 → 补充结果 → 预览并保存说明。

这是交互验证，不是单元测试的替代品：它创建真实的 Tk 窗口、真实的控件树，
并驱动真实的按钮回调（只把“用户选文件”这一步替换为固定路径）。

用法（项目根）：
    .\\.venv\\Scripts\\python.exe -X utf8 tests\\gui_smoke.py [输出目录]

退出码 0 = 全部步骤通过；1 = 有步骤失败；2 = 无法创建图形环境。
"""

from __future__ import annotations

import ctypes
import struct
import sys
import tempfile
import time
import traceback
import zlib
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

import tkinter as tk  # noqa: E402
from tkinter import ttk  # noqa: E402

from tests import synthetic  # noqa: E402
from tests.gui_assertions import unnegated_claims  # noqa: E402
from investigator import ui as ui_module  # noqa: E402
from investigator.guides import current_card  # noqa: E402
from investigator.reports import MAX_ARRAY_ELEMENTS  # noqa: E402
from investigator.ui import InvestigatorApp  # noqa: E402

CHECKS: list[tuple[str, bool, str]] = []
ERRORS: list[str] = []           # 对话框驱动或 Tk 回调里的意外错误
EXPECTED_ERRORS: list[str] = []  # 受控场景中预期出现的（保存失败等）
SCHEDULED: list[tuple[object, str]] = []  # (owner, after id)，销毁前统一取消


def schedule(owner, delay: int, callback) -> str:
    """登记 after 回调；窗口销毁前取消，避免 Tcl 报 invalid command name。"""
    after_id = owner.after(max(1, delay), callback)
    SCHEDULED.append((owner, after_id))
    return after_id


def cancel_pending(owner) -> None:
    for entry in [item for item in SCHEDULED if item[0] is owner]:
        SCHEDULED.remove(entry)
        try:
            owner.after_cancel(entry[1])
        except tk.TclError:
            pass


def check(name: str, ok: bool, detail: str = "") -> None:
    CHECKS.append((name, bool(ok), detail))


def widget_texts(widget) -> list[str]:
    """递归收集控件树里的可见文本。"""
    found: list[str] = []
    try:
        text = widget.cget("text")
        if text:
            found.append(str(text))
    except tk.TclError:
        pass
    if isinstance(widget, tk.Text):
        found.append(widget.get("1.0", "end").strip())
    for child in widget.winfo_children():
        found.extend(widget_texts(child))
    return found


def body_texts(app: InvestigatorApp) -> list[str]:
    return widget_texts(app.body)


def footer_buttons(app: InvestigatorApp) -> list[str]:
    return [t for t in widget_texts(app.footer) if t]


# ---------------------------------------------------------------- 对话框驱动

def find_button(widget, text: str):
    for child in widget.winfo_children():
        try:
            if isinstance(child, ttk.Button) and str(child.cget("text")) == text:
                return child
        except tk.TclError:
            pass
        found = find_button(child, text)
        if found is not None:
            return found
    return None


def find_toplevel(app, title: str):
    for window in app.winfo_children():
        try:
            if isinstance(window, tk.Toplevel) and window.winfo_exists() \
                    and window.title() == title:
                return window
        except tk.TclError:
            pass
    return None


def wait_for_toplevel(app, title: str, tries: int = 100):
    for _ in range(tries):
        window = find_toplevel(app, title)
        if window is not None:
            return window
        app.update()
        time.sleep(0.02)
    return None


def preview_text(window) -> str:
    for child in window.winfo_children():
        if isinstance(child, tk.Text):
            return child.get("1.0", "end")
        found = preview_text(child)
        if found:
            return found
    return ""


def when_toplevel(app, title: str, callback, tries: int = 250,
                  interval: int = 20) -> None:
    """非阻塞地等某个对话框出现，出现后调用 callback(window)。

    不能同步等待：下一个对话框往往在上一个对话框 ``wait_window`` 退栈期间才创建，
    在定时器回调里循环 ``update()`` 会挡住主线程，双方互相等待而卡死。
    """
    def probe(remaining: int) -> None:
        try:
            app.tk.call("info", "exists", app)   # 解释器/窗口已销毁则不再访问
            if not app.winfo_exists():           # 窗口已按预期关闭，不再等待
                return
            window = find_toplevel(app, title)
        except tk.TclError:              # 解释器已销毁：视为窗口已关闭
            return
        if window is not None:
            callback(window)
            return
        if remaining <= 0:
            ERRORS.append(f"没有出现对话框：{title}")
            return
        schedule(app, interval, lambda: probe(remaining - 1))

    schedule(app, 1, lambda: probe(tries))


def handle_preview(app, action, clicked: list[str], capture: list | None,
                   close_window: bool = True) -> None:
    """在预览窗口出现后：记录内容 → 执行动作（如保存）→ 处理错误 → 关闭窗口。"""
    def on_preview(preview) -> None:
        clicked.append("预览说明")
        if capture is not None:
            capture.append(preview_text(preview))
        action()
        save = find_button(preview, "保存")
        if save is not None and preview.winfo_exists():
            clicked.append("保存")
            # 保存失败会弹出模态错误框；先排好关闭动作，否则 invoke 会阻塞在这里。
            watch = schedule(app, 1, lambda: close_export_error(app))
            save.invoke()
            # 保存成功会直接关闭窗口（连同主窗口）：撤掉没机会执行的看门回调，
            # 否则 Tcl 会在窗口销毁后报 invalid command name。
            try:
                app.after_cancel(watch)
            except tk.TclError:
                pass
        if close_window and preview.winfo_exists():
            preview.destroy()   # 模拟用户关闭预览（取消）

    when_toplevel(app, "预览说明", on_preview)


def drive_dialog(app, title: str, button: str, action, fires: int = 1,
                 capture: list | None = None, then_click: str | None = None,
                 expect_preview: bool = False) -> list[str]:
    """等对话框出现，点按钮；预览窗口再按脚本完成保存并关闭。

    对话框按钮的回调会在预览窗口里阻塞，所以预览由另一个 after 回调驱动。
    ``then_click``：保存取消/失败后提示框仍在，点它选择的后续按钮（如“返回”）。
    """
    clicked: list[str] = []

    def on_dialog(window) -> None:
        target = find_button(window, button)
        if target is None:
            ERRORS.append(f"对话框 {title} 里没有按钮：{button}")
            return
        clicked.append(button)
        if expect_preview:
            handle_preview(app, action, clicked, capture)
        try:
            target.invoke()   # 保存路径会在这里进入预览的 wait_window
        except tk.TclError as error:
            ERRORS.append(f"点击 {title}/{button} 失败：{error}")
            return
        dialog = find_toplevel(app, title)
        if then_click and dialog is not None:
            follow = find_button(dialog, then_click)
            if follow is not None:
                clicked.append(then_click)
                follow.invoke()

    schedule(app, fires, lambda: when_toplevel(app, title, on_dialog))
    return clicked


def drive_preview(app, action, fires: int = 1, capture: list | None = None) -> list[str]:
    """直接驱动“保存说明”后的预览窗口。"""
    clicked: list[str] = []
    schedule(app, fires, lambda: handle_preview(app, action, clicked, capture))
    return clicked


def drive_steps(app, steps, fires: int = 1) -> list[str]:
    """按顺序驱动多个模态对话框。

    每个元素为 (标题, 按钮, 是否进入预览保存, 之后点哪个按钮, 预览内容收集)。
    下一步在点击当前按钮前排入事件队列：按钮回调可能一直阻塞到下一个对话框关闭。
    """
    clicked: list[str] = []

    def run_step(index: int) -> None:
        if index >= len(steps):
            return
        title, button, expect_preview, then_click, capture = steps[index]

        def on_dialog(window) -> None:
            target = find_button(window, button)
            if target is None:
                ERRORS.append(f"对话框 {title} 里没有按钮：{button}")
                return
            clicked.append(button)
            # 下一步在点击当前按钮前就排入队列：回调可能阻塞到下一个对话框关闭。
            if index + 1 < len(steps):
                schedule(app, 1, lambda: run_step(index + 1))
            if expect_preview:
                handle_preview(app, lambda: None, clicked, capture)
            try:
                target.invoke()
            except tk.TclError as error:
                ERRORS.append(f"点击 {title}/{button} 失败：{error}")
                return
            if then_click:
                dialog = find_toplevel(app, title)
                if dialog is not None:
                    follow = find_button(dialog, then_click)
                    if follow is not None:
                        clicked.append(then_click)
                        follow.invoke()

        when_toplevel(app, title, on_dialog)

    schedule(app, fires, lambda: run_step(0))
    return clicked


def drive_choose_report(app, *steps, fires: int = 1) -> list[str]:
    """已有调查时点“选择报告”：先选“开始另一件问题”，再按给定顺序处理后续提示。"""
    chain = [("开始新调查还是添加结果", "开始另一件问题", False, None, None), *steps]
    return drive_steps(app, chain, fires=fires)


def close_export_error(app) -> None:
    """保存失败会弹出错误对话框；记录并关闭，避免模态阻塞。"""
    window = wait_for_toplevel(app, "没有保存成功", tries=20)
    if window is None:
        return
    EXPECTED_ERRORS.append("保存失败时显示了错误对话框")
    back = find_button(window, "返回")
    if back is not None:
        back.invoke()
    if window.winfo_exists():
        window.destroy()


# ---------------------------------------------------------------- 截图

def capture_window(app: InvestigatorApp, target: Path) -> bool:
    """用 GDI PrintWindow 抓取窗口并写成 PNG（不需要第三方库）。"""
    try:
        import ctypes.wintypes  # noqa: F401  (Windows 类型需要显式导入)
        user32 = ctypes.windll.user32
        gdi32 = ctypes.windll.gdi32

        class BITMAPINFOHEADER(ctypes.Structure):
            _fields_ = [("biSize", ctypes.c_uint32), ("biWidth", ctypes.c_int32),
                        ("biHeight", ctypes.c_int32), ("biPlanes", ctypes.c_uint16),
                        ("biBitCount", ctypes.c_uint16), ("biCompression", ctypes.c_uint32),
                        ("biSizeImage", ctypes.c_uint32), ("biXPelsPerMeter", ctypes.c_int32),
                        ("biYPelsPerMeter", ctypes.c_int32), ("biClrUsed", ctypes.c_uint32),
                        ("biClrImportant", ctypes.c_uint32)]

        class BITMAPINFO(ctypes.Structure):
            _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", ctypes.c_uint32 * 3)]

        # 让 Tk 完成布局与重绘，否则刚创建的窗口可能还没画上按钮。
        app.update_idletasks()
        app.update()
        time.sleep(0.35)
        app.update()

        hwnd = user32.GetAncestor(app.winfo_id(), 2)  # GA_ROOT
        rect = ctypes.wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        width = rect.right - rect.left
        height = rect.bottom - rect.top
        if width <= 0 or height <= 0:
            return False

        hdc = user32.GetWindowDC(hwnd)
        memdc = gdi32.CreateCompatibleDC(hdc)
        bitmap = gdi32.CreateCompatibleBitmap(hdc, width, height)
        gdi32.SelectObject(memdc, bitmap)
        user32.PrintWindow(hwnd, memdc, 2)  # PW_RENDERFULLCONTENT

        info = BITMAPINFO()
        info.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        info.bmiHeader.biWidth = width
        info.bmiHeader.biHeight = -height
        info.bmiHeader.biPlanes = 1
        info.bmiHeader.biBitCount = 32
        info.bmiHeader.biCompression = 0
        buffer = ctypes.create_string_buffer(width * height * 4)
        gdi32.GetDIBits(memdc, bitmap, 0, height, buffer, ctypes.byref(info), 0)

        rows = []
        for y in range(height):
            line = buffer.raw[y * width * 4:(y + 1) * width * 4]
            # BGRA -> RGB
            rows.append(b"".join(
                line[x * 4 + 2:x * 4 + 3] + line[x * 4 + 1:x * 4 + 2] + line[x * 4:x * 4 + 1]
                for x in range(width)
            ))

        def chunk(tag: bytes, data: bytes) -> bytes:
            return (struct.pack(">I", len(data)) + tag + data
                    + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

        raw = b"".join(b"\x00" + row for row in rows)
        png = (b"\x89PNG\r\n\x1a\n"
               + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
               + chunk(b"IDAT", zlib.compress(raw))
               + chunk(b"IEND", b""))
        target.write_bytes(png)

        gdi32.DeleteObject(bitmap)
        gdi32.DeleteDC(memdc)
        user32.ReleaseDC(hwnd, hdc)
        return True
    except Exception:  # noqa: BLE001 - 截图失败不影响冒烟结论
        traceback.print_exc()
        return False


# ---------------------------------------------------------------- 冒烟

def make_app() -> InvestigatorApp:
    app = InvestigatorApp()
    original = app.report_callback_exception

    def report_callback_exception(exc, val, tb) -> None:
        ERRORS.append(f"{exc.__name__}: {val}")
        original(exc, val, tb)

    app.report_callback_exception = report_callback_exception
    return app


def alive(app) -> bool:
    try:
        return bool(app.winfo_exists())
    except tk.TclError:
        return False


def shutdown(app, shots_done: bool = False) -> None:
    """结束一个窗口实例：撤销排队的驱动回调并销毁。

    同一进程里多个 Tk 解释器共用屏幕级 grab；上一个窗口残留的 grab 会让
    下一个窗口的预览 ``grab_set`` 失败（another application has grab）。
    """
    if not shots_done and alive(app):
        cancel_pending(app)
        try:
            app.destroy()
        except tk.TclError:
            pass


def load_primary(app, path: Path) -> None:
    """新窗口没有已打开的调查：直接选文件，不经过“新调查/加结果”询问。"""
    with mock.patch.object(ui_module.filedialog, "askopenfilename", return_value=str(path)):
        app.choose_report()
    app.update()


def load_addition(app, path: Path) -> None:
    with mock.patch.object(ui_module.filedialog, "askopenfilename", return_value=str(path)):
        app.choose_addition()
    app.update()


def run(workdir: Path) -> int:
    samples = synthetic.write_sample_set(workdir / "samples")
    shots = workdir / "screenshots"
    shots.mkdir(parents=True, exist_ok=True)
    saved_note = workdir / "handoff.md"

    try:
        app = make_app()
    except tk.TclError as error:
        print(f"无法创建图形环境：{error}", file=sys.stderr)
        return 2

    try:
        app.update()
        check("窗口已创建并有标题", app.title() == "排查助手", app.title())
        check("窗口可见", bool(app.winfo_ismapped()))

        # ---- A. 尚未选择报告 ----
        texts = body_texts(app)
        check("初始界面提示选择报告", any("选择已有报告" in t for t in texts))
        check("初始界面有主按钮", any(t == "选择已有报告" for t in texts))
        check("初始界面有次要入口", any(t == "支持哪些报告" for t in texts)
              and any(t == "报告在哪里 / 我没有报告" for t in texts))
        capture_window(app, shots / "01-welcome.png")

        # ---- 次要入口 ----
        app._set_view("supported")
        app.update()
        check("支持哪些报告有内容", any("camera_timed_capture" in t for t in body_texts(app)))
        app._set_view("no_report")
        app.update()
        no_report_text = " ".join(body_texts(app))
        check("我还没有报告有材料提示",
              "在哪里找" in no_report_text and "怎样识别" in no_report_text)
        app._go_home()
        app.update()

        # ---- B. 选择 QR 报告（整图读出但 ROI 出错） ----
        with mock.patch.object(ui_module.filedialog, "askopenfilename",
                               return_value=str(samples["qr_full_ok_roi_error"])):
            app.choose_report()
        app.update()

        texts = body_texts(app)
        joined = " ".join(texts)
        check("已进入报告状态", app.session.primary is not None)
        check("显示目前发现", "目前发现" in texts)
        check("显示还不能确认", "这份报告还不能说明什么" in texts)
        check("显示下一步", "现在做什么" in texts)
        check("QR 读出被说明", "读出了一个二维码" in joined)
        check("ROI 错误未被隐藏", "ROI" in joined and "解码报告错误" in joined)
        # 只能出现“不代表内容正确”这类否定，不能出现肯定式宣称。
        # 按控件逐个判断：前一控件的否定说明不能豁免后面控件里的肯定结论。
        affirmative = ("内容正确。", "内容是正确的", "二维码正常", "内容已验证", "确认为正确")
        claims = unnegated_claims(texts, affirmative)
        check("未宣称内容正确", not claims, claims)
        check("明确否定了“读出即正确”", "不代表内容正确" in joined)
        check("未验证被保留", "未验证" in joined)
        check("页脚有补充结果与保存说明",
              "添加操作后的结果" in footer_buttons(app)
              and "保存说明" in footer_buttons(app))
        capture_window(app, shots / "02-report.png")

        # ---- 技术详情折叠 ----
        check("技术详情默认折叠", "查看技术详情" in " ".join(widget_texts(app.body)))
        app._toggle_technical()
        app.update()
        tech = " ".join(widget_texts(app.body))
        check("展开后出现技术字段", "schema_version" in tech and "E01" in tech)
        app._toggle_technical()
        app.update()

        # ---- 可选补充说明（用户反馈） ----
        app._show_note()
        app.update()
        app.note_text.insert("1.0", "我重新拍了一张，看起来正常了")
        app._record_note()
        app.update()
        feedback = " ".join(widget_texts(app.body))
        check("用户说明被记录", "看起来正常了" in feedback)
        check("用户说明标为未验证", "未验证" in feedback or "用户反馈" in feedback)
        check("用户反馈未升级为复验通过",
              dict(app.session.recheck_dimension())["复验"] == "待结果")

        # ---- C. 补充结果（另一批次，不能证明恢复） ----
        with mock.patch.object(ui_module.filedialog, "askopenfilename",
                               return_value=str(samples["review_consistent"])):
            app.choose_addition()
        app.update()

        joined = " ".join(widget_texts(app.body))
        check("出现与之前相比", "与之前相比" in joined)
        check("类型不同被指出不可比较", "不能比较" in joined or "不可比较" in joined
              or "类型不同" in joined)
        capture_window(app, shots / "03-comparison.png")

        # ---- 未记录草稿在重渲染/收起后保留 ----
        app._show_note()
        app.update()
        app.note_text.insert("1.0", "尚未记录的草稿")
        app._toggle_technical()
        app.update()
        draft_after_toggle = app._note_text_value()
        app._toggle_technical()
        app._hide_note()
        app.update()
        app._show_note()
        app.update()
        check("展开技术详情不丢草稿", draft_after_toggle == "尚未记录的草稿")
        check("收起再展开保留草稿", app._note_text_value() == "尚未记录的草稿")
        app.note_text.delete("1.0", "end")
        app._hide_note()
        app.update()

        # ---- 保存说明：预览内容 + 独占新建 ----
        previews: list[str] = []
        unsaved_during_preview: list[bool] = []
        with mock.patch.object(ui_module.filedialog, "asksaveasfilename",
                               return_value=str(saved_note)):
            drive_preview(
                app,
                lambda: unsaved_during_preview.append(app.session.has_unsaved_content()),
                capture=previews,
            )
            app.save_note()
        app.update()

        content = saved_note.read_text(encoding="utf-8") if saved_note.exists() else ""
        check("说明文件已保存", saved_note.exists())
        check("保存前出现预览", bool(previews))
        check("预览显示完整说明", any("## 简明结论" in p and "## 未附原始文件" in p
                                      for p in previews))
        check("预览与保存内容一致", bool(previews)
              and previews[0].rstrip("\n") == content.rstrip("\n"))
        check("预览时不标记为已保存", unsaved_during_preview == [True])
        check("预览含用户反馈", "## 用户反馈" in content and "看起来正常了" in content)
        check("说明含下一步", "## 下一步" in content)
        check("说明含尚未确认", "## 这份报告还不能说明什么" in content)
        check("说明含比较限制", "## 前后结果与比较限制" in content)
        check("说明含技术详情", "## 技术详情" in content)
        check("说明声明未附原始文件", "未附原始报告" in content)
        check("说明不含本机绝对路径",
              "D:\\" not in content and str(workdir) not in content)
        check("说明不含 QR 载荷", synthetic.SYNTHETIC_PAYLOAD not in content)
        check("保存成功后未保存标志清除", not app.session.has_unsaved_content())
        check("保存后提示已保存", any("已保存说明" in t for t in widget_texts(app.body)))
        capture_window(app, shots / "04-saved.png")

        # ---- 重名保护（不覆盖、不显示成功） ----
        app.session.add_note("第二条说明")
        app._notice = None
        app._render()
        app.update()
        before = saved_note.read_text(encoding="utf-8")
        expected_before = len(EXPECTED_ERRORS)
        with mock.patch.object(ui_module.filedialog, "asksaveasfilename",
                               return_value=str(saved_note)):
            drive_preview(app, lambda: None)
            app.save_note()
        app.update()
        check("重名不覆盖", saved_note.read_text(encoding="utf-8") == before)
        check("重名时出现保存失败提示", len(EXPECTED_ERRORS) > expected_before)
        check("重名失败不显示已保存", not any("已保存说明" in t for t in widget_texts(app.body)))
        check("重名失败保留未保存状态", app.session.has_unsaved_content())
        check("重名失败后主窗口恢复可交互", app.grab_current() in (None, app))

        # ---- 普通保存取消 ----
        cancel_target = workdir / "cancelled.md"
        expected_before = len(EXPECTED_ERRORS)
        with mock.patch.object(ui_module.filedialog, "asksaveasfilename", return_value=""):
            drive_preview(app, lambda: None)
            result = app.save_note()
        app.update()
        check("取消保存返回未保存", result is False)
        check("取消保存不改动已有文件", saved_note.read_text(encoding="utf-8") == before)
        check("取消保存保留未保存状态", app.session.has_unsaved_content())
        check("取消保存不弹失败提示", len(EXPECTED_ERRORS) == expected_before)

        # ---- 键盘可达 ----
        check("绑定了 Ctrl+O", bool(app.bind("<Control-o>")))
        check("绑定了 Ctrl+S", bool(app.bind("<Control-s>")))

        # ---- 关闭窗口：保存取消 → 不关闭 ----
        close_saved = workdir / "closed-save.md"
        with mock.patch.object(ui_module.filedialog, "asksaveasfilename", return_value=""):
            drive_dialog(app, "还有未保存的内容", "保存说明", lambda: None,
                         capture=previews, expect_preview=True, then_click="返回")
            app.on_close()
        app.update()
        check("关闭时取消保存仍保持窗口", alive(app))
        check("关闭时取消保存保留内容", app.session.has_unsaved_content()
              and len(app.session.notes) == 2)

        # ---- 关闭窗口：保存失败 → 不关闭 ----
        expected_before = len(EXPECTED_ERRORS)
        with mock.patch.object(ui_module.filedialog, "asksaveasfilename",
                               return_value=str(close_saved)), \
                mock.patch("pathlib.Path.open", side_effect=PermissionError("拒绝访问")):
            drive_dialog(app, "还有未保存的内容", "保存说明", lambda: None,
                         expect_preview=True, then_click="返回")
            app.on_close()
        app.update()
        check("关闭时保存失败仍保持窗口", alive(app))
        check("关闭时保存失败未被误报成功", not any("已保存说明" in t for t in widget_texts(app.body)))
        check("关闭时保存失败保留未保存状态", app.session.has_unsaved_content())
        check("关闭时保存失败未写文件", not close_saved.exists())
        check("关闭时保存失败有提示", len(EXPECTED_ERRORS) > expected_before)
        check("关闭时保存失败后窗口可交互", app.grab_current() in (None, app))

        # ---- 关闭窗口：保存成功 → 关闭 ----
        with mock.patch.object(ui_module.filedialog, "asksaveasfilename",
                               return_value=str(close_saved)):
            drive_dialog(app, "还有未保存的内容", "保存说明", lambda: None,
                         expect_preview=True)
            app.on_close()
        check("关闭时保存成功生成文件", close_saved.exists())
        check("关闭时保存成功才关闭窗口", not alive(app))
        if alive(app):
            app.destroy()

        # ---- 重新打开：正常 → 异常不得通过 ----
        app = make_app()   # 上一窗口已在“关闭时保存成功”中销毁
        app.update()
        load_primary(app, samples["review_consistent"])
        load_addition(app, samples["review_missing_image"])
        joined = " ".join(widget_texts(app.body))
        check("正常→异常判未通过", "未通过" in joined)
        check("正常→异常不判通过", "范围内通过" not in joined)
        check("正常→异常指出新出现的问题", "新出现" in joined and "无法核实" in joined)
        capture_window(app, shots / "05-regression-failed.png")
        abnormal_previews: list[str] = []
        abnormal_target = workdir / "abnormal.md"
        with mock.patch.object(ui_module.filedialog, "asksaveasfilename",
                               return_value=str(abnormal_target)):
            drive_preview(app, lambda: None, capture=abnormal_previews)
            app.save_note()
        abnormal_text = abnormal_target.read_text(encoding="utf-8") \
            if abnormal_target.exists() else ""
        check("导出反映新异常", "未通过" in abnormal_text and "新出现的问题" in abnormal_text)
        check("导出不声称通过", "范围内通过" not in abnormal_text)

        # ---- 新调查不混入旧说明 ----
        old_id = app.session.investigation_id
        app.session.add_note("只属于旧调查的说明")
        app._notice = None
        app._render()
        with mock.patch.object(ui_module.filedialog, "askopenfilename",
                               return_value=str(samples["qr_single_read"])):
            drive_choose_report(app, ("还有未保存的内容", "放弃本次内容", False, None, None))
            app.choose_report()
        app.update()
        check("新调查使用新的调查 ID", app.session.investigation_id != old_id)
        check("新调查不带入旧说明",
              all("只属于旧调查" not in t for t in widget_texts(app.body)))
        check("新调查未保存状态已重置", not app.session.has_unsaved_content())

        # ---- 切换报告：保存取消 → 不切换 ----
        app.session.add_note("切换测试说明")
        current = app.session.primary
        with mock.patch.object(ui_module.filedialog, "asksaveasfilename", return_value=""), \
                mock.patch.object(ui_module.filedialog, "askopenfilename",
                                  return_value=str(samples["review_consistent"])):
            drive_choose_report(app,
                                ("还有未保存的内容", "保存说明", True, "返回", None))
            app.choose_report()
        app.update()
        check("切换时取消保存不切换", app.session.primary is current)
        check("切换时取消保存保留内容", app.session.has_unsaved_content())
        check("切换时取消保存后窗口可交互", app.grab_current() in (None, app))

        # ---- 切换报告：保存失败 → 不切换 ----
        switch_failed = workdir / "switch-failed.md"
        with mock.patch.object(ui_module.filedialog, "asksaveasfilename",
                               return_value=str(switch_failed)), \
                mock.patch.object(ui_module.filedialog, "askopenfilename",
                                  return_value=str(samples["review_consistent"])), \
                mock.patch("pathlib.Path.open", side_effect=PermissionError("拒绝访问")):
            drive_choose_report(app,
                                ("还有未保存的内容", "保存说明", True, "返回", None))
            app.choose_report()
        app.update()
        check("切换时保存失败不切换", app.session.primary is current)
        check("切换时保存失败保留内容", app.session.has_unsaved_content())
        check("切换时保存失败未写文件", not switch_failed.exists())

        # ---- 切换报告：保存成功 → 切换 ----
        switch_saved = workdir / "switch-saved.md"
        with mock.patch.object(ui_module.filedialog, "asksaveasfilename",
                               return_value=str(switch_saved)), \
                mock.patch.object(ui_module.filedialog, "askopenfilename",
                                  return_value=str(samples["review_consistent"])):
            drive_choose_report(app,
                                ("还有未保存的内容", "保存说明", True, None, None))
            app.choose_report()
        app.update()
        check("切换时保存成功生成文件", switch_saved.exists())
        check("切换时保存成功才切换", app.session.primary is not None
              and app.session.primary.report_type == "capture_task_review")

        # ---- 未记录草稿：切换前必须处理 ----
        app._show_note()
        app.update()
        app.note_text.insert("1.0", "未记录的草稿")
        with mock.patch.object(ui_module.filedialog, "askopenfilename",
                               return_value=str(samples["qr_single_read"])):
            drive_choose_report(app,
                                ("还有未记录的说明", "放弃这段文字并继续", False, None, None))
            app.choose_report()
        app.update()
        check("切换时处理未记录草稿", app.session.primary.report_type == "label_baseline")
        check("草稿不会混入用户反馈",
              all("未记录的草稿" not in text for _, text in
                  app.session.user_feedback_dimension()))

        # ---- 取消选择或读取失败不破坏原调查 ----
        current = app.session.primary
        with mock.patch.object(ui_module.filedialog, "askopenfilename", return_value=""):
            drive_choose_report(app)
            app.choose_report()
        app.update()
        check("取消选文件保留原调查", app.session.primary is current)

        broken = workdir / "broken.json"
        broken.write_text("{ not json", encoding="utf-8")
        with mock.patch.object(ui_module.filedialog, "askopenfilename",
                               return_value=str(broken)):
            drive_choose_report(app)
            app.choose_report()
        app.update()
        check("读取失败有提示", any("无法读取" in t for t in widget_texts(app.body)))
        check("读取失败不破坏已有结果", app.session.primary is current)

        # ---- D. 补充记录反馈：实际点击“做不了或不确定” → 交接 ----
        shutdown(app)
        app = make_app()
        app.update()
        load_primary(app, samples["review_consistent"])
        load_addition(app, samples["review_missing_image"])
        joined = " ".join(widget_texts(app.body))
        check("补充记录显示缺图步骤", "核对无法核实的那一帧图片" in joined)
        check("补充记录卡属于补充记录 1",
              current_card(app.session).context == "补充记录 1")
        blocked_button = find_button(app.body, "做不了或不确定")
        check("补充记录卡有反馈按钮", blocked_button is not None)
        if blocked_button is not None:
            blocked_button.invoke()
            app.update()
        feedbacks = app.session.feedbacks
        check("点击后记录了一条步骤反馈", len(feedbacks) == 1
              and feedbacks[0].context == "补充记录 1")
        joined = " ".join(widget_texts(app.body))
        check("做不了或不确定后进入交接", "保存当前说明，交给技术人员继续处理" in joined)
        check("交接卡不再索取缺图步骤", "核对无法核实的那一帧图片" not in joined)
        check("反馈未升级复验", app.session.additions[0].recheck_result == "未通过")
        check("根因仍为未知",
              "未知" in dict(app.session.root_cause_dimension())["根因判断"])
        blocked_previews: list[str] = []
        blocked_target = workdir / "blocked.md"
        with mock.patch.object(ui_module.filedialog, "asksaveasfilename",
                               return_value=str(blocked_target)):
            drive_preview(app, lambda: None, capture=blocked_previews)
            app.save_note()
        blocked_text = blocked_target.read_text(encoding="utf-8") \
            if blocked_target.exists() else ""
        check("导出含反馈归属", "补充记录 1" in blocked_text
              and "做不了或不确定" in blocked_text)
        check("导出含步骤 ID 与版本", "g2.frame.find-image" in blocked_text
              and f"v{current_card(app.session).guide_version}" in blocked_text)
        check("导出仍保留比较限制", "比较限制" in blocked_text)
        check("导出当前卡与界面一致",
              "handoff.save" in blocked_text and "保存当前说明" in blocked_text)
        check("导出未把反馈写成复验通过", "范围内通过" not in blocked_text)
        capture_window(app, shots / "06-feedback-handoff.png")

        # ---- E. 已做完不重复；后续补充记录不继承反馈 ----
        shutdown(app)
        app = make_app()
        app.update()
        load_primary(app, samples["review_consistent"])
        load_addition(app, samples["review_missing_image"])
        done_button = find_button(app.body, "已做完")
        check("补充记录卡有已做完按钮", done_button is not None)
        if done_button is not None:
            done_button.invoke()
            app.update()
        card_after_done = current_card(app.session)
        joined = " ".join(widget_texts(app.body))
        check("已做完后不再显示同一步骤为当前动作",
              card_after_done.step_id == "after.observation")
        check("已做完后界面说明等待新结果",
              "需要核对变化时再添加新结果" in joined)
        check("已做完不是修复证明", "不是问题已修好的证明" in joined)

        third = synthetic.write_report(
            workdir / "samples" / "review-missing-image-3.json",
            synthetic.capture_review_report(
                verification_status="inconsistent",
                issues=[{"code": "frame_unverifiable", "frame_count": 3,
                         "detail": "缺少留证图片"}],
                counts={"reported_samples": 2, "csv_pairs": 2, "verified_frames": 1},
                frames=[{"frame_count": 1, "image_sha256_match": True, "metrics": synthetic.review_metrics()}],
            ),
        )
        load_addition(app, third)
        card_second = current_card(app.session)
        joined = " ".join(widget_texts(app.body))
        check("第二份补充记录重新给出缺图步骤",
              card_second.context == "补充记录 2"
              and card_second.step_id == "g2.frame.find-image")
        check("第二份补充记录不继承已完成", "已由你记录完成" not in card_second.related)
        still_button = find_button(app.body, "问题仍在")
        check("第二份补充记录仍有反馈按钮", still_button is not None)
        if still_button is not None:
            still_button.invoke()
            app.update()
        joined = " ".join(widget_texts(app.body))
        check("问题仍在保留用户声明",
              "问题仍在" in joined and "用户声明" in joined)
        check("问题仍在不改复验",
              [item.recheck_result for item in app.session.additions]
              == ["未通过", "未通过"])
        check("问题仍在不改根因",
              "未知" in dict(app.session.root_cause_dimension())["根因判断"])

        # 新调查清除步骤反馈
        with mock.patch.object(ui_module.filedialog, "askopenfilename",
                               return_value=str(samples["qr_single_read"])):
            drive_choose_report(app,
                                ("还有未保存的内容", "放弃本次内容", False, None, None))
            app.choose_report()
        app.update()
        check("新调查清除步骤反馈", app.session.feedbacks == [])
        check("新调查不带入旧反馈",
              all("问题仍在" not in text for _, text in
                  app.session.user_feedback_dimension()))
        capture_window(app, shots / "07-new-investigation-cleared.png")

        # ---- F. 没有报告：记录找不到材料并保存交接说明 ----
        shutdown(app)
        app = make_app()
        app.update()
        app._set_view("no_report")
        app.update()
        app.handoff_text.insert("1.0", "找不到这次采集的任务目录")
        handoff_button = find_button(app.body, "记录找不到 / 不确定")
        check("材料页有交接记录按钮", handoff_button is not None)
        if handoff_button is not None:
            handoff_button.invoke()
            app.update()
        joined = " ".join(widget_texts(app.body))
        check("交接记录标为用户声明",
              "找不到这次采集的任务目录" in joined and "未独立验证" in joined)
        handoff_target = workdir / "no-report-handoff.md"
        handoff_previews: list[str] = []
        with mock.patch.object(ui_module.filedialog, "asksaveasfilename",
                               return_value=str(handoff_target)):
            drive_preview(app, lambda: None, capture=handoff_previews)
            app.save_note()
        handoff_text = handoff_target.read_text(encoding="utf-8") \
            if handoff_target.exists() else ""
        check("无报告时可保存交接说明", handoff_target.exists())
        check("无报告时先预览交接说明", bool(handoff_previews)
              and "找不到这次采集的任务目录" in handoff_previews[0])
        check("交接说明含用户声明", "找不到这次采集的任务目录" in handoff_text
              and "未独立验证" in handoff_text)
        check("交接说明声明没有诊断结论",
              "尚未选择报告" in handoff_text and "没有可判断的结论" in handoff_text)
        check("交接说明未附原始文件", "未附原始报告" in handoff_text)
        capture_window(app, shots / "08-handoff-saved.png")

        # ---- G. 主报告步骤反馈：实际点击并检查卡片转换 ----
        shutdown(app)
        app = make_app()
        app.update()
        load_primary(app, samples["review_missing_image"])
        primary_card = current_card(app.session)
        check("主报告卡上下文正确",
              primary_card.context == "主报告"
              and primary_card.step_id == "g2.frame.find-image")
        primary_done = find_button(app.body, "已做完")
        check("主报告卡有已做完按钮", primary_done is not None)
        if primary_done is not None:
            primary_done.invoke()
            app.update()
        primary_card_after = current_card(app.session)
        joined = " ".join(widget_texts(app.body))
        check("主报告已做完后转为等待新结果",
              primary_card_after.step_id == "after.observation")
        check("主报告反馈标为未独立验证", "未独立验证" in joined)
        feedback_items = app.session.feedbacks
        check("主报告反馈带上下文与版本", len(feedback_items) == 1
              and feedback_items[0].context == "主报告"
              and feedback_items[0].guide_version == primary_card.guide_version)
        check("主报告反馈不带入补充记录",
              all(item.context != "补充记录 1" for item in feedback_items))
        check("主报告反馈不改复验",
              dict(app.session.recheck_dimension())["复验"] == "待结果")
        check("主报告反馈不改根因",
              "未知" in dict(app.session.root_cause_dimension())["根因判断"])
        primary_target = workdir / "primary-feedback.md"
        with mock.patch.object(ui_module.filedialog, "asksaveasfilename",
                               return_value=str(primary_target)):
            drive_preview(app, lambda: None)
            app.save_note()
        primary_text = primary_target.read_text(encoding="utf-8") \
            if primary_target.exists() else ""
        check("主报告反馈导出带上下文", "主报告：g2.frame.find-image" in primary_text)
        check("主报告反馈导出为等待新结果",
              "需要核对变化时再添加新结果" in primary_text)
        capture_window(app, shots / "09-primary-feedback.png")

        # ---- H. 覆盖范围与重复导入：不得把已知异常换成“通过/证据不足” ----
        shutdown(app)
        app = make_app()
        app.update()
        load_primary(app, samples["review_missing_image"])
        frame1_only = synthetic.write_report(
            workdir / "samples" / "review-frame1-only.json",
            synthetic.capture_review_report(
                verification_status="consistent",
                counts={"reported_samples": 1, "csv_pairs": 1, "verified_frames": 1},
                frames=[{"frame_count": 1, "image_sha256_match": True, "metrics": synthetic.review_metrics()}],
            ),
        )
        load_addition(app, frame1_only)
        joined = " ".join(widget_texts(app.body))
        check("未覆盖原问题帧判证据不足",
              current_card(app.session).step_id == "after.added-insufficient")
        check("未覆盖原问题帧不显示范围内通过", "范围内通过" not in joined)
        check("未覆盖原问题帧写明帧号", "帧 2" in joined or "帧 2" in
              current_card(app.session).note)
        uncovered_target = workdir / "uncovered.md"
        with mock.patch.object(ui_module.filedialog, "asksaveasfilename",
                               return_value=str(uncovered_target)):
            drive_preview(app, lambda: None)
            app.save_note()
        uncovered_text = uncovered_target.read_text(encoding="utf-8") \
            if uncovered_target.exists() else ""
        check("导出不把未覆盖帧写成通过",
              "证据不足" in uncovered_text and "范围内通过" not in uncovered_text)

        # 重复导入较早的正常报告，不能把此前“未通过”替换成“证据不足”。
        shutdown(app)
        app = make_app()
        app.update()
        load_primary(app, samples["review_consistent"])
        load_addition(app, samples["review_missing_image"])
        load_addition(app, samples["review_consistent"])   # 重复导入主报告
        joined = " ".join(widget_texts(app.body))
        check("重复导入后界面仍保留未通过", "未通过" in joined)
        check("重复导入给出重复卡", current_card(app.session).step_id
              == "after.repeat-import")
        repeat_target = workdir / "repeat-import.md"
        with mock.patch.object(ui_module.filedialog, "asksaveasfilename",
                               return_value=str(repeat_target)):
            drive_preview(app, lambda: None)
            app.save_note()
        repeat_text = repeat_target.read_text(encoding="utf-8") \
            if repeat_target.exists() else ""
        check("重复导入后导出结论仍为未通过",
              "未通过" in repeat_text and "补充结果复验：证据不足" not in repeat_text)
        check("重复导入导出说明没有新增证据", "重复导入" in repeat_text)

        # 失败恢复：坏文件/超限补充不改变原调查，换有效文件后继续。
        before_count = len(app.session.additions)
        broken_addition = workdir / "broken-addition.json"
        broken_addition.write_text("{ not json", encoding="utf-8")
        with mock.patch.object(ui_module.filedialog, "askopenfilename",
                               return_value=str(broken_addition)):
            app.choose_addition()
        app.update()
        check("坏补充文件有提示",
              any("无法读取" in t for t in widget_texts(app.body)))
        check("坏补充文件不改变已有结果",
              len(app.session.additions) == before_count)
        over = synthetic.capture_review_report()
        over["big"] = [0] * (MAX_ARRAY_ELEMENTS + 1)
        over_path = synthetic.write_report(
            workdir / "samples" / "review-over-array.json", over)
        with mock.patch.object(ui_module.filedialog, "askopenfilename",
                               return_value=str(over_path)):
            app.choose_addition()
        app.update()
        joined = " ".join(widget_texts(app.body))
        check("超限补充文件被明确拒绝",
              "超过上限" in joined or "too_many_elements" in joined)
        check("超限补充文件不改变已有结果",
              len(app.session.additions) == before_count)
        frame3 = synthetic.write_report(
            workdir / "samples" / "review-missing-image-3b.json",
            synthetic.capture_review_report(
                verification_status="inconsistent",
                issues=[{"code": "frame_unverifiable", "frame_count": 3,
                         "detail": "缺少留证图片"}],
                counts={"reported_samples": 2, "csv_pairs": 2, "verified_frames": 1},
                frames=[{"frame_count": 1, "image_sha256_match": True, "metrics": synthetic.review_metrics()}],
            ),
        )
        load_addition(app, frame3)
        check("失败后改选有效补充文件可继续",
              len(app.session.additions) == before_count + 1
              and current_card(app.session).context.endswith(str(before_count + 1)))

        # 主报告交接后添加新结果：旧反馈保留，当前卡更新到新补充记录。
        shutdown(app)
        app = make_app()
        app.update()
        load_primary(app, samples["review_missing_image"])
        primary_blocked = find_button(app.body, "做不了或不确定")
        check("主报告有交接按钮", primary_blocked is not None)
        if primary_blocked is not None:
            primary_blocked.invoke()
            app.update()
        check("主报告交接后进入交接卡",
              current_card(app.session).step_id == "handoff.save")
        load_addition(app, frame3)
        check("交接后添加结果更新当前卡",
              current_card(app.session).context == "补充记录 1"
              and current_card(app.session).step_id == "g2.frame.find-image")
        check("交接后旧反馈仍保留",
              any(item.context == "主报告" for item in app.session.feedbacks))
        handoff_add_target = workdir / "handoff-then-add.md"
        with mock.patch.object(ui_module.filedialog, "asksaveasfilename",
                               return_value=str(handoff_add_target)):
            drive_preview(app, lambda: None)
            app.save_note()
        handoff_add_text = handoff_add_target.read_text(encoding="utf-8") \
            if handoff_add_target.exists() else ""
        check("交接后导出保留旧反馈与新补充记录",
              "主报告：g2.frame.find-image" in handoff_add_text
              and "补充记录 1" in handoff_add_text)

        # 未知复核状态不能被界面说成“发现了问题”。
        shutdown(app)
        app = make_app()
        app.update()
        future = synthetic.write_report(
            workdir / "samples" / "review-future-status.json",
            synthetic.capture_review_report(verification_status="future_status"),
        )
        load_primary(app, future)
        joined = " ".join(widget_texts(app.body))
        check("未知复核状态不被说成发现问题", "本次复核发现了问题" not in joined)
        check("未知复核状态保留原值并交接",
              "future_status" in joined
              and current_card(app.session).step_id == "handoff.save")

        # 回归一：正常 → 帧 2 缺图 → 仅帧 1 正常；再覆盖帧 2。
        # 使用真实读取器/Session/Tk 控件/预览和实际文件；只有系统文件选择为固定路径。
        from tests.test_issue_lifecycle import review, missing
        shutdown(app)
        app = make_app()
        app.update()
        lifecycle_normal = synthetic.write_report(
            workdir / "samples" / "lifecycle-normal.json", review(tag="gui-initial"))
        lifecycle_missing = synthetic.write_report(
            workdir / "samples" / "lifecycle-missing.json",
            review((1,), issues=[missing(2)], tag="gui-missing"))
        lifecycle_partial = synthetic.write_report(
            workdir / "samples" / "lifecycle-partial.json", review((1,), tag="gui-partial"))
        lifecycle_full = synthetic.write_report(
            workdir / "samples" / "lifecycle-full.json", review(tag="gui-full"))
        load_primary(app, lifecycle_normal)
        load_addition(app, lifecycle_missing)
        load_addition(app, lifecycle_partial)
        text = " ".join(body_texts(app))
        check("三份连续导入保留原报告和两次比较",
              len(app.session.additions) == 2 and app.session.primary.source_name == lifecycle_normal.name)
        check("三份导入主区保留帧 2 未解决及缺失证据",
              "未解决" in text and "缺少帧 2" in text)
        check("三份导入当前卡不宣称调查恢复",
              current_card(app.session).step_id != "after.added-passed"
              and "未解决" in current_card(app.session).related)
        lifecycle_target = workdir / "lifecycle-unresolved.md"
        lifecycle_preview = []
        with mock.patch.object(ui_module.filedialog, "asksaveasfilename",
                               return_value=str(lifecycle_target)):
            drive_preview(app, lambda: None, capture=lifecycle_preview)
            app.save_note()
        lifecycle_export = lifecycle_target.read_text(encoding="utf-8")
        issue = app.session.get_issue_details(app.session.investigation_id, "P01")
        scope = issue["evidence"]["补充记录 2"]
        check("查询和导出给出同一局部复核的帧集合及执行身份",
              issue["status"] == "open" and scope["verified_frame_counts"] == [1]
              and scope["review_id"] in lifecycle_export
              and scope["reviewed_at_utc"] in lifecycle_export
              and "frames（按全部逐帧记录核实的帧号） | [1]" in lifecycle_export)
        check("三份导入真实导出保留未解决问题与历史",
              "缺少帧 2" in lifecycle_export and "调查问题历史" in lifecycle_export
              and "仅与主报告的单次比较" in lifecycle_export)
        check("三份导入预览与实际导出一致",
              bool(lifecycle_preview) and lifecycle_preview[0].rstrip() == lifecycle_export.rstrip())
        capture_window(app, shots / "lifecycle-unresolved.png")
        load_addition(app, lifecycle_full)
        closed = app.session.get_issue_details(app.session.investigation_id, "P01")
        check("完整复核后查询与界面显示同一问题在范围内关闭",
              closed["status"] == "closed_in_scope" and closed["resolved_by"] == "补充记录 3"
              and "范围内通过" in " ".join(body_texts(app)))
        check("随后有效完整结果允许范围内关闭",
              app.session.investigation_summary()[0] == "范围内通过"
              and not app.session.unresolved_review_problems()
              and current_card(app.session).step_id == "after.added-passed")
        check("关闭问题后旧失败仍在历史",
              app.session.additions[0].recheck_result == "未通过"
              and len(app.session.additions) == 3)

        # 回归二：consistent/计数声称核实两帧，但帧 2 摘要 false、metrics null。
        shutdown(app)
        app = make_app()
        app.update()
        load_primary(app, lifecycle_missing)
        contradictory = review(tag="gui-contradictory")
        contradictory["frames"][1]["image_sha256_match"] = False
        contradictory["frames"][1]["metrics"] = None
        contradictory_path = synthetic.write_report(
            workdir / "samples" / "lifecycle-contradictory.json", contradictory)
        load_addition(app, contradictory_path)
        text = " ".join(body_texts(app))
        check("矛盾报告导入后保留帧级事实与校验提示",
              bool(app.session.additions[-1].report.warnings)
              and "矛盾" in text and "帧 2" in text)
        check("矛盾报告导入后界面不宣称通过",
              app.session.additions[-1].recheck_result != "范围内通过"
              and current_card(app.session).step_id != "after.added-passed"
              and "范围内通过" not in text)
        contradictory_target = workdir / "lifecycle-contradictory.md"
        with mock.patch.object(ui_module.filedialog, "asksaveasfilename",
                               return_value=str(contradictory_target)):
            drive_preview(app, lambda: None)
            app.save_note()
        contradictory_export = contradictory_target.read_text(encoding="utf-8")
        check("矛盾报告实际导出保留矛盾与未解决问题且不宣称通过",
              "矛盾" in contradictory_export and "未解决" in contradictory_export
              and "范围内通过" not in contradictory_export)
        check("保存说明不会关闭矛盾报告中的问题",
              bool(app.session.unresolved_review_problems()))
        capture_window(app, shots / "lifecycle-contradictory.png")

        # 取消预览：不写文件、不清除未保存状态。
        shutdown(app)
        app = make_app()
        app.update()
        load_primary(app, samples["review_consistent"])
        app.session.add_note("预览取消测试")
        app._render()
        app.update()
        cancelled_target = workdir / "preview-cancelled.md"
        cancelled = []

        def close_preview(window) -> None:
            cancelled.append("预览说明")
            window.destroy()

        with mock.patch.object(ui_module.filedialog, "asksaveasfilename",
                               return_value=str(cancelled_target)):
            when_toplevel(app, "预览说明", close_preview)
            result = app.save_note()
        app.update()
        check("取消预览返回未保存", result is False)
        check("取消预览没有写文件", not cancelled_target.exists())
        check("取消预览保留未保存状态", app.session.has_unsaved_content())

    finally:
        cancel_pending(app)   # 关闭窗口后不再执行排队的驱动回调
        try:
            app.destroy()
        except tk.TclError:
            pass

    for message in ERRORS:
        check(f"无意外界面错误：{message}", False, message)

    passed = sum(1 for _, ok, _ in CHECKS if ok)
    for name, ok, detail in CHECKS:
        print(f"{'ok  ' if ok else 'FAIL'} {name}" + (f"  [{detail}]" if not ok and detail else ""))
    print(f"\n{passed}/{len(CHECKS)} 项通过")
    print(f"截图目录：{shots}")
    return 0 if passed == len(CHECKS) else 1


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.mkdtemp(prefix="rfg-gui-"))
    target.mkdir(parents=True, exist_ok=True)
    print(f"工作目录：{target}\n")
    raise SystemExit(run(target))
