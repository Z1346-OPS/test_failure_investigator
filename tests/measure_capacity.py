"""累积容量观察脚本（不是自动验收测试，不设任意阈值）。

测量同一调查连续导入不同报告、重复导入同一报告、长说明之后的：
导入耗时、当前卡耗时、导出渲染耗时与大小、界面重渲染耗时。
只使用临时目录中的合成报告；不启动摄像头、不联网、不安装依赖。

用法（项目根）：
    .\\.venv\\Scripts\\python.exe -B -X utf8 tests\\measure_capacity.py
"""

from __future__ import annotations

import tempfile
import time
import tracemalloc
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
import sys

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from tests import synthetic  # noqa: E402

from investigator.explain import explain_report  # noqa: E402
from investigator.export import render_markdown, save_markdown  # noqa: E402
from investigator.guides import current_card  # noqa: E402
from investigator.reports import load_report  # noqa: E402
from investigator.session import Session  # noqa: E402

RUN_ID = "capacity" + "0" * 24
LONG_NOTE = "观察" * 500   # 1000 字符


def make_primary() -> Session:
    session = Session()
    report = load_report(
        _write("primary.json", synthetic.capture_review_report(run_id=RUN_ID)))
    session.load_primary(report, explain_report(report))
    return session


def _write(name: str, payload: dict) -> Path:
    return synthetic.write_report(_TMP / name, payload)


def distinct_addition_paths(count: int) -> list[Path]:
    paths: list[Path] = []
    for index in range(count):
        payload = synthetic.capture_review_report(
            run_id=RUN_ID,
            verification_status="inconsistent",
            issues=[{"code": "frame_unverifiable", "frame_count": 1000 + index,
                     "detail": f"distinct-{index}"}],
            counts={"reported_samples": 2, "csv_pairs": 2, "verified_frames": 1},
            frames=[{"frame_count": 1, "image_sha256_match": True, "metrics": {}}],
        )
        paths.append(_write(f"addition-{index:03d}.json", payload))
    return paths


def distinct_import(count: int) -> dict:
    session = make_primary()
    paths = distinct_addition_paths(count)
    tracemalloc.start()
    start = time.perf_counter()
    for path in paths:
        report = load_report(path)
        session.add_addition(report, explain_report(report))
    add_seconds = time.perf_counter() - start
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    start = time.perf_counter()
    card = current_card(session)
    card_seconds = time.perf_counter() - start
    start = time.perf_counter()
    text = render_markdown(session)
    export_seconds = time.perf_counter() - start
    start = time.perf_counter()
    saved = save_markdown(session, _TMP / f"distinct-{count}.md")
    save_seconds = time.perf_counter() - start
    return {
        "count": count,
        "import_s": add_seconds,
        "card_s": card_seconds,
        "export_s": export_seconds,
        "save_s": save_seconds,
        "export_bytes": saved.stat().st_size,
        "text_chars": len(text),
        "peak_kib": peak / 1024,
        "card": f"{card.context}/{card.step_id}" if card else "(none)",
    }


def repeat_import(count: int) -> dict:
    session = make_primary()
    path = _write("repeat.json", synthetic.capture_review_report(run_id=RUN_ID))
    report = load_report(path)
    start = time.perf_counter()
    for _ in range(count):
        session.add_addition(report, explain_report(report))
    add_seconds = time.perf_counter() - start
    start = time.perf_counter()
    text = render_markdown(session)
    export_seconds = time.perf_counter() - start
    return {
        "count": count,
        "import_s": add_seconds,
        "export_s": export_seconds,
        "export_bytes": len(text.encode("utf-8")),
        "repeat_entries": sum(1 for item in session.additions if item.is_repeat),
        "card": f"{current_card(session).context}/{current_card(session).step_id}",
    }


def long_notes(count: int) -> dict:
    session = make_primary()
    start = time.perf_counter()
    for _ in range(count):
        session.add_note(LONG_NOTE)
    note_seconds = time.perf_counter() - start
    start = time.perf_counter()
    text = render_markdown(session)
    export_seconds = time.perf_counter() - start
    return {
        "count": count,
        "note_s": note_seconds,
        "export_s": export_seconds,
        "export_bytes": len(text.encode("utf-8")),
    }


def gui_render(count: int) -> dict | None:
    try:
        import tkinter as tk
        from investigator.ui import InvestigatorApp
    except Exception:  # noqa: BLE001 - 无图形环境时报告未测量
        return None
    try:
        app = InvestigatorApp()
    except tk.TclError:
        return None
    try:
        session = make_primary()
        for path in distinct_addition_paths(count):
            report = load_report(path)
            session.add_addition(report, explain_report(report))
        app.session = session
        app._view = "report"
        start = time.perf_counter()
        app._render()
        app.update_idletasks()
        app.update()
        seconds = time.perf_counter() - start
        widgets = _widget_count(app.body)
        return {"count": count, "render_s": seconds, "widgets": widgets}
    finally:
        try:
            app.destroy()
        except tk.TclError:
            pass


def _widget_count(widget) -> int:
    total = 1
    for child in widget.winfo_children():
        total += _widget_count(child)
    return total


def main() -> int:
    global _TMP
    with tempfile.TemporaryDirectory(prefix="capacity-probe-") as tmp:
        _TMP = Path(tmp)
        print("环境：Windows 11 / Python 3.12.10 / 本地临时目录")
        print("单次测量；合成材料；不设验收阈值。\n")

        print("[不同有效报告：同一调查逐份导入]")
        print(f"{'份数':>4} {'导入s':>8} {'卡片s':>8} {'导出s':>8} "
              f"{'保存s':>8} {'导出字节':>10} {'峰值MiB':>8} 当前卡")
        for count in (1, 10, 50):
            row = distinct_import(count)
            print(f"{row['count']:>4} {row['import_s']:>8.4f} {row['card_s']:>8.5f} "
                  f"{row['export_s']:>8.4f} {row['save_s']:>8.4f} "
                  f"{row['export_bytes']:>10} {row['peak_kib']/1024:>8.2f} {row['card']}")

        print("\n[重复导入同一报告]")
        print(f"{'份数':>4} {'导入s':>8} {'导出s':>8} {'导出字节':>10} 重复条目 当前卡")
        for count in (1, 10, 50):
            row = repeat_import(count)
            print(f"{row['count']:>4} {row['import_s']:>8.4f} {row['export_s']:>8.4f} "
                  f"{row['export_bytes']:>10} {row['repeat_entries']:>8} {row['card']}")

        print("\n[长说明：每条 1000 字符]")
        print(f"{'条数':>4} {'记录s':>8} {'导出s':>8} {'导出字节':>10}")
        for count in (1, 10, 50):
            row = long_notes(count)
            print(f"{row['count']:>4} {row['note_s']:>8.4f} {row['export_s']:>8.4f} "
                  f"{row['export_bytes']:>10}")

        print("\n[GUI 重渲染：不同有效报告]")
        for count in (1, 10, 50):
            row = gui_render(count)
            if row is None:
                print(f"{count:>4} 未测量（图形环境不可用）")
            else:
                print(f"{row['count']:>4} render={row['render_s']:.4f}s "
                      f"widgets={row['widgets']}")

    print("\n说明：未发现需要提前停止的持续变慢；测量到 50 份为止。")
    print("代码中没有调查总量上限；这不等于容量无限或性能已保证。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
