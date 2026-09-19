from pathlib import Path
import importlib.util,json,tempfile,unittest,copy,zipfile
ROOT=Path(__file__).resolve().parents[1]
def mod(name,file):
 spec=importlib.util.spec_from_file_location(name,ROOT/'tools'/file)
 m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
scope=mod('scope','scope_manifest.py');brief=mod('brief','task_brief.py')

class ScopeTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
  (self.root/'backend/app').mkdir(parents=True)
  (self.root/'backend/app/main.py').write_text('x = 1\n')
 def tearDown(self):self.tmp.cleanup()
 def snapshot(self):return scope.capture(self.root,['backend/app'])
 def test_same(self):self.assertTrue(scope.compare(self.root,self.snapshot())['unchanged'])
 def test_modified(self):
  m=self.snapshot();(self.root/'backend/app/main.py').write_text('x = 2\n')
  self.assertEqual(scope.compare(self.root,m)['modified'],['backend/app/main.py'])
 def test_added(self):
  m=self.snapshot();(self.root/'backend/app/new.py').write_text('y=3')
  self.assertEqual(scope.compare(self.root,m)['added'],['backend/app/new.py'])
 def test_removed(self):
  m=self.snapshot();(self.root/'backend/app/main.py').unlink()
  self.assertEqual(scope.compare(self.root,m)['removed'],['backend/app/main.py'])
 def test_secret_excluded(self):
  (self.root/'backend/app/.env').write_text('SECRET=test-placeholder')
  (self.root/'backend/app/key.pem').write_text('PRIVATE TEST PLACEHOLDER')
  self.assertEqual(len(self.snapshot()['files']),1)
 def test_runtime_excluded(self):
  p=self.root/'backend/app/__pycache__';p.mkdir();(p/'a.pyc').write_bytes(b'abc')
  self.assertEqual(len(self.snapshot()['files']),1)
 def test_root_traversal(self):
  with self.assertRaises(ValueError):scope.capture(self.root,['../anything'])
 def test_absolute(self):
  with self.assertRaises(ValueError):scope.capture(self.root,['/etc/passwd'])
 def test_dot_root(self):
  with self.assertRaises(ValueError):scope.capture(self.root,['.'])
 def test_explicit_env(self):
  with self.assertRaises(ValueError):scope.capture(self.root,['.env'])
 def test_missing(self):
  with self.assertRaises(ValueError):scope.capture(self.root,['missing'])
 def test_symlink_file(self):
  (self.root/'backend/app/link').symlink_to(self.root/'backend/app/main.py')
  with self.assertRaises(ValueError):self.snapshot()
 def test_symlink_dir(self):
  (self.root/'backend/app/link').symlink_to(self.root/'backend',target_is_directory=True)
  with self.assertRaises(ValueError):self.snapshot()
 def test_ancestor_symlink(self):
  (self.root/'link').symlink_to(self.root/'backend',target_is_directory=True)
  with self.assertRaises(ValueError):scope.capture(self.root,['link/app'])
 def test_empty_scope(self):
  with self.assertRaises(ValueError):scope.capture(self.root,[])
 def test_file_limit(self):
  (self.root/'backend/app/new.py').write_text('new')
  with self.assertRaises(ValueError):scope.capture(self.root,['backend/app'],{'max_files':1})
 def test_byte_limit(self):
  with self.assertRaises(ValueError):scope.capture(self.root,['backend/app'],{'max_file_bytes':1})
 def test_total_limit(self):
  with self.assertRaises(ValueError):scope.capture(self.root,['backend/app'],{'max_total_bytes':1})
 def test_overlap_scope(self):
  m=scope.capture(self.root,['backend','backend/app']);self.assertEqual(len(m['files']),1)
 def test_bad_limit(self):
  with self.assertRaises(ValueError):scope.capture(self.root,['backend/app'],{'max_files':True})
 def test_manifest_corruption(self):
  m=self.snapshot();m['files']['backend/app/main.py']['sha256']='0'*64
  with self.assertRaises(ValueError):scope.compare(self.root,m)
 def test_no_writes(self):
  before=sorted(str(p.relative_to(self.root)) for p in self.root.rglob('*'))
  self.snapshot();after=sorted(str(p.relative_to(self.root)) for p in self.root.rglob('*'))
  self.assertEqual(before,after)

class BriefTests(unittest.TestCase):
 def test_core(self):self.assertIn('版本化课程',brief.read_brief('T06'))
 def test_optional(self):self.assertIn('用户点名',brief.read_brief('O01'))
 def test_injection(self):
  with self.assertRaises(ValueError):brief.read_brief('../T06')
 def test_old_task_not_replayed(self):
  with self.assertRaises(ValueError):brief.read_brief('T05')
 def test_all_thirtytwo(self):
  ids=[f'T{i:02d}' for i in range(6,34)]+[f'O{i:02d}' for i in range(1,5)]
  for i in ids:self.assertIn('监督',brief.read_brief(i))
 def test_local_match(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);p=root/'.rebuild-kit/tasks';p.mkdir(parents=True)
   (root/'.rebuild-kit/TASKS.json').write_bytes((ROOT/'references/TASKS.original.json').read_bytes())
   (p/'T06.md').write_bytes((ROOT/'references/original_cards/T06.md').read_bytes())
   self.assertIn('T06',brief.read_brief('T06',root))
 def test_plan_drift_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);(root/'.rebuild-kit').mkdir();(root/'.rebuild-kit/TASKS.json').write_text('{}')
   with self.assertRaises(ValueError):brief.read_brief('T06',root)
 def test_card_drift_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);p=root/'.rebuild-kit/tasks';p.mkdir(parents=True)
   (root/'.rebuild-kit/TASKS.json').write_bytes((ROOT/'references/TASKS.original.json').read_bytes())
   (p/'T06.md').write_text('changed')
   with self.assertRaises(ValueError):brief.read_brief('T06',root)
 def test_duplicate_json_key_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'a.json';p.write_text('{"a":1,"a":2}')
   with self.assertRaises(ValueError):brief.load_json(p)

if __name__=='__main__':unittest.main()
