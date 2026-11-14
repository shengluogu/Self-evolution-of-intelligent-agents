# skill_tools：Skill 库与工具注册

三个工具（search / extract / save）+ 一个文件夹式 Skill 库。`a_module.py` 是 hook 入口，供 `main.py` 以 `module:function` 形式挂载。

## 用法

```bash
conda activate langgraph-alfworld
cd langgraph_skill_demo
export DEEPSEEK_API_KEY='你的 Key'  # 或写入本目录 .env（已 gitignore，勿提交）

# 单测（fake LLM，离线）
python -m unittest discover -v

# mock 模式（禁 save）：验证检索接入
python main.py --mode mock --episodes 2 --search-hook a_module:search_skill

# 真实 ALFWorld 全链路
python main.py --mode alfworld --split valid_seen --episodes 2 --max-steps 30 \
  --search-hook a_module:search_skill \
  --extract-hook a_module:extract_skill \
  --save-hook a_module:save_skill
```

## 工具一览

| 工具 | 文件 | 状态 | 行为 |
| --- | --- | --- | --- |
| `search_skill` | `search_tool.py` | ✅ | LLM 读全库 name/description 挑相关 skill；库空返回 `[]` 不调 LLM |
| `extract_skill` | `extract_tool.py` | 已接入 | 对照已有摘要与成功轨迹，返回有逐步证据的新候选，已有经验完全覆盖时跳过 |
| `save_skill` | `save_tool.py` | ✅ | 一次 LLM 调用查重并产出最终 skill；无重复新建（新 id），有重复合并进第一条（保留其 id、删多余文件） |

## Skill 格式

`skills/` 一文件一 skill（`skill-0001.json`），纯 JSON、扁平、不绑定具体环境：

```json
{
  "id": "skill-0001",
  "name": "put-item-in-basket",
  "description": "什么任务适用、核心策略。",
  "steps": ["第一步", "第二步"]
}
```

必填 `id/name/description/steps`（str/str/str/list[str]），允许额外字段（校验不拒绝未知键）。

## 加新工具的标准流程

1. 在 `skill_tools/` 新建 `xxx_tool.py`
2. 在 `schemas.py` 补输入/输出模型
3. 用 `@tool` 注册四件套：

```python
from skill_tools.registry import tool

@tool(name="xxx", description="一句话用处", input=XxxInput, output=XxxOutput)
def xxx(...): ...
```

4. 需要 LLM 时 `from llm import deepseek_json`（JSON mode + Pydantic 校验，`DEEPSEEK_API_KEY`/`DEEPSEEK_MODEL` 环境变量，`.env` 自动加载；`max_tokens=256`，提示词要求简洁）
5. 需要存取库时 `from skill_tools import store`（`load_all/save/delete/next_id`）
6. 补离线单测：`patch("skill_tools.xxx_tool.deepseek_json", ...)` 注入 fake LLM

## 模块职责

| 模块 | 职责 |
| --- | --- |
| `../llm.py` | DeepSeek JSON 调用 + `.env` 读取（从 main.py 拆出，与主流程共用） |
| `schemas.py` | Skill / SkillCandidate / 各工具 I/O 模型 |
| `registry.py` | `@tool` 装饰器，登记到 `TOOLS` |
| `store.py` | `skills/` 读写、id 分配（`skill-%04d.json`，同 id 覆盖） |
| `test_*.py` | fake LLM 单测，不需要真实 Key |

## 注意

- 框架契约：search 抛异常任务照跑（记 `skill_errors`）；extract/save 抛异常记 `hook_error`，不翻案任务结果
- `--mode mock` 禁止挂 `--save-hook`（main.py 现有约束）
