import json
import sys
from pathlib import Path

project = Path('/home/ocastellan/skill_evolution_eval/langgraph_skill_demo')
sys.path.insert(0, str(project))

from environments.alfworld_adapter import ALFWorldAdapter
from main import build_graph, choose_action_with_deepseek, save_run
from skill_hooks import SkillHooks

env = ALFWorldAdapter(project / 'config/alfworld_text.yaml',
                      Path('/home/ocastellan/.cache/alfworld'), 'valid_seen')
# Search returns []; extract/save are irrelevant to action selection and disabled.
graph = build_graph(env, SkillHooks(), choose_action_with_deepseek, max_steps=40)

try:
    for _ in range(15):
        env.reset()
    for index in (16, 17):
        result = graph.invoke({}, config={'recursion_limit': 90})
        path = save_run(result, project / 'logs' / 'control', index)
        print(json.dumps({
            'index': index,
            'task': result['task'],
            'status': result['status'],
            'steps': result['step_count'],
            'retrieved_skill_ids': result['retrieved_skill_ids'],
            'agent_context': result['agent_context'],
            'log': str(path),
        }, ensure_ascii=False), flush=True)
finally:
    env.close()
