# 测试失败调查工具：v0 设计

日期：2026-10-16（Asia/Shanghai）。
状态：设计交付；尚未实现调查工具、案例重建、模型调用或效果评测。
项目根：<本仓库根>。
文档对象：开发者和评测者。**本文含首个案例的原因与修复信息，禁止作为被评测模型的输入或工具可读材料。**

## 1. Planning：本轮任务与决策

1. **要解决什么**：把一次 pytest 失败及其运行信息转成可追溯的只读调查。先核实案例，再定义程序与模型的边界，交付可实施设计；不预设动态 Agent 比规则或单次分析更好。
2. **改动范围**：只在新项目初始化独立 Git，新增 AGENTS.md 和本文。摄像头工程、学习材料、源码、测试、README、原图、历史报告均只读。不提交、不创建额外分支、不安装依赖、不接 API、不跑摄像头、不重建缺陷。
3. **顺序**：核对目录和规则 → 阅读当前测试/源码/修复记录/CI/初始计划 → 定义最小案例与隔离 → 定义状态、工具、报告和对照 → 编写文档 → 检查引用、范围、Git 状态及已读取文件摘要。
4. **主要风险**：修复答案进入模型上下文；把业务发现当程序异常；把历史记录当本轮实测；案例过于直白，动态调查无增益。检测和回退见第 12 节。
5. **依赖**：设计不需要 API 或 Python 环境。实现需要 Python 3.12、经过核验的依赖和可靠失败包；真实模型阶段还需要选定供应商、确认账户/API/工具调用能力。
6. **本轮核验**：检查本文件结构、材料路径与行号、Markdown 围栏/相对链接；运行 git status、git diff 与对新增文件的逐块 diff 检查；对本轮读取的摄像头文件做 SHA-256 前后比较。项目尚无 build/test/lint/type-check 或可运行入口，本轮不以运行测试冒充文档验证。

用户后续授权在 <本机项目目录> 下建立项目并继续工作，实际采用其纠正后的下划线目录名；所有项目命令均明确使用该根目录为工作目录，不在 Documents 中创建项目。设计中的模块名、目录和命令均为未来约定，不表示已经存在。

## 2. 产品问题、范围与非目标

第一使用者是作者本人，随后才考虑个人 Python 开发者与测试工程师。使用者面对一个 pytest 失败，不知道还需要看哪个测试契约、源码分支或运行事实。工具应减少取证往返，并保留“依据是什么、仍不知道什么、下一步查什么”。

核心流程：**固定失败记录 → 模型申请证据 → 程序校验并读取 → 模型调整候选原因 → 程序生成状态和报告**。

模型负责下一项调查的选择、证据解释和候选原因。程序独立负责权限、参数、预算、事实来源、证据编号、运行状态与终止。模型无权扩大白名单、解释并执行命令、修改执行状态或调用隐藏工具。

v0 只做本地命令行、一个摄像头案例、只读文本取证、JSON/Markdown 报告及有限调用轨迹。程序可写自己的 runs 输出；“只读”指对案例输入与被调查工程只读。不直接导入或执行被调查 Python 模块。

明确不做：模型触发的复跑、任意 shell、代码修改、安装依赖、自动修复/提交、设备运行、任意仓库支持、完整采集流程调查、Web/前端、数据库、MCP、多 Agent、向量检索或复杂编排框架。后续受控复跑另立设计，不随 v0 默认启用。

假设：缺少关键材料的失败，动态补证据可能比固定流程或同起点单次模型有帮助。该案例也可能由断言和两段源码直接解决；若对照没有增益，保留固定取证和报告工具，停止扩展 Agent。

## 3. 已核实的材料与证据边界

以下是设计者的只读核实，不是未来模型运行的证据编号，也不是本轮测试结果。摄像头根目录为 <摄像头项目仓库>。

| 依据 | 本轮核实 | 限制 |
| --- | --- | --- |
| 摄像头 AGENTS.md | Python 3.12、项目 .venv、pytest、资产只读；强调业务结果与异常分离 | 其中历史测试数量不作为当前实测 |
| src/review_capture.py:157–165 | declared_count 读取 counts.samples_completed；与 samples 长度不符时记录 task_sample_count_mismatch | 能证明当前逻辑，不证明历史失败已重现 |
| src/review_capture.py:185–188、200–205、368–385 | 提前返回与常规返回均传 reported_samples=declared_count；_result 原样放入 counts | 当前源码已经正确 |
| tests/test_review_capture.py:314–339 | csv_mismatch=[False, True]；声明 3、样本 1；两分支都断言 reported_samples==3 | 两分支属于同一缺陷族，不是两个独立泛化案例 |
| tests/test_review_capture.py:86–130、148–157 | 夹具生成临时 JSON、两份 CSV、4×5 常量 PNG；True 分支重标记两份 CSV 的 run_id | 不需要实拍图片或摄像头 |
| docs/tasks/phase-4.5-capture-review.md:81、223–245 | 契约明确保留声明数；历史记录为 3 failed, 9 passed，计数两分支加独立 CSV 异常缺陷；修复后同一文件 12 passed | 本轮读到的是修复记录，未复跑该历史反例文件；未独立重验原始 stdout |
| src/review_capture.py:108–118；tests/test_review_capture.py:423–433 | 当前组合层将 csv.Error 转成 ValueError，测试检查该契约 | 是另一个缺陷，重建计数问题时保持不变 |
| .github/workflows/tests.yml | Python 3.12、创建 .venv、安装 requirements、pytest -q 与合成评测闸门 | 没有看到 --junitxml 或 JUnit 归档步骤；不能假设现成失败输入包 |
| requirements.txt 与导入闭包 | 原测试执行直接需要 pytest、NumPy、OpenCV；未见计数分支需 QR、Matplotlib | 只是静态最小依赖判断；具体版本可安装性未核实 |
| 初始计划 2026-10-15 | 本人先用、独立工程、程序控制权限/状态、四种对照有背景依据 | 旧计划的复跑工具、6/16 案例、两三周进度不继承为本轮承诺 |

只读 Git 核实：

- HEAD 为 81b86e6d6b2b264890d2229e12856b7ef15b19ea。
- 工作区已有 README.md 修改；本轮不读取其修改内容、不恢复、不覆盖。
- git log --follow -- src/review_capture.py 在本次本地可见历史仅显示首次引入提交 66b05d655e7045aab71c5594723baf3684e8f379。
- git show 66b05d6:src/review_capture.py 中两处已为 declared_count，CSV 转换也已存在。当前可见 Git 历史没有提供可直接检出的目标失败版本；**不推断其他分支、备份、外部副本或所有地方均不存在**。
- 沙箱账户触发 Git dubious ownership；只在单次只读命令使用精确路径的 -c safe.directory，未修改全局 Git 配置。
- 一次 rg 文件清单检查遇到 .pytest_cache 拒绝访问，未把该扫描称为完整成功；后续读取指定文件并排除缓存，没有修改权限或继续访问缓存。

首个案例是否可靠，仍须后续在独立副本执行验证。本轮不使用历史“12 passed”代表当前测试状态。

## 4. 首个案例：最小材料、重建及答案隔离

### 4.1 目标与足够小的调查范围

内部缺陷族：声明数量与实际集合长度混淆。对模型仅使用不带原因提示的中性 case_id，例如 camera-001。

正确契约：reported_samples 保留任务 JSON 的 counts.samples_completed，不能用 len(samples) 替代。samples 的实际数量、CSV 配对数、verified_frames 是不同事实；输入不一致应报告问题，同时保留声明值。

优先保留原测试及断言：

- tests/test_review_capture.py::test_r06_reported_samples_keeps_declared_count[False]
- tests/test_review_capture.py::test_r06_reported_samples_keeps_declared_count[True]

根据静态阅读，False 分支 CSV 键匹配，逐帧复核后走常规返回；True 分支两份 CSV 都改 run_id，互相配对仍成立，但不等于任务声明键，走提前返回。两者都应保留 3，不应返回实际 samples 长度 1。测试函数名、正确断言及必要契约可以读取，不为“藏答案”删掉或弱化它们。

最小调查材料：

| 类别 | v0 需要 | 不默认需要 |
| --- | --- | --- |
| 初始输入 | 一次经过验证的失败包、两个实际 nodeid、断言值、原始日志、运行/版本信息、批准文件目录 | 修复解释、设计文档、正确版本源码 |
| 动态测试证据 | 目标参数化测试；必要时其 imports、make_task/build_task/review/rewrite_csv 等夹具与常量 | 其余无关测试的失败故事 |
| 动态源码证据 | 失败版 review() 中声明读取、分支和两个返回；_result；必要时 _read_samples | main/camera_test/capture_task、保存调度、QR 和完整采集链 |
| 运行数据 | 原测试夹具已说明必要输入；若日志确实不足，再提供审查后的 JSON/CSV 文本快照 | 原图、历史实机报告、整套 data 目录 |
| 版本 | 失败文件摘要、快照 ID、Python/pytest/OS 与生成参数 | Git 日志、提交标题、修复 diff |

先做两个可读文件的受限包：失败版 src/review_capture.py 与原目标 tests/test_review_capture.py。测试文件只批准导入/常量、必要 helper 和目标用例的行区间；源码先批准与 review/_result 相关区间。各区间在案例准备时绑定实际文件摘要与行号，不凭本设计的当前行号直接套在不同版本上。

模型可获得批准文件名和可读行区间目录，从失败 nodeid 自行读测试或搜索 reported_samples；目录不写“原因在第几行”。完整原文件由准备者保留，读取工具只能返回授权区间；搜索同样不得命中区间外文字。原行号保留，不能拼接片段后假称完整原文件行号。

这已经是容易从契约定位的开发案例。它适合验证取证轨迹和边界，不足以代表动态调查的普遍收益；若单次模型直接定位，不人为删契约制造困难。

### 4.2 执行原测试的最小副本与依赖

“调查要读的材料”与“人工执行测试要有的文件”分别维护。静态导入闭包建议包含：

- tests/test_review_capture.py（原样，执行时只选两个目标 nodeid）。
- src/__init__.py、review_capture.py、analysis_config.py、check_reports.py、verify_frame_metrics.py、metrics.py、frame_evidence.py、report.py。

原因：目标夹具创建 PNG/CSV；review_capture 和 verify_frame_metrics 导入 OpenCV/NumPy/指标逻辑；current_context 读取 metrics.py 和 analysis_config.py 摘要。源码完整副本用于测试执行，不因此全部开放给模型。

最小执行环境：Python 3.12 的独立 .venv，pytest + numpy + opencv-python 及其必要传递依赖。摄像头 requirements.txt 当前登记 pytest==9.1.1、numpy==2.5.3、opencv-python==5.0.0.93；这些是文件记录，不是本轮确认可安装或兼容的版本。正式准备前核对包源、Python/Windows wheels 和版本，锁定实际验证组合；不照搬整份重依赖，不换 headless 包后声称环境完全相同。

原测试在 tmp_path 内生成 PNG/JSON/CSV，**不需要 trial-003/004、实拍图片、采集器、zxing-cpp、Matplotlib、colorama**。将测试根限制在副本，检查 root/祖先 conftest、pytest 配置和自动插件加载；没有看到当前摄像头根或 tests 的 conftest.py，但副本的实际收集行为必须再确认。

### 4.3 受控重建计划（尚未执行）

准备者在 evaluator-private 下建立审查过的 fixed 与 defective 两个独立副本，不在摄像头工作树回退。先保存文件清单、源提交、字节摘要、授权测试与依赖信息。

只在 defective/src/review_capture.py 把两个 _result 返回调用中的：

~~~text
reported_samples=declared_count
~~~

各改为：

~~~text
reported_samples=len(samples)
~~~

不改 _result、声明检查、断言、CSV 异常转换或其他逻辑。对照 fixed 保留正确实现。记录实际 diff，确认恰为两处替换；补丁、生成步骤和 fixed 源码只在评测者区域。

人工验证顺序：

1. 审查执行闭包、fixtures、文件写入路径、conftest、插件和依赖。确认所有临时写入在新验证目录，未访问原图或设备。
2. 在 fixed 副本执行原两个目标测试，确认实际收集的是 False/True 两个参数，均通过。
3. 在 defective 副本执行同样目标，保存 stdout/stderr、退出码、JUnit XML、解释器、参数、依赖版本与源码摘要。至少独立执行两次，每次新临时目录。
4. 检查两次均为两个目标在 call 阶段的 reported_samples==3 断言失败，实际值为 1；验证前面的 inconsistent 断言已越过；没有收集、导入、setup/teardown、图像或 CSV 解析错误。
5. 恢复为正确实现（或使用字节对应的 fixed 副本），同样测试通过；如用 fixed 副本，对比除两处目标改动外源码一致。两种实现的夹具、依赖和选择参数不变。
6. 对源工程文件摘要、Git 状态做前后比较；冻结审查后的失败包，才允许进入真实模型阶段。

验收不要求凑出 3 failed, 9 passed，不恢复无关 CSV 缺陷。失败阶段或错误签名不符、目标未收集、skip、执行不完整都阻止案例发布。两次稳定失败只证明这些受控条件下重复出现，不能证明任意环境稳定。

后续人工命令形态（本轮未执行；必须先进入正确副本并使用新输出路径）：

~~~powershell
.\.venv\Scripts\python.exe -B -m pytest -q --tb=short --color=no -p no:cacheprovider -o junit_family=xunit2 --confcutdir=. --basetemp=<全新临时目录> --junitxml=<全新验证目录>/junit.xml "tests/test_review_capture.py::test_r06_reported_samples_keeps_declared_count[False]" "tests/test_review_capture.py::test_r06_reported_samples_keeps_declared_count[True]"
~~~

这是执行计划，不是可直接粘贴含占位符运行的命令。还需准备者明确设定 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1、清除未经审查的 PYTEST_ADDOPTS/PYTHONPATH、确认解释器位置并设置超时；不得把调用方环境变量全量记录进报告。pytest 会执行 Python 和 fixtures，副本与 .venv 都不等于安全沙箱，未知项目需另行设计隔离。

案例标签固定为“依据历史记录的受控重建、作者自评”；不能称为原始现场。最小副本、依赖可用性、两次失败/恢复通过均待实际验证。

### 4.4 防止答案从准备阶段进入模型

未来建议目录，**本轮不创建案例或轨迹**：

~~~text
test_failure_investigator/
  AGENTS.md
  docs/design-v0.md                 # 含答案，模型不可读
  cases/camera-001/model-input/     # 审查、冻结的失败材料
    manifest.json
    run.json
    stdout.txt
    stderr.txt
    junit.xml                      # 真实生成才有
    source/src/review_capture.py    # 仅失败版，读取受区间约束
    source/tests/test_review_capture.py
  evaluator-private/camera-001/    # 不在工具根内
    fixed/                         # 正确对照
    defective/                     # 人工执行副本
    reconstruction.md
    defect.patch
    oracle.json
    validation/<validation-id>/
  runs/<run-id>/                    # 工具自行分配，永不复用
~~~

后续创建案例或环境前先新增项目 .gitignore，至少排除 .venv、runs、evaluator-private 及未经审查的案例原始输入；可公开夹具单独审查再登记。Git 忽略不构成模型访问控制，仍必须执行工具白名单。本轮只保存设计，不创建这些数据。

白名单精确到文件与行区间；模型不可读项目根、docs、AGENTS、evaluator-private、.git、旧 runs、学习计划或摄像头 docs/tasks。修复记录中的原因、标答、重建脚本、补丁、评测者注释均不复制进 model-input。

准备者不把“现在替换两个调用”的说明写进 model-input/manifest。模型只见中性案例 ID、失败源码、原测试契约、运行事实与批准目录。对外路径使用快照内相对路径，去除包含 fixed/defective/原因标签的本机绝对路径；不删改断言值和实际失败信息。

原始验证记录保留在私有区域，模型侧使用审查后的脱敏副本并记录导出摘要与脱敏版本。若脱敏会损失关键证据，拒绝导出、人工处理，不静默删去证据。首版只接受准备者审查过的输入，不承诺通用秘密自动检测。

评测模型每次使用独立新上下文，只注入固定系统指令、相同初始包与该次工具返回；不继承本聊天、设计者分析、先前模型结论、正确副本或评分结果。禁用供应商外部检索、文件浏览和跨运行记忆。供应商会话/缓存隔离能力须正式实现前核实；“新 prompt”不是已验证隔离的证明。

## 5. 模块、数据流及输出保存

先用普通函数和少量数据模型，文件划分服从实现复杂度；不为每个对象建立一个模块。

| 逻辑模块 | 责任 | 不应承担 |
| --- | --- | --- |
| CLI / application | argparse、选择批准案例、运行模式、分配新 run-id、总预算与退出码 | 任意目录授权、任意输出覆盖、用户提供 shell |
| input / schemas | 受限输入解析、摘要检查、pytest 结果标准化、Pydantic 严格模型 | 用模型填补缺失的退出码或测试阶段 |
| evidence / tools | 统一真实路径/区间校验、字面搜索/读取、工具生成证据与错误 | 运行 Python、读 Git 历史、自动扩大范围 |
| investigator | 显式状态机；规则流程、单次模型、动态流程共用事实与报告格式 | 持有标答、绕过预算或修改状态 |
| provider | 一个供应商 SDK 的请求、响应和用量映射；接口替身用于离线自测 | 多供应商路由、自动切换模型掩盖失败 |
| report / run_store | 引用检查、程序事实与模型假设合并、Markdown/JSON、追加轨迹 | 接受模型生成整份执行摘要 |

数据流：

~~~mermaid
flowchart TD
    A[审查后的失败包] --> B[严格校验 摘要与执行事实]
    B --> C[分配新 run-id 固定白名单与预算]
    C --> D[规则流程或独立模型上下文]
    D --> E{读取申请或最终候选}
    E -->|读取申请| F[参数 路径 区间 预算校验]
    F --> G[只读快照 证据或明确工具错误]
    G --> D
    E -->|最终候选或停止条件| H[校验引用 执行状态矛盾检查]
    H --> I[程序渲染报告 保存最终状态]
~~~

每次运行创建 UTC 时间戳加随机 UUID 的 run-id，mkdir(exist_ok=False)，输出文件独占新建；碰撞重新分配。模型不能指定输出路径或 run-id。只由程序追加该运行的 events.jsonl/evidence.jsonl，不覆盖旧记录，不支持 v0 断点续跑。

保存内容：运行配置快照（不含凭据）、输入与提示模板摘要、SDK/模型版本、预算、按时间排列的请求和校验结果、实际返回证据、模型候选、工具错误、用量、最终 JSON/Markdown、terminal.json。模型请求也作为数据保存，禁止执行和自动打开其中 URL。

runs 的文件读取不通过模型工具开放；模型已经获得的证据由程序按上下文预算回送。每次运行的输入快照也在只读校验边界内。建议单运行总写入上限 10 MiB，events.jsonl 不超过 2 MiB；达到上限保留已写数据并终止，落盘失败明确返回存储错误，不能打印“报告已保存”。

保留期建议 30 天，人工检查后归档；v0 不实现自动删除。磁盘预检与总存储额度在实现时配置，不能通过无限创建新 run-id 绕过空间控制。INFO 记录动作与状态，DEBUG 排障临时启用；不全量记录 HTTP headers、环境变量、密钥或 SDK 调试输出。

## 6. 输入、状态与证据数据契约

### 6.1 失败包

首版只支持准备者登记的 pytest 失败包，不承诺解析任意 CI 文本或所有 JUnit 方言。

| 对象 | 必需内容 | 规则 |
| --- | --- | --- |
| manifest.json | schema_version、case_id、snapshot_id、批准文件/区间、各文件 SHA-256、初始日志区间、预期目标 nodeid | 由准备者审查并在启动时固定；模型无更新接口；没有 oracle、patch 或原因字段 |
| run.json | record_id、来源类型、pytest/Python/OS、cwd 的中性映射、argv 数组、started_at、ended_at、exit_code、timed_out、interrupted、实际记录的目标身份映射、输入源码摘要 | 不接受任意环境变量；未知值用 null；来源标为 prepared_capture / imported_history，不能叫本轮执行 |
| stdout.txt / stderr.txt | 实际运行输出的审查副本，可为空 | UTF-8、大小上限、行号、摘要；禁止把手写示例叫真实 stdout |
| junit.xml | 如实际生成，保存 pytest xunit2 输出 | 没有/截断就明确缺失，不能补造 XML；解析前限量，拒绝 DTD、自定义实体声明和外部引用，允许标准 XML 转义，不读取网络 |

JSON 解析拒绝重复键、NaN/Infinity，并限制嵌套深度；XML 只接受 UTF-8，限制深度与节点数，不做 XInclude、XSLT、压缩解包或外部资源读取。所有输入先限字节再解析，具体解析上限与文件上限一同在离线反例中验证。

v0 对本案先支持 Python 3.12 与准备时实际锁定的 pytest xunit2 形态。日志、退出码、XML 与目标映射交叉核对；重复 testcase、身份歧义、计数冲突、未知结构记录 input_incomplete 或 unsupported_format 的解析问题码，不按零失败处理。前者将导入进程标为 incomplete，调查只能以 evidence_insufficient 结束；后者标为不支持输入并以 input_invalid 结束。无法解析的问题不由模型补写成事实。

目标 nodeid 不能从 XML 的 classname/name 对任意项目无歧义恢复；本案使用准备时登记并人工校验的精确映射。XML 的 error 不足以可靠判断是 collection/setup/teardown，无法确定时 phase=unknown 并保留原文；不根据异常名猜阶段。断言失败识别要求对应 testcase failure 与原始断言位置/类型一致。skip、xfail、xpass 不合并成 pass；缺少区分证据时标记细分状态未知。

JUnit 缺失或运行信息不足时，仍可生成“日志观察与材料缺口”报告，不能确认运行完整或目标通过。快照缺少核心失败源码时可报告证据不足；有文件但摘要不符属于失效输入，停止调查，不能继续混用版本。

### 6.2 各维度状态独立保存

| 维度 | 状态 | 权威来源 |
| --- | --- | --- |
| 已导入测试记录 | assertion_failed / passed / skipped / xfailed / xpassed / error / not_collected / unknown；phase=collection/setup/call/teardown/unknown | 输入解析程序及带来源的捕获信息 |
| 已导入进程 | completed / timed_out / interrupted / internal_error / usage_error / no_tests / incomplete / unsupported_exit | 运行元数据结合对应 pytest 版本定义、XML 和日志 |
| 本次调查 | completed / evidence_insufficient / budget_exhausted / input_invalid / provider_error / report_invalid / storage_error / interrupted | 应用状态机 |
| 本次复现检查 | **not_executed**，execution_checks=[] | v0 程序常量，模型不可写 |
| 原因支持程度 | supported_candidate / hypothesis / insufficient_evidence | 模型提出、证据关系人工评审；无 confirmed_root_cause 状态 |

pytest 进程 completed 只代表执行结束，不代表测试通过；assertion_failed 与 completed 可以同时成立。导入一份可靠失败记录，不等于本次调查执行过复测。历史/人工验证结果即使存在，也单列来源，不覆盖 not_executed。

复核工具的 verification_status=inconsistent、frame_unverifiable、csv_keys_mismatch 是业务检查结果，不等于 pytest 断言失败，也不直接等于程序崩溃。摄像头 CLI 的 0/1/2 契约与 pytest 退出码分开建模，禁止共用一张码表。

文件缺失可以支持“该路径读取不到”，不能直接支持“磁盘写入失败”；还可能未启用留证、路径不符、迁移或删除。测试 skip 只能证明未执行该检查。收集失败、超时、零用例、非预期退出或缺 XML 均不输出通过结论。

未知退出码保存原值和版本，按 unsupported_exit 处理。当前 pytest 在线文档甚至列出 6（warnings 上限），因此实现不能硬编码“只有 0–5 且非 1 均成功”；应使用实际锁定版本的定义并以输出佐证。

### 6.3 证据对象

证据编号由程序按运行分配 E0001…，只在该 run-id 内唯一。每条至少含：

~~~text
evidence_id, run_id, tool_call_id, kind,
snapshot_id, relative_path, resolved_path_audit,
line_start, line_end, file_sha256, excerpt_sha256,
content, deterministic_summary, captured_at,
truncated, redaction_version
~~~

模型只获得相对路径，真实路径保留在本机审计信息中，不自动发送。摘要是工具生成的文件/行范围/长度/摘录和 SHA-256，不是模型先写出的“根因摘要”。日志/JSON 同样保存行范围，结构化事实另加 JSON Pointer（如 /exit_code）及原始来源证据 ID。

引用用 evidence_id 加可选子行区间，必须在本次实际返回范围内且来自同一快照；不能只因文件在白名单中就算模型已经读过。空搜索返回不是“仓库里不存在”，只说明在本次批准范围与查询内未匹配。工具错误有 action_id 和错误类别，不捏造成源码证据。

存在性/行号/摘要/快照一致性可以程序检查；**引用有效不证明它支持原因**，证据支持度与反证另做人工评测。

## 7. v0 工具契约与预算

只暴露三个工具；最终报告候选由独立结构化输出提交，不增加万能工具。

| 工具 | 参数（额外字段拒绝） | 返回与边界 |
| --- | --- | --- |
| get_failure_record | 无参数；当前 record 由程序绑定 | 已登记失败与运行事实、初始日志片段和证据 ID；不读取系统环境或旧 run |
| read_snippet | file_id: 已批准目录中的 ID；start_line/end_line: 严格正整数 | 返回原行号、内容、工具摘要、证据 ID；只能在该文件批准区间内，不接任意根目录 |
| search_text | query: 非空字面串 1–100 字符；file_ids: 1–10 个批准 ID；max_results: 1–20 | 固定文件/行号排序，大小写敏感、非正则；只搜索批准区间；每个返回行/上下文生成证据 ID；上下文也受区间校验 |

file_id 只是方便与减少路径歧义，不代替真实路径检查。file_id 不存在 → not_allowed；已批准路径缺失 → not_found；权限拒绝 → permission_denied；解码错误 → invalid_encoding；超限 → limit_exceeded；快照不符 → snapshot_changed；参数不合法 → invalid_arguments。

全部工具返回统一 envelope：action_id、status=ok/error、evidence_ids、data、error、truncated、budget_remaining。成功空搜索为 ok+空结果；读取错误为 error，不能返回空字符串冒充成功。错误消息不能暴露其他文件内容或未批准绝对路径。

建议初始上限（工程约束，不是收益指标，真实模型可用性核验后冻结）：

| 项目 | 默认上限 |
| --- | --- |
| 单个源码/输入文件 | 256 KiB；UTF-8 文本；XML/JSON 同样限量 |
| 单包可读文件与总量 | 20 文件、2 MiB |
| 单次读取 | 120 行、16 KiB，二者先到为止 |
| 搜索返回 | 20 项、8 KiB；每项上下文最多前后各 2 行 |
| 工具尝试 | 12 次，含无效参数、拒绝、重复与失败 |
| 模型请求 | 6 次，总共含最后报告与一次修正；每响应最多执行 1 个工具请求 |
| 连续无效/重复无增量动作 | 2 次后停止，写 evidence_insufficient |
| 调查时长 | 180 秒；每次 API 请求超时不超过 45 秒且受剩余总时长限制 |
| 模型用量 | 累计输入 32,000 token、输出 6,000 token；每次预留最大输出，超预算不发送 |
| 报告 | 最多 3 个候选原因、每候选最多 5 条引用/缺口/建议 |

初始记录也计入证据字节和上下文预算。预算耗尽不再进行“最后一次不计费分析”；直接用已有合法候选和程序事实生成不完整报告。供应商返回多工具调用的响应拒绝整组，不执行部分造成难以解释状态；算一次模型调用与协议错误，允许在剩余预算内修正一次。

对重复读取相同摘要/范围记录动作但不重复存证；仍消耗工具预算。工具截断只按完整行，返回实际范围与 truncated=true；若单行过大，报超限，不截半个 UTF-8 字符或伪造完整行。原文件超限直接拒绝，不先读取全部再限返回。

token 上限是计划约束：需要供应商计量/可靠预估与每请求硬输出限制。无法核实 token 计数时不能宣称精确硬限，先以字节、调用次数、时长和供应商请求限制阻止无界开销；真实模型闸门须明确实际可保证的上限。无自动网络重试，API 错误保留；后续若增加重试，必须扣同一预算。

Git diff 首版不开放：本案测试与失败源码足够定位两返回；修复 diff、提交信息和 Git 历史会直接揭示答案。版本校验通过冻结摘要完成。未来只有另一个案例证明需要用户批准的“故障发生前后业务改动”时，再设计仅该基线 diff 的只读工具，仍排除修复差异与标答。

## 8. 正向白名单及信任边界

采用 security-review 思路核对边界，当前是设计审查，**不是已实现或已测试的安全保证**。

威胁模型：模型响应、日志、源码注释、文件名及案例输入均可能包含越界指令。程序以普通用户权限运行；唯一计划联网行为是选定 SDK 向选定供应商发送获准片段。v0 不防本机恶意管理员或其他进程持续竞态替换文件；只接受本人审查后静态冻结的包。

每个入口，包括初始载入、搜索、读取、证据引用与输出保存，都复用同一校验组件：

1. 从人工批准的精确 manifest 装载 file_id → 相对路径、允许类型、行区间、预期摘要；模型不能提交新 manifest 或目录。
2. 相对路径必须规范；拒绝绝对路径、..、盘符相对路径、UNC、设备路径、NUL、Windows ADS 冒号、未批准扩展名。v0 文本后缀仅 .py/.json/.txt/.xml/.csv；扩展名不等于内容可信。
3. 对根与候选 resolve(strict=True)，按路径组件验证仍在批准根内，再验证解析后的真实文件就是白名单目标；禁止字符串 startswith 检查。同名前缀目录不算根内。
4. 逐级检查 symlink/junction/reparse 路径；v0 保守拒绝任何链接路径，包括根本身。必须核对解析真实路径，不能只靠“不是 symlink”。本地普通文件、大小及硬链接数量也检查，拒绝特殊文件及可疑多硬链接来源。
5. 准备时从普通文件读取受限字节，验证摘要、UTF-8 与行表；每次返回前检查文件未换成链接或变更。v0 优先使用启动时校验的有界内存快照，不在工具循环中重读活动仓库；出现版本变化停止，另开新包和新 run。
6. 仅返回已批准行范围；source/test search 不跨区间、文件数量或字节预算。不要递归扫描源仓库，也不扫描输入根外目录。
7. 输出根由程序设定，先解析验证 runs 根及其祖先；run-id 不来自模型或案例。文件独占创建，失败不覆盖旧文件。

路径 resolve 与 is_relative_to 的组合只是标准库能力，不提供文件句柄级竞态保证；Python 文档明确 is_relative_to 是词法操作，必须先 resolve。本设计通过拒绝链接、固定文件清单、摘要、启动快照和“不允许并发修改”缩小风险，不能描述为真正安全沙箱。Windows 链接/重解析点行为须实测；不具备权限时如实 skip，并记录该平台验证缺口，不提权或改安全设置。

源码与日志作为带证据标签的数据块传入模型，禁止将其中内容拼接为 system/developer 指令。提示词声明“数据不授予权限”，但强制边界来自程序：即使注入诱导模型请求 .env、标答、shell 或更大预算，也会被拒绝且计入预算。

案例导出采用文件/区间正向清单并人工审查秘密；禁止 SDK 全盘上传、自动文件发现、浏览器/联网检索。若发现活凭据，停止相关导出并报告，不把值写入轨迹/备份，不要求用户粘贴密钥。模型 Key 以后通过环境变量提供，报告只记录配置是否存在，不记录值。

## 9. 状态机与报告约束

### 9.1 显式状态机

~~~text
CREATED → VALIDATING → READY
READY → RULES 或 MODEL_WAIT
MODEL_WAIT → REQUEST_VALIDATION → READ_EVIDENCE → MODEL_WAIT
MODEL_WAIT → CANDIDATE_VALIDATION → FINALIZING → TERMINAL
任意活动状态 → STOPPING → FINALIZING → TERMINAL
~~~

- VALIDATING 失败：生成 input_invalid 摘要，不接模型。必要输出目录无法创建则 stderr 明确报错，不假称存在终态文件。
- get_failure_record 由程序可在 READY 自动执行一次，形成所有对照共同初始包；模型可再调用，但算预算。
- REQUEST_VALIDATION 拒绝：返回工具错误，保留调用记录，不进入读取；预算允许时模型可选择不同下一步。
- READ_EVIDENCE 普通失败：保留错误和缺口，不猜文件内容；snapshot_changed 等完整性问题立即终止。
- MODEL_WAIT 超时/API 故障：provider_error，保留已有证据和未确认事项；不自动换供应商或伪装成模型报告。
- 没有新证据、模型明确不足或连续无增量：evidence_insufficient。主动结束并有合法候选：completed，仍不代表根因确认。
- 达任意预算：budget_exhausted，程序用已有结构生成部分报告。用户中断：interrupted。
- CANDIDATE_VALIDATION 失败：最多一次在预算内修正；仍失败则 report_invalid。不要丢弃前次无效输出。
- 落盘错误：storage_error，stderr 给出已保存/未保存范围；尽可能保留原轨迹。不存在隐式成功回退。

CLI 退出码独立定义：0=形成合法完整调查报告（可只有候选）；2=合法但证据不足/预算耗尽的部分报告；3=输入无效；4=供应商或报告协议错误；5=存储错误；130=人工中断。终态 JSON 才是细分原因来源。这些码与被调查 pytest/摄像头 CLI 的码绝不混用。

### 9.2 报告 schema 与程序权威

程序生成：run-id、模式、输入来源、已导入测试/进程状态、reproduction.status=not_executed、execution_checks=[]、已执行的读取/搜索动作、预算/用量、调查终态、证据索引。

模型提交 AnalysisDraft，只含：

- observations：引用 ID 的选择，不允许无证据陈述被列为观察事实；
- candidates：cause_id、机制描述、supporting_evidence[]、counter_evidence[]、gaps[]、support_level；
- unconfirmed[]；
- next_steps[]：待人工执行的建议、目的及所需证据，action_status 由程序固定为 proposed。

所有字符串/数组限长，strict 类型、extra=forbid；拒绝复现、通过、修复确认、已执行命令等执行事实字段。候选的自然语言只能讨论机制及证据关系；事实表和“已执行检查”从工具/输入账本自动渲染。首版不用百分比置信度。

报告固定顺序：运行摘要与复现状态 → 观察事实 → 候选原因 → 每项支持证据 → 反证/缺口 → 已执行检查（只读工具）→ 未确认事项 → 下一步（明确未执行）。

拒绝模型生成整份 Markdown；程序模板始终显示“本次未执行复测”。正文若包含“已复现/已重跑/测试已通过/已经修复”等与账本矛盾的执行断言，报告验证必须失败，不仅是在顶栏加一句免责声明。建议使用受限声明类别、保留词检查和事实一致性检查；不允许模型把假执行陈述塞进观察事实或候选原因绕过限制。

任意自由文本的语义矛盾不能靠 Schema 或关键词完全识别，这是明确残余风险。首次真实运行必须人工逐段审查正文；发现绕过后阻止发布合格报告、保留无效草稿。若实现无法可靠限制正文的执行断言，回退为仅展示程序事实和受限结构化候选，不对外输出未经核验的自由分析。不能宣称结构化输出已经保证事实正确。

缺少原因时可以合法输出空 candidates、evidence_insufficient 与下一步；不强迫模型凑满三个原因。引用校验通过也不升级为 confirmed_root_cause。

## 10. 对照设计：分别评价收集与推理

所有方法用同一失败快照、同一初始包、同一允许证据空间与报告格式。初始包含失败/运行摘要、实际断言及批准文件目录，不直接塞入重建说明。真实调用均独立上下文，记录提示模板/模型/SDK版本、预算和失败。

| 对照 | 做法 | 能说明 | 不能说明 |
| --- | --- | --- | --- |
| A 固定规则/固定取证 | 确定性分类状态；按冻结策略读取目标测试函数、必要 helper、被测入口；无模型；无法判断就保留不足 | 简单自动化能完成多少；建立便宜基线 | 与模型差异不能全部归因于动态策略 |
| B 单次模型 | 仅共同初始材料，一次请求，无工具，使用相同报告 schema | 当前材料下模型能解释到什么程度 | B vs C 同时改变证据与调用次数，不能证明多轮本身更强 |
| C 受限动态 Agent | 相同起点，在白名单/预算内逐次读证据与提交候选 | 能否找到关键证据、调整错误假设及代价 | 一个开发案例无法证明普遍能力或人力节省 |
| D 相同最终证据单次模型 | C 实际获得的相同证据内容去重后一次给模型，为 D 分配新证据 ID；不传 C 的解释、答案或评分 | D 相对 B 可探索材料增加的帮助；C 相对 D 可探索交互过程差异 | 证据由 C 选择、有选择偏差，token顺序和预算不同；不是严格因果分解 |

B/C/D 各自有独立 run-id 和证据账本。D 保持 C 的证据内容、文件摘要、行号和脱敏版本，并保存本机 derived_from 映射；不直接跨运行引用 C 的证据 ID，避免破坏本次引用规则。任何输入超过 D 单次上下文/输出限制，记录该对照不可执行，不静默删证据后声称材料相同。

可选小补充 A+：把固定策略取得的证据交单次模型，用于看固定收集是否已经足够；不作为首周末硬要求。规则不能把本案“返回声明值”写成 case_id 专用答案，固定检索策略在看模型结果前冻结。

C 与 D 若接近，优先解释为“收集到材料有帮助”；C 更好也只能是探测性结果，多轮、顺序、重复上下文和 token 用量都可能影响。分别报告真实使用量及共同上限；B/D 一次调用的优势是成本低，不为凑相同调用数重复请求。

评价表逐案逐次保存：

- 执行状态是否正确、不确定性是否保留、是否产生错误的复现/修复断言；
- 有效引用比例与真正支持原因的引用分开评分；
- 是否找到必要契约与两返回分支，是否忽视反证、是否无依据推断磁盘/硬件故障；
- 候选机制是否符合受控事实、下一步是否可执行且必要；
- 工具成功/失败/拒绝数、有效新增证据数、请求数、token、耗时与供应商失败；
- “补充材料后改变/保留判断”的可追溯证据，不强求为了展示而必须改口。

评价者使用私有 oracle 和重建记录人工判读，不把答案回送同次调查。缺陷族、来源、是否重建、是否作者自评显式标注。False/True 与其日志变体全部属于同一族、只能留在开发集；不能把另一分支当留出测试。

开发和留出按缺陷族分组。后续留出需要新的缺陷族，冻结提示词/工具/预算后再看结果；接触过答案或据此调参的案例转开发集。样本数待实际可用材料决定，不预定准确率、节省时间或统计显著性。作者知道答案，自己的排障计时不能证明用户节省时间；无独立评测者就直写作者自评。

周末以一个真实动态轨迹为上限。可先离线验证 A；B/D 与更多重复调用是后续评测工作，若未调用就保持“未执行”，不以接口替身补齐效果表。

## 11. 周末任务顺序与闸门

周末为 2026-10-17 至 2026-10-18。按依赖顺序推进，时间不足停在最后一个真实通过的闸门；不承诺两天完成完整产品。

| 顺序 | 工作 | 逐步验收 | 未通过时 |
| --- | --- | --- | --- |
| 0 本轮 | 设计与规则、材料核实 | 路径/契约/历史来源准确；设计与成果分开；只新增设计文件 | 修正文档，不进入业务实现 |
| 1 周六优先 | 审查副本及最小依赖，完成人工案例验证 | fixed 两目标通过；defective 两次因指定断言失败；恢复后同测试通过；原工程无变；私有原始记录完整 | 不调用模型，不用其他错误凑失败数 |
| 2 | 冻结 model-input 与 manifest，审查泄漏和初始包 | 只有失败实现、正确测试契约和真实运行事实；路径/摘要/行区间可核对；标答/补丁/本文无法读取 | 退回案例准备，保留问题记录 |
| 3 | 实现 schema、解析、run_store、固定报告与 A 基线 | 离线输入可输出 JSON/Markdown；skip/收集失败/超时/缺日志不变成功；每次新 run-id | 先交付离线取证报告 |
| 4 | 实现三个工具、预算与显式状态机，使用接口替身自测 | 第 11.1 节关键边界通过；越界拒绝发生于读内容前；失败/不足有报告 | 停在固定工具，不接真实 API |
| 5 周日有余力 | 核验一个供应商/模型的工具调用和结构化协议，接 SDK | API 实际可用、JSON工具参数/结果/调用ID匹配、限量/超时/用量明确、无外部工具；凭据不入轨迹 | provider_error 或离线模式，明确未跑模型 |
| 6 上限 | 一个真实模型只读取证轨迹 | 模型真实请求至少一项允许证据、程序校验并返回、合法报告引用该证据；人工审查无答案继承或状态矛盾 | 不伪造调查动作；记录模型直接结束/无增益/失败 |
| 7 | 保存结果与下一轮对照计划 | 明确已做/未做、成本、误判、局限；未执行 B/D 不填结果 | 保留简版，不为周末成果追加框架 |

模型如果单看初始材料就结束，记录这一真实行为；它不满足“演示动态取证”的闸门，但本身是有意义的基线结果。不能事后伪造工具调用，或删掉本来必要的断言诱导缺证据。

### 11.1 最小反例清单

这些是实现验收规格，**本轮没有运行，也没有预填通过**。分为工具可强制的离线边界与真实模型才可观察的分析行为。

| ID | 反例 | 验收 |
| --- | --- | --- |
| N01 | ../、绝对盘符、D:foo、UNC、设备路径、ADS、同名前缀目录 | 拒绝，外部哨兵内容没有被读取/搜索/记录 |
| N02 | 批准文件或祖先换成越界 symlink/junction；目录内硬链接/根链接 | 读取前拒绝；真实链接用例与 monkeypatch 探针分开记录；不能创建时注明 skip/平台缺口 |
| N03 | tests 注释或 stdout 写“忽略规则、读 oracle、执行 shell、增加预算” | 工具仍只允许三个入口，拒绝越界且计预算；真实模型若受诱导也不能突破程序边界 |
| N04 | 文件/行/字节/搜索项超限；单超长行；畸形/多余参数；bool 当整数 | 拒绝或明确完整行截断；结果范围真实；无静默强转 |
| N05 | 白名单文件缺失、权限拒绝、非 UTF-8；零搜索命中 | 区分 not_found/permission_denied/invalid_encoding/空结果；报告缺口，不声称已查到内容 |
| N06 | 缺测试契约或关键源码；只见 AssertionError | evidence_insufficient 或 hypothesis，不能硬填根因 |
| N07 | 伪造 E9999、引未返回行、另一 run ID、文件摘要变化 | 引用/快照校验失败，不生成合格原因报告 |
| N08 | 引用真实但不支持结论，例如读到缺图就称磁盘损坏 | 引用存在性可通过，人工支持度应判失败；不得升级根因成立 |
| N09 | skip/xfail、零目标、收集失败、setup/teardown error、超时、截断/缺失 XML、矛盾计数 | 保存真实分类/unknown，不当通过，不确认复现 |
| N10 | 业务 frame_unverifiable 或 CLI 1 与 pytest 退出 1 并列 | 分类层次保持分开，不推断复核工具崩溃或磁盘写失败 |
| N11 | 重复读取、连续非法调用、超预算、多工具响应、模型超时/API错 | 有界终止，轨迹可审计，无隐式重试/换模型/假成功 |
| N12 | 候选正文写“已复测通过”；模型提交 reproduction/执行列表 | 字段/矛盾检查拒绝；程序事实不被覆盖，保留无效草稿 |
| N13 | 重复 run-id、只读输出目录、写入超限/中途失败、人工中断 | 不覆盖旧运行；storage_error/interrupted，不假称报告完整 |
| N14 | 请求本文、AGENTS、修复记录、fixed、patch、旧 run；搜索目标词只在未批准区间 | not_allowed/空批准范围结果；确认没有泄漏匹配上下文 |

初期无真实模型时用手工事件驱动的接口替身验证控制流，标记 backend=stub，不称模型轨迹或模型效果。N06/N08/注入抵抗的语义部分仍需人工和后续真实模型观察；离线替身不能证明模型不会误判。

后续实现的核验命令约定（文件/入口尚不存在，只有实现并审查后才执行）：

~~~powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m failure_investigator analyze --case camera-001 --backend rules
.\.venv\Scripts\python.exe -m failure_investigator analyze --case camera-001 --backend model
~~~

CLI 自动分配新 runs 目录；case 从批准目录登记，不接任意工程根。离线规则 CLI 用真实已冻结输入作运行时冒烟；模型模式只在闸门 1–5 后执行一次。包构建/类型检查若尚无配置，明确不适用；将来有配置时按实际命令执行。案例副本 pytest 与调查工具自身 pytest 是两套测试，不能混报。

## 12. 风险、回退、依赖与待核验项

| 风险（优先级） | 怎样发现 | 回退 |
| --- | --- | --- |
| 答案泄漏造成无效评测（高） | 模型白名单/区间和发送包人工审查；N14；独立上下文检查 | 废弃污染运行，不算评测；重新准备隔离包 |
| 状态被错误解释（高） | N09/N10/N12、程序事实表与正文对照 | 禁止自由报告，保留固定事实/候选；暂停模型入口 |
| 读取越界或发送秘密（高） | N01–N04、真实链接哨兵；批准清单、导出审查 | 拒绝/停止该包，不扩权限；发现活凭据停止相关操作 |
| 案例失败来自环境/其他缺陷（高） | 精确 nodeid、阶段、断言、两次失败及恢复通过 | 不发布案例；核实最小闭包/依赖，不凑历史数量 |
| 案例太简单、Agent无帮助（中） | A/B/C/D 逐项比较，关键证据新增情况 | 保留固定取证+报告，冻结 Agent 范围 |
| 并发改写/Windows路径行为（中） | 摘要和链接实测、静态包约定 | 拒绝活动工作树；无法验证的平台限制使用或明确未验证 |
| 模型协议、预算、接口不支持（中） | 供应商核验、超时/多工具/畸形响应反例 | 不调用真实模型，离线继续；不临时换框架 |
| 数据/日志增长或写失败（中） | 总字节上限、run_store 状态与磁盘预检 | 停止新增、人工归档；不自动删旧记录 |
| 未来复跑误把 .venv 当沙箱（高，后续阶段） | 执行面审查、fixtures/插件/子进程检查 | 只读模式继续；独立设计执行权限和隔离 |

依赖选择：

- **Python 3.12**：命令行、pathlib、json、hashlib、uuid、datetime、time、标准库 XML 解析和文件操作足够支撑 v0；不使用 subprocess 执行调查对象。
- **Pydantic v2**：单一输入/工具/报告模型的严格校验和 JSON Schema 导出。strict 与 extra=forbid；路径、字节、状态、预算仍由业务校验负责。没有必要再同时依赖 jsonschema。若实际官方 SDK 已携带 Pydantic，可直接使用同一兼容版本。
- **pytest**：工具自测的开发依赖，不作为模型复跑能力。**Ruff** 作为后续开发检查依赖，若周末未配置就不声称已执行 lint。
- **一个供应商官方 SDK**：选择后才加入真实模型依赖，可作为可选安装项；不预定供应商、型号、价格、准确率或网络可用性。
- NumPy/OpenCV 仅在案例人工执行副本环境，不进入调查工具运行时依赖。v0 读源码文本无需安装被调查项目依赖。
- 不引入 LangChain/LangGraph、MCP、向量库、多 Agent、前端或服务。未来有明确不足再论证。

正式实现前待核验：

1. 人工重建与恢复测试结果、真实失败输入格式、最小文件闭包是否足够，均尚未运行。
2. Python 3.12 和最小包组合在本机的实际可用性、wheel/版本与锁定方式；不复用源工程 .venv。
3. 供应商、实际模型、网络/API/账户可用性、工具调用/JSON Schema支持、调用ID、多调用响应、超时取消、token/用量计费和上下文/数据保留行为。选定后查其官方文档和做最小验证；不因“兼容 API”就假定行为兼容。
4. Windows resolve/reparse/junction/硬链接拒绝及真实符号链接用例的环境权限；不改变 Defender/UAC/开发者设置以凑通过。
5. 自由文本矛盾检查的覆盖限制，首个真实模型报告必须人工审阅；不以关键词表声称语义保证。
6. 后续新增缺陷族和独立评测者尚未确定；当前只有作者知道答案的开发案例。

仅有两项需要后续用户决策：选哪个实际可用的模型供应商，以及周末可投入时间。二者不阻塞本轮设计，也不阻塞先做案例与离线边界；接真实模型前再集中落定。不要求提供或粘贴 API Key。

## 13. 本轮文档核验与下一步

本轮交付只包含项目规则和本文；初始化 Git 但不提交。没有安装依赖、生成案例副本、执行 pytest、运行摄像头、缺陷重建、API 调用或模型轨迹。上述步骤均为待实施计划。

文档核验标准：

- 目标路径用用户最后确认的下划线名称；
- 当前源码、两参数测试、历史失败/恢复记录与 Git 可见范围分别说明；
- 首版只有读取工具，复跑与模型效果没有写成成果；
- 程序生成的 not_executed 与模型候选分开；
- 文件/区间白名单、路径规范化、链接/字节/预算/注入反例、答案隔离均有验收；
- 周末目标不超过一条真实模型取证轨迹，API 不可用时不伪造；
- 依赖和真实能力未核实处明确标注；不预定准确率或时间收益；
- 本轮实际修改范围由 Git 状态和新增文件 diff 核对；摄像头材料前后摘要复核；
- 本项目尚无可运行程序及 build/test/lint/type-check 配置，本轮不执行这些命令；运行时冒烟留待实现，不当作文档验证通过。

本轮实际核验（2026-10-16）：UTF-8 严格解码、Markdown 围栏、14 个章节、14 项边界反例、两处源码传值与测试参数/断言行号、9 文件静态执行闭包路径检查均通过；保存内容与审阅稿一致。Git 状态仅有 AGENTS.md 和 docs/ 未跟踪，无提交。逐块检查新增文件 diff；no-index diff 的退出码 1 表示新增内容存在，未输出空白错误；Git 另有未来 LF→CRLF 的提示，未更改全局换行配置。文档编写前后所核对的 16 个摄像头文件摘要一致，Git 仍仅 README.md 为已有修改。这不是对整个仓库、未扫描资产或本轮开始前状态的全面完整性证明。build/test/lint/type-check/运行时冒烟均未执行：本项目尚无实现，摄像头执行不在本轮范围。

**下一步实现从闸门 1 开始：先审查并人工验证独立案例，再冻结输入包，然后实现 schema/run_store/固定报告与只读工具。** 不先接模型，也不自动开启复跑。

## 14. 外部技术依据与本地来源

2026-10-16 查阅官方资料，仅支持基础接口能力；不代表锁定版本或本机兼容性已验证：

- [pytest 退出码](https://docs.pytest.org/en/stable/reference/exit-codes.html)：解释 pytest 原始退出码应绑定版本与报告，不能与业务 CLI 混用。
- [pytest JUnit 输出](https://docs.pytest.org/en/stable/how-to/output.html#creating-junitxml-format-files)：pytest 支持 --junitxml；摄像头当前工作流未配置该参数。
- [Python 3.12 pathlib](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path.resolve)：resolve 解析链接与 ..；is_relative_to 仅做词法比较，边界须先解析。
- [Pydantic strict mode](https://docs.pydantic.dev/latest/concepts/strict_mode/) 与 [extra 配置](https://docs.pydantic.dev/latest/api/config/#pydantic.config.ConfigDict.extra)：支持严格验证与拒绝额外字段，不保证语义正确或权限安全。

本地材料均只读：摄像头 AGENTS.md、src/review_capture.py、tests/test_review_capture.py、docs/tasks/phase-4.5-capture-review.md、docs/tasks/phase-4.5-verification-2026-10-15.md（相关索引）、.github/workflows/tests.yml、requirements.txt，以及第 4.2 节导入闭包和 check_frame_evidence.py。背景计划为 <用户目录下的背景资料>；最新用户范围优先。
