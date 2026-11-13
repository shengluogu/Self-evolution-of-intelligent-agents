# 智能体 Skill 自进化技术创新报告

**依据：**本分支基于[集成分支](https://github.com/shengluogu/Self-evolution-of-intelligent-agents/tree/wsy/chenx-integration)提交 `d590870`。真实实验在 WSL 独立克隆中完成，所需模型调用修正已纳入本分支。

## 1 引言

项目希望在不训练模型的情况下，把任务执行经验提炼为可复用的 Skill，供后续任务检索和使用。研究背景参考 [ExpeL](https://ojs.aaai.org/index.php/AAAI/article/view/29936) 的经验提炼，以及 [ALFWorld](https://arxiv.org/abs/2010.03768) 的文本交互任务。

## 2 任务设计与分析

系统分为三部分：A 负责 Skill 检索与保存，B 从成功轨迹提取候选，C 负责 ALFWorld 环境交互与流程编排。智能体每步根据任务、观察和合法动作选择一条命令；环境的 `done` 与 `won` 共同判定成功。主要难点是让候选 Skill 有执行证据，并控制库内重复。

## 3 智能体与 Skill 自进化方法

[LangGraph 执行图](https://github.com/shengluogu/Self-evolution-of-intelligent-agents/blob/midterm-report/langgraph_skill_demo/main.py)按“初始化 → 检索 → 注入 → 选动作 → 环境执行 → 结束处理”循环。非法动作不送入环境；轨迹记录观察、动作和反馈。

Skill 以 JSON 文件保存，包含 `id`、`name`、`description`、`steps`。A 按任务检索并将结果注入模型输入。任务成功后，B 只从有效动作提取候选，要求每条候选步骤引用原轨迹的 `source_steps`；证据不足则拒绝。A 保存时决定新建或与已有 Skill 合并。[检索](https://github.com/shengluogu/Self-evolution-of-intelligent-agents/blob/midterm-report/langgraph_skill_demo/skill_tools/search_tool.py) · [提取](https://github.com/shengluogu/Self-evolution-of-intelligent-agents/blob/midterm-report/langgraph_skill_demo/skill_tools/extract_tool.py) · [保存](https://github.com/shengluogu/Self-evolution-of-intelligent-agents/blob/midterm-report/langgraph_skill_demo/skill_tools/save_tool.py)

项目的技术改进是**成功门槛、步骤证据校验和入库查重合并**的组合。

## 4 实验结果

| 验证 | 结果 | 含义 |
| --- | --- | --- |
| 集成分支离线单元测试 | **36/36 通过** | 接口、证据校验和 Skill 库操作在测试场景中通过。 |
| 两轮 mock 任务 | **2/2 成功，各 3 步** | 固定任务的流程可运行，不代表模型能力。 |
| 空库任务：热杯子放边桌 | **7 步成功**；B 提取、A 新建 `skill-0001` | [原始日志](real_skill_eval/20261113T030255273115Z_episode4.json) · [生成的 Skill](real_skill_eval/skill-0001.json) |
| 相似任务：加热鸡蛋放台面 | **21 步成功**；检索并注入新 Skill | [原始日志](real_skill_eval/20261113T030654596840Z_episode16.json) |
| 相似任务：热盘子放餐桌 | **12 步成功**；检索并注入新 Skill | [原始日志](real_skill_eval/20261113T030711928821Z_episode17.json) |

实验使用官方 ALFWorld `valid_seen`。为观察新建过程，先在独立克隆中备份仓库自带的示例 Skill，从空库运行；第 4 项真实任务成功并生成 Skill。随后定点运行该划分中第 16、17 项相似任务；两项日志的 `retrieved_skill_ids` 和 `agent_context` 均记录了新 Skill，动作轨迹也完成了加热与放置。两项任务的 B 入口返回 `no_candidate`，表示现有 Skill 已覆盖，没有重复入库。

在相同任务 ID、`deepseek-flash` 配置和每项最多 40 步的设置下，又分别运行了一次无 Skill 对照。对照使用相同 Agent Loop，检索结果为 `[]`，没有调用提取与保存接口。这些是历史实验设置；本分支后续运行默认最多 100 步，未改写原始日志。

| 任务 | 有 Skill | 无 Skill | 对照日志 |
| --- | ---: | ---: | --- |
| 加热鸡蛋放台面 | 成功，21 步 | 成功，40 步 | [无 Skill 日志](real_skill_eval/20261113T033147085053Z_episode16.json) |
| 热盘子放餐桌 | 成功，12 步 | 成功，23 步 | [无 Skill 日志](real_skill_eval/20261113T033213137765Z_episode17.json) |

两项任务在这一次配对运行中均成功；有 Skill 共 33 步，无 Skill 共 63 步。模型输出有随机性，每个条件仅运行一次，因此步数差异是观察值，尚不足以断言 Skill 造成了稳定的性能提升。[无 Skill 对照脚本](real_skill_eval/run_no_skill_control.py)可复查任务选择和运行设置。

原分支的 `deepseek-flash` 调用限制为 `max_tokens=256`，第一次真实运行因默认思考耗尽输出配额，返回空 JSON。实验克隆将思考模式设为 `disabled`，并把输出上限调为 1024；[修正差异](real_skill_eval/llm.patch)。修正后 **36/36** 离线测试通过。此修正已纳入 `midterm-report` 分支。

上述日志证明检索、注入、提取、保存和后续真实任务执行已经联通。配对对照显示两组任务均成功，有 Skill 组在这次运行中步数较少；当前样本不足以估计成功率增益或稳定的步数收益。

## 5 结论

集成代码经本地修正后，在真实 ALFWorld 任务中完成了一次“成功轨迹 → Skill 保存 → 两项相似任务检索并执行”的闭环。同任务对照观察到有 Skill 时步数较少；性能提升的稳定性仍需重复实验验证。

## 参考文献

1. [ALFWorld](https://arxiv.org/abs/2010.03768), ICLR 2021。
2. [ExpeL](https://ojs.aaai.org/index.php/AAAI/article/view/29936), AAAI 2024。
3. [Reflexion](https://papers.nips.cc/paper_files/paper/2023/hash/1b44b878bb782e6954cd888628510e90-Abstract-Conference.html), NeurIPS 2023。
4. [Voyager](https://mlanthology.org/tmlr/2024/wang2024tmlr-voyager/), TMLR 2024。
5. [SkillRL](https://arxiv.org/abs/2602.08234), 2026。
