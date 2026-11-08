"""版本化的排查指引：材料来源、当前操作卡与停止条件。

本模块是界面当前卡、详细帮助和导出的**唯一动作文案来源**。它只整理已核实的
人工操作，不运行摄像头、不生成命令、不推断根因，也不把用户声明变成复验结论。

核实来源（只读核对，未运行摄像头项目入口）：
  * 摄像头项目 `src/analyze_label.py`：`--output` 独占新建结果 JSON；
    `report_type=label_baseline`、`schema_version=2`。
  * 摄像头项目 `src/run_capture.py` 与 `src/capture_task.py`：`--output-dir` 指定
    必须不存在的新目录，任务报告名为 `capture_task.json`；
    `report_type=camera_timed_capture`、`schema_version=1`。
  * 摄像头项目 `src/review_capture.py`：只接收任务目录，把复核 JSON 打印到终端；
    没有 `--output`，不创建文件；`report_type=capture_task_review`、`schema_version=1`。
  * 摄像头项目 `docs/tasks/capture-review-walkthrough.md` 第 1 节：示例把复核命令的
    stdout 写成新的 JSON，不覆盖旧文件。

时间与版本：2026-10-20，指引版本见 :data:`GUIDE_VERSION`。步骤 ID 与版本会写入
会话记录和导出，旧步骤记录不会被当前卡覆盖。
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # 只用于类型提示，避免与 session 形成导入环
    from .session import Session

GUIDE_VERSION = "2026-10-20.1"

# ---------------------------------------------------------------- 反馈词汇

FEEDBACK_DONE = "done"
FEEDBACK_STILL = "still"
FEEDBACK_NOT_SEEN = "not_seen"
FEEDBACK_BLOCKED = "blocked"

FEEDBACK_LABELS = {
    FEEDBACK_DONE: "已做完",
    FEEDBACK_STILL: "问题仍在",
    FEEDBACK_NOT_SEEN: "暂时没再出现",
    FEEDBACK_BLOCKED: "做不了或不确定",
}

FEEDBACK_ORDER = (FEEDBACK_DONE, FEEDBACK_STILL, FEEDBACK_NOT_SEEN, FEEDBACK_BLOCKED)

# 哪些步骤可以显示哪些反馈选项：不一次铺满，也不提供与动作不符的选项。
OBSERVATION_FEEDBACK = (FEEDBACK_DONE, FEEDBACK_STILL, FEEDBACK_NOT_SEEN, FEEDBACK_BLOCKED)
RECORD_FEEDBACK = (FEEDBACK_DONE, FEEDBACK_BLOCKED)
CHECK_FEEDBACK = (FEEDBACK_DONE, FEEDBACK_STILL, FEEDBACK_BLOCKED)


# ---------------------------------------------------------------- 材料帮助

@dataclass(frozen=True)
class MaterialHelp:
    label: str
    scenario: str
    source: str
    identify: str
    scope: str


MATERIAL_HELP = (
    MaterialHelp(
        label="QR 分析报告",
        scenario="G1：读出了码、歧义、ROI 结果不同",
        source=(
            "摄像头项目的 `src/analyze_label.py` 用 `--output` 指定、并独占新建的结果 "
            "JSON。不是图片，也不是 `--expected-file` 指向的答案文本或批量评测 JSON。"
        ),
        identify="文件内 `report_type` 为 `label_baseline`，`schema_version` 为 `2`。",
        scope="一次选择这一份分析结果；整图与 ROI 条目都在同一份文件里。",
    ),
    MaterialHelp(
        label="定时采集任务报告",
        scenario="G3：设备打开失败、采集提前结束",
        source=(
            "你运行 `src/run_capture.py` 时用 `--output-dir` 指定的**新目录**；"
            "目录中的 `capture_task.json` 是任务报告。"
        ),
        identify="文件内 `report_type` 为 `camera_timed_capture`，`schema_version` 为 `1`。",
        scope="选择 `capture_task.json` 本身，不要选整个目录、CSV 或留证 PNG。",
    ),
    MaterialHelp(
        label="采集复核报告",
        scenario="G2：任务完成，但复核提示缺图或指标差异",
        source=(
            "`src/review_capture.py` 接收任务目录，把复核 JSON **打印到终端**；"
            "它没有 `--output`，不会自动生成 `review.json`。要留存时，按摄像头项目 "
            "`docs/tasks/capture-review-walkthrough.md` 第 1 节的做法写成**新文件**，"
            "不要覆盖旧文件。"
        ),
        identify="文件内 `report_type` 为 `capture_task_review`，`schema_version` 为 `1`。",
        scope="选择一份复核 JSON；原始任务目录和图片由你另行人工查看，不会自动打开。",
    ),
)

MATERIAL_HELP_FOOTER = (
    "文件位置以你实际选择的文件或当时的运行参数为准。本程序不扫描磁盘，也不猜最新版。\n"
    "一次选择一份报告；CSV、PNG、普通日志、批量评测 JSON、expected 答案文本都不能"
    "作为本程序的报告导入。\n"
    "找不到时：可以记录“找不到 / 不确定”并保存交接说明。这只是用户声明，"
    "不会因此判断问题已解决。"
)

PRACTICE_NOTE = (
    "以下是 `tests/synthetic.py` 生成的合成报告，不是实拍记录、真实二维码载荷或私人报告。"
    "正式试用时由主持者提供并选择文件；本程序不自动生成、扫描或猜测它们的位置。"
)

PRACTICE_CASES = (
    ("G2 缺图", "review-missing-image.json", "复核指出有帧无法核实，verified_frames 为 0。"),
    ("G2 正常对照", "review-consistent.json", "同一 run_id 的检查范围内一致，用于比较限制。"),
    ("G2 未复核", "review-not-reviewed.json", "没有完成有效复核，counts 为 null。"),
    ("G1 无独立答案", "qr-single-read.json", "整图读出，但没有独立答案，内容仍未验证。"),
    ("G1 ROI 出错", "qr-full-ok-roi-error.json", "整图读出、ROI 解码错误同时保留。"),
    ("G3 打开失败", "task-open-failed.json", "请求编号打开失败，原因未知。"),
)

MATERIALS_VIEW_TITLE = "报告在哪里 / 我没有报告"


# ---------------------------------------------------------------- 步骤

@dataclass(frozen=True)
class GuideStep:
    guide_id: str
    step_id: str
    title: str
    related: str
    where: str
    actions: tuple[str, ...]
    observe: str
    return_hint: str
    stop: str
    feedback: tuple[str, ...]
    source: tuple[str, ...]

    @property
    def version(self) -> str:
        return GUIDE_VERSION


@dataclass(frozen=True)
class ActionCard:
    """当前界面只突出一个动作；所有文案来自 :class:`GuideStep`。"""

    step: GuideStep
    context: str = "主报告"
    note: str = ""
    related_override: str | None = None

    @property
    def guide_id(self) -> str:
        return self.step.guide_id

    @property
    def guide_version(self) -> str:
        return self.step.version

    @property
    def step_id(self) -> str:
        return self.step.step_id

    @property
    def title(self) -> str:
        return self.step.title

    @property
    def related(self) -> str:
        return self.related_override or self.step.related

    @property
    def feedback_choices(self) -> tuple[tuple[str, str], ...]:
        return tuple((choice, FEEDBACK_LABELS[choice])
                     for choice in FEEDBACK_ORDER if choice in self.step.feedback)


# ---------------------------------------------------------------- G1 QR

G1_TRUTH = GuideStep(
    guide_id="G1",
    step_id="g1.truth.source",
    title="确认是否存在独立的原始答案",
    related=(
        "报告里有读出、歧义或冲突，但没有独立答案；读出本身或重复一致都不能证明"
        "内容正确。"
    ),
    where=(
        "你保存独立答案的地方，或当时运行 `analyze_label.py` 时用 `--expected-file` "
        "指定的答案文件。这份报告不包含独立答案。"
    ),
    actions=(
        "先找独立答案文件或答案记录；只确认来源，不要打开二维码里的链接。",
        "如果找到了，确认它的来源独立于本次解码结果。",
        "没有找到就记录“没有独立答案”，不要用本次解码文本反填。",
    ),
    observe="是否存在独立答案，以及答案是否来自本次解码之外。",
    return_hint=(
        "回来记录“有 / 没有独立答案”。如果另行做了带独立答案的新分析，"
        "选择“添加操作后的结果”。"
    ),
    stop=(
        "没有独立答案时保持未验证；保存说明并交给技术人员，不要猜测内容是否正确。"
    ),
    feedback=CHECK_FEEDBACK,
    source=(
        "摄像头项目 `src/analyze_label.py`：`--expected-file` 为独立已知答案，"
        "`--output` 为结果 JSON（只读核对，未运行）。",
        "`docs/first-guide-and-trial-plan.md` G1：单一读出与独立答案分开。",
    ),
)

G1_TRUTH_SCOPE = GuideStep(
    guide_id="G1",
    step_id="g1.truth.scope",
    title="核对答案来源、图片身份和比对范围",
    related="报告记录了逐字节比对结果；它只在覆盖的答案和范围内成立。",
    where=(
        "技术详情里的 `known_truth.source_description`、`source.sha256` 和 "
        "`decode_summaries[].truth_check.status`。"
    ),
    actions=(
        "确认答案来源是否独立于本次解码输出。",
        "确认比对覆盖哪些区域；整图和 ROI 分开看。",
        "不要把结果扩展到整机、其他图片或其他场景。",
    ),
    observe="答案来源、图片摘要、覆盖区域和每个区域的比对状态。",
    return_hint="回来记录核对结果。如果另有同一张图片的新分析，可添加结果。",
    stop="来源或范围无法确认时保存交接，不要宣称内容正确。",
    feedback=CHECK_FEEDBACK,
    source=(
        "`docs/first-guide-and-trial-plan.md` G1：比对结果只在答案与范围内成立。",
        "`AGENTS.md`：QR 单一读出不代表内容正确。",
    ),
)

G1_REGION = GuideStep(
    guide_id="G1",
    step_id="g1.region.error",
    title="保留出错或歧义区域与整图的对照",
    related=(
        "整图与 ROI 的结果要分开看；不能只挑较好的整图结果，也不能用重扫消除"
        "错误或歧义状态。"
    ),
    where=(
        "技术详情里的 `decode_summaries`：每个区域的 `region`、`decode.status` 和 "
        "`truth_check.status`；图片身份看 `source.sha256`。"
    ),
    actions=(
        "确认整图与 ROI 条目指向同一张图片摘要。",
        "抄下出错或歧义区域的范围和状态；不要用另一张图或另一个 ROI 替代。",
        "保留原始错误类型、尝试记录和整体状态。",
    ),
    observe="区域范围、解码状态、图片摘要，以及整体是否标记为包含错误。",
    return_hint=(
        "回来记录观察。如果另行得到了同一图片的新分析，选择“添加操作后的结果”"
        "并核对是否同一图片和同一范围。"
    ),
    stop=(
        "无法确认同图、没有新结果或仍不确定时，保存交接；根因未知，不改记为成功。"
    ),
    feedback=OBSERVATION_FEEDBACK,
    source=(
        "`docs/first-guide-and-trial-plan.md` G1：整图与 ROI 分开，错误状态保留。",
        "`AGENTS.md`：QR 单一读出或多个一致不代表内容正确。",
    ),
)

# ---------------------------------------------------------------- G2 采集复核

G2_FRAME = GuideStep(
    guide_id="G2",
    step_id="g2.frame.find-image",
    title="核对无法核实的那一帧图片是否还在原任务目录",
    related=(
        "复核记录了帧无法核实；原因可能是缺失、不可读或其他，不能直接归因为"
        "磁盘写入失败。"
    ),
    where=(
        "你当时运行定时采集时用 `--output-dir` 指定的任务目录。复核报告本身不包含"
        "该目录路径，程序不能替你定位，也不会自动打开或读取更多文件。"
    ),
    actions=(
        "打开那个任务目录，确认里面有 `capture_task.json` 和本次 `run_id` 对应的记录。",
        "找到 `camera_frame_<run_id>_<帧号>.png`，只查看文件是否存在、能否打开。",
        "不要替换、改名或用另一张图片顶替缺失的留证图片。",
    ),
    observe="这个文件是否存在、能否打开；目录是否确实是这次 run_id 的目录。",
    return_hint=(
        "回来记录观察（例如“文件在 / 不在 / 打不开”）。如果另行获得了新的复核报告，"
        "选择“添加操作后的结果”。"
    ),
    stop=(
        "找不到目录、不确定是否同一批次，或文件无法确认时，保存交接并停止；"
        "文件存在也不能单独证明复验通过。"
    ),
    feedback=OBSERVATION_FEEDBACK,
    source=(
        "摄像头项目 `src/capture_task.py`：`REPORT_NAME = capture_task.json`；"
        "留证图片名为 `camera_frame_<run_id>_<帧号>.png`（只读核对，未运行）。",
        "`docs/tasks/capture-review-walkthrough.md`：复核只检查已有目录，不修改输入。",
        "`docs/first-guide-and-trial-plan.md` G2：缺图不能直接归因为磁盘写入失败。",
    ),
)

G2_METRIC = GuideStep(
    guide_id="G2",
    step_id="g2.metric.context",
    title="核对指标差异对应的帧、批次和比较口径",
    related=(
        "复核记录了记录值与按当前算法重算的值不同；不能据此认定相机损坏。"
    ),
    where=(
        "复核报告的 `issues`、`comparison_basis` 和技术详情；原始任务目录里的 CSV"
        "与对应留证图片。"
    ),
    actions=(
        "确认差异帧号，抄下记录值和重算值两个数。",
        "确认两次计算是否同一批次、同一 `comparison_basis`。",
        "不要编辑 CSV、替换图片或改阈值来对齐结果。",
    ),
    observe="差异指标名称与两个值；批次和比较口径是否一致。",
    return_hint=(
        "回来记录观察。如果另行得到了同批次、同口径的新复核，选择“添加操作后的结果”。"
    ),
    stop=(
        "口径不同或无法确认批次时保存交接；不能判为已恢复，也不能判为硬件故障。"
    ),
    feedback=OBSERVATION_FEEDBACK,
    source=(
        "`docs/first-guide-and-trial-plan.md` G2：保留两个指标值和 comparison_basis。",
        "`AGENTS.md`：指标差异不直接归因为硬件故障。",
    ),
)

G2_NOT_REVIEWED = GuideStep(
    guide_id="G2",
    step_id="g2.not-reviewed.inputs",
    title="先确认任务目录和复核输入是否完整",
    related=(
        "这次没有完成有效复核；不能当作 0 帧通过，也不能判断数据一致或不一致。"
    ),
    where=(
        "采集任务目录（`capture_task.json`、两份 CSV、留证图片）以及复核程序的"
        "终端输出或错误记录。"
    ),
    actions=(
        "确认任务目录和运行记录属于同一次采集。",
        "保留复核程序的输出与错误记录；不要手工修改 CSV 来匹配结果。",
        "如果另行完成了有效复核，把终端 JSON 保存为新的 `.json` 文件，不覆盖旧文件。",
    ),
    observe="任务状态、复核状态和错误记录；是否拿到了新的有效复核。",
    return_hint=(
        "如果拿到了新的有效复核文件，选择“添加操作后的结果”；否则保存交接。"
    ),
    stop="仍然没有有效复核时保存说明并停止，不猜测数据是否正确。",
    feedback=RECORD_FEEDBACK,
    source=(
        "摄像头项目 `src/review_capture.py`：复核失败只写 stderr 并以 2 退出；"
        "没有 `--output`（只读核对，未运行）。",
        "`docs/tasks/capture-review-walkthrough.md` 第 1 节：stdout 保存为新文件。",
    ),
)

G2_RECORDS = GuideStep(
    guide_id="G2",
    step_id="g2.records.preserve",
    title="保留记录差异的原始字段，交给技术人员",
    related=(
        "复核登记的差异不在已核实的自动处理范围内；不能靠修改记录或原图来消除。"
    ),
    where="复核报告的 `issues`、`warnings`、`counts` 和对应任务目录的原始文件。",
    actions=(
        "保留问题码、帧号、`issues` / `warnings` 原文和三个计数。",
        "不要修改 CSV、图片或任务记录来让结果看起来一致。",
        "没有已核实步骤时不要尝试自动修复或重算。",
    ),
    observe="问题码是否指向同一对象、同一帧，以及原始字段是否完整。",
    return_hint="如果另行得到了新的有效复核，可添加结果；否则保存说明交接。",
    stop="无法确认对象或材料不完整时保存交接，不猜测修复动作。",
    feedback=RECORD_FEEDBACK,
    source=(
        "`docs/first-guide-and-trial-plan.md` G2：保留原始问题码、帧号与计数。",
        "`AGENTS.md`：不同工具和业务问题不合并成单一标签。",
    ),
)

G2_CONSISTENT = GuideStep(
    guide_id="G2",
    step_id="g2.consistent.scope",
    title="核对这次复核覆盖的范围是否包含你关心的问题",
    related="本次检查范围内记录一致；这不能说明相机合格。",
    where=(
        "技术详情里的 `counts`（`reported_samples`、`csv_pairs`、`verified_frames`）"
        "和 `warnings`。"
    ),
    actions=(
        "确认覆盖的帧数与你关心的批次一致。",
        "查看 `warnings` 是否提示测量口径缺失或不同。",
        "如果有未覆盖的帧，保留原始记录，不要外推。",
    ),
    observe="覆盖范围、三个计数和口径提示。",
    return_hint="如果另行获得了同一对象的新复核，可添加结果；否则保存说明。",
    stop="范围不足或口径不明时保存交接，不能写相机合格。",
    feedback=CHECK_FEEDBACK,
    source=(
        "`docs/first-guide-and-trial-plan.md` G2：一致只在检查范围内成立。",
        "`AGENTS.md`：三类计数不互相替代。",
    ),
)

# ---------------------------------------------------------------- G3 采集任务

G3_OPEN = GuideStep(
    guide_id="G3",
    step_id="g3.open-failed.intent",
    title="对照失败记录的请求编号和你原本想用的设备",
    related=(
        "这次没有成功打开请求的设备；单凭记录不能确定是编号、占用、权限、驱动"
        "还是硬件原因。"
    ),
    where=(
        "失败记录的 `config.camera_index` 与 `camera.requested_backend`；以及你"
        "实际连接、原本想用的设备。"
    ),
    actions=(
        "确认失败记录里的编号是否是你原本想用的那台设备。",
        "查看你之后是否手动重试过，并找到了新的任务目录或复核记录。",
        "不要为了产生记录而反复打开设备，也不要改权限或驱动来“试”。",
    ),
    observe="请求编号与你实际设备是否一致；是否已有后续运行记录。",
    return_hint=(
        "回来记录观察。如果已有后续采集或复核结果，选择“添加操作后的结果”。"
    ),
    stop=(
        "没有后续记录、无法确认同一设备或仍不确定时保存交接；后续成功也不证明"
        "根因或物理恢复。"
    ),
    feedback=OBSERVATION_FEEDBACK,
    source=(
        "摄像头项目 `src/run_capture.py`：`--camera-index` 与 `--output-dir`；"
        "`src/capture_task.py` 的 `open_failed` 记录（只读核对，未运行）。",
        "`docs/first-guide-and-trial-plan.md` G3：不自动打开设备，不默认建议改驱动。",
    ),
)

G3_COMPLETED = GuideStep(
    guide_id="G3",
    step_id="g3.completed.scope",
    title="保存说明；如需判断画面质量，另行核对复核记录",
    related="采集流程走完，不代表画面质量合格，也不评价设备整体状态。",
    where="技术详情里的 `counts`、`camera` 和 `samples`；需要质量结论时看复核记录。",
    actions=(
        "确认这次运行的编号、后端和样本计数。",
        "如需判断画面质量，另行查看对应的复核记录，不要用采集完成代替复核。",
        "保存说明时保留“本次只读取记录”的执行边界。",
    ),
    observe="运行编号、后端、样本计数；是否有独立的复核结果。",
    return_hint="如果拿到了复核结果，可添加；否则保存说明。",
    stop="没有复核或范围不足时保存交接，不写画面质量结论。",
    feedback=RECORD_FEEDBACK,
    source=(
        "`docs/first-guide-and-trial-plan.md` G3：后续成功不等于根因确认。",
        "`AGENTS.md`：执行情况与业务观察分开。",
    ),
)

G3_FAILED = GuideStep(
    guide_id="G3",
    step_id="g3.failed.preserve",
    title="保留失败记录，确认之后是否产生过新结果",
    related="这次任务没有正常完成；具体原因需要看原始错误记录，本程序不作推测。",
    where="任务报告的 `status`、`stop_reason`、`primary_error` 和 `cleanup_errors`。",
    actions=(
        "保留原始错误记录和停止原因，不改记为成功。",
        "确认你之后是否手动重试过，以及是否产生了新的采集或复核记录。",
        "没有已核实步骤时不要猜测驱动、硬件或权限原因。",
    ),
    observe="原始错误、停止原因；是否已有后续记录。",
    return_hint="如果有后续采集或复核结果，可添加；否则保存说明。",
    stop="材料不足时保存交接，不反复建议重试。",
    feedback=RECORD_FEEDBACK,
    source=(
        "`docs/first-guide-and-trial-plan.md` G3：无法确认原因就交接。",
        "`AGENTS.md`：执行错误不等于硬件损坏。",
    ),
)

# ---------------------------------------------------------------- 复验之后

AFTER_OBSERVATION = GuideStep(
    guide_id="after",
    step_id="after.observation",
    title="已记录你的观察；需要核对变化时再添加新结果",
    related="你记录的是用户观察，未独立验证；它不能单独把复验改成通过。",
    where=(
        "不需要再找同一份材料。如果另行获得了新报告，使用底部“添加操作后的结果”。"
    ),
    actions=(
        "如果问题仍在或暂时没再出现，保留你的原话；它仍是用户声明。",
        "如果拿到了新报告，添加结果并核对对象、批次和比较口径。",
        "没有新结果时保存说明并停止。",
    ),
    observe="新报告是否属于同一对象、同一批次和相同比较口径。",
    return_hint="选择“添加操作后的结果”，或保存说明。",
    stop="没有新结果或无法确认关联时保存交接；用户声明不能算复验通过。",
    feedback=(),
    source=(
        "`docs/first-guide-and-trial-plan.md`：用户说恢复不等于复验通过。",
        "`AGENTS.md`：复验通过不等于根因确认。",
    ),
)

AFTER_REPEAT = GuideStep(
    guide_id="after",
    step_id="after.repeat-import",
    title="这次导入与已有材料内容相同，没有新增证据",
    related="重复导入同一份文件不会产生新的复验结果。",
    where="底部“添加操作后的结果”或“保存说明”。",
    actions=(
        "如果另有不同的报告，再添加那一份。",
        "没有新报告时保存说明交接；不要用重复导入凑出通过。",
    ),
    observe="新文件的摘要是否与已有材料不同。",
    return_hint="添加不同的报告，或保存说明。",
    stop="没有新增材料时停止比较，保留“证据不足”状态。",
    feedback=(),
    source=("`AGENTS.md`：原始记录不覆盖，新结果追加并关联。",),
)

AFTER_STILL = GuideStep(
    guide_id="after",
    step_id="after.added-still",
    title="补充结果仍显示同一问题；不能据此关闭问题",
    related="新结果登记了同一对象上的问题，部分改善不能关闭其他问题。",
    where="对比区“与之前相比”；底部“添加操作后的结果”或“保存说明”。",
    actions=(
        "保留两次结果和比较限制，不需要重复提交同一份材料。",
        "如果另有同一对象的新复核，可以添加；没有就保存交接。",
        "不要修改记录或图片来让结果看起来一致。",
    ),
    observe="新结果是否仍列同一问题码和帧；比较范围是否一致。",
    return_hint="添加新的有效结果，或保存说明。",
    stop="没有新结果时保存交接；不能写成已修复。",
    feedback=(),
    source=(
        "`docs/workflow-design.md` 第 7 节：复验状态与比较限制。",
        "`AGENTS.md`：缺失、未知和冲突必须保留。",
    ),
)

AFTER_INCOMPARABLE = GuideStep(
    guide_id="after",
    step_id="after.added-incomparable",
    title="补充结果与原始问题不能直接比较",
    related="对象、批次或比较口径不同，不能证明之前的问题已恢复。",
    where="对比区“与之前相比”列出的比较限制。",
    actions=(
        "保留两份记录各自的运行标识、对象和口径。",
        "只有在能获得同一对象的可比结果时才继续比较；否则保存交接。",
        "不要把不同批次或不同对象的正常结果当作复验通过。",
    ),
    observe="两份记录的对象、run_id、图片摘要和 comparison_basis 是否一致。",
    return_hint="如果有可比的新结果，可添加；否则保存说明。",
    stop="不可比较时保存交接，不猜测原因或修复效果。",
    feedback=(),
    source=(
        "`AGENTS.md`：不同批次不能证明旧问题已恢复。",
        "`docs/first-guide-and-trial-plan.md` G2/G3：比较条件必须明示。",
    ),
)

AFTER_INSUFFICIENT = GuideStep(
    guide_id="after",
    step_id="after.added-insufficient",
    title="补充结果不足以形成复验结论",
    related="新结果没有完成有效复核，或没有可用于比较的完整结果。",
    where="对比区“与之前相比”和补充记录的技术详情。",
    actions=(
        "保留新结果的状态和限制，不把它当作通过或失败。",
        "补齐有效复核后再添加；没有就保存交接。",
        "不要用空计数、未完成状态或重复文件替代结果。",
    ),
    observe="新结果是否有可评价的复核状态和完整计数。",
    return_hint="添加有效结果，或保存说明。",
    stop="证据不足时保存交接，保持“证据不足 / 不可比较”。",
    feedback=(),
    source=(
        "`docs/workflow-design.md` 第 7 节：证据不足与不可比较分开。",
        "`AGENTS.md`：缺失与未知必须保留。",
    ),
)

AFTER_PASSED = GuideStep(
    guide_id="after",
    step_id="after.added-passed",
    title="在已核实的可比较范围内，登记的问题不再出现",
    related="这只说明该对象和该检查范围内的结果，不说明原因，也不说明整台设备合格。",
    where="对比区“与之前相比”；保存说明。",
    actions=(
        "保留原报告、新结果和比较范围，不要删掉旧的失败记录。",
        "在说明中写明“范围内通过”，不要写成已修复或根因已确认。",
        "如果范围不覆盖你关心的帧，另行保留记录并交接。",
    ),
    observe="比较范围是否覆盖原问题；是否仍有未解决的未知项。",
    return_hint="保存说明；如需扩展范围，另行核对。",
    stop="不能外推到其他批次、其他对象或根因。",
    feedback=(),
    source=(
        "`docs/first-guide-and-trial-plan.md`：只写指定范围内的复验通过。",
        "`AGENTS.md`：复验通过不等于根因确认。",
    ),
)

QR_PASSED_WITHOUT_ISSUES = replace(
    AFTER_PASSED,
    title="本次检查范围内，两份记录均未登记问题",
    actions=("保留主报告和补充报告，分别注明各自的解码结果与内容核验结论。",),
    observe="答案来源、核验范围和仍未知的事项是否已写入交接说明。",
)

GENERIC_HANDOFF = GuideStep(
    guide_id="handoff",
    step_id="handoff.save",
    title="保存当前说明，交给技术人员继续处理",
    related="现有材料不足以继续做有依据的人工核对。",
    where="主窗口底部“保存说明”。",
    actions=(
        "先预览说明，检查里面有没有不愿分享的路径或个人信息。",
        "保存为新的 `.md` 文件；不要覆盖同名文件。",
        "把说明交给技术人员；他们可能仍需另行索取原始记录。",
    ),
    observe="说明里是否写清已知、未知和仍缺的材料。",
    return_hint="保存后停止；本程序不会自动修复或推断根因。",
    stop="保存失败时留在原界面重试，不要声称已保存。",
    feedback=(),
    source=(
        "`docs/simple-app-design.md` 第 4 节：说明不是完整证据包。",
        "`AGENTS.md`：未执行就写未执行，不伪造结论。",
    ),
)


# ---------------------------------------------------------------- 选择当前卡

def _feedback(session, step_id: str, *, context: str = "主报告",
              guide_version: str | None = None):
    """按调查、上下文和指引版本取反馈；旧会话对象没有新签名时退回 step_id。"""
    finder = getattr(session, "latest_feedback", None)
    if finder is None:
        return None
    try:
        return finder(step_id, context=context, guide_version=guide_version)
    except TypeError:   # 兼容只接受 step_id 的旧测试替身
        return finder(step_id)


def _card(step: GuideStep, *, context: str = "主报告", note: str = "",
          related: str | None = None) -> ActionCard:
    return ActionCard(step=step, context=context, note=note, related_override=related)


def _handoff_for(step: GuideStep, *, context: str, note: str,
                 related: str | None = None) -> ActionCard:
    related = related or f"你选择了“做不了或不确定”。这一步的停止条件是：{step.stop}"
    return _card(GENERIC_HANDOFF, context=context,
                 note=note, related=related)


def _primary_steps(report) -> list[GuideStep]:
    """按报告字段选择有序步骤；未知情况只给交接，不猜修复动作。"""
    report_type = report.report_type
    if report_type == "label_baseline":
        summaries = report.get("decode_summaries", default=[]) or []
        states = [
            ((summary.get("decode") or {}).get("status"), summary.get("region") or {})
            for summary in summaries
        ]
        decoded_like = any(state in {"decoded", "ambiguous", "conflict"} for state, _ in states)
        failed = any(
            state in {"decode_error", "execution_error"}
            or (summary.get("truth_check") or {}).get("status") == "decode_error"
            for (state, _), summary in zip(states, summaries)
        )
        ambiguous = any(state in {"ambiguous", "conflict"} for state, _ in states)
        truth = (report.get("known_truth", default={}) or {}).get("status", "not_provided")
        truth_provided = truth == "provided"
        checks = [
            (summary.get("truth_check") or {}).get("status") for summary in summaries
        ]
        compared = any(state in {"correct", "incorrect"} for state in checks)
        unusable = any(state not in {"correct", "incorrect", "not_provided"} for state in checks)
        steps: list[GuideStep] = []
        if not truth_provided and decoded_like:
            steps.append(G1_TRUTH)
        if truth_provided and (compared or unusable):
            steps.append(G1_TRUTH_SCOPE)
        if failed or ambiguous or report.get("status") == "completed_with_errors":
            steps.append(G1_REGION)
        if not steps:
            steps.append(GENERIC_HANDOFF)
        return steps

    if report_type == "capture_task_review":
        from .reports import review_validation_warnings
        if report.warnings or review_validation_warnings(report.data):
            return [GENERIC_HANDOFF]
        verification = report.get("verification_status")
        if verification == "not_reviewed":
            return [G2_NOT_REVIEWED]
        # 未知状态不能按“发现问题”或“一致”给出动作；保留原字段并交接。
        if verification not in {"consistent", "inconsistent"}:
            return [GENERIC_HANDOFF]
        if verification == "consistent":
            # 与问题码矛盾的一致结论不能只展示自身步骤，冲突交给技术人员。
            if report.get("issues", default=[]) or []:
                return [GENERIC_HANDOFF]
            return [G2_CONSISTENT]
        codes = []
        for issue in report.get("issues", default=[]) or []:
            code = issue.get("code")
            if code and code not in codes:
                codes.append(code)
        steps = []
        if "frame_unverifiable" in codes:
            steps.append(G2_FRAME)
        if "metric_mismatch" in codes:
            steps.append(G2_METRIC)
        if any(code in KNOWN_RECORD_CODES for code in codes):
            steps.append(G2_RECORDS)
        if not steps:
            # inconsistent 但没有问题码，或问题码未知：保留原始记录，交给技术人员。
            steps.append(GENERIC_HANDOFF)
        return steps

    # camera_timed_capture
    status = report.get("status")
    stop_reason = report.get("stop_reason")
    if status == "completed":
        return [G3_COMPLETED]
    if stop_reason == "open_failed":
        return [G3_OPEN]
    return [G3_FAILED]


def _step_for_new_problem(report) -> GuideStep:
    report_type = report.report_type
    if report_type == "capture_task_review":
        codes = [issue.get("code") for issue in report.get("issues", default=[]) or []]
        if "frame_unverifiable" in codes:
            return G2_FRAME
        if "metric_mismatch" in codes:
            return G2_METRIC
        if any(code in KNOWN_RECORD_CODES for code in codes):
            return G2_RECORDS
        return GENERIC_HANDOFF
    if report_type == "label_baseline":
        return G1_REGION
    if report.get("stop_reason") == "open_failed":
        return G3_OPEN
    return G3_FAILED


KNOWN_RECORD_CODES = {
    "image_hash_mismatch", "csv_keys_mismatch",
    "task_sample_count_mismatch", "task_sample_state_mismatch",
    "task_not_completed", "measurement_context_unavailable",
    "measurement_context_differs",
}


def _steps_for_new_problems(report, keys) -> list[GuideStep]:
    """只为新出现的问题给出有序步骤；未知问题码只给交接。"""
    if report.report_type == "capture_task_review":
        codes: list[str] = []
        for key in keys:
            code = key.split(":", 1)[0]
            if code and code not in codes:
                codes.append(code)
        steps: list[GuideStep] = []
        if "frame_unverifiable" in codes:
            steps.append(G2_FRAME)
        if "metric_mismatch" in codes:
            steps.append(G2_METRIC)
        if any(code in KNOWN_RECORD_CODES for code in codes):
            steps.append(G2_RECORDS)
        if not steps:
            steps.append(GENERIC_HANDOFF)
        return steps
    if report.report_type == "label_baseline":
        return [G1_REGION]
    if report.get("stop_reason") == "open_failed":
        return [G3_OPEN]
    return [G3_FAILED]


def _addition_steps(addition) -> list[GuideStep]:
    """补充记录对应的有序步骤；没有具体动作时只给汇总卡（空列表）。"""
    if getattr(addition, "is_repeat", False):
        return []
    new_keys = getattr(addition, "new_problem_keys", []) or []
    if new_keys:
        return _steps_for_new_problems(addition.report, new_keys)
    return []


def _addition_note(addition) -> str:
    note = addition.recheck_reason
    if addition.comparison_reason != addition.recheck_reason:
        note = f"{note} 比较限制：{addition.comparison_reason}"
    return note


def _addition_related(addition, step: GuideStep) -> str:
    if getattr(addition, "new_problem_keys", []) or []:
        related = f"新结果出现了原记录中没有登记的问题：{addition.recheck_reason}"
        if addition.report.report_type == "camera_timed_capture":
            related += " 这是另一次运行；即使正常，也不证明原失败的根因或物理恢复。"
        return related
    related = f"{step.related} {addition.recheck_reason}"
    if (step is AFTER_INCOMPARABLE
            and addition.report.report_type == "camera_timed_capture"):
        related += (" 这是后续的另一次运行；即使它正常，也不能证明原打开失败的根因"
                    "或物理恢复。")
    return related


def _addition_summary_card(primary, addition, context: str) -> ActionCard:
    """没有具体动作时的汇总卡。"""
    from .session import (  # 延迟导入，避免模块加载环
        RECHECK_FAILED,
        RECHECK_INCOMPARABLE,
        RECHECK_INSUFFICIENT,
        RECHECK_PASSED,
        registered_problem_labels,
    )

    note = _addition_note(addition)
    if getattr(addition, "is_repeat", False):
        return _card(AFTER_REPEAT, context=context, note=note,
                     related=f"{AFTER_REPEAT.related} {addition.recheck_reason}")

    if addition.recheck_result == RECHECK_FAILED:
        step = AFTER_STILL
    elif addition.recheck_result == RECHECK_INCOMPARABLE:
        step = AFTER_INCOMPARABLE
    elif addition.recheck_result == RECHECK_INSUFFICIENT:
        step = AFTER_INSUFFICIENT
    elif addition.recheck_result == RECHECK_PASSED:
        step = AFTER_PASSED
        # “范围内通过”已排除补充报告登记问题；主报告也没有问题时只陈述本次记录。
        if primary.report_type == "label_baseline" and not registered_problem_labels(primary):
            step = QR_PASSED_WITHOUT_ISSUES
    else:
        step = AFTER_INSUFFICIENT
    return _card(step, context=context, note=note,
                 related=_addition_related(addition, step))


def _addition_card(session, addition, number: int) -> ActionCard:
    """补充记录卡：先走该记录自己的步骤，再处理归属于它的用户反馈。

    反馈按调查 + “补充记录 N” + 指引版本查询，后续补充记录不会继承。
    “做不了或不确定”直接进入交接；“已做完”转到下一步或等待新结果的卡，
    不反复索取已经完成的材料；“问题仍在 / 暂时没再出现”只保留用户声明。
    """
    context = f"补充记录 {number}"
    note = _addition_note(addition)
    handled: tuple[GuideStep, object] | None = None
    for step in _addition_steps(addition):
        feedback = _feedback(session, step.step_id, context=context,
                             guide_version=step.version)
        if feedback is None:
            return _card(step, context=context, note=note,
                         related=_addition_related(addition, step))
        if feedback.choice == FEEDBACK_BLOCKED:
            return _handoff_for(
                step, context=context, note=note,
                related=f"你选择了“做不了或不确定”。这一步的停止条件是：{step.stop}")
        if feedback.choice in {FEEDBACK_STILL, FEEDBACK_NOT_SEEN}:
            declaration = f"你记录：{feedback.label}（用户声明，未独立验证）。"
            return _card(AFTER_OBSERVATION, context=context,
                         note=f"{declaration} {note}",
                         related=f"{AFTER_OBSERVATION.related} 你的说法是"
                                 f"“{feedback.label}”，仍需新结果才能核对变化。")
        handled = (step, feedback)
        # “已做完”继续看该记录的下一个步骤，不重复索取已完成的材料。

    if handled is not None:
        step, feedback = handled
        declaration = (f"你已完成步骤 {step.step_id}（{feedback.label}）；"
                       f"这不是问题已修好的证明。")
        return _card(AFTER_OBSERVATION, context=context,
                     note=f"{declaration} {note}",
                     related=f"{AFTER_OBSERVATION.related} {step.title} 已由你记录完成。")
    return _addition_summary_card(session.primary, addition, context)


def _with_primary_detail(card: ActionCard, report) -> ActionCard:
    """给固定的步骤补上当前报告里的具体对象；不改变动作内容。"""
    if card.step is G2_FRAME:
        frames = []
        for issue in report.get("issues", default=[]) or []:
            if issue.get("code") == "frame_unverifiable" and issue.get("frame_count") is not None:
                frames.append(str(issue.get("frame_count")))
        if frames:
            related = (f"复核记录了帧 {'、'.join(frames)} 无法核实；原因可能是缺失、"
                       f"不可读或其他，不能直接归因为磁盘写入失败。")
            return ActionCard(card.step, card.context, card.note, related)
    if card.step is G2_METRIC:
        frames = []
        for issue in report.get("issues", default=[]) or []:
            if issue.get("code") == "metric_mismatch" and issue.get("frame_count") is not None:
                frames.append(str(issue.get("frame_count")))
        if frames:
            related = (f"复核记录了帧 {'、'.join(frames)} 的指标差异；不能据此"
                       f"认定相机损坏。")
            return ActionCard(card.step, card.context, card.note, related)
    if card.step is G3_OPEN:
        index = report.get("config", default={}).get("camera_index")
        backend = (report.get("camera", default={}) or {}).get("requested_backend")
        if index is not None:
            related = (f"这次用编号 {index}、后端 {backend or '未知'} 打开设备失败；"
                       f"单凭记录不能确定编号、占用、权限、驱动还是硬件原因。")
            return ActionCard(card.step, card.context, card.note, related)
    return card


def _record_card(session: "Session") -> ActionCard | None:
    """确定当前只突出的一项动作。纯函数，不修改会话。"""
    primary = getattr(session, "primary", None)
    if primary is None:
        return None

    additions = list(getattr(session, "additions", []) or [])
    if additions:
        return _addition_card(session, additions[-1], len(additions))

    steps = _primary_steps(primary)
    handled: tuple[GuideStep, object] | None = None
    for step in steps:
        feedback = _feedback(session, step.step_id)
        if feedback is None:
            return _with_primary_detail(_card(step), primary)
        if feedback.choice == FEEDBACK_BLOCKED:
            return _with_primary_detail(
                _handoff_for(step, context="主报告",
                             note=f"你记录：{feedback.label}（用户声明，未独立验证）。"),
                primary,
            )
        if feedback.choice in {FEEDBACK_STILL, FEEDBACK_NOT_SEEN}:
            note = f"你记录：{feedback.label}（用户声明，未独立验证）。"
            return _card(AFTER_OBSERVATION, note=note,
                         related=f"{AFTER_OBSERVATION.related} 你的说法是“{feedback.label}”，"
                                 f"仍需新结果才能核对变化。")
        handled = (step, feedback)
        # “已做完”继续看下一个未处理步骤，避免反复索取已经完成的材料。

    if handled is not None:
        step, feedback = handled
        note = (f"你已完成步骤 {step.step_id}（{feedback.label}）；这不是问题已修好的证明。")
        return _card(AFTER_OBSERVATION, note=note,
                     related=f"{AFTER_OBSERVATION.related} {step.title} 已由你记录完成。")
    return _card(GENERIC_HANDOFF)


def current_card(session: "Session") -> ActionCard | None:
    """当前操作读同一调查状态，局部比较不会覆盖尚未解决的问题。"""
    card = _record_card(session)
    if card is None or session.primary.report_type != "capture_task_review":
        return card
    problems = session.review_problems()
    if not problems:
        return card
    state, summary = session.investigation_summary()
    if any(problem.resolved_by is None for problem in problems):
        step = AFTER_INSUFFICIENT if card.step is AFTER_PASSED else card.step
        # 在此只陈述调查状态；单次比较及其范围保留在对比区。
        note = summary if card.step is AFTER_PASSED else f"{summary} {card.note}"
        related = summary if card.step is AFTER_PASSED else f"{summary} {card.related}"
        return ActionCard(step, card.context, note, related)
    from .session import RECHECK_PASSED
    if state == RECHECK_PASSED:
        return ActionCard(AFTER_PASSED, card.context, summary, summary)
    return ActionCard(card.step, card.context, f"{summary} {card.note}", f"{summary} {card.related}")
