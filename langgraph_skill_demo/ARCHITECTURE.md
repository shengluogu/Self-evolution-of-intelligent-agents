# Agent、环境与 Skill 分离（第一版）

本版以 `wsy/chenx-integration` 为基线，在 `chenx` 实现。保留原有 LangGraph 主流程、三个 Skill hook 和 ALFWorld 命令行用法，后续 MiniWoB 接入与实例级工具分离见 MINIWOB.md。

## 边界

- `core/contracts.py`：公共 `Environment`、`Snapshot`、`Action`、`ValidationResult` 契约，无 ALFWorld 或 Skill 实现依赖。
- `core/runner.py`：初始化 → 检索 → 注入 → 决策/执行循环 → 成功后提取和保存；只调用环境契约和注入的 hooks/chooser。
- `environments/alfworld_adapter.py`：负责数据路径、官方接口、任务解析、合法动作、成功判定和内部信息过滤。数据加载暂时留在适配器内，不引入数据管理框架。
- `environments/mock.py`：独立测试环境。旧 ALFWorld 模块保留 `Snapshot`、`MockEnvironment` 导出，兼容原调用方。
- `environments/factory.py`：入口创建环境，延迟导入 ALFWorld 实现。
- `policies/llm_policy.py`：根据公共任务、文本观察、动作说明、Skill 和历史生成动作；不访问环境实例。
- `skill_tools/`：检索、证据提取、查重与保存；不读取环境数据或调用环境。
- `main.py`：CLI、组件组装和 episode 调度；兼容原 `build_graph` 等导入路径。

## 环境契约

实现 `reset()`、`validate_action(action)`、`step(action)` 和 `close()`。reset/step 返回 Snapshot，校验返回 ValidationResult。

观察第一版仍是文本。动作可为字符串或 JSON 可序列化字典。`action_spec` 告诉 policy 动作如何表达；`allowed_actions` 是可选的枚举候选，不能替代环境校验。新环境通过 factory 和入口配置接入，不修改 runner 节点。

Snapshot 保留旧的 `done/won/split` 字段以减少改动；新适配器可用 `terminated/truncated`，`won` 表示任务成功，公共 `success/finished` 属性提供统一读取。split 默认空，不要求新环境使用 ALFWorld 划分。环境元数据放 `metadata`。

`done` 在 Agent 状态中表示流程结束；`terminated/truncated` 表示环境结束原因。Agent 步数耗尽记录为 `step_limit`，环境截断为 `truncated`。初始已结束任务不执行动作。原始环境 info 和专家计划不进入决策输入。

## Skill 和轨迹

三个 hook 签名保持不变：`search_skill(task)`、`extract_skill(task, trace)`、`save_skill(candidate)`。

轨迹保留 step、observation、allowed_actions、action、feedback、valid，补充 action_spec；实际执行的动作包含 reward。动作可以是字典。提取器使用动作前观察、动作及反馈，并检查 source_steps。策略描述应泛化任务参数和临时标识，不能直接复用某次任务的元素编号。

通过 `--skills-dir` 选择独立库；默认仍使用现有 skills/。目录由入口设置，三个工具只操作选定目录。第一版一个进程使用一个库，不支持同进程并发切换库。新环境应选择自己的目录，避免跨环境查重误合并。保存与合并保留元数据和 evidence；跨环境迁移策略留待后续。

## 使用与验证

在 langgraph_skill_demo 目录、原 conda 环境中：

```bash
python -m unittest discover -q
python main.py --graph
python main.py --mode mock --episodes 2
python main.py --mode alfworld --episodes 1 --max-steps 30 \
  --search-hook a_module:search_skill \
  --extract-hook a_module:extract_skill \
  --save-hook a_module:save_skill \
  --skills-dir logs/alfworld-skills
```

`--graph` 不创建真实环境；即使选择 alfworld 模式，也不要求安装 ALFWorld 或准备数据。运行 Agent 仍需要 requirements.txt 中的基础依赖。

边界测试覆盖结构化动作、非法动作拦截、环境截断、初始终态、无 ALFWorld 时输出图、独立技能目录、元数据保存及结构化证据。既有测试继续覆盖 ALFWorld 接口、专家信息过滤和 Skill 异常隔离。

## 本版验收记录（2026-11-14）

- 46 项离线测试通过，包括原有 36 项和新增 10 项边界测试。
- 真实 ALFWorld valid_seen：`clean some lettuce and put it in fridge.`，7 步成功。
- 首次提取曾返回空 JSON；提取调用输出预算由 256 提高到 1024，其他调用默认不变。随后重放成功轨迹，完成真实提取、入库和检索命中。
- 使用该独立库再次运行真实任务，7 步成功，检索命中 `skill-0001`，Skill 无错误，提取返回 `no_candidate`。已有技能覆盖时不生成新候选是正常路径。
- 回归库与日志存于本地忽略的 logs/，不修改仓库中的种子技能。

上述验证证明接口与闭环可运行；单项任务回归不代表完整 ALFWorld 成功率评测，也未验证 Web 环境。

## 环境工具分离与 MiniWoB 扩展

- core/tools.py 定义最小 EnvironmentTools 协议；交互工具按环境实例绑定，未添加全局 registry。
- ALFWorldAdapter 委托 ALFWorldTools 校验与执行；保留字符串兼容。
- MiniWoBAdapter 与 MiniWoBTools 共享一个原生环境；get_dom 为内部观察能力，其余三个工具进入 action_spec。
- factory 只创建本次所选环境，MiniWoB 的依赖延迟导入。Skill 工具仍通过原 hooks 独立提供。
- runner 仅增加可选 native_actions 轨迹字段，没有 MiniWoB 专属节点或分支。
