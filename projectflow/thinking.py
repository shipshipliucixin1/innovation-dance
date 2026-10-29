"""Domain-neutral, editable cognitive scaffolds. No model is needed for templates."""
STATES = {'EXPLORE': '探索', 'UNDERSTAND': '理解', 'IDEATE': '构思',
          'VALIDATE': '验证', 'EXECUTE': '执行', 'REFLECT': '复盘'}
_TEMPLATES = [
    ('understand', '深入理解', ['我还没有弄清楚的问题', '我目前自己的理解']),
    ('example', '用具体例子解释', ['我希望看到的具体场景', '抽象解释中最难理解的部分']),
    ('check', '检查自己的理解', ['请检查我的理解', '我不确定的推理环节']),
    ('counter', '寻找反例', ['我目前相信的判断', '我担心没有考虑的情况']),
    ('boundary', '分析适用边界', ['我想使用的方法', '实际使用条件与限制']),
    ('compare', '比较不同方案', ['我正在比较的方案', '我最关心的取舍']),
    ('expand', '扩展新想法', ['我想解决或改进的问题', '我初步想到的方法']),
    ('problem', '明确核心问题', ['我想解决的问题', '我的初步想法']),
    ('hypothesis', '寻找关键假设', ['我的方案', '它成立需要哪些条件']),
    ('validate', '设计验证方法', ['我想检验的猜想', '我觉得最简单的验证方式']),
    ('action', '拆分下一步行动', ['我希望完成的目标', '已有条件与目前障碍']),
    ('result', '分析实验结果', ['我原先预计会发生', '实际观察到', '我认为原因可能是']),
    ('reflect', '复盘原有认识', ['我原来的判断', '这次的新证据', '我想调整的认识']),
]
TEMPLATES = {key: {'id': key, 'label': label, 'fields': fields} for key, label, fields in _TEMPLATES}
DEFAULTS = {'EXPLORE': ['problem', 'example', 'expand'], 'UNDERSTAND': ['understand', 'check', 'counter'],
            'IDEATE': ['expand', 'hypothesis', 'compare'], 'VALIDATE': ['validate', 'boundary', 'counter'],
            'EXECUTE': ['action', 'boundary', 'result'], 'REFLECT': ['result', 'reflect', 'validate']}


def infer_state(text):
    for state, words in [('REFLECT', ['结果', '观察到', '复盘', 'result']),
                         ('EXECUTE', ['实现', '报错', '困难', '执行', 'implement']),
                         ('VALIDATE', ['验证', '假设', '实验', 'test']),
                         ('UNDERSTAND', ['理解', '原理', '为什么', 'explain']),
                         ('IDEATE', ['方案', '想法', '开发', '设计', 'idea'])]:
        if any(w in text.lower() for w in words):
            return state
    return 'EXPLORE'


def recommend(state, text='', proposed=None):
    state = state if state in STATES else infer_state(text)
    valid = []
    for key in (proposed if isinstance(proposed, list) else []) + DEFAULTS[state]:
        if isinstance(key, str) and key in TEMPLATES and key not in valid:
            valid.append(key)
    return valid[:3]


def guided_prompt(template_id, values):
    if template_id not in TEMPLATES or not isinstance(values, list):
        raise ValueError('未知的思考模板')
    fields = TEMPLATES[template_id]['fields']
    if len(values) != len(fields) or not all(isinstance(x, str) for x in values):
        raise ValueError('模板字段不完整')
    if not any(len(v.strip()) >= 2 for v in values):
        raise ValueError('请至少填写一个实质字段（两个字符以上）')
    parts = [f'{k}：{v.strip()}' for k, v in zip(fields, values) if v.strip()]
    return '我选择「' + TEMPLATES[template_id]['label'] + '」。\n' + '\n'.join(parts) + '\n请结合前面的讨论和我的理解继续；指出尚未成立的判断，保留我需要自己决定的问题。'


PROGRESS = {
    'NOT_STARTED': '要开始这项工作，目前最缺少的条件是什么？可以在十分钟内完成的第一步是什么？',
    'BLOCKED': '你原本预期哪个环节能够运行？实际在哪一步出现偏差？有什么错误、输入或观察记录？',
    'PROGRESS': '目前完成的部分是否已经足以检验关键假设？还缺什么证据？',
    'RESULT': '结果与原先预期有什么区别？哪些证据改变了你的认识？下一步要保留或修改什么？',
}
