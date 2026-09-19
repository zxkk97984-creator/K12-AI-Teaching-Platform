#!/usr/bin/env python3
"""Validate delivery files only. Does not inspect or mutate the K12 application."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT=Path(__file__).resolve().parents[1]

def main() -> int:
    checks=[]
    def test(name, fn):
        try:
            if not fn():
                raise ValueError(name)
            checks.append({'check':name,'status':'PASS'})
        except Exception as exc:
            checks.append({'check':name,'status':'FAIL','error':type(exc).__name__})
    def read(path):return json.loads((ROOT/path).read_text(encoding='utf-8'))
    index=read('PROMPT_INDEX.json')
    ref=read('references/TASKS.original.json')
    source=read('references/SOURCE_MANIFEST.json')
    rows=index['tasks']; original={t['id']:t for t in ref['tasks']}
    expected={f'T{i:02d}' for i in range(6,34)}|{f'O{i:02d}' for i in range(1,5)}
    test('32个后续ID无缺漏/重复',lambda:len(rows)==32 and {t['id'] for t in rows}==expected)
    test('28核心与4可选',lambda:sum(not t['optional'] for t in rows)==28 and sum(t['optional'] for t in rows)==4)
    for row in rows:
        ident=row['id']; origin=original[ident]
        test(ident+'元数据与原任务一致',lambda r=row,o=origin:all(r[k]==o[k] for k in ('id','title','optional','depends_on','required_gates','acceptance_ids')) and r['original_card']==o['card'])
        path=ROOT/row['prompt']; card=ROOT/'references/task_cards'/f'{ident}.md'
        test(ident+'完整Prompt包含原卡与续作补充',lambda p=path,c=card:p.is_file() and c.read_text(encoding='utf-8').strip() in p.read_text(encoding='utf-8') and '本次续作补充' in p.read_text(encoding='utf-8'))
        test(ident+'原卡hash未改变',lambda c=card,r=row:hashlib.sha256(c.read_bytes()).hexdigest()==r['original_card_sha256']==source['source_cards'][r['id']])
    test('原TASKS逐字hash一致',lambda:hashlib.sha256((ROOT/'references/TASKS.original.json').read_bytes()).hexdigest()==source['source_task_catalog_sha256']==index['source_catalog_sha256'])
    def safe_paths():
        for row in rows:
            p=(ROOT/row['prompt']).resolve()
            if not p.is_relative_to(ROOT) or not p.is_file():return False
        return True
    test('所有Prompt路径安全可读',safe_paths)
    test('不携带覆盖用progress或根.env',lambda:not any(p.name in ('progress.json','.env','TASKS.json') for p in ROOT.rglob('*') if p.is_file()))
    combined=(ROOT/'全部任务Prompt_合订本.md').read_text(encoding='utf-8')
    test('合订本覆盖全部32份原样Prompt',lambda:all((ROOT/t['prompt']).read_text(encoding='utf-8').strip() in combined for t in rows))
    test('入口与公共约束文件存在',lambda:all((ROOT/p).is_file() for p in ('START_HERE.txt','COMMON_RULES.md','CURRENT_CHECKPOINT.md','TASK_OVERVIEW.md','README_使用说明.md')))
    test('全部Python语法可编译',lambda:all(compile(p.read_text(encoding='utf-8'),str(p),'exec') is not None for p in ROOT.rglob('*.py')))
    def checksum_check():
        manifest=ROOT/'SHA256SUMS.txt'
        if not manifest.is_file():return False
        listed=set()
        for line in manifest.read_text(encoding='utf-8').splitlines():
            digest,rel=line.split('  ',1)
            p=(ROOT/rel).resolve()
            if not p.is_relative_to(ROOT) or not p.is_file():return False
            if hashlib.sha256(p.read_bytes()).hexdigest()!=digest:return False
            listed.add(rel)
        actual={p.relative_to(ROOT).as_posix() for p in ROOT.rglob('*') if p.is_file() and p.name!='SHA256SUMS.txt' and '__pycache__' not in p.parts}
        return listed==actual
    test('独立包SHA256清单覆盖并匹配',checksum_check)
    fail=sum(c['status']=='FAIL' for c in checks)
    print(json.dumps({'scope':'PROMPT_PACKAGE_ONLY_NOT_APP_OR_KNODO','checks':len(checks),'passed':len(checks)-fail,'failed':fail,'results':checks},ensure_ascii=False,indent=2))
    return 1 if fail else 0

if __name__=='__main__':raise SystemExit(main())
