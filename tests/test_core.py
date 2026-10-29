import json
import os
import sqlite3
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch

from projectflow import content
from projectflow.llm import Model, endpoint, parse_object
from projectflow.server import make_server
from projectflow.service import SCHEMAS, Service
from projectflow.store import PUBLIC_FIELDS, Store, is_due, task_markdown
from projectflow.thinking import STATES, TEMPLATES, guided_prompt, recommend

TEST_TMP = Path(__file__).resolve().parent / '.tmp'
TEST_TMP.mkdir(exist_ok=True)


class FakeModel:
    def __init__(self):
        self.calls = []
        self.reply = json.dumps({'answer': '请先明确资料查找的具体场景。', 'suggestions': ['problem', 'hypothesis', 'validate'], 'state': 'IDEATE', 'save_hint': True})

    def public(self):
        return {'configured': True, 'has_key': False, 'model': 'test', 'base_url': 'http://fake/v1', 'timeout': 5}

    def call(self, messages):
        self.calls.append(messages)
        return self.reply


class CoreTests(unittest.TestCase):
    def setUp(self):
        env = patch.dict(os.environ, {'LLM_API_KEY': '', 'LLM_BASE_URL': '', 'LLM_MODEL': ''})
        env.start()
        self.addCleanup(env.stop)
        self.tmp = tempfile.TemporaryDirectory(dir=TEST_TMP)
        self.root = Path(self.tmp.name)
        self.model = FakeModel()
        self.service = Service(self.root, self.model)
        self.scope = {'mode': 'demo', 'owner': 'demo-a'}

    def tearDown(self):
        self.tmp.cleanup()

    def save(self, kind, data, **kwargs):
        return self.service.save({**self.scope, 'kind': kind, 'data': data, **kwargs})['id']

    def test_initialization_idempotent_and_migration_backup(self):
        store = Store(self.root / 'old.sqlite3')
        store.put('projects', 'me', {'title': 'keep'}, 'old')
        with store.connect() as db:
            db.execute('PRAGMA user_version=1')
        again = Store(store.path)
        self.assertEqual(again.get('projects', 'old')['title'], 'keep')
        self.assertEqual(len(list(self.root.glob('old.before-v2-*.sqlite3'))), 1)
        Store(store.path)
        self.assertEqual(len(again.list('projects')), 1)

    def test_refuse_newer_database(self):
        file = self.root / 'future.sqlite3'
        with sqlite3.connect(file) as db:
            db.execute('PRAGMA user_version=99')
        db.close()
        with self.assertRaises(ValueError):
            Store(file)

    def test_interest_and_project_persistence(self):
        self.save('interests', {'title': '内容创作'})
        pid = self.save('projects', {'title': '采访节目', 'goal': '研究用户需求'})
        fresh = Service(self.root, self.model)
        state = fresh.state(self.scope)
        self.assertEqual(state['interests'][0]['title'], '内容创作')
        self.assertTrue(any(p['id'] == pid for p in state['projects']))

    def test_version_snapshots_not_overwritten(self):
        pid = self.save('projects', {'title': '方案', 'approach': 'A'})
        self.save('projects', {'approach': 'B'}, id=pid, reason='有新证据', evidence='一次访谈')
        versions = self.service.community.list('versions', 'demo-a', pid)
        self.assertEqual(len(versions), 2)
        self.assertEqual({v['snapshot']['approach'] for v in versions}, {'A', 'B'})
        self.assertEqual(next(v for v in versions if v['version'] == 2)['reason'], '有新证据')

    def test_templates_dynamic_and_validation(self):
        self.assertGreaterEqual(len(TEMPLATES), 13)
        self.assertNotEqual(recommend('IDEATE'), recommend('REFLECT'))
        for state in STATES:
            self.assertEqual(len(recommend(state, proposed=['invalid', None, 'problem', 'problem'])), 3)
        with self.assertRaises(ValueError):
            guided_prompt('problem', ['', ' '])
        prompt = guided_prompt('problem', ['资料找不到', '自动标签'])
        self.assertIn('资料找不到', prompt)
        self.assertIn('自动标签', prompt)

    def test_structured_parser(self):
        self.assertEqual(parse_object('```json\n{"title":"草案"}\n```', ['title'])['title'], '草案')
        for invalid in ['[]', '{"title":null}', '{"title":""}', 'not JSON']:
            with self.assertRaises(ValueError):
                parse_object(invalid, ['title'])

    def test_chat_and_guided_context_persisted(self):
        cid = self.save('conversations', {'title': '知识工具', 'state': 'UNDERSTAND'})
        self.service.ai({**self.scope, 'conversation_id': cid, 'text': '我想做知识整理工具', 'action': 'chat'})
        self.service.ai({**self.scope, 'conversation_id': cid, 'template_id': 'problem', 'values': ['资料太多找不到', '自动标签'], 'action': 'chat'})
        serialized = json.dumps(self.model.calls[-1], ensure_ascii=False)
        self.assertIn('资料太多找不到', serialized)
        self.assertIn('自动标签', serialized)
        self.assertIn('我想做知识整理工具', serialized)
        msgs = self.service.community.list('messages', 'demo-a', cid)
        self.assertEqual(len(msgs), 4)
        self.assertEqual(self.service.community.get('conversations', cid)['state'], 'UNDERSTAND')

    def test_invalid_recommendations_fall_back(self):
        cid = self.save('conversations', {'title': '理解', 'state': 'UNDERSTAND'})
        self.model.reply = '{"answer":"正常回答","suggestions":["bogus"],"state":["bad"]}'
        result = self.service.ai({**self.scope, 'conversation_id': cid, 'text': '为什么', 'action': 'chat'})
        self.assertEqual(result['suggestions'], recommend('UNDERSTAND'))
        self.model.reply = '普通文本回答'
        result = self.service.ai({**self.scope, 'conversation_id': cid, 'text': '为什么', 'action': 'chat'})
        self.assertEqual(result['answer'], '普通文本回答')

    def test_extracted_idea_draft_needs_confirmation_and_links(self):
        cid = 'demo-conv-0'
        self.model.reply = json.dumps({k: '用户确认前的推测' for k in SCHEMAS['idea']})
        draft = self.service.ai({**self.scope, 'action': 'idea', 'conversation_id': cid})['draft']
        self.assertEqual(draft['status'], 'DRAFT')
        self.assertEqual(len(self.service.community.list('ideas', 'demo-a')), 1)
        iid = self.save('ideas', draft)
        self.assertEqual(self.service.community.get('ideas', iid)['source_conversation_id'], cid)
        pid = self.save('projects', {'title': '新项目', 'related_idea_id': iid, 'source_conversation_id': cid})
        eid = self.save('experiments', {'title': '小实验', 'related_idea_id': iid, 'related_project_id': pid})
        self.assertEqual(self.service.community.get('ideas', iid)['related_project_id'], pid)
        self.assertEqual(self.service.community.get('experiments', eid)['related_project_id'], pid)

    def test_source_message_must_belong_to_conversation(self):
        with self.assertRaises(ValueError):
            self.save('ideas', {'title': 'bad', 'source_conversation_id': 'demo-conv-0', 'source_message_ids': ['demo-conv-1-m0']})

    def test_task_export_import_and_status(self):
        draft = self.service.local_task({**self.scope, 'project_id': 'demo-project-0'})['draft']
        tid = self.save('tasks', draft, parent='demo-project-0')
        markdown = task_markdown(self.service.community.get('tasks', tid))
        for part in ('验收标准', '不允许的操作', '需要人工确认', '已知输入', '预期输出'):
            self.assertIn(part, markdown)
        self.save('tasks', {'status': 'DELEGATED'}, id=tid)
        rid = self.save('results', {'summary': '完成原型', 'evidence': '测试报告', 'unfinished': '用户试用'}, parent=tid)
        self.assertEqual(self.service.community.get('results', rid)['parent'], tid)
        self.assertEqual(self.service.community.get('tasks', tid)['status'], 'DELEGATED')

    def test_standalone_experiment_can_delegate_without_project(self):
        count = len(self.service.community.list('projects'))
        eid = self.save('experiments', {'title': '小验证', 'hypothesis': '一种简化是否可行', 'first_action': '准备输入', 'criteria': '比较两种结果'})
        draft = self.service.local_task({**self.scope, 'experiment_id': eid})['draft']
        tid = self.save('tasks', draft, parent=eid)
        self.save('results', {'summary': '完成首个样例'}, parent=tid)
        self.assertEqual(self.service.community.get('tasks', tid)['related_experiment_id'], eid)
        self.assertIn('比较两种结果', draft['acceptance'])
        self.assertEqual(len(self.service.community.list('projects')), count)

    def test_generated_drafts_validated_and_idea_experiments_link_project(self):
        iid = self.save('ideas', {'title': '早期想法'})
        for action in ('experiment', 'project', 'task'):
            self.model.reply = json.dumps({k: '待检查的' + k for k in SCHEMAS[action]})
            self.assertIn('title', self.service.ai({**self.scope, 'action': action, 'idea_id': iid})['draft'])
        self.model.reply = '{"title": "missing fields"}'
        with self.assertRaises(ValueError):
            self.service.ai({**self.scope, 'action': 'experiment', 'idea_id': iid})
        eid = self.save('experiments', {'title': '先建立的微实验', 'related_idea_id': iid})
        pid = self.save('projects', {'title': '后建立的项目', 'related_idea_id': iid})
        self.assertEqual(self.service.community.get('experiments', eid)['related_project_id'], pid)

    def test_public_scope_cannot_be_switched_by_edit(self):
        cid = self.service.public_conversation({**self.scope, 'snapshot_id': 'demo-public-0'})['conversation_id']
        self.save('conversations', {'title': '更名'}, id=cid)
        self.assertEqual(self.service.community.get('conversations', cid)['public_snapshot_id'], 'demo-public-0')
        with self.assertRaises(ValueError):
            self.save('conversations', {'project_id': 'demo-project-0'}, id=cid)
        self.service.community.put('profiles', 'demo-b', {'name': 'B', 'bio': 'PRIVATE_BIO'}, 'demo-b')
        self.assertNotIn('PRIVATE_BIO', json.dumps(self.service.state(self.scope)['profiles']))

    def test_review_uses_saved_results(self):
        tid = self.save('tasks', {'title': '验证'}, parent='demo-project-0')
        self.save('results', {'summary': '失败的运行', 'issues': '输入格式错误'}, parent=tid)
        result = self.service.ai({**self.scope, 'action': 'review', 'project_id': 'demo-project-0'})
        self.assertIn('输入格式错误', json.dumps(self.model.calls[-1], ensure_ascii=False))
        self.assertEqual(self.service.community.get('conversations', result['conversation_id'])['state'], 'REFLECT')

    def test_due_reminder(self):
        rid = self.save('reminders', {'question': '具体障碍是什么', 'date': '2020-01-01'}, parent='demo-project-0')
        self.assertTrue(any(r['id'] == rid for r in self.service.state(self.scope)['due']))
        self.save('reminders', {'date': '2099-01-01'}, id=rid)
        self.assertFalse(any(r['id'] == rid for r in self.service.state(self.scope)['due']))
        self.assertFalse(is_due({'date': '2020-01-01', 'status': 'DONE'}, '2026-10-29'))
        with self.assertRaises(ValueError):
            self.save('reminders', {'question': 'x', 'date': 'tomorrow'}, parent='demo-project-0')

    def test_public_snapshot_whitelist_and_no_auto_update(self):
        private = self.service.community.get('projects', 'demo-project-0')
        request = {**self.scope, 'project_id': private['id'], 'confirmed': True, 'data': {'title': '公开', 'summary': '简介', 'private_messages': 'SECRET', 'api_key': 'KEY'}}
        sid = self.service.publish(request)['id']
        snap = self.service.community.get('snapshots', sid)
        self.assertNotIn('SECRET', json.dumps(snap))
        self.assertNotIn('KEY', json.dumps(snap))
        self.assertEqual(snap['parent'], '')
        self.save('projects', {'goal': 'PRIVATE_CHANGE'}, id=private['id'])
        self.assertNotIn('PRIVATE_CHANGE', json.dumps(self.service.community.get('snapshots', sid)))
        with self.assertRaises(ValueError):
            self.service.publish({**request, 'confirmed': False})

    def test_public_ai_never_reads_private_data(self):
        db = self.service.community
        self.save('projects', {'evidence': 'OWNER_PRIVATE_SECRET'}, id='demo-project-0')
        db.put('messages', 'demo-a', {'role': 'user', 'content': 'SECRET_CHAT'}, parent='demo-conv-0')
        db.put('profiles', 'demo-b', {'name': 'B', 'bio': 'PARTICIPANT_PRIVATE_BIO'}, 'demo-b')
        b = {'mode': 'demo', 'owner': 'demo-b'}
        cid = self.service.public_conversation({**b, 'snapshot_id': 'demo-public-0'})['conversation_id']
        self.service.ai({**b, 'action': 'public', 'conversation_id': cid, 'text': '我会向量检索，可以参与什么？'})
        sent = json.dumps(self.model.calls[-1], ensure_ascii=False)
        for forbidden in ['OWNER_PRIVATE_SECRET', 'SECRET_CHAT', 'PARTICIPANT_PRIVATE_BIO']:
            self.assertNotIn(forbidden, sent)
        self.assertIn('个人知识检索工具', sent)
        with self.assertRaises(ValueError):
            self.service.ai({**b, 'action': 'chat', 'conversation_id': cid, 'text': '尝试混入私人上下文'})
        with self.assertRaises(ValueError):
            self.service.ai({**b, 'action': 'chat', 'conversation_id': 'demo-conv-0', 'text': '读取其他人'})

    def test_private_state_and_foreign_links_isolated(self):
        b = {'mode': 'demo', 'owner': 'demo-b'}
        state = self.service.state(b)
        for kind in ('projects', 'conversations', 'messages', 'ideas', 'tasks'):
            self.assertTrue(all(x['owner'] == 'demo-b' for x in state[kind]))
        with self.assertRaises(ValueError):
            self.service.save({**b, 'kind': 'conversations', 'data': {'title': 'unauthorized', 'project_id': 'demo-project-0'}})
        with self.assertRaises(ValueError):
            self.service.save({**b, 'kind': 'projects', 'id': 'demo-project-0', 'data': {'title': 'steal'}})

    def test_comments_proposals_persist_and_owner_accepts(self):
        b = {'mode': 'demo', 'owner': 'demo-b'}
        comment = self.service.save({**b, 'kind': 'comments', 'parent': 'demo-public-0', 'data': {'text': '建议比较两种检索方式'}})['id']
        proposal = self.service.save({**b, 'kind': 'proposals', 'parent': 'demo-public-0', 'data': {'title': '一起做基准', 'skills': '检索评估', 'related_comment_id': comment, 'status': 'ACCEPTED'}})['id']
        self.assertEqual(self.service.community.get('proposals', proposal)['status'], 'PROPOSED')
        with self.assertRaises(ValueError):
            self.service.proposal_status({**b, 'id': proposal, 'status': 'ACCEPTED'})
        self.service.proposal_status({**self.scope, 'id': proposal, 'status': 'ACCEPTED'})
        fresh = Service(self.root, self.model)
        self.assertEqual(fresh.community.get('proposals', proposal)['status'], 'ACCEPTED')
        self.assertEqual(fresh.community.get('comments', comment)['text'], '建议比较两种检索方式')

    def test_demo_reset_does_not_touch_personal(self):
        personal = self.service.personal.put('projects', 'me', {'title': '真实工作'})
        self.save('comments', {'text': '演示评论'}, parent='demo-public-0')
        self.service.reset_demo({'mode': 'demo', 'confirmed': True})
        self.assertEqual(self.service.personal.get('projects', personal)['title'], '真实工作')
        self.assertEqual(self.service.community.list('comments'), [])
        self.assertEqual(len(self.service.community.list('profiles')), 4)
        with self.assertRaises(ValueError):
            self.service.reset_demo({'mode': 'personal', 'confirmed': True})

    def test_five_domains_complete_linked_flow(self):
        for title in ['图片整理 App', '时间序列预测方法', '创业访谈节目', '互动教学工具', '机器人导航算法']:
            cid = self.save('conversations', {'title': title, 'state': 'IDEATE'})
            self.service.ai({**self.scope, 'action': 'chat', 'conversation_id': cid, 'text': '我想做' + title})
            iid = self.save('ideas', {'title': title, 'hypothesis': '待检验', 'source_conversation_id': cid})
            pid = self.save('projects', {'title': title, 'related_idea_id': iid, 'source_conversation_id': cid})
            self.save('experiments', {'title': '小验证', 'related_idea_id': iid, 'related_project_id': pid})
            task = self.service.local_task({**self.scope, 'project_id': pid})['draft']
            self.assertIn(title, task['title'])
            for term in ['VLN', 'SLAM', 'Habitat', 'place node', '导航成功率']:
                self.assertNotIn(term, json.dumps(task, ensure_ascii=False))

    def test_rss_atom_parse_and_dedup(self):
        rss = b'<rss><channel><item><title>Real</title><link>https://example.org/a</link><description>&lt;p&gt;body&lt;/p&gt;</description></item></channel></rss>'
        atom = b'<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Real</title><link href="/a"/><summary>body</summary></entry></feed>'
        self.assertEqual(content.parse_feed(rss)[0]['content'], 'body')
        self.assertEqual(content.parse_feed(atom, 'https://example.org/feed')[0]['url'], 'https://example.org/a')
        source = self.save('sources', {'title': 'Source', 'url': 'https://example.org/feed'})
        with patch('projectflow.content.fetch', return_value=(rss, 'https://example.org/feed')):
            self.assertEqual(self.service.sync({**self.scope, 'id': source})['added'], 1)
            self.assertEqual(self.service.sync({**self.scope, 'id': source})['added'], 0)
        for bad in [b'<html/>', b'<!DOCTYPE rss><rss/>', b'<rss>']:
            with self.assertRaises(ValueError):
                content.parse_feed(bad)

    def test_feed_discovery_verifies_and_rejects_private_addresses(self):
        page = b'<link rel="alternate" type="application/atom+xml" href="/feed">'
        feed = b'<feed xmlns="http://www.w3.org/2005/Atom"/>'
        with patch('projectflow.content.fetch', side_effect=[(page, 'https://example.org/'), (feed, 'https://example.org/feed')]):
            self.assertEqual(content.discover('https://example.org/')[0]['url'], 'https://example.org/feed')
        with self.assertRaises(ValueError):
            content.check_public('http://127.0.0.1/private')

    def test_missing_config_and_network_error(self):
        model = Model(self.root)
        with self.assertRaisesRegex(ValueError, '配置'):
            model.call([])
        model.config = {'base_url': 'http://127.0.0.1:1/v1', 'model': 'local', 'timeout': 5}
        with self.assertRaisesRegex(ValueError, '连接失败'):
            model.call([])

    def test_config_never_persists_key_in_plaintext(self):
        model = Model(self.root)
        model.configure({'base_url': 'http://127.0.0.1:1234/v1', 'model': 'local', 'key': 'PRIVATE_KEY', 'timeout': 5})
        self.assertNotIn('PRIVATE_KEY', (self.root / 'data' / 'model.json').read_text())
        self.assertNotIn('PRIVATE_KEY', json.dumps(model.public()))
        with patch('projectflow.credentials.save', side_effect=ValueError('安全存储不可用')):
            with self.assertRaisesRegex(ValueError, '安全存储'):
                model.configure({'base_url': 'http://example.org/v1', 'model': 'x', 'key': 'NO_WRITE', 'persist_key': True})
        self.assertNotIn('NO_WRITE', (self.root / 'data' / 'model.json').read_text())

    def test_endpoint_validation(self):
        self.assertEqual(endpoint('https://example.org/v1'), 'https://example.org/v1/chat/completions')
        for bad in ['file:///tmp/key', 'https://key@example.org', 'https://example.org?key=x']:
            with self.assertRaises(ValueError):
                endpoint(bad)

    def test_legacy_import_is_additive_and_transactional(self):
        backup = {'version': 2, 'project': {'name': 'legacy'}, 'interests': ['写作'], 'sources': [], 'articles': [{'title': 'old', 'content': 'text', 'chat': [{'role': 'user', 'content': 'old message'}]}], 'ideas': []}
        before = len(self.service.community.list('projects'))
        self.service.legacy_import({**self.scope, 'backup': backup})
        self.assertEqual(len(self.service.community.list('projects')), before + 1)
        backup['articles'][0]['chat'][0]['role'] = 'system'
        with self.assertRaises(ValueError):
            self.service.legacy_import({**self.scope, 'backup': backup})
        self.assertEqual(len(self.service.community.list('projects')), before + 1)


class HTTPTests(unittest.TestCase):
    def setUp(self):
        env = patch.dict(os.environ, {'LLM_API_KEY': '', 'LLM_BASE_URL': '', 'LLM_MODEL': ''})
        env.start()
        self.addCleanup(env.stop)
        self.tmp = tempfile.TemporaryDirectory(dir=TEST_TMP)
        self.server = make_server(Path(__file__).resolve().parent.parent, 0, Path(self.tmp.name))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = 'http://127.0.0.1:' + str(self.server.server_port)
        with urllib.request.urlopen(self.url + '/api/state') as r:
            self.state = json.load(r)

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.tmp.cleanup()

    def post(self, path, data, origin=None, token=None):
        headers = {'Content-Type': 'application/json', 'Origin': origin or self.url, 'X-ProjectFlow-CSRF': token if token is not None else self.state['csrf']}
        req = urllib.request.Request(self.url + path, data=json.dumps(data).encode(), headers=headers)
        with urllib.request.urlopen(req) as r:
            return json.load(r)

    def test_no_key_application_starts_and_writes(self):
        with urllib.request.urlopen(self.url) as r:
            self.assertIn(b'ProjectFlow', r.read())
        result = self.post('/api/save', {'kind': 'projects', 'data': {'title': 'HTTP project'}})
        self.assertTrue(result['id'])
        with self.assertRaises(urllib.error.HTTPError) as cm:
            self.post('/api/ai', {'action': 'test'})
        self.assertEqual(cm.exception.code, 400)

    def test_cross_origin_and_csrf_rejected(self):
        data = {'kind': 'interests', 'data': {'title': 'bad'}}
        for overrides in [{'origin': 'https://evil.example'}, {'token': ''}]:
            with self.assertRaises(urllib.error.HTTPError) as cm:
                self.post('/api/save', data, **overrides)
            self.assertEqual(cm.exception.code, 403)

    def test_static_allowlist_and_host(self):
        for path in ['/.env', '/data/personal.sqlite3', '/projectflow/server.py']:
            with self.assertRaises(urllib.error.HTTPError) as cm:
                urllib.request.urlopen(self.url + path)
            self.assertEqual(cm.exception.code, 404)
        req = urllib.request.Request(self.url + '/api/state', headers={'Host': 'evil.example'})
        with self.assertRaises(urllib.error.HTTPError) as cm:
            urllib.request.urlopen(req)
        self.assertEqual(cm.exception.code, 403)

    def test_real_http_model_protocol_with_local_fixture(self):
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        captured = []
        class Fixture(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_POST(self):
                captured.append(json.loads(self.rfile.read(int(self.headers['Content-Length']))))
                data = json.dumps({'choices': [{'message': {'content': 'fixture connection OK'}}]}).encode()
                self.send_response(200)
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)
        fixture = ThreadingHTTPServer(('127.0.0.1', 0), Fixture)
        thread = threading.Thread(target=fixture.serve_forever, daemon=True)
        thread.start()
        try:
            self.post('/api/config', {'base_url': f'http://127.0.0.1:{fixture.server_port}/v1', 'model': 'fixture', 'timeout': 5})
            response = self.post('/api/ai', {'action': 'test'})
            self.assertEqual(response['answer'], 'fixture connection OK')
            self.assertEqual(captured[0]['model'], 'fixture')
        finally:
            fixture.shutdown()
            fixture.server_close()
            thread.join()


if __name__ == '__main__':
    unittest.main()
