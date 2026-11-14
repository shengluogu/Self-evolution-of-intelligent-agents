# Agent Loop：ALFWorld 与 MiniWoB++

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

## 在 WSL 中运行 MiniWoB++

以下命令在 WSL Ubuntu 终端执行。本机已安装 Python 环境、Chrome 和匹配驱动，可直接准备环境：

```bash
cd /home/nixnehc/Self-evolution-of-intelligent-agents
git switch chenx
git pull --ff-only
conda activate langgraph-alfworld
cd langgraph_skill_demo

export PATH="$HOME/.local/bin:$PATH"
export SE_BROWSER_PATH="$HOME/.cache/miniwob-browser/chrome-linux64/chrome"
export SE_DRIVER_VERSION=157.0.8103.78
export SE_OFFLINE=true
export SE_AVOID_STATS=true
```

浏览器路径和版本为本机安装配置；其他机器需先安装 `requirements.txt`、`requirements-miniwob.txt`、Chrome/Chromium 及匹配驱动，详见 [安装说明](MINIWOB.md#安装)。MiniWoB 不需要下载 ALFWorld 数据。`SE_OFFLINE` 仅控制 Selenium Manager 的版本查询，模型调用仍需要联网。

DeepSeek 密钥从本目录 `.env` 或环境变量 `DEEPSEEK_API_KEY` 读取。请勿提交 `.env`。

### 先运行一个任务

不挂 Skill hooks，先观察 Agent 是否能完成登录：

```bash
python main.py \
  --mode miniwob \
  --task login-user \
  --seed 0 \
  --episodes 1 \
  --max-steps 20
```

结束时终端输出 `status`、`steps`、`skill_status` 和 JSON 日志路径 `log`。`status=success` 表示任务成功；未挂提取 hook 时，`skill_status=pending_extract_hook` 是正常结果。默认日志位于本目录 `logs/`，可打开输出中的 JSON 文件查看每步观察、工具动作与反馈。

### 运行 Skill 闭环

```bash
python main.py \
  --mode miniwob \
  --task login-user \
  --seed 0 \
  --episodes 2 \
  --max-steps 20 \
  --search-hook a_module:search_skill \
  --extract-hook a_module:extract_skill \
  --save-hook a_module:save_skill
```

两轮依次使用 seed 0、1。每轮先检索技能，任务成功后再尝试提取和保存；是否产生新技能由提取结果决定，`no_candidate` 不表示任务失败。日志中的 `retrieved_skill_ids` 可用于检查后续任务是否检索命中，但不能单凭命中判断技能提高了成功率。

MiniWoB 默认技能目录为 `data/miniwob-skills/`，与 ALFWorld 分开；可用 `--skills-dir` 指定其他目录。若想从空库开始，可指定一个尚未使用的目录，例如 `--skills-dir logs/miniwob-demo-skills`。

可将任务替换为 `click-test-2`、`click-button`、`enter-text` 或 `click-checkboxes`。任务名不带 `miniwob/` 前缀和 `-v1` 后缀。

### 浏览器显示与时限

当前 Adapter 使用 `render_mode=None`，即无头模式：真实网页会被操作，但不会弹出浏览器窗口。当前没有可视化启动参数；终端和 JSON 日志可查看执行结果。可见浏览器需要后续增加 `render_mode="human"` 配置支持。

默认配置 `config/miniwob.yaml` 将任务墙钟时限设为 120 秒，包含模型推理时间；`--max-steps` 只控制 Agent 步数。这个时限扩展了原始 MiniWoB 设置，结果不应直接与原始限时基准比较。
