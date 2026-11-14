# 同学 C：ALFWorld Agent Loop

Agent、环境与 Skill 已拆分；架构与扩展方式见 [架构说明](ARCHITECTURE.md)。现有 ALFWorld CLI 和三个 hook 签名保持兼容。

## 对接接口

现有 `a_module.py` 提供以下三个入口，也可用 `module:function` 注入其他实现：

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
python -m unittest discover -q

# 输出 LangGraph 的 Mermaid 流程图
python main.py --graph

# 不调用模型，用两轮模拟任务检查执行流程
python main.py --mode mock --episodes 2

# 设置真实运行所需的 DeepSeek API Key
export DEEPSEEK_API_KEY='你的 Key'

# 在 valid_seen 运行两项任务，每项最多 30 步；三个 hook 依次接入 A 检索、B 提取、A 保存
python main.py --mode alfworld --split valid_seen --episodes 2 --max-steps 30 \
  --search-hook a_module:search_skill \
  --extract-hook a_module:extract_skill \
  --save-hook a_module:save_skill
```

流程图及详细状态见 [C任务流程图与运行说明.md](C任务流程图与运行说明.md)。

## 环境工具与 MiniWoB++

ALFWorld 已将交互分离为实例级 execute 工具；MiniWoB++ 按环境绑定 click、type_text、press_key。安装、配置、运行及计时说明见 [MiniWoB 接入说明](MINIWOB.md)。
