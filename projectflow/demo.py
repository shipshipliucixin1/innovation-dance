"""Original fictional fixtures. Loaded only into demo.sqlite3."""
from .store import public_fields

USERS = [('demo-a', '林舟 · 软件开发者'), ('demo-b', '陈禾 · 数据分析研究者'),
         ('demo-c', '许晴 · 独立产品开发者'), ('demo-d', '周言 · 内容创作者')]


def seed(store):
    if store.list('profiles'):
        return
    with store.connect() as db:
        for owner, name in USERS:
            store.put('profiles', owner, {'name': name, 'simulated': True}, owner, db=db)
        entries = [
            ('demo-a', '个人知识检索工具', '软件与知识管理', '资料很多，回忆不起读过的内容', '先比较关键词搜索与标签筛选', '检索评价标准、界面设计'),
            ('demo-b', '轻量数据可视化工作台', '数据分析', '非专业用户不易理解 CSV 中的异常', '已画出三种交互草图，尚未开展用户测试', '可视化设计、真实需求访谈'),
            ('demo-c', '交互式编程教程', '教育与产品', '初学者难以理解变量与循环', '制作可逐步执行的最小教程', '教学设计与试用反馈'),
            ('demo-d', '创造者访谈节目', '内容创作', '想了解创造者如何从模糊想法开始行动', '完成第一期选题与嘉宾研究提纲', '采访问题、音频制作经验')]
        for i, (owner, title, domain, problem, approach, help_) in enumerate(entries):
            cid = 'demo-conv-' + str(i)
            store.put('conversations', owner, {'title': title + ' · 示例讨论', 'state': 'EXPLORE', 'sample': True}, cid, db=db)
            for j, (role, text) in enumerate([
                ('user', '我想做' + title + '，但还没想清楚第一步。'),
                ('assistant', '【预置示例对话，非实时 AI】先明确一个你能观察到的问题：' + problem + '。你希望在什么具体场景检验自己的方案？')]):
                store.put('messages', owner, {'role': role, 'content': text, 'sample': True, 'suggestions': ['problem', 'example', 'expand']}, cid + '-m' + str(j), cid, db=db)
            idea_id = 'demo-idea-' + str(i)
            store.put('ideas', owner, {'title': title + '的最小验证', 'description': '【模拟示例】' + problem,
                'problem': problem, 'hypothesis': '一个更简单的流程可能改善体验（待验证）', 'possible_approach': approach,
                'uncertainties': '用户是否真正需要；判断依据是否足够', 'source_conversation_id': cid,
                'source_message_ids': [cid + '-m0', cid + '-m1'], 'status': 'CONFIRMED', 'sample': True}, idea_id, db=db)
            pid = 'demo-project-' + str(i)
            project = {'title': title, 'domain': domain, 'background': '【虚构项目，仅用于本地演示】', 'problem': problem,
                'goal': '完成一个可以检查的小型原型或证据包', 'understanding': '目前仍是待验证方案，尚无真实效果证据',
                'approach': approach, 'conditions': '可自行准备的小样本与本地工具', 'uncertainties': '效果、成本与用户接受度',
                'deliverables': '原型、观察记录与简短结论', 'next_action': '选取一个具体场景，记录当前流程', 'evidence': '',
                'status': 'NOT_STARTED', 'related_idea_id': idea_id, 'source_conversation_id': cid, 'sample': True}
            store.put('projects', owner, project, pid, db=db)
            store.put('versions', owner, {'version': 1, 'summary': '初始示例计划', 'reason': '演示数据', 'evidence': '', 'snapshot': project}, pid + '-v1', pid, db=db)
            store.put('experiments', owner, {'title': title + ' · 20 分钟启动', 'hypothesis': '更简单的流程是否有效',
                'conditions': '先准备 5 个典型样例', 'steps': '记录旧流程；试用原型；比较观察记录', 'outputs': '一份可检查的记录',
                'criteria': '比较完成情况、耗时和主观困难，不预设改善', 'failures': '样本偏差、原型不可用', 'time': '20 分钟开始',
                'first_action': '准备第一个样例', 'related_idea_id': idea_id, 'related_project_id': pid, 'source_conversation_id': cid, 'sample': True}, 'demo-exp-' + str(i), pid, db=db)
            snap = public_fields({'title': title, 'summary': '【模拟项目】' + problem, 'domain': domain, 'problem': problem,
                                  'progress': '初步构思', 'approach': approach, 'help': help_, 'directions': '先一起定义一个小验证'})
            store.put('snapshots', owner, snap, 'demo-public-' + str(i), db=db)
