#!/usr/bin/env python3
"""Read-only check of the delivered plan overlay. Does not test the user's app."""
from pathlib import Path
import hashlib,json,re,sys
ROOT=Path(__file__).resolve().parents[1]

def main():
    checks=[]
    def check(name,ok):checks.append({'check':name,'result':'PASS' if ok else 'FAIL'})
    try:
        manifest=ROOT/'SHA256SUMS.txt'
        listed=set()
        for line in manifest.read_text('utf-8').splitlines():
            sha,rel=line.split('  ',1);p=ROOT/rel
            safe=not Path(rel).is_absolute() and '..' not in Path(rel).parts and not p.is_symlink()
            check('sha256 '+rel,safe and p.is_file() and hashlib.sha256(p.read_bytes()).hexdigest()==sha)
            listed.add(rel)
        actual={p.relative_to(ROOT).as_posix() for p in ROOT.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.name!='SHA256SUMS.txt'}
        check('manifest inventory matches',listed==actual)
        catalog=json.loads((ROOT/'references/TASKS.original.json').read_text('utf-8'))
        index=json.loads((ROOT/'TASK_EXECUTION_INDEX.json').read_text('utf-8'))
        check('original catalog hash',hashlib.sha256((ROOT/'references/TASKS.original.json').read_bytes()).hexdigest()==index['original_catalog_sha256'])
        originals={t['id']:t for t in catalog['tasks']}; active=set();done=set()
        def visit(t):
            if t in active or t not in originals:raise ValueError('Invalid dependency graph')
            if t in done:return
            active.add(t)
            for dep in originals[t]['depends_on']:visit(dep)
            active.remove(t);done.add(t)
        for t in originals:visit(t)
        check('38 original tasks acyclic',len(done)==38)
        check('32 paired task briefs',len(index['tasks'])==32 and len({t['id'] for t in index['tasks']})==32)
        for t in index['tasks']:
            i=t['id']; original=originals[i]
            check(i+' frozen task metadata',all(t[k]==v for k,v in original.items()))
            brief=(ROOT/t['brief']).read_text('utf-8')
            check(i+' implementation and review brief',all(x in brief for x in ['B实施步骤','A独立复核重点','交接与判定']))
            for rel in ['references/continuation/'+i+'.txt','references/original_cards/'+i+'.md']:
                check(i+' reference '+rel,(ROOT/rel).is_file())
        check('no replacement progress or runtime control',not any(p.name=='progress.json' for p in ROOT.rglob('*')) and not (ROOT/'.herdr-control').exists())
        for p in (ROOT/'templates').glob('*.example.json'):
            data=json.loads(p.read_text('utf-8'))
            check(p.name+' parse/example-only',p.name=='scope.example.json' or data.get('example_only') is True)
        check('eight stage specifications',all((ROOT/f'milestones/M{i}.md').is_file() for i in range(8)))
        failures=sum(r['result']=='FAIL' for r in checks)
        print(json.dumps({'scope':'DELIVERY_ONLY_NOT_APP_TESTS','checks':len(checks),'passed':len(checks)-failures,'failed':failures,'results':checks},ensure_ascii=False,indent=2))
        return 1 if failures else 0
    except Exception as e:
        print('PACKAGE CHECK ERROR: '+str(e),file=sys.stderr);return 2
if __name__=='__main__':raise SystemExit(main())
