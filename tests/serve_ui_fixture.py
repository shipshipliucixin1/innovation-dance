"""Explicit test-only UI fixture, never used by start.bat or the application.

Run from the repository with its isolated interpreter. All generated text and
the UI banner clearly identify it as a fixture, not a live model.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from projectflow.server import make_server
from projectflow.service import SCHEMAS


class Fixture:
    def public(self):
        return {'configured': True, 'has_key': False, 'base_url': '', 'model': 'TEST FIXTURE', 'timeout': 5, 'test_fixture': True}

    def call(self, messages):
        prompt = messages[-1]['content']
        label = '【测试夹具，非真实 AI】'
        if '只返回 JSON 对象' in prompt:
            requested = json.loads(prompt.split('字段如下：', 1)[1].split('\n数据：', 1)[0])
            for kind, fields in SCHEMAS.items():
                if set(requested) == set(fields):
                    return json.dumps({key: label + {'title': '知识检索的小验证', 'problem': '资料太多不易找回', 'hypothesis': '自动标签可能改善查找（待验证）', 'possible_approach': '比较手工标签与自动标签', 'uncertainties': '评价问题与数据偏差'}.get(key, '根据提供的数据检查此字段') for key in fields}, ensure_ascii=False)
        if '仅回复' in prompt:
            return label + '连接测试完成'
        return json.dumps({'answer': label + '已经收到你的输入：\n' + prompt + '\n建议先用五份资料比较查找体验；真实效果仍待验证。',
                           'suggestions': ['problem', 'hypothesis', 'validate'], 'state': 'IDEATE', 'save_hint': True}, ensure_ascii=False)


if __name__ == '__main__':
    server = make_server(ROOT, 43128, ROOT / '.qa' / 'fixture')
    server.application.model = Fixture()
    print('TEST FIXTURE ONLY: http://127.0.0.1:43128 (not a real AI)', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
