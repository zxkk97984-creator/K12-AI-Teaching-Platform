from __future__ import annotations
import copy
import json
from pathlib import Path
import unittest
from validate_contracts import validate_teaching, validate_designer, schema_validate

ROOT = Path(__file__).resolve().parents[1]
def load(name):
    return json.loads((ROOT / "contracts" / "examples" / f"{name}.json").read_text(encoding="utf-8"))

class TeachingTests(unittest.TestCase):
    def setUp(self):
        self.req, self.resp = load("teaching-request"), load("teaching-response")
    def test_valid(self): validate_teaching(self.req, self.resp)
    def test_nullable_grade(self):
        self.req["learner"]["grade"] = None
        validate_teaching(self.req, self.resp)
    def test_null_action(self):
        self.resp["action"] = None
        validate_teaching(self.req, self.resp)
    def test_each_stage_boundary(self):
        for g, stage in [(1,"PRIMARY_LOWER"),(3,"PRIMARY_LOWER"),(4,"PRIMARY_UPPER"),(6,"PRIMARY_UPPER"),(7,"JUNIOR"),(9,"JUNIOR"),(10,"SENIOR"),(12,"SENIOR")]:
            with self.subTest(grade=g):
                self.req["learner"].update(grade=g,stage=stage)
                validate_teaching(self.req,self.resp)
    def test_bad_grades(self):
        for g in [0,13,"5",True]:
            with self.subTest(grade=g), self.assertRaises(Exception):
                self.req["learner"]["grade"] = g
                validate_teaching(self.req,self.resp)
    def test_stage_mismatch(self):
        self.req["learner"]["stage"] = "SENIOR"
        with self.assertRaises(Exception): validate_teaching(self.req,self.resp)
    def test_binding_keys(self):
        for key in ["request_id","lesson_session_id","base_revision","curriculum_revision"]:
            v=copy.deepcopy(self.resp);v[key]=99 if key=="base_revision" else "wrong"
            with self.subTest(key=key), self.assertRaises(Exception): validate_teaching(self.req,v)
    def test_unknown_top_field(self):
        self.resp["review_status"]="APPROVED"
        with self.assertRaises(Exception): validate_teaching(self.req,self.resp)
    def test_unauthorized_action(self):
        self.req["allowed_actions"]=[]
        with self.assertRaises(Exception): validate_teaching(self.req,self.resp)
    def test_unknown_action(self):
        self.resp["action"]={"type":"RUN_SHELL","command":"echo x"}
        with self.assertRaises(Exception): validate_teaching(self.req,self.resp)
    def test_unknown_animation(self):
        self.resp["action"]["resource_id"]="foreign"
        with self.assertRaises(Exception): validate_teaching(self.req,self.resp)
    def test_resource_not_in_allowlist(self):
        self.req["allowed_actions"].append("OPEN_RESOURCE")
        self.resp["action"]={"type":"OPEN_RESOURCE","resource_id":"foreign"}
        with self.assertRaises(Exception): validate_teaching(self.req,self.resp)
    def test_code_not_in_allowlist(self):
        self.req["allowed_actions"].append("OPEN_CODE_TASK")
        self.resp["action"]={"type":"OPEN_CODE_TASK","task_id":"foreign"}
        with self.assertRaises(Exception): validate_teaching(self.req,self.resp)
    def test_source_triplet(self):
        for key in ["source_id","revision","locator"]:
            v=copy.deepcopy(self.resp);v["source_refs"][0][key]="foreign"
            with self.subTest(key=key), self.assertRaises(Exception): validate_teaching(self.req,v)
    def test_evidence_foreign(self):
        self.resp["evidence_refs"]=["foreign"]
        with self.assertRaises(Exception): validate_teaching(self.req,self.resp)
    def test_model_cannot_complete(self):
        self.resp["phase_suggestion"]="COMPLETED"
        with self.assertRaises(Exception): validate_teaching(self.req,self.resp)
    def test_unallowed_phase(self):
        self.resp["phase_suggestion"]="PRACTICE"
        with self.assertRaises(Exception): validate_teaching(self.req,self.resp)
    def test_reply_budget(self):
        self.req["limits"]["max_reply_chars"]=80
        self.resp["message_markdown"]="文"*81
        with self.assertRaises(Exception): validate_teaching(self.req,self.resp)
    def test_quiz_valid(self):
        self.resp["action"]={"type":"OFFER_QUIZ","objective_ids":self.req["chapter"]["objective_ids"],"question_count":2,"difficulty":"EASY"}
        validate_teaching(self.req,self.resp)
    def test_quiz_bounds(self):
        valid={"type":"OFFER_QUIZ","objective_ids":self.req["chapter"]["objective_ids"],"question_count":2,"difficulty":"EASY"}
        for key,value in [("objective_ids",["foreign"]),("question_count",3),("difficulty","HARD")]:
            v=copy.deepcopy(self.resp);v["action"]={**valid,key:value}
            with self.subTest(key=key), self.assertRaises(Exception): validate_teaching(self.req,v)
    def test_code_without_facts(self):
        self.req["operation"]="CODE_FEEDBACK"
        with self.assertRaises(Exception): validate_teaching(self.req,self.resp)

class DesignerTests(unittest.TestCase):
    def setUp(self): self.req,self.resp=load("designer-request"),load("quiz-draft")
    def test_quiz_valid(self): validate_designer(self.req,self.resp)
    def test_wrong_binding(self):
        for key in ["request_id","chapter_id","curriculum_revision","stage"]:
            v=copy.deepcopy(self.resp);v[key]="SENIOR" if key=="stage" else "foreign"
            with self.subTest(key=key), self.assertRaises(Exception): validate_designer(self.req,v)
    def test_count(self):
        self.req["quiz_spec"]["count"]=2
        with self.assertRaises(Exception): validate_designer(self.req,self.resp)
    def test_false_review(self):
        self.resp["reviewer"]="AI批准"
        with self.assertRaises(Exception): validate_designer(self.req,self.resp)
    def test_wrong_answer_key(self):
        self.resp["questions"][0]["correct_answer"]="Z"
        with self.assertRaises(Exception): validate_designer(self.req,self.resp)
    def test_duplicate_option(self):
        self.resp["questions"][0]["options"][1]["key"]="A"
        with self.assertRaises(Exception): validate_designer(self.req,self.resp)
    def test_type_not_allowed(self):
        self.req["quiz_spec"]["question_types"]=["TRUE_FALSE"]
        with self.assertRaises(Exception): validate_designer(self.req,self.resp)
    def test_hint_count(self):
        self.resp["questions"][0]["hints"]=["only"]
        with self.assertRaises(Exception): validate_designer(self.req,self.resp)
    def test_source(self):
        self.resp["questions"][0]["source_refs"][0]["source_id"]="foreign"
        with self.assertRaises(Exception): validate_designer(self.req,self.resp)
    def test_objective(self):
        self.resp["questions"][0]["objective_id"]="foreign"
        with self.assertRaises(Exception): validate_designer(self.req,self.resp)
    def test_designer_operation_contract(self):
        self.req["operation"]="LESSON_PACKAGE_DRAFT"
        with self.assertRaises(Exception): schema_validate("designer-request",self.req)
    def test_package_valid(self): validate_designer(load("designer-package-request"),load("lesson-package-draft"))
    def test_package_fake_resource(self):
        v=load("lesson-package-draft");v["activities"][0]["suggested_resource_id"]="foreign"
        with self.assertRaises(Exception): validate_designer(load("designer-package-request"),v)
    def test_package_fake_production(self):
        v=load("lesson-package-draft");v["asset_requests"][0]["status"]="GENERATED"
        with self.assertRaises(Exception): validate_designer(load("designer-package-request"),v)
    def test_package_template(self):
        r=load("designer-package-request");r["lesson_spec"]["allowed_animation_templates"]=[]
        with self.assertRaises(Exception): validate_designer(r,load("lesson-package-draft"))
    def test_binary_search_unsorted(self):
        r=load("designer-package-request");r["lesson_spec"]["allowed_animation_templates"]=["BINARY_SEARCH"]
        v=load("lesson-package-draft");v["animation_specs"][0].update(template="BINARY_SEARCH",target=2)
        with self.assertRaises(Exception): validate_designer(r,v)
    def test_ordering_missing_item(self):
        self.req["quiz_spec"]["question_types"]=["ORDERING"]
        q=self.resp["questions"][0];q.pop("options");q.pop("correct_answer")
        q.update(type="ORDERING",items=[{"key":"a","text":"1"},{"key":"b","text":"2"},{"key":"c","text":"3"}],correct_order=["a","b"])
        with self.assertRaises(Exception): validate_designer(self.req,self.resp)

if __name__ == "__main__": unittest.main()
