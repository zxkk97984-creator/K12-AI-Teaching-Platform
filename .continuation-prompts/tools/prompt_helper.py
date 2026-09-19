#!/usr/bin/env python3
"""Read-only continuation prompt viewer. No API, database, shell or progress writes."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
from urllib.parse import urlsplit

PACKAGE = Path(__file__).resolve().parents[1]
STATUSES = {'NOT_STARTED', 'IN_PROGRESS', 'BLOCKED', 'DONE', 'FAILED'}
SEMANTIC_FIELDS = ('id','title','milestone','optional','depends_on','required_gates',
                   'read_files','card','allowed_project_paths','acceptance_ids')

class InputError(ValueError):
    pass


def no_duplicates(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise InputError('JSON中存在重复字段；先核对文件，不覆盖进度。')
        out[key] = value
    return out


def load_json(path: Path) -> dict:
    obj = json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=no_duplicates)
    if not isinstance(obj, dict):
        raise InputError('清单/进度必须为JSON对象。')
    return obj


def compare_catalog(actual: dict, reference: dict) -> None:
    if actual.get('target_root') != reference.get('target_root'):
        raise InputError('目标根目录与原包不一致；需核对合法变更，不能自动替换。')
    rows, refs = actual.get('tasks'), reference.get('tasks')
    if not isinstance(rows,list) or not isinstance(refs,list) or len(rows)!=len(refs):
        raise InputError('任务数量发生变化，先核对版本。')
    if len({t.get('id') for t in rows}) != len(rows):
        raise InputError('任务ID重复。')
    for a,b in zip(rows, refs):
        for field in SEMANTIC_FIELDS:
            if a.get(field) != b.get(field):
                raise InputError(f"任务语义不同：{b.get('id')} / {field}；先对齐已批准变更，不改回旧值。")


def check_progress(progress: dict, catalog: dict) -> None:
    if progress.get('target_root') != catalog.get('target_root'):
        raise InputError('实际progress与任务表目标不一致。')
    states, gates = progress.get('tasks'), progress.get('gates')
    if not isinstance(states,dict) or not isinstance(gates,dict):
        raise InputError('进度缺少tasks/gates对象。')
    for task in catalog['tasks']:
        value=states.get(task['id'])
        if not isinstance(value,dict) or value.get('status') not in STATUSES:
            raise InputError(f"{task['id']}进度缺失或状态非法。")
        if not isinstance(value.get('evidence',[]),list):
            raise InputError(f"{task['id']} evidence应为列表。")


def evidence_values(evidence: list) -> list[str]:
    values=[]
    for item in evidence:
        if isinstance(item,str) and item.strip():
            values.append(item.strip())
        elif isinstance(item,dict):
            for key in ('path','file','file_path','report','url'):
                value=item.get(key)
                if isinstance(value,str) and value.strip():
                    values.append(value.strip())
    return values


def usable_evidence(evidence: list, project: Path, *, allow_url: bool=False) -> bool:
    """Check one local report exists. This never certifies truth of its contents."""
    for value in evidence_values(evidence):
        parsed=urlsplit(value)
        if parsed.scheme in ('http','https'):
            if allow_url and parsed.hostname and not parsed.username and not parsed.password:
                return True  # Reference present only; Agent must verify relevance.
            continue
        if parsed.scheme:
            continue
        p=Path(value)
        if not p.is_absolute():
            p=project/p
        try:
            p=p.resolve()
            # External logs may be additional evidence, but at least one local
            # record should persist in project. Do not traverse arbitrary files.
            if p.is_relative_to(project.resolve()) and p.is_file() and p.stat().st_size>0:
                return True
        except OSError:
            continue
    return False


def blockers(task: dict, progress: dict, project: Path) -> list[str]:
    why=[]
    for dep in task['depends_on']:
        s=progress['tasks'].get(dep,{})
        if s.get('status')!='DONE':
            why.append(f'前置{dep}未DONE')
        elif not usable_evidence(s.get('evidence',[]),project):
            why.append(f'前置{dep}缺可定位的本地证据文件；需人工核对')
    for gate in task['required_gates']:
        s=progress['gates'].get(gate,{})
        if s.get('status')!='PASS':
            why.append(f'{gate}仍未PASS')
        elif not usable_evidence(s.get('evidence',[]),project,allow_url=True):
            why.append(f'{gate}缺可定位依据；需人工核对')
    return why


def select_next(catalog: dict, progress: dict, project: Path, prompt_ids: set[str]):
    eligible=[]
    for task in catalog['tasks']:
        state=progress['tasks'][task['id']]['status']
        if task['id'] not in prompt_ids or task['optional'] or state in ('DONE','BLOCKED'):
            continue
        if not blockers(task,progress,project):
            eligible.append(task)
    # Resume current work before starting another independent task.
    for state in ('IN_PROGRESS','FAILED'):
        match=next((t for t in eligible if progress['tasks'][t['id']]['status']==state),None)
        if match:
            return match
    return eligible[0] if eligible else None


def prompt_path(index: dict, task_id: str) -> Path:
    row=next((t for t in index['tasks'] if t['id']==task_id),None)
    if row is None:
        raise InputError('本包仅含T06—T33与O01—O04。')
    p=(PACKAGE/row['prompt']).resolve()
    if not p.is_relative_to(PACKAGE) or not p.is_file():
        raise InputError('Prompt路径不安全或文件缺失。')
    return p


def main() -> int:
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('action',choices=['next','show','status'])
    ap.add_argument('task',nargs='?')
    ap.add_argument('--project',type=Path,default=Path('/home/zxk/Projects/K12'))
    args=ap.parse_args()
    try:
        ref=load_json(PACKAGE/'references/TASKS.original.json')
        index=load_json(PACKAGE/'PROMPT_INDEX.json')
        if args.action=='show':
            if not args.task:
                raise InputError('show需要任务ID，例如 show T06。')
            print('【只读预览】本输出不证明当前依赖/门禁已满足，也不授权执行可选任务。\n')
            print(prompt_path(index,args.task).read_text(encoding='utf-8'))
            return 0
        if args.task:
            raise InputError('next/status不接受任务ID。')
        project=args.project.resolve()
        if project != Path(ref['target_root']).resolve():
            raise InputError('此续作包只对应/home/zxk/Projects/K12；不会对其他项目选任务。')
        if not project.is_dir():
            raise InputError('项目目录不在当前运行环境；请在你的电脑项目中运行next，或使用show查看Prompt。')
        catalog=load_json(project/'.rebuild-kit/TASKS.json')
        progress=load_json(project/'.rebuild-kit/progress.json')
        compare_catalog(catalog,ref)
        check_progress(progress,catalog)
        ids={t['id'] for t in index['tasks']}
        if args.action=='status':
            for task in catalog['tasks']:
                if task['id'] not in ids:continue
                state=progress['tasks'][task['id']]['status']
                reason=blockers(task,progress,project)
                if state=='BLOCKED':reason.insert(0,'本项仍BLOCKED，新证据到位后显式复核恢复，不自动重试')
                prefix='【可选，默认不执行】' if task['optional'] else ''
                print(f"{task['id']} [{state}] {prefix}{task['title']}"+((' | '+'；'.join(reason)) if reason else ''))
            return 0
        task=select_next(catalog,progress,project,ids)
        if task is None:
            print('目前没有可自动选择的核心任务。工具不会改进度或门禁；用status核对阻塞/证据，收到新条件后显式恢复。')
            return 2
        print('【只读选择】已检查进度标记与证据位置；仍须Agent读取证据、核对源码和授权范围。\n')
        print(prompt_path(index,task['id']).read_text(encoding='utf-8'))
        return 0
    except (InputError,OSError,ValueError,KeyError,TypeError) as exc:
        if isinstance(exc,InputError):
            print('未选择任务：'+str(exc),file=sys.stderr)
        else:
            print('读取或校验失败：'+type(exc).__name__+'；保留文件并核对原任务表/进度，不自动修复。',file=sys.stderr)
        return 2


if __name__=='__main__':
    raise SystemExit(main())
