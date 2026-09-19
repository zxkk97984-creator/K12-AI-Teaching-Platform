#!/usr/bin/env python3
"""Print a fixed paired task brief. Read-only; never dispatches or changes progress."""
from __future__ import annotations
import argparse, hashlib, json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def load_json(path: Path):
    def unique(pairs):
        out = {}
        for key, value in pairs:
            if key in out: raise ValueError('duplicate JSON key')
            out[key] = value
        return out
    return json.loads(path.read_text('utf-8'), object_pairs_hook=unique)

def read_brief(task_id: str, project: Path | None = None) -> str:
    if not re.fullmatch(r'(?:T(?:0[6-9]|[12][0-9]|3[0-3])|O0[1-4])', task_id):
        raise ValueError('Only T06–T33 and O01–O04 are in this continuation overlay.')
    index = load_json(ROOT / 'TASK_EXECUTION_INDEX.json')
    task = next(t for t in index['tasks'] if t['id'] == task_id)
    if project is not None:
        project = project.resolve(strict=True)
        catalog = project / '.rebuild-kit/TASKS.json'
        if load_json(catalog) != load_json(ROOT / 'references/TASKS.original.json'):
            raise ValueError('Local TASKS differs from referenced plan. Stop; do not overwrite it.')
        card = project / '.rebuild-kit' / task['card']
        expected = ROOT / 'references/original_cards' / f'{task_id}.md'
        if card.read_bytes() != expected.read_bytes():
            raise ValueError('Local task card changed. Reconcile explicitly before using this brief.')
    return (ROOT / task['brief']).read_text('utf-8')

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('task_id'); p.add_argument('--project', type=Path)
    a = p.parse_args()
    try:
        text = read_brief(a.task_id, a.project)
    except (ValueError, OSError, StopIteration, KeyError, TypeError) as e:
        print('FAIL: ' + str(e), file=sys.stderr); return 2
    print('查看材料不等于满足依赖或授权；本工具不派工、不修改progress、不调用Herdr或模型。\n')
    print(text)
    return 0
if __name__ == '__main__': raise SystemExit(main())
