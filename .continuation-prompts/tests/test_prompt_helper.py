from __future__ import annotations
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('prompt_helper',ROOT/'tools/prompt_helper.py')
h=importlib.util.module_from_spec(spec)
spec.loader.exec_module(h)
CAT=json.loads((ROOT/'references/TASKS.original.json').read_text('utf-8'))
IDX=json.loads((ROOT/'PROMPT_INDEX.json').read_text('utf-8'))
IDS={t['id'] for t in IDX['tasks']}

def task(name):return next(t for t in CAT['tasks'] if t['id']==name)

class HelperTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.project=Path(self.tmp.name)
        self.state={'target_root':CAT['target_root'],'tasks':{t['id']:{'status':'NOT_STARTED','evidence':[]} for t in CAT['tasks']},'gates':{g:{'status':'BLOCKED','evidence':[]} for t in CAT['tasks'] for g in t['required_gates']}}
        for n in range(6):self.done(f'T{n:02d}')
    def tearDown(self):self.tmp.cleanup()
    def done(self,name):
        p=self.project/'docs/acceptance'/f'{name}.md';p.parent.mkdir(parents=True,exist_ok=True);p.write_text('synthetic test evidence, not real application acceptance')
        self.state['tasks'][name]={'status':'DONE','evidence':[p.relative_to(self.project).as_posix()]}
    def select(self):return h.select_next(CAT,self.state,self.project,IDS)
    def test_01_catalog_equal(self):h.compare_catalog(copy.deepcopy(CAT),CAT)
    def test_02_title_change(self):
        other=copy.deepcopy(CAT);other['tasks'][6]['title']='different'
        with self.assertRaises(h.InputError):h.compare_catalog(other,CAT)
    def test_03_dependencies_change(self):
        other=copy.deepcopy(CAT);other['tasks'][6]['depends_on']=[]
        with self.assertRaises(h.InputError):h.compare_catalog(other,CAT)
    def test_04_gates_change(self):
        other=copy.deepcopy(CAT);other['tasks'][11]['required_gates']=[]
        with self.assertRaises(h.InputError):h.compare_catalog(other,CAT)
    def test_05_grade_before_t06_not_reset(self):
        self.assertEqual(self.select()['id'],'T06')
        self.assertEqual(self.state['tasks']['T05']['status'],'DONE')
    def test_06_after_t06_select_t07(self):
        self.done('T06');self.assertEqual(self.select()['id'],'T07')
    def test_07_blocked_t11_select_t12(self):
        for n in range(6,11):self.done(f'T{n:02d}')
        self.state['tasks']['T11']['status']='BLOCKED'
        self.assertEqual(self.select()['id'],'T12')
    def test_08_blocked_t13_select_t14(self):
        for n in range(6,11):self.done(f'T{n:02d}')
        self.done('T12');self.state['tasks']['T11']['status']='BLOCKED';self.state['tasks']['T13']['status']='BLOCKED'
        self.assertEqual(self.select()['id'],'T14')
    def test_09_failed_resume_priority(self):
        self.done('T06');self.done('T07');self.state['tasks']['T08']['status']='FAILED'
        self.assertEqual(self.select()['id'],'T08')
    def test_10_in_progress_priority(self):
        self.done('T06');self.done('T10');self.state['tasks']['T12']['status']='IN_PROGRESS'
        self.assertEqual(self.select()['id'],'T12')
    def test_11_dont_retry_self_blocked(self):
        self.state['tasks']['T06']['status']='BLOCKED'
        self.assertEqual(self.select()['id'],'T10')
    def test_12_no_optional_auto_execution(self):
        for n in range(34):self.done(f'T{n:02d}')
        self.assertIsNone(self.select())
    def test_13_gate_pass_without_evidence_blocked(self):
        for dep in task('T11')['depends_on']:self.done(dep)
        for gate in task('T11')['required_gates']:self.state['gates'][gate]['status']='PASS'
        self.assertTrue(h.blockers(task('T11'),self.state,self.project))
    def test_14_gate_has_source_not_truth_certified(self):
        for dep in task('T11')['depends_on']:self.done(dep)
        for gate in task('T11')['required_gates']:self.state['gates'][gate]={'status':'PASS','evidence':['https://example.invalid/synthetic-authorized-evidence']}
        self.assertEqual(h.blockers(task('T11'),self.state,self.project),[])
    def test_15_done_missing_file(self):
        self.state['tasks']['T04']['evidence']=['docs/acceptance/missing.md']
        self.assertTrue(h.blockers(task('T06'),self.state,self.project))
    def test_16_empty_evidence(self):
        self.state['tasks']['T01']['evidence']=[]
        self.assertTrue(h.blockers(task('T06'),self.state,self.project))
    def test_17_evidence_dict_supported(self):
        self.state['tasks']['T01']['evidence']=[{'path':'docs/acceptance/T01.md','kind':'report'}]
        self.assertEqual(h.blockers(task('T06'),self.state,self.project),[])
    def test_18_external_path_does_not_substitute_local_record(self):
        self.assertFalse(h.usable_evidence(['/etc/passwd'],self.project))
    def test_19_absolute_local_record(self):
        self.assertTrue(h.usable_evidence([str(self.project/'docs/acceptance/T01.md')],self.project))
    def test_20_progress_not_mutated(self):
        before=copy.deepcopy(self.state);self.select();h.blockers(task('T11'),self.state,self.project)
        self.assertEqual(before,self.state)
    def test_21_blocked_not_unlocked_by_pass(self):
        for dep in task('T11')['depends_on']:self.done(dep)
        for gate in task('T11')['required_gates']:self.state['gates'][gate]={'status':'PASS','evidence':['docs/acceptance/T05.md']}
        self.state['tasks']['T11']['status']='BLOCKED'
        self.assertNotEqual(self.select()['id'],'T11')
    def test_22_invalid_status(self):
        self.state['tasks']['T06']['status']='VERIFIED'
        with self.assertRaises(h.InputError):h.check_progress(self.state,CAT)
    def test_23_wrong_progress_target(self):
        self.state['target_root']='/tmp/another-project'
        with self.assertRaises(h.InputError):h.check_progress(self.state,CAT)
    def test_24_show_valid_file(self):self.assertTrue(h.prompt_path(IDX,'T06').is_file())
    def test_25_show_unknown_id(self):
        with self.assertRaises(h.InputError):h.prompt_path(IDX,'T05')
    def test_26_prompt_path_escape(self):
        bad=copy.deepcopy(IDX);bad['tasks'][0]['prompt']='../../outside.txt'
        with self.assertRaises(h.InputError):h.prompt_path(bad,'T06')
    def test_27_duplicate_json(self):
        p=self.project/'duplicate.json';p.write_text('{"tasks":{},"tasks":{}}')
        with self.assertRaises(h.InputError):h.load_json(p)
    def test_28_cli_preview_offline(self):
        p=subprocess.run([sys.executable,'-B',str(ROOT/'tools/prompt_helper.py'),'show','T06'],capture_output=True,text=True,timeout=10)
        self.assertEqual(p.returncode,0,p.stderr);self.assertIn('只读预览',p.stdout);self.assertIn('版本化课程导入',p.stdout)
    def test_29_reference_catalog_unchanged(self):
        before=(ROOT/'references/TASKS.original.json').read_bytes();self.select()
        self.assertEqual(before,(ROOT/'references/TASKS.original.json').read_bytes())
    def test_30_t33_human_gate_required(self):
        self.done('T31');self.done('T32')
        self.assertTrue(any('G_HUMAN_CONTENT_REVIEW' in x for x in h.blockers(task('T33'),self.state,self.project)))
    def test_31_t32_available_when_t31_blocked(self):
        for n in range(31):self.done(f'T{n:02d}')
        self.state['tasks']['T31']['status']='BLOCKED'
        self.assertEqual(self.select()['id'],'T32')
    def test_32_optional_preview_does_not_enable(self):
        self.assertTrue(h.prompt_path(IDX,'O01').is_file())
        self.assertEqual(self.state['tasks']['O01']['status'],'NOT_STARTED')

if __name__=='__main__':unittest.main(verbosity=2)
