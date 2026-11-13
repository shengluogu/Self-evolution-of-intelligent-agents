# 同学 C：ALFWorld Agent Loop

A/B/C 模块已集成；真实 Skill 提取、保存与后续检索的记录见[中期报告](../midterm_report/智能体Skill自进化_技术创新报告.md)。

## 对接接口

`a_module.py` 对外提供以下三个 hook，提取逻辑位于 `skill_tools/extract_tool.py`：

| 负责人 | 启动参数 | 函数签名 |
| --- | --- | --- |
| A 检索 | `--search-hook a_module:search_skill` | `search_skill(task: str) -> list[dict]` |
| B 提取 | `--extract-hook a_module:extract_skill` | `extract_skill(task: str, trace: list[dict]) -> dict \| None` |
| A 保存 | `--save-hook a_module:save_skill` | `save_skill(candidate: dict) -> Any` |

调用顺序：A 检索 → C 执行任务 → 成功时 B 提取 → A 保存。B 的 `trace` 每步包含 `step`、`observation`、`allowed_actions`、`action`、`feedback`、`valid`；执行过的动作还包含 `reward`。

## 安装

```bash
git clone https://github.com/shengluogu/Self-evolution-of-intelligent-agents.git
cd Self-evolution-of-intelligent-agents/langgraph_skill_demo
conda create -y -n langgraph-alfworld python=3.11
conda activate langgraph-alfworld
python -m pip install -r requirements.txt alfworld
alfworld-download
```

数据默认下载到每个人的 `~/.cache/alfworld`，运行时自动从该目录读取。

## 运行

```bash
# 检查 Agent Loop 和 A/B 接口的单元测试
python -m unittest test_agent_loop.py

# 输出 LangGraph 的 Mermaid 流程图
python main.py --graph

# 不调用模型，用两轮模拟任务检查执行流程
python main.py --mode mock --episodes 2

# 设置真实运行所需的 DeepSeek API Key
export DEEPSEEK_API_KEY='你的 Key'

# 在 valid_seen 运行两项任务，每项最多 100 步；三个 hook 依次接入 A 检索、B 提取、A 保存
python main.py --mode alfworld --split valid_seen --episodes 2 --max-steps 100 \
  --search-hook a_module:search_skill \
  --extract-hook a_module:extract_skill \
  --save-hook a_module:save_skill
```

早期流程图和阶段说明见 [C任务流程图与运行说明.md](C任务流程图与运行说明.md)。
