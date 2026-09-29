import ast, unittest
from pathlib import Path
from types import SimpleNamespace
import inbox, views
source=ast.parse(Path('session.py').read_text(encoding='utf-8'))
cls=next(n for n in source.body if isinstance(n,ast.ClassDef) and any(isinstance(f,ast.FunctionDef) and f.name=='inbox_read' for f in n.body))
methods=[n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name.startswith('inbox_')]
ns={}; exec(compile(ast.fix_missing_locations(ast.Module(body=[ast.ClassDef(name='InboxSession',bases=[],keywords=[],body=methods,decorator_list=[])],type_ignores=[])),'session.py','exec'),ns)
class InboxTests(unittest.TestCase):
 def setUp(self):
  self.s=ns['InboxSession'](); self.s.L=SimpleNamespace(inbox=[])
 def msg(self, kind='trade_offer', status='unread'):
  m=dict(id=len(self.s.L.inbox)+1,kind=kind,status=status,subject='Test',payload={}); self.s.L.inbox.append(m); return m
 def test_read_preserves_offer(self):
  m=self.msg(); self.s.inbox_read(m['id']); self.assertEqual(m['status'],'open'); self.assertEqual(inbox.pending(self.s.L),[m]); self.assertTrue(self.s.inbox_message(m['id'])['decide'])
 def test_bulk_and_clear_preserve_decisions(self):
  m=self.msg(); self.msg('league'); self.s.inbox_mark_all(); self.s.inbox_clear_read(); self.assertEqual(self.s.L.inbox,[m])
 def test_delete_guards_pending(self):
  m=self.msg(); self.assertFalse(self.s.inbox_delete(m['id'])['ok']); m['status']='declined'; self.assertTrue(self.s.inbox_delete(m['id'])['ok']); self.assertEqual(self.s.L.inbox,[])
 def test_injury_status_exposed(self):
  for status in ('done','expired','open'):
   m=self.msg('injury_decision',status); self.assertEqual(self.s.inbox_message(m['id'])['status'],status)
if __name__ == '__main__':
 unittest.main()
