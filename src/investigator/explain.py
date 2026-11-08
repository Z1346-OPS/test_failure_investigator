"""确定性解释：把一份已校验的报告翻译成“发现 / 还不能确认 / 下一步”。

规则来自 docs/first-guide-and-trial-plan.md 的 G1–G3 场景卡。全部为固定规则，
不调用模型、不联网。解释只能引用报告里实际存在的字段。

必须守住的边界（见 docs/product-direction.md、docs/workflow-design.md）：
  * QR 单一读出不是内容正确；没有独立答案就保持未验证。
  * 缺图/无法核实不能直接归因为磁盘写入失败。
  * 指标差异不能直接归因为硬件损坏。
  * 用户说恢复不等于复验通过；后续成功不等于根因确认。
  * 材料不足就保留未知，只给一项有依据的下一步；不生成根因猜测列表。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .reports import LoadedReport, label_validation_warnings, review_validation_warnings

# ---------------------------------------------------------------- 词汇表

DECODE_TEXT = {
    "decoded": "读出了一个二维码",
    "not_decoded": "没有读出二维码",
    "ambiguous": "检测到多个候选码，存在歧义，尚不能选定一个有效答案",
    "conflict": "多次尝试读出的内容互相冲突，不能选定一个答案",
    "decode_error": "检测到候选码，但解码报告错误",
    "execution_error": "解码过程发生执行错误，这次尝试的结果无效",
}

# 解析失败的尝试：这些是执行错误，不是“没有二维码”。
FAILED_DECODE_STATES = frozenset({"decode_error", "execution_error"})

REVIEW_ISSUE_TEXT = {
    "frame_unverifiable": "有帧无法核实",
    "metric_mismatch": "记录值与按当前算法重算的值不同",
    "image_hash_mismatch": "留证图片的文件摘要与任务记录不一致",
    "csv_keys_mismatch": "CSV 的关联键与任务声明的集合不一致",
    "task_sample_count_mismatch": "任务声明的样本数与实际记录不一致",
    "task_sample_state_mismatch": "样本的保存状态与任务声明不一致",
    "task_not_completed": "任务本身没有完成",
    "measurement_context_unavailable": "任务缺少测量口径字段",
    "measurement_context_differs": "任务的测量口径与当前不同",
}

STOP_REASON_TEXT = {
    "duration_reached": "按设定时长结束",
    "no_samples": "到时结束但没有取得完整样本",
    "read_failed": "读取画面失败",
    "invalid_frame": "读到无效图像",
    "open_failed": "打开设备失败",
    "release_failed": "释放设备失败",
    "interrupted": "被中断",
    "execution_error": "执行出错",
    "save_failed": "保存失败",
    "measurement_failed": "测量失败",
}


@dataclass
class NextStep:
    title: str
    why: str
    bring_back: str


@dataclass
class Explanation:
    kind: str
    headline: str
    findings: list[str] = field(default_factory=list)
    unknowns: list[str] = field(default_factory=list)
    next_steps: list[NextStep] = field(default_factory=list)
    technical: list[tuple[str, str]] = field(default_factory=list)
    evidence: list[tuple[str, str, str]] = field(default_factory=list)


class _Evidence:
    """证据索引：编号由程序产生，绑定字段定位。"""

    def __init__(self) -> None:
        self.items: list[tuple[str, str, str]] = []

    def add(self, locator: str, note: str = "") -> str:
        ident = f"E{len(self.items) + 1:02d}"
        self.items.append((ident, locator, note))
        return ident


def _region_label(region: dict) -> str:
    kind = region.get("kind")
    if kind == "roi":
        return (f"ROI（x={region.get('x')}, y={region.get('y')}, "
                f"宽={region.get('width')}, 高={region.get('height')}）")
    return "整图"


def _base_technical(report: LoadedReport) -> list[tuple[str, str]]:
    return [
        ("来源文件", report.source_name),
        ("文件摘要（SHA-256，前 16 位）", report.source_sha256[:16]),
        ("文件大小（字节）", str(report.size_bytes)),
        ("报告类型", f"{report.report_type}"),
        ("schema_version", str(report.schema_version)),
    ]


# ---------------------------------------------------------------- QR（G1）

def qr_content_conclusion(report: LoadedReport) -> str:
    """交接首页对单份 QR 报告自身的内容核验结论。"""
    if report.warnings or label_validation_warnings(report.data):
        return "记录存在校验提示，内容比对结论仍需复核。"
    truth = report.get("known_truth", "status")
    findings = []
    for summary in report.get("decode_summaries", default=[]):
        region = summary["region"]
        label = _region_label(region) if region.get("kind") in {"full_image", "roi"} else "未知区域"
        state = summary["decode"]["status"]
        result = summary["truth_check"]["status"]
        if truth == "provided" and state == "decoded" and result in {"correct", "incorrect"}:
            match = "一致" if result == "correct" else "不一致"
            findings.append(f"{label}读出的内容与所给答案逐字节{match}")
        else:
            findings.append(label + DECODE_TEXT.get(state, "的解码状态未知"))
    if not findings:
        return "缺少区域结果，内容正确性未验证。"
    text = "；".join(findings)
    if truth == "not_provided":
        return text + "，但未提供独立答案，内容正确性未验证。"
    if truth != "provided":
        return text + "，独立答案状态未知。"
    return text + "。"


def _explain_qr(report: LoadedReport) -> Explanation:
    evidence = _Evidence()
    findings: list[str] = []
    unknowns: list[str] = []
    steps: list[NextStep] = []

    status = report.get("status", default="未知")
    summaries = report.get("decode_summaries", default=[]) or []
    truth = report.get("known_truth", default={}) or {}
    truth_status = truth.get("status", "not_provided")
    truth_provided = truth_status == "provided"
    attempts = report.get("attempts", default=[]) or []

    findings.append(f"这份 QR 分析的整体状态是 {status}。")

    # 区域结果分开列出：整图与 ROI 不能只挑较好的一次。
    region_states: dict[str, str] = {}
    for index, summary in enumerate(summaries):
        region = summary.get("region", {}) or {}
        label = _region_label(region)
        decode = summary.get("decode", {}) or {}
        state = decode.get("status", "未知")
        region_states[label] = state
        locator = f"decode_summaries[{index}].decode.status"
        ident = evidence.add(locator, f"{label} 的解码状态")
        text = DECODE_TEXT.get(state, f"状态为未预期的 {state!r}")
        findings.append(f"{label}：{text}。（{ident}，{locator}）")

    if not summaries:
        unknowns.append("报告里没有区域汇总，无法判断任何区域的结果。")

    # 执行错误不能被正常项覆盖。
    failed_regions = [label for label, state in region_states.items() if state in FAILED_DECODE_STATES]
    if failed_regions:
        findings.append(
            "以下区域包含解码或执行错误，需要与正常区域分开看待："
            + "、".join(failed_regions) + "。"
        )
    if status == "completed_with_errors":
        unknowns.append("分析整体标记为包含错误，报告的可读结果不能代表全部分析都成功。")

    failed_attempts = [
        i for i, attempt in enumerate(attempts)
        if (attempt.get("decode", {}) or {}).get("status") in FAILED_DECODE_STATES
    ]
    if failed_attempts:
        ident = evidence.add("attempts[].decode.status", "失败的解码尝试")
        findings.append(
            f"共有 {len(failed_attempts)} 次解码尝试失败，原始记录保留在 attempts 中。（{ident}）"
        )

    # 真值：逐区域的 truth_check.status 才是比对结果；
    # known_truth.status 只说明是否存在独立答案。
    region_truth: dict[str, str] = {}
    for index, summary in enumerate(summaries):
        region = summary.get("region", {}) or {}
        check = summary.get("truth_check", {}) or {}
        region_truth[_region_label(region)] = check.get("status", "未知")
    evidence.add("known_truth.status", "独立答案是否提供")

    matched: list[str] = []
    mismatched: list[str] = []
    errored: list[str] = []
    if not truth_provided:
        unknowns.append("没有独立答案，尚未验证内容是否正确。"
                        "重复读出或解码器自身输出都不能当作独立答案。")
    else:
        matched = [label for label, state in region_truth.items() if state == "correct"]
        mismatched = [label for label, state in region_truth.items() if state == "incorrect"]
        # 区域级比对状态不是一致/不一致（而不是没比对）时不能被“没有不一致”掩盖。
        errored = [f"{label}：{state}" for label, state in region_truth.items()
                   if state not in {"correct", "incorrect", "not_provided"}]
        if matched:
            findings.append("报告记录了与独立答案逐字节比对一致的结果（"
                            + "、".join(matched) + "）。")
            unknowns.append("比对一致只针对这份答案和这次分析范围，"
                            "不能扩展成整机或跨场景结论。")
        if mismatched:
            findings.append("报告记录了与独立答案逐字节比对不一致的结果（"
                            + "、".join(mismatched) + "）。")
            unknowns.append("比对不一致只说明这份答案不匹配，原因未知。")
        if errored:
            findings.append("以下区域的答案比对没有给出可用结果（"
                            + "；".join(errored) + "）。")
            unknowns.append("比对未完成不等于内容正确，也不等于内容错误，需要查看原始记录。")
        if not matched and not mismatched and not errored:
            unknowns.append("虽然有独立答案，但没有任何区域完成可用的逐字节比对。")
        evidence.add("decode_summaries[].truth_check.status", "逐区域比对结果")

        source = truth.get("source_description")
        if isinstance(source, str) and source:
            unknowns.append(f"答案来源是用户声明的（未由本程序独立核实）：{source}。")

    any_decoded = any(state == "decoded" for state in region_states.values())
    any_ambiguous = any(state == "ambiguous" for state in region_states.values())
    any_conflict = any(state == "conflict" for state in region_states.values())

    # 下一步：最多突出一项，来自已核实指引。
    if not truth_provided and (any_decoded or any_ambiguous or any_conflict):
        steps.append(NextStep(
            title="确认是否有独立的原始答案和已有比对结果",
            why="只有独立答案与解码结果逐字节比对，才能判断内容是否正确。",
            bring_back="独立答案的来源说明，以及已有的比对记录；没有就说明没有。",
        ))
    elif matched or mismatched or errored:
        steps.append(NextStep(
            title="核对答案来源、图片身份和比对范围",
            why="比对结果只在它覆盖的答案与范围内成立。",
            bring_back="答案的独立来源、对应图片标识和本次比对覆盖的范围。",
        ))
    if any_ambiguous or any_conflict:
        steps.append(NextStep(
            title="保留整图与 ROI 的对照，交给技术人员",
            why="歧义或冲突不能靠重复扫描消除，需要保留原状态判断。",
            bring_back="各区域的解码状态、尝试记录和 ROI 范围。",
        ))
    if failed_regions or failed_attempts:
        steps.append(NextStep(
            title="保留原始错误类型与工具参数",
            why="执行错误的原因未知，需要保留原始记录而不是改记成功。",
            bring_back="错误类型、工具版本与参数、原始退出码（没有就写未知）。",
        ))
    if not steps:
        steps.append(NextStep(
            title="保存当前说明，交给技术人员继续处理",
            why="现有材料不足以给出进一步的人工核对动作。",
            bring_back="这份说明；技术人员可能需要另行索取原始分析记录。",
        ))

    if any_decoded and not truth_provided:
        unknowns.append("读出本身不代表内容正确，需要独立答案才能判断。")
    checks = list(dict.fromkeys(report.warnings + label_validation_warnings(report.data)))
    if checks:
        findings.extend("记录校验提示：" + warning for warning in checks)
        unknowns.append("记录的身份、比对或校验条件尚有缺失，不能据此确认复验通过。")

    return Explanation(
        kind="qr",
        headline="QR 分析 · 本次先帮你读懂报告",
        findings=findings,
        unknowns=unknowns,
        next_steps=steps,
        technical=_base_technical(report) + [
            ("analysis_id", str(report.get("analysis_id", default="未知"))),
            ("顶层 status", str(status)),
            ("独立答案状态", str(truth_status)),
            ("区域数量", str(len(summaries))),
            ("解码尝试次数", str(len(attempts))),
        ],
        evidence=evidence.items,
    )


# ---------------------------------------------------------------- 复核（G2）

def _explain_review(report: LoadedReport) -> Explanation:
    evidence = _Evidence()
    findings: list[str] = []
    unknowns: list[str] = []
    steps: list[NextStep] = []

    task_status = report.get("task_status", default="未知")
    verification = report.get("verification_status", default="未知")
    counts = report.get("counts", default=None)
    issues = report.get("issues", default=[]) or []
    warnings = report.get("warnings", default=[]) or []
    checks = list(dict.fromkeys(report.warnings + review_validation_warnings(report.data)))

    findings.append(f"被复核的采集任务状态是 {task_status}。")
    evidence.add("task_status", "被复核任务的状态")
    seen_codes: set[str] = set()

    if verification == "consistent" and not issues:
        if checks:
            findings.append("报告声明一致，但存在校验矛盾或缺失，不能确认检查通过。")
        else:
            findings.append("本次检查范围内，记录与重算结果一致。")
        unknowns.append(
            "报告的一致性声明仍有矛盾或缺失，不能据此确认检查通过。"
            if checks else "一致只说明这份检查范围内没有发现问题，不能说明相机合格。")
        if counts:
            findings.append(
                f"报告声称核实 {counts.get('verified_frames')} 帧，"
                f"任务声明 {counts.get('reported_samples')} 个样本，"
                f"CSV 配对 {counts.get('csv_pairs')} 项。"
            )
            if counts.get("verified_frames") == 0:
                unknowns.append("没有帧通过核实，这次复核没有取得可确认的结果。")
            evidence.add("counts", "三个数量分别记录，不互相替代")
        else:
            unknowns.append("计数为 null，不能说明检查覆盖了多少帧。")
        steps.append(NextStep(
            title="核对这次检查的范围和帧数是否覆盖你关心的问题",
            why="一致只在覆盖范围内成立。",
            bring_back="你关心的是哪一批、哪一帧；以及本次检查是否覆盖到。",
        ))
    elif verification == "not_reviewed":
        findings.append("这次没有完成有效复核，不能判断数据是否一致。")
        if counts is None:
            unknowns.append("计数为 null，表示没有计数结果，不能当作 0 帧通过。")
        unknowns.append("没有完成复核不等于数据有问题，也不等于数据没问题。")
        evidence.add("verification_status", "未复核")
        steps.append(NextStep(
            title="先补齐可读的任务记录和复核材料",
            why="没有有效复核输入时，一致性无法评价。",
            bring_back="对应的采集任务记录，以及能产生复核结果的输入文件。",
        ))
    elif verification == "inconsistent" or verification == "consistent":
        # 一致但列出问题码：记录自相矛盾，不能只按“一致”展示。
        if verification == "consistent":
            findings.append("报告状态标记为一致，但同时又列出了问题码；这两个结论互相矛盾。")
            unknowns.append("状态与问题码冲突，不能只按一致处理；需要人工核对原始复核记录。")
        else:
            findings.append("本次复核发现了问题。")
        if counts:
            findings.append(
                f"报告声称核实 {counts.get('verified_frames')} 帧，"
                f"任务声明 {counts.get('reported_samples')} 个样本，"
                f"CSV 配对 {counts.get('csv_pairs')} 项。"
            )
            if counts.get("verified_frames") == 0:
                unknowns.append("没有帧通过核实，说明这次复核没有取得可确认的结果。")
            evidence.add("counts", "三个数量分别记录，不互相替代")

        seen_codes = _add_review_issues(issues, findings, unknowns, evidence)

        if not issues:
            unknowns.append("复核标记为有问题，但没有列出具体问题码，需要人工查看原始输出。")
            steps.append(NextStep(
                title="保存当前说明并交给技术人员",
                why="复核结论没有可核对的问题码，需要保留原始记录判断。",
                bring_back="这份说明和原始复核输出。",
            ))
        else:
            steps.extend(_review_issue_steps(seen_codes))
    else:
        findings.append(
            f"复核状态为未预期的 {verification!r}，不能判断数据是一致还是不一致。")
        unknowns.append("未预期的复核状态不能被当作通过，也不能当作发现了问题；"
                        "需要保留原始记录。")
        evidence.add("verification_status", "未预期的复核状态")
        if counts:
            findings.append(
                f"报告记录的覆盖帧数、样本数和 CSV 配对分别为 "
                f"{counts.get('verified_frames')}、{counts.get('reported_samples')}、"
                f"{counts.get('csv_pairs')}；计数本身不能替代一致性结论。"
            )
        if issues:
            seen_codes = _add_review_issues(issues, findings, unknowns, evidence)
        steps.append(NextStep(
            title="保存当前说明，交给技术人员继续处理",
            why="复核状态不在已支持范围内，不能判断数据是否一致。",
            bring_back="这份说明和原始复核记录。",
        ))

    if checks:
        findings.extend("记录校验提示：" + warning for warning in checks)
        unknowns.append("记录自身的矛盾或缺失尚未核对，不能作为问题已消失的证据。")
        steps = [NextStep(
            title="保存矛盾记录并交给技术人员核对",
            why="总体结论不能覆盖计数和帧级事实；原始字段保持不变。",
            bring_back="原复核输出与当前说明，不需要修改或补造报告字段。")]
    if warnings:
        findings.append(f"复核还记录了 {len(warnings)} 条提示，原始内容保留在技术详情。")
        evidence.add("warnings", "口径类提示，限制可比较范围")

    if not steps:
        steps.append(NextStep(
            title="保存当前说明，交给技术人员继续处理",
            why="现有材料不足以给出进一步的人工核对动作。",
            bring_back="这份说明；技术人员可能需要另行索取原始复核记录。",
        ))

    return Explanation(
        kind="capture_review",
        headline="采集复核 · 本次先帮你读懂报告",
        findings=findings,
        unknowns=unknowns,
        next_steps=steps,
        technical=_base_technical(report) + [
            ("run_id", str(report.get("run_id", default="未知"))),
            ("task_status", str(task_status)),
            ("verification_status", str(verification)),
            ("comparison_basis", str(report.get("comparison_basis", default="未知"))),
            ("counts", "null（没有计数结果）" if counts is None else str(counts)),
            ("问题码", "、".join(sorted(seen_codes)) if issues else "（无）"),
            ("提示条数", str(len(warnings))),
            ("记录校验", "；".join(checks) if checks else "未发现报告内部矛盾"),
        ],
        evidence=evidence.items,
    )


def _add_review_issues(issues, findings, unknowns, evidence) -> set[str]:
    """原样保留问题码，并为每个问题补一条影响说明（UI 与导出同源）。"""
    seen_codes: set[str] = set()
    for index, issue in enumerate(issues):
        code = issue.get("code", "未知")
        seen_codes.add(code)
        text = REVIEW_ISSUE_TEXT.get(code, f"问题码 {code!r}（未预期，原样保留）")
        frame = issue.get("frame_count")
        where = f"（帧 {frame}）" if frame is not None else ""
        ident = evidence.add(f"issues[{index}]", text)
        findings.append(f"{text}{where}。（{ident}）")

        if code == "frame_unverifiable":
            unknowns.append(
                "无法核实的原因需要看具体说明（缺失、不可读还是其他）；"
                "这个结果本身不能证明磁盘写入失败。"
            )
        elif code == "metric_mismatch":
            unknowns.append("记录值与重算值不同，不能据此认定相机损坏。")
        elif code == "image_hash_mismatch":
            unknowns.append("图片文件摘要不一致，可能是文件被改动或记录有误，原因未知。")
        elif code == "csv_keys_mismatch":
            unknowns.append("CSV 键集合与任务声明不一致，说明记录不完整，具体原因未知。")
    return seen_codes


def _review_issue_steps(seen_codes: set[str]) -> list[NextStep]:
    steps: list[NextStep] = []
    if "frame_unverifiable" in seen_codes:
        steps.append(NextStep(
            title="核对对应帧的图片位置和材料是否完整",
            why="无法核实往往来自文件缺失、拿错目录或权限问题，需要人工确认。",
            bring_back="该帧的图片是否还在原位置，以及是否漏带了目录。",
        ))
    if "metric_mismatch" in seen_codes:
        steps.append(NextStep(
            title="核对出现差异的帧是否同批次、算法上下文是否可比",
            why="不同批次或不同算法上下文的重算值不能直接对比。",
            bring_back="该帧所属批次，以及两次计算所用的算法与阈值说明。",
        ))
    if "frame_unverifiable" not in seen_codes and "metric_mismatch" not in seen_codes:
        steps.append(NextStep(
            title="保存当前说明并交给技术人员",
            why="问题码未在已核实指引覆盖范围内，需要保留原始记录判断。",
            bring_back="这份说明和原始复核输出。",
        ))
    return steps


# ---------------------------------------------------------------- 采集任务（G3）

def _explain_capture_task(report: LoadedReport) -> Explanation:
    evidence = _Evidence()
    findings: list[str] = []
    unknowns: list[str] = []
    steps: list[NextStep] = []

    status = report.get("status", default="未知")
    stop_reason = report.get("stop_reason", default="未知")
    config = report.get("config", default={}) or {}
    camera = report.get("camera", default={}) or {}
    counts = report.get("counts", default={}) or {}
    samples = report.get("samples", default=[]) or []
    primary_error = report.get("primary_error", default=None)
    cleanup_errors = report.get("cleanup_errors", default=[]) or []

    camera_index = config.get("camera_index")
    backend = camera.get("actual_backend") or camera.get("requested_backend") or "未知"
    stop_text = STOP_REASON_TEXT.get(stop_reason, f"停止原因 {stop_reason!r}（未预期）")

    findings.append(f"这次采集的状态是 {status}，{stop_text}。")
    evidence.add("status", "任务状态")
    evidence.add("stop_reason", "停止原因")

    if status == "completed":
        completion = "报告声明完成" if report.warnings else "按计划完成"
        findings.append(
            f"{completion}了 {counts.get('samples_completed')} 个样本，"
            f"读取 {counts.get('read_attempts')} 次，有效帧 {counts.get('valid_frames')} 个。"
        )
        evidence.add("counts", "读取/有效帧/样本计数")
        unknowns.append("采集完成只说明这次流程走完，不能说明画面质量或设备合格。")
        steps.append(NextStep(
            title="保存当前说明；如需判断画面质量，另行核对留证图片与复核记录",
            why="采集完成本身不评价画面质量。",
            bring_back="如果需要评价，带上对应的复核记录或具体关心的帧。",
        ))
    else:
        # 执行失败：区分“执行出错”和“业务结果”，不把两者混成一个标签。
        if stop_reason == "open_failed":
            findings.append(
                f"这次没有成功打开请求的设备（编号 {camera_index}，后端 {backend}）。"
            )
            unknowns.append(
                "单凭这条记录还不能确定是编号不对、设备被占用、权限、驱动还是硬件原因。"
            )
            steps.append(NextStep(
                title="对照这次请求的编号与后端，确认是不是你原本想用的那台设备",
                why="打开失败只表示这一次没有成功，先确认目标设备是否一致。",
                bring_back="你实际想用的设备，以及之后是否手动重试过、产生了哪些新记录。",
            ))
        elif stop_reason == "read_failed":
            findings.append("采集过程中读取画面失败，任务提前结束。")
            unknowns.append("读取失败的原因未知，可能是设备状态、占用或连接问题。")
            steps.append(NextStep(
                title="确认失败后是否已经手动重新采集，并保留新的采集与复核记录",
                why="需要新的记录才能判断后续是否可用。",
                bring_back="新记录的运行标识、时间和复核结果；没有就说明没有。",
            ))
        else:
            findings.append(f"这次任务没有正常完成（{stop_text}）。")
            unknowns.append("具体原因需要看原始错误记录，本程序不作推测。")
            steps.append(NextStep(
                title="保留原始错误记录并交给技术人员",
                why="停止原因不在已核实指引的常见范围内。",
                bring_back="这份说明和原始任务报告。",
            ))

    if primary_error:
        stage = primary_error.get("stage", "未知")
        etype = primary_error.get("type", "未知")
        ident = evidence.add("primary_error", "首个执行错误")
        findings.append(f"记录了执行错误：阶段 {stage}，类型 {etype}。（{ident}）")
        unknowns.append("执行错误不等于硬件损坏，也不等于业务问题，需要保留原始错误判断。")

    if cleanup_errors:
        findings.append(f"释放设备时记录了 {len(cleanup_errors)} 条错误。")
        evidence.add("cleanup_errors", "释放阶段错误")

    if samples:
        findings.append(f"任务报告里保留了 {len(samples)} 条样本记录。")
        evidence.add("samples", "逐样本记录")
    if report.warnings:
        findings.extend("记录校验提示：" + warning for warning in report.warnings)
        unknowns.append("任务记录自身的矛盾尚未核对，完成状态和计数仅为报告声明。")

    if not steps:
        steps.append(NextStep(
            title="保存当前说明，交给技术人员继续处理",
            why="现有材料不足以给出进一步的人工核对动作。",
            bring_back="这份说明；技术人员可能需要另行索取原始任务报告。",
        ))

    return Explanation(
        kind="capture_task",
        headline="定时采集任务 · 本次先帮你读懂报告",
        findings=findings,
        unknowns=unknowns,
        next_steps=steps,
        technical=_base_technical(report) + [
            ("run_id", str(report.get("run_id", default="未知"))),
            ("status", str(status)),
            ("stop_reason", str(stop_reason)),
            ("camera_index", str(camera_index)),
            ("requested_backend", str(camera.get("requested_backend", "未知"))),
            ("actual_backend", str(camera.get("actual_backend", "未知"))),
            ("first_frame_size", str(camera.get("first_frame_size", "未知"))),
            ("capture_elapsed_seconds",
             str(report.get("timings", default={}).get("capture_elapsed_seconds", "未知"))),
            ("样本数", str(len(samples))),
        ],
        evidence=evidence.items,
    )


def unknown_impact(text: str) -> str:
    """为“这份报告还不能说明什么”的每一项补一句影响说明。

    只解释已有未知的边界，不推断原因，也不新增事实。界面和导出共用这里的
    一句话，避免两处各写一套。匹配不到时保留保守的通用说明。
    """
    rules = (
        ("没有独立答案",
         "即使读出了二维码，也不能判断内容是否正确。"),
        ("读出本身不代表内容正确",
         "读出次数或重复一致不能替代独立答案。"),
        ("比对一致只针对",
         "一致性不能扩展成整机、其他图片或其他场景的结论。"),
        ("比对不一致只说明",
         "这只说明这份答案不匹配，不能据此推断原因。"),
        ("比对未完成",
         "没有完成比对既不代表正确，也不代表错误。"),
        ("无法核实的原因",
         "现有记录只能说明这一帧没有核对结果，不能归因为磁盘或硬件。"),
        ("记录值与重算值不同",
         "差异本身不能证明相机损坏，也不能证明记录正确。"),
        ("图片文件摘要不一致",
         "可能是文件被改动或记录有误，原因未知。"),
        ("CSV 键集合",
         "记录不完整，具体原因未知。"),
        ("检查范围内没有发现问题",
         "一次检查范围内一致，不能说明相机合格。"),
        ("采集完成只说明",
         "流程完成不等于画面质量或设备状态合格。"),
        ("单凭这条记录还不能确定",
         "不能把这次失败归因为某个具体原因。"),
        ("没有完成复核",
         "不能判断数据是一致还是不一致。"),
        ("执行错误不等于",
         "需要保留原始错误判断，不能改记为成功。"),
        ("没有帧通过核实",
         "这次复核没有取得可确认的结果。"),
    )
    for marker, impact in rules:
        if marker in text:
            return impact
    return "这会限制当前能得出的结论，需要保留为未知。"


def explain_report(report: LoadedReport) -> Explanation:
    """把一份已校验的报告翻译成解释。纯函数，不修改输入。"""
    if report.report_type == "label_baseline":
        return _explain_qr(report)
    if report.report_type == "capture_task_review":
        return _explain_review(report)
    return _explain_capture_task(report)
