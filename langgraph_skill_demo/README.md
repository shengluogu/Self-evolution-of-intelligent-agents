# 同学 C：LangGraph Agent Loop 与 ALFWorld 文本环境

本目录是同学 C 的任务执行模块。它负责从 ALFWorld 读取任务和合法动作，逐步选择并执行动作，记录轨迹，并在成功后调用 Skill 提取与保存接口。A/B 的正式模块尚未接入；当前已通过模拟测试和官方 ALFWorld `valid_seen` 环境的单步检查，尚未完成 DeepSeek 真实任务与 Skill 复用验收。

## A/B/C 对接

运行时用 `module:function` 指定 Python 可导入的函数。模块可放在本目录，或通过 `PYTHONPATH` 加入导入路径。接口边界在 `skill_hooks.py`，调用位置在 `main.py`。

| 负责人 | 命令行参数 | 函数签名 | 调用时机与返回值 |
| --- | --- | --- | --- |
| A：检索 | `--search-hook a_module:search_skill` | `search_skill(task: str) -> list[dict]` | 每个任务 `reset()` 后调用一次。`task` 是环境观察中的任务文字；返回匹配 Skill 的字典列表，未命中返回 `[]`。 |
| B：提取 | `--extract-hook b_module:extract_skill` | `extract_skill(task: str, trace: list[dict]) -> dict \| None` | 仅在环境报告成功后调用。返回候选 Skill 字典；无可靠候选时返回 `None`。 |
| A：保存 | `--save-hook a_module:save_skill` | `save_skill(candidate: dict) -> Any` | 仅在 B 返回非空候选后调用；返回值写入运行日志的 `save_result`。 |

B 接收的 `trace` 按时间顺序包含每一步：`step`（从 1 开始）、`observation`、`allowed_actions`、`action`、`feedback`、`valid`。环境成功执行的步骤还可包含 `reward`；环境异常时可包含 `environment_error`。B 应根据这些字段提取候选，不依赖 ALFWorld 的内部 `infos` 或专家计划。失败任务、步数上限和模型错误均不调用 B/A 保存。

检索结果会整体序列化为 JSON，放入每次 DeepSeek 动作请求的 `skills` 字段；当前不做重排或截断。`retrieved_skill_ids` 只表示检索命中，**不证明模型实际采用了 Skill**。未配置 A 的检索函数时返回 `[]`；检索异常会记录在 `skill_errors` 中，不阻断环境任务。正式 A/B 的签名若不同，请在 `skill_hooks.py` 做薄适配，不要把模拟函数当成正式实现。

## 环境与数据

以下命令在 Linux/WSL 中从仓库根目录执行。使用 Python 3.11；项目要求 `langgraph>=1.0`，不能使用 Python 3.9。ALFWorld 文本数据默认下载到 `~/.cache/alfworld`，不应提交到 Git。

```bash
cd langgraph_skill_demo
conda create -n langgraph-alfworld python=3.11
conda activate langgraph-alfworld
python -m pip install -r requirements.txt alfworld
alfworld-download
```

`alfworld-download` 需联网；如需改变数据位置，先设置 `ALFWORLD_DATA`，运行时用同一目录传入 `--alfworld-data`。运行真实任务前由各人在 shell 中设置 `DEEPSEEK_API_KEY`，不要将 Key 写入仓库或日志。

## 运行与验证

在 `langgraph_skill_demo` 目录、激活环境后运行：

```bash
python -m unittest test_agent_loop.py
python main.py --graph
python main.py --mode mock --episodes 2
```

mock 模式固定选第一个合法动作，不调用 DeepSeek，也禁止连接正式保存接口；它只能验证流程和接口形状。真实任务示例：

```bash
export DEEPSEEK_API_KEY='你的 Key'
python main.py --mode alfworld --split valid_seen --episodes 2 --max-steps 30 \
  --search-hook a_module:search_skill \
  --extract-hook b_module:extract_skill \
  --save-hook a_module:save_skill
```

如果 A/B 模块尚未交付，先省略对应 hook 参数。日志写入 `logs/`，每个 episode 一份 JSON；检查 `status`、`trace`、`skill_status`、`retrieved_skills`、`candidate_skill` 和 `save_result`。真实 Skill 复用验收需要至少两项相似任务：第一项成功并提取保存，第二项检索命中，再核对实际动作。`valid_seen` 是训练场景已出现的验证划分；也可选 `valid_unseen` 检查新场景。

更详细的流程与当前验收状态见 [C任务流程图与运行说明.md](C任务流程图与运行说明.md)。
