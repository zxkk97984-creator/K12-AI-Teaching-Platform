import copy
import json
from pathlib import Path
import unittest
import task_prompt

ROOT=Path(__file__).resolve().parents[1]

class TaskSchedulingTests(unittest.TestCase):
    def setUp(self):
        self.catalog=json.loads((ROOT/"TASKS.json").read_text(encoding="utf-8"))
        self.progress=json.loads((ROOT/"progress.json").read_text(encoding="utf-8"))
        self.tasks={x["id"]:x for x in self.catalog["tasks"]}
    def mark_deps(self,tid):
        for dep in self.tasks[tid]["depends_on"]:
            self.progress["tasks"][dep].update(status="DONE",evidence=["synthetic-test-report-only"])
    def test_initial_task_ready(self):self.assertEqual(task_prompt.blockers(self.tasks["T00"],self.progress),[])
    def test_dependency_blocks(self):self.assertTrue(task_prompt.blockers(self.tasks["T01"],self.progress))
    def test_done_without_evidence_blocks(self):
        self.progress["tasks"]["T00"]["status"]="DONE"
        self.assertTrue(task_prompt.blockers(self.tasks["T01"],self.progress))
    def test_api_gate_blocks_live(self):
        self.mark_deps("T11")
        result=task_prompt.blockers(self.tasks["T11"],self.progress)
        self.assertEqual(len(result),2)
    def test_offline_task_not_blocked_by_live_gates(self):
        self.mark_deps("T12")
        self.assertEqual(task_prompt.blockers(self.tasks["T12"],self.progress),[])
    def test_pass_without_gate_evidence_blocks(self):
        self.mark_deps("T11")
        for gate in self.tasks["T11"]["required_gates"]:self.progress["gates"][gate]["status"]="PASS"
        self.assertEqual(len(task_prompt.blockers(self.tasks["T11"],self.progress)),2)

if __name__=="__main__":unittest.main()
