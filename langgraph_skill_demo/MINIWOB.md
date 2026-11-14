# MiniWoB++ 第一版

支持 DOM 点击和表单任务。每次运行只绑定所选环境的工具，不使用全局交互工具注册表。Skill hooks 与交互工具分开。

## 环境和工具

ALFWorld：`alfworld_adapter.py` 管生命周期、数据和结果；`alfworld_tools.py` 只提供 `execute(command)`，按当前 admissible_commands 校验。旧字符串动作仍可用。

MiniWoB：`miniwob/adapter.py` 管任务、seed、浏览器、观察、奖励和结束状态；`miniwob/tools.py` 管工具 schema、参数校验和原生动作执行。

模型可用动作：

```json
{"tool": "click", "ref": 4}
{"tool": "type_text", "ref": 7, "text": "hello", "clear": true}
{"tool": "press_key", "key": "<Enter>"}
```

`type_text` 默认追加，clear=true 时依次点击、Ctrl+A、Backspace、输入。作为一次 Agent 动作计步；trace.native_actions 记录实际执行的原生操作，任一子动作结束任务时立即停止。

get_dom() 是内部观察接口，不注册为模型动作；reset 和每次执行后自动提供最新 DOM。观察保留父子关系、标签、文本、输入值、flags、可读聚焦状态和几何信息。MiniWoB 的输入类型可能编码在标签中，例如 input_text。复选框状态可通过其 value 读取。ref 以当前观察为准，不应写死到 Skill 中。

工具与原生环境实例绑定，不可跨实例使用。首版不包括滚动、拖拽、绘图或图像模型。

## 安装

在现有 Python 3.11 环境中：

```bash
python -m pip install -r requirements.txt -r requirements-miniwob.txt
```

需要 Linux Chrome/Chromium 和匹配的 ChromeDriver，二者可通过 PATH 或 Selenium Manager 配置发现。Ubuntu 缺共享库时安装对应系统包；本次 WSL 所需为 libnss3、libnspr4、libasound2t64。

本机验证使用 Chrome for Testing / ChromeDriver 157.0.8103.78，位于用户缓存 ~/.cache/miniwob-browser，命令链接位于 ~/.local/bin。新 shell 可运行：

```bash
export PATH="$HOME/.local/bin:$PATH"
export SE_BROWSER_PATH="$HOME/.cache/miniwob-browser/chrome-linux64/chrome"
export SE_DRIVER_VERSION=157.0.8103.78
export SE_OFFLINE=true
export SE_AVOID_STATS=true
```

这些变量用于本机已安装的匹配浏览器，其他机器应按各自安装位置设置。offline 避免 Selenium Manager 在启动时联网检查版本，不影响模型请求。

## 运行

```bash
python main.py --mode miniwob --task login-user --seed 0 --episodes 2 --max-steps 20 \
  --search-hook a_module:search_skill \
  --extract-hook a_module:extract_skill \
  --save-hook a_module:save_skill
```

任务名不带 miniwob/ 前缀或 -v1 后缀。每轮 seed 递增；默认配置在 config/miniwob.yaml，可用 --miniwob-config 替换。

MiniWoB 默认技能目录为 data/miniwob-skills，独立于 ALFWorld 的旧 skills/；--skills-dir 可显式选择目录。运行日志默认在 logs/。默认数据模式 test；此字段是 MiniWoB 模式，不对应 ALFWorld 的 valid_seen。

使用二值奖励，只有 terminated 且奖励为 1 才计成功。原生 terminated/truncated 分开记录。MiniWoB 的浏览器墙钟超时可能由环境表现为失败终止，不保证都标为 truncated。

默认 episode_timeout_ms=120000，在 reset 开始计时之前设置 core.EPISODE_MAX_TIME。LLM 推理时间包含在预算内，未暂停计时。此配置扩展了原始任务时限，不应与原始限时 benchmark 结果直接比较。

## 验证

```bash
python -m unittest discover -q
python main.py --graph
python main.py --mode mock --episodes 2
```

浏览器和模型验证需要实际依赖与 API key，离线单测不需要。模型 smoke test 的成功不能代表整个 MiniWoB 基准成功率。

## 本次验收（2026-11-14）

- 61 项离线测试通过。
- 第一阶段 ALFWorld 真实模型回归：8 步成功，使用 execute 工具。
- MiniWoB 五类任务（seed=0）均成功：click-test-2 / click-button 各 1 步，enter-text 2 步，login-user 3 步，click-checkboxes 2 步。
- 真实浏览器验证追加输入、clear=true 覆盖、Tab 按键和提交；任务成功。
- login-user 成功轨迹提取并保存 Skill；seed=1 通过 CLI 再运行，检索命中已保存 Skill，3 步成功且无 hook 错误。
- 非空 Skill 库的真实 save 合并和再次检索通过。保存输出预算由 256 提高到 1024，以避免结构化 Skill JSON 截断。
- 独立等待 11 秒后任务仍可执行，验证扩展时限生效。
- 验证轨迹和技能库位于本地忽略的 logs/miniwob-validation、logs/miniwob-cli，未修改原种子技能。

验证中曾出现结构化动作及 Skill 保存的输出截断，已分别提高对应调用预算并复验。上述结果为少量 smoke tests，不是全量评测，也不能据此断言 Skill 提高了成功率。
