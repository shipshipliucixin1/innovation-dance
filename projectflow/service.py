"""Application operations and trust boundaries, independent of the HTTP layer."""
import json
from datetime import date
from . import content, demo
from .llm import SYSTEM, parse_object
from .store import KINDS, PUBLIC_FIELDS, Store, is_due, public_fields, task_markdown
from .thinking import STATES, TEMPLATES, guided_prompt, infer_state, recommend, PROGRESS

SCHEMAS = {
    'idea': ('title', 'description', 'problem', 'hypothesis', 'possible_approach', 'uncertainties'),
    'experiment': ('title', 'hypothesis', 'conditions', 'steps', 'outputs', 'criteria', 'failures', 'time', 'first_action'),
    'project': ('title', 'background', 'problem', 'goal', 'conditions', 'understanding', 'approach', 'uncertainties', 'deliverables', 'next_action', 'evidence', 'domain'),
    'task': ('title', 'background', 'goal', 'context', 'inputs', 'outputs', 'constraints', 'acceptance', 'forbidden', 'confirmation'),
    'article': ('mechanism', 'reason', 'connection', 'question'),
}
FIELDS = {
    'profiles': ('name', 'bio'), 'interests': ('title',), 'sources': ('title', 'url'),
    'articles': ('title', 'url', 'source', 'content', 'read', 'saved', 'analysis', 'external_id', 'excerpt'),
    'conversations': ('title', 'state', 'project_id', 'article_id'),
    'ideas': (*SCHEMAS['idea'], 'source_conversation_id', 'source_message_ids', 'related_project_id', 'status'),
    'experiments': (*SCHEMAS['experiment'], 'source_conversation_id', 'related_idea_id', 'related_project_id', 'status', 'feedback'),
    'projects': (*SCHEMAS['project'], 'status', 'related_idea_id', 'source_conversation_id', 'progress_note'),
    'tasks': (*SCHEMAS['task'], 'status', 'related_experiment_id', 'generation'),
    'results': ('summary', 'evidence', 'paths', 'issues', 'unfinished', 'expected', 'review'),
    'reminders': ('date', 'question', 'status'),
    'comments': ('text', 'kind'),
    'proposals': ('title', 'problem', 'skills', 'first_action', 'related_comment_id', 'status'),
}
REQUIRED = {'profiles': 'name', 'interests': 'title', 'sources': 'title', 'articles': 'title', 'conversations': 'title',
            'ideas': 'title', 'experiments': 'title', 'projects': 'title', 'tasks': 'title', 'results': 'summary',
            'reminders': 'question', 'comments': 'text', 'proposals': 'title'}


class Service:
    def __init__(self, root, model):
        self.root, self.model = root, model
        self.personal = Store(root / 'data' / 'personal.sqlite3')
        self.community = Store(root / 'data' / 'demo.sqlite3')
        if not self.personal.list('profiles'):
            self.personal.put('profiles', 'me', {'name': '我的创造空间', 'bio': ''}, 'me')
        demo.seed(self.community)

    def scope(self, data):
        mode, owner = data.get('mode', 'personal'), data.get('owner', 'me')
        if mode == 'personal' and owner == 'me':
            return self.personal, owner
        if mode == 'demo' and owner in dict(demo.USERS):
            return self.community, owner
        raise ValueError('无效的本地模式或演示身份')

    def state(self, data):
        db, owner = self.scope(data)
        result = {}
        for kind in KINDS:
            if kind in ('snapshots', 'comments', 'proposals'):
                result[kind] = db.list(kind)
            elif kind == 'profiles' and data.get('mode') == 'demo':
                result[kind] = [p if p['owner'] == owner else {k: p[k] for k in ('id', 'owner', 'name')} for p in db.list(kind)]
            else:
                result[kind] = db.list(kind, owner)
        result.update(templates=TEMPLATES, states=STATES, progress_questions=PROGRESS,
                      model=self.model.public(), due=[r for r in result['reminders'] if is_due(r)])
        return result

    def save(self, request):
        db, owner = self.scope(request)
        kind, identity = request.get('kind'), request.get('id')
        if kind not in FIELDS:
            raise ValueError('此记录必须通过专用操作创建')
        data = request.get('data', {})
        if not isinstance(data, dict):
            raise ValueError('数据格式无效')
        old = db.get(kind, identity, owner) if identity else {}
        parent = old.get('parent', request.get('parent', ''))
        clean = {k: data[k] for k in FIELDS[kind] if k in data}
        clean = {**{k: old[k] for k in FIELDS[kind] if k in old}, **clean}
        for key, value in clean.items():
            if key in ('read', 'saved', 'excerpt'):
                if not isinstance(value, bool):
                    raise ValueError('布尔字段格式无效')
            elif key == 'source_message_ids':
                if not isinstance(value, list) or not all(isinstance(x, str) for x in value):
                    raise ValueError('来源消息格式无效')
            elif not isinstance(value, str) or len(value) > 100000:
                raise ValueError('字段必须是文本，且不超过 100000 字符')
        required = REQUIRED[kind]
        if not str(clean.get(required, '')).strip():
            raise ValueError('请填写必填项：' + required)
        if kind in ('sources', 'articles') and clean.get('url'):
            clean['url'] = content.url(clean['url'])
        if kind == 'sources' and not clean.get('url'):
            raise ValueError('请填写订阅地址')
        if kind == 'sources' and any(x['url'] == clean['url'] and x['id'] != identity for x in db.list(kind, owner)):
            raise ValueError('订阅源已存在')
        # Validate every private foreign reference against the current owner.
        for field, target in [('source_conversation_id', 'conversations'), ('related_idea_id', 'ideas'),
                              ('related_project_id', 'projects'), ('project_id', 'projects'),
                              ('article_id', 'articles'), ('related_experiment_id', 'experiments')]:
            if clean.get(field):
                db.get(target, clean[field], owner)
        cid = clean.get('source_conversation_id')
        for mid in clean.get('source_message_ids', []):
            msg = db.get('messages', mid, owner)
            if not cid or msg['parent'] != cid:
                raise ValueError('来源消息必须属于关联对话')
        if kind == 'conversations':
            if old.get('public_snapshot_id'):
                if clean.get('project_id') or clean.get('article_id'):
                    raise ValueError('公开讨论不能关联私人项目或文章')
                clean['public_snapshot_id'] = old['public_snapshot_id']
            if clean.get('state', 'AUTO') not in (*STATES, 'AUTO'):
                raise ValueError('未知思考状态')
        parent_kind = {'tasks': 'projects', 'results': 'tasks', 'reminders': 'projects', 'comments': 'snapshots', 'proposals': 'snapshots'}
        if kind == 'tasks' and clean.get('related_experiment_id') == parent:
            parent_kind['tasks'] = 'experiments'
        if kind in parent_kind:
            db.get(parent_kind[kind], parent, None if kind in ('comments', 'proposals') else owner)
        if kind == 'proposals':
            if identity:
                raise ValueError('合作提议状态请由项目作者通过专用操作处理')
            clean['status'] = 'PROPOSED'
            if clean.get('related_comment_id'):
                comment = db.get('comments', clean['related_comment_id'])
                if comment['parent'] != parent:
                    raise ValueError('评论不属于当前公开项目')
        valid_status = {'tasks': ('DRAFT', 'DELEGATED', 'RUNNING', 'DONE', 'BLOCKED'),
                        'projects': tuple(PROGRESS), 'reminders': ('PENDING', 'DONE', 'CANCELLED'),
                        'ideas': ('DRAFT', 'CONFIRMED', 'REJECTED'), 'experiments': ('PLANNED', 'RUNNING', 'DONE')}
        if kind in valid_status and clean.get('status') and clean['status'] not in valid_status[kind]:
            raise ValueError('无效的记录状态')
        if kind == 'reminders':
            date.fromisoformat(clean.get('date', ''))
            clean.setdefault('status', 'PENDING')
        if kind == 'articles' and not identity:
            if any((clean.get('url') and a.get('url') == clean['url']) or (a['title'] == clean['title'] and a.get('source') == clean.get('source')) for a in db.list('articles', owner)):
                raise ValueError('文章已经存在')
        with db.connect() as conn:
            identity = db.put(kind, owner, clean, identity, parent, db=conn)
            if kind == 'projects':
                count = conn.execute('SELECT count(*) FROM versions WHERE parent=?', (identity,)).fetchone()[0]
                db.put('versions', owner, {'version': count + 1, 'summary': str(request.get('summary') or '保存项目计划'),
                    'reason': str(request.get('reason') or '人工编辑'), 'evidence': str(request.get('evidence') or clean.get('evidence', '')),
                    'related_conversation_id': clean.get('source_conversation_id', ''), 'snapshot': clean}, parent=identity, db=conn)
                if clean.get('related_idea_id'):
                    idea = db.get('ideas', clean['related_idea_id'], owner)
                    db.put('ideas', owner, {**idea, 'related_project_id': identity}, idea['id'], idea['parent'], db=conn)
                    for experiment in db.list('experiments', owner):
                        if experiment.get('related_idea_id') == idea['id'] and not experiment.get('related_project_id'):
                            db.put('experiments', owner, {**experiment, 'related_project_id': identity}, experiment['id'], identity, db=conn)
        return {'id': identity}

    def publish(self, data):
        db, owner = self.scope(data)
        if data.get('confirmed') is not True:
            raise ValueError('请先检查并确认公开快照')
        if data.get('project_id'):
            db.get('projects', data['project_id'], owner)
        snap = public_fields(data.get('data'))
        if not snap['title'].strip() or not snap['summary'].strip():
            raise ValueError('请填写公开标题和简介')
        identity = data.get('id')
        if identity:
            db.get('snapshots', identity, owner)
        return {'id': db.put('snapshots', owner, snap, identity)}

    def proposal_status(self, data):
        db, owner = self.scope(data)
        proposal = db.get('proposals', data['id'])
        db.get('snapshots', proposal['parent'], owner)
        if data.get('status') not in ('PROPOSED', 'ACCEPTED', 'DECLINED'):
            raise ValueError('状态无效')
        db.put('proposals', proposal['owner'], {**proposal, 'status': data['status']}, proposal['id'], proposal['parent'])
        return {'ok': True}

    def private_context(self, db, owner, conversation):
        context = {'scope': '仅当前用户的私人上下文', 'interests': [x['title'] for x in db.list('interests', owner)]}
        if conversation.get('project_id'):
            context['project'] = db.get('projects', conversation['project_id'], owner)
        if conversation.get('article_id'):
            article = db.get('articles', conversation['article_id'], owner)
            context['article'] = {k: str(article.get(k, ''))[:24000] for k in ('title', 'source', 'content', 'url')}
        return context

    def ai(self, data):
        db, owner = self.scope(data)
        action = data.get('action', 'chat')
        if action == 'test':
            return {'answer': self.model.call([{'role': 'user', 'content': '请仅回复：连接成功。'}])[:300]}
        if action in ('chat', 'public'):
            conversation = db.get('conversations', data['conversation_id'], owner)
            is_public = bool(conversation.get('public_snapshot_id'))
            if (action == 'public') != is_public:
                raise ValueError('对话上下文类型不匹配')
            prompt = guided_prompt(data['template_id'], data.get('values')) if data.get('template_id') else str(data.get('text', '')).strip()
            if not prompt:
                raise ValueError('请先输入内容')
            history = sorted(db.list('messages', owner, conversation['id']), key=lambda x: (x['created_at'], x['id']))[-20:]
            if is_public:
                ctx = db.snapshot_context(conversation['public_snapshot_id'])
                ctx['voluntary_participant_background'] = str(data.get('background', ''))[:10000]
                system = SYSTEM + '你只知道提供的公开项目及公开评论。无法访问原作者私人记录、未公开实验或设置。明确此边界，不得代表项目作者接受合作。'
            else:
                ctx = self.private_context(db, owner, conversation)
                system = SYSTEM
            requested = conversation.get('state', 'AUTO')
            state = requested if requested in STATES else infer_state(prompt)
            shape = {'answer': '有上下文的自然回答', 'suggestions': list(TEMPLATES)[:3], 'state': state,
                     'save_hint': False}
            messages = [{'role': 'system', 'content': system + '\n只返回 JSON，格式：' + json.dumps(shape, ensure_ascii=False) + '\nsuggestions 从模板 ID 中选三个：' + ','.join(TEMPLATES) + '。state 只能建议，不覆盖用户手动状态。用户形成具体方案或可验证假设时 save_hint=true。'},
                        {'role': 'user', 'content': '上下文数据：' + json.dumps(ctx, ensure_ascii=False)},
                        *[{'role': m['role'], 'content': m['content']} for m in history], {'role': 'user', 'content': prompt}]
            raw = self.model.call(messages)
            try:
                obj = parse_object(raw, ('answer',))
            except ValueError:
                # Ordinary chat remains usable even when structured recommendations fail.
                obj = {'answer': raw, 'format_fallback': True}
            suggestions = recommend(state, prompt, obj.get('suggestions') if requested not in STATES else None)
            model_state = obj.get('state')
            if not isinstance(model_state, str) or model_state not in STATES:
                model_state = state
            with db.connect() as conn:
                db.put('messages', owner, {'role': 'user', 'content': prompt}, parent=conversation['id'], db=conn)
                db.put('messages', owner, {'role': 'assistant', 'content': obj['answer'], 'suggestions': suggestions,
                    'suggested_state': model_state,
                    'save_hint': obj.get('save_hint') is True and not is_public,
                    'format_fallback': obj.get('format_fallback', False)}, parent=conversation['id'], db=conn)
            return {'answer': obj['answer'], 'suggestions': suggestions}
        if action == 'review':
            project = db.get('projects', data['project_id'], owner)
            tasks = db.list('tasks', owner, project['id'])
            results = [r for t in tasks for r in db.list('results', owner, t['id'])]
            prompt = '结合实际计划、任务与手工导入的结果，比较预期与现实，区分报告声称和已检查证据，解释设计取舍，提出一个可检验的下一步。\n' + json.dumps({'project': project, 'tasks': tasks, 'reported_results': results}, ensure_ascii=False)
            answer = self.model.call([{'role': 'system', 'content': SYSTEM}, {'role': 'user', 'content': prompt}])
            cid = db.put('conversations', owner, {'title': project['title'] + ' · 结果复盘', 'state': 'REFLECT', 'project_id': project['id']})
            with db.connect() as conn:
                db.put('messages', owner, {'role': 'user', 'content': '请基于项目中已保存的任务与结果复盘。'}, parent=cid, db=conn)
                db.put('messages', owner, {'role': 'assistant', 'content': answer, 'suggestions': recommend('REFLECT')}, parent=cid, db=conn)
            return {'conversation_id': cid, 'answer': answer}
        if action not in SCHEMAS:
            raise ValueError('未知模型任务')
        context = {}
        cid = data.get('conversation_id')
        if cid:
            conversation = db.get('conversations', cid, owner)
            if conversation.get('public_snapshot_id'):
                raise ValueError('请在私人工作台提取自己的想法')
            context['conversation'] = sorted(db.list('messages', owner, cid), key=lambda x: (x['created_at'], x['id']))[-20:]
            context.update(self.private_context(db, owner, conversation))
        for field, kind in [('idea_id', 'ideas'), ('project_id', 'projects'), ('experiment_id', 'experiments'), ('article_id', 'articles')]:
            if data.get(field):
                context[field] = db.get(kind, data[field], owner)
        if not context:
            raise ValueError('请先选择对话、想法或项目')
        instruction = {
            'idea': '从实际讨论提取一个值得保留的想法。未知或推测明确标注待确认，不把 AI 推断当作用户事实。',
            'experiment': '设计最小微实验。第一步可在10–30分钟开始，提供对照、判断依据和可能失败原因，产物可以是记录、代码、草图或反馈。',
            'project': '生成简洁、可操作的项目草案。不写冗长计划，未知条件待确认。',
            'task': '生成可交给外部执行工具的独立任务书，提供输入输出、约束、验收标准、禁止操作及需人工确认事项。只是草案，不代表已执行。',
            'article': '仅根据文章文本分析核心机制、质量与阅读价值、和项目的可能联系及值得追问的问题。摘要不足时明确说明。'}[action]
        schema = {k: '文本' for k in SCHEMAS[action]}
        raw = self.model.call([{'role': 'system', 'content': SYSTEM}, {'role': 'user', 'content': instruction + '\n只返回 JSON 对象，每个值为字符串，字段如下：' + json.dumps(schema, ensure_ascii=False) + '\n数据：' + json.dumps(context, ensure_ascii=False)}])
        obj = parse_object(raw, SCHEMAS[action])
        draft = {k: obj[k] for k in SCHEMAS[action]}
        if action == 'idea':
            draft.update(source_conversation_id=cid or '', source_message_ids=[x['id'] for x in context.get('conversation', [])], status='DRAFT')
        if action in ('project', 'experiment'):
            idea = context.get('idea_id', {})
            draft.update(source_conversation_id=idea.get('source_conversation_id', cid or ''), related_idea_id=data.get('idea_id', ''))
        if action == 'experiment':
            draft['related_project_id'] = data.get('project_id', '')
        if action == 'task':
            draft.update(related_experiment_id=data.get('experiment_id', ''), generation='AI 生成的可编辑草案，尚未执行', status='DRAFT')
        return {'draft': draft}

    def public_conversation(self, data):
        db, owner = self.scope(data)
        snap = db.get('snapshots', data['snapshot_id'])
        existing = [c for c in db.list('conversations', owner) if c.get('public_snapshot_id') == snap['id']]
        cid = existing[0]['id'] if existing else db.put('conversations', owner, {'title': '公开讨论 · ' + snap['title'], 'state': 'EXPLORE', 'public_snapshot_id': snap['id']})
        return {'conversation_id': cid}

    def local_task(self, data):
        db, owner = self.scope(data)
        exp = db.get('experiments', data['experiment_id'], owner) if data.get('experiment_id') else None
        if data.get('project_id'):
            p = db.get('projects', data['project_id'], owner)
        elif exp:
            p = {'title': exp['title'], 'goal': exp.get('hypothesis', ''), 'next_action': exp.get('first_action', ''),
                 'background': '用于检验以下假设的微实验：' + exp.get('hypothesis', ''), 'problem': exp.get('hypothesis', ''),
                 'conditions': exp.get('conditions', ''), 'approach': exp.get('steps', ''), 'deliverables': exp.get('outputs', '')}
        else:
            raise ValueError('请先选择项目或微实验')
        draft = {'title': p['title'] + ' · 下一步任务', 'background': p.get('background', '待补充'),
                 'goal': p.get('next_action') or p.get('goal', '待明确'),
                 'context': '\n'.join(str(p.get(k, '')) for k in ('problem', 'understanding', 'approach', 'evidence')),
                 'inputs': p.get('conditions', '待确认'), 'outputs': p.get('deliverables', '待明确'),
                 'constraints': '先检查现有工作；最小可运行改动；区分事实与假设；记录验证证据。',
                 'acceptance': '逐项说明完成情况，给出可检查的产物、运行步骤与证据；未验证事项明确标注。',
                 'forbidden': '不得删除无关数据、泄露密钥、修改其他环境或声称未执行的工作已经完成。',
                 'confirmation': '不可逆操作、公开发布和对外发送信息前由用户明确确认。', 'generation': '本地字段组装，非模型生成', 'status': 'DRAFT'}
        if exp:
            draft['related_experiment_id'] = exp['id']
            draft['context'] += '\n微实验：' + json.dumps({k: exp.get(k, '') for k in SCHEMAS['experiment']}, ensure_ascii=False)
            draft['acceptance'] += '\n微实验判断依据：' + exp.get('criteria', '待确认')
        return {'draft': draft, 'markdown': task_markdown(draft)}

    def sync(self, data):
        db, owner = self.scope(data)
        source = db.get('sources', data['id'], owner)
        raw, final = content.fetch(source['url'])
        articles = content.parse_feed(raw, final)
        existing = db.list('articles', owner)
        added = 0
        with db.connect() as conn:
            for a in articles:
                if any((a['url'] and e.get('url') == a['url']) or (e.get('external_id') == a['external_id'] and e.get('source') == source['title']) or (e['title'] == a['title'] and e.get('source') == source['title']) for e in existing):
                    continue
                a.update(source=source['title'], read=False, saved=False)
                db.put('articles', owner, a, db=conn)
                existing.append(a)
                added += 1
        return {'added': added}

    def legacy_import(self, data):
        db, owner = self.scope(data)
        v = data.get('backup')
        if not isinstance(v, dict) or v.get('version') != 2 or not isinstance(v.get('project'), dict):
            raise ValueError('需要旧版 ProjectFlow v2 JSON 备份；导入只新增记录')
        for key in ('articles', 'sources', 'ideas', 'interests'):
            if not isinstance(v.get(key), list):
                raise ValueError('备份缺少列表：' + key)
        with db.connect() as conn:
            p = v['project']
            pid = db.put('projects', owner, {'title': str(p.get('name') or '旧版项目'), 'background': str(p.get('description', '')), 'problem': str(p.get('question', '')), 'status': 'NOT_STARTED'}, db=conn)
            db.put('versions', owner, {'version': 1, 'summary': '旧版导入', 'reason': '显式新增导入', 'snapshot': p}, parent=pid, db=conn)
            for interest in v['interests']:
                if not isinstance(interest, str):
                    raise ValueError('兴趣格式无效，导入已回滚')
                db.put('interests', owner, {'title': interest}, db=conn)
            for source in v['sources']:
                db.put('sources', owner, {'title': str(source['name']), 'url': content.url(source['url'])}, db=conn)
            for a in v['articles']:
                if not isinstance(a.get('content'), str) or not isinstance(a.get('chat'), list):
                    raise ValueError('文章或对话格式无效，导入已回滚')
                aid = db.put('articles', owner, {'title': str(a['title']), 'content': a['content'], 'url': content.url(a['url']) if a.get('url') else '', 'source': str(a.get('source', '')), 'read': bool(a.get('read')), 'saved': bool(a.get('saved'))}, db=conn)
                cid = db.put('conversations', owner, {'title': str(a['title']), 'article_id': aid, 'project_id': pid, 'state': 'AUTO'}, db=conn)
                for m in a['chat']:
                    if m.get('role') not in ('user', 'assistant') or not isinstance(m.get('content'), str):
                        raise ValueError('对话消息无效，导入已回滚')
                    db.put('messages', owner, {'role': m['role'], 'content': m['content']}, parent=cid, db=conn)
            for idea in v['ideas']:
                kind = 'experiments' if idea.get('type') == 'experiment' else 'ideas'
                db.put(kind, owner, {'title': str(idea['title']), 'description': str(idea.get('text', '')), 'steps': str(idea.get('text', '')), 'feedback': str(idea.get('feedback', '')), 'related_project_id': pid}, db=conn)
        return {'project_id': pid, 'message': '旧版数据已新增导入；未读取或导入旧 API 设置和密钥'}

    def reset_demo(self, data):
        if data.get('mode') != 'demo' or data.get('confirmed') is not True:
            raise ValueError('仅可确认重置演示数据库')
        # Transactional DELETE, never unlink a potentially open database.
        with self.community.connect() as db:
            for kind in KINDS:
                db.execute(f'DELETE FROM {kind}')
        demo.seed(self.community)
        return {'ok': True}
