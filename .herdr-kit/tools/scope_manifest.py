#!/usr/bin/env python3
"""Bounded read-only source hashing. Prints JSON; never edits files or restores code.

Not a security boundary. It detects scoped file changes under an agreed freeze.
The caller must exclude unrelated work and use a safe new output path.
"""
from __future__ import annotations
import argparse, hashlib, json, os, sys
from pathlib import Path, PurePosixPath

SKIP_DIRS = {'.git','.venv','venv','node_modules','__pycache__','.pytest_cache','.ruff_cache',
 '.mypy_cache','.cache','.next','dist','build','coverage','test-results','playwright-report',
 '.snapshots','.herdr-control','.herdr-kit','.continuation-prompts','.rebuild-kit',
 'storage','logs','.agents','.codex'}
SKIP_FILES = {'.env','id_rsa','id_ed25519','credentials.json','secrets.json','auth.json',
 'cookies.json','cookies.txt','storage-state.json','.DS_Store'}

def safe_relative(text: str) -> PurePosixPath:
    rel = PurePosixPath(text)
    if not text or rel.is_absolute() or '..' in rel.parts or '\\' in text or rel == PurePosixPath('.'):
        raise ValueError('Scope paths must be explicit project-relative paths without traversal.')
    return rel

def excluded(path: Path) -> bool:
    return (bool(set(path.parts) & SKIP_DIRS) or path.name in SKIP_FILES
        or path.name.startswith('.env.') or path.suffix in {'.pem','.key','.p12','.pfx','.db','.sqlite','.sqlite3','.pyc','.log'}
        or path.name.endswith('.tsbuildinfo'))

def capture(root: Path, paths: list[str], limits: dict | None = None) -> dict:
    if root.is_symlink(): raise ValueError('Project root itself must not be a symlink.')
    root = root.resolve(strict=True)
    if not root.is_dir() or not paths: raise ValueError('A project directory and explicit nonempty scope are required.')
    lim = {'max_files':15000,'max_file_bytes':33554432,'max_total_bytes':536870912}
    if limits:
        if set(limits) - set(lim): raise ValueError('Unknown limit.')
        lim.update(limits)
    if any(isinstance(v,bool) or not isinstance(v,int) or v <= 0 for v in lim.values()):
        raise ValueError('Limits must be positive integers.')
    allfiles: dict[str, Path] = {}; skips = set()
    for text in paths:
        rel = safe_relative(text); p = root / str(rel)
        for i in range(1, len(rel.parts)+1):
            if (root / Path(*rel.parts[:i])).is_symlink(): raise ValueError('Symlink in explicit scope path.')
        if excluded(Path(str(rel))): raise ValueError('Explicit scope includes a excluded secret/runtime path.')
        if not p.exists(): raise ValueError('Explicit scope path missing: '+str(rel))
        if p.is_file(): allfiles[str(rel)] = p
        elif p.is_dir():
            for dirpath, dirs, files in os.walk(p, followlinks=False):
                current = Path(dirpath)
                for d in list(dirs):
                    f = current/d; r=f.relative_to(root)
                    if excluded(r): dirs.remove(d); skips.add(str(r)); continue
                    if f.is_symlink(): raise ValueError('Unexcluded symlink directory in source scope.')
                for name in files:
                    f=current/name; r=f.relative_to(root)
                    if excluded(r): skips.add(str(r)); continue
                    if f.is_symlink(): raise ValueError('Unexcluded symlink file in source scope.')
                    if not f.is_file(): raise ValueError('Non-regular entry in source scope.')
                    allfiles[str(r)] = f
        else: raise ValueError('Unsupported source entry.')
    if len(allfiles)>lim['max_files']: raise ValueError('File-count limit exceeded.')
    total = 0; records = {}
    for rel,f in sorted(allfiles.items()):
        before = f.stat(); total += before.st_size
        if before.st_size > lim['max_file_bytes'] or total > lim['max_total_bytes']:
            raise ValueError('Byte limit exceeded. Narrow or explicitly revise scope limits.')
        h=hashlib.sha256()
        with f.open('rb') as stream:
            for block in iter(lambda:stream.read(1024*1024),b''): h.update(block)
        after = f.stat()
        if (before.st_size,before.st_mtime_ns,before.st_ino)!=(after.st_size,after.st_mtime_ns,after.st_ino):
            raise ValueError('Source changed during capture; acquire a stable handoff.')
        records[rel]={'bytes':before.st_size,'sha256':h.hexdigest()}
    canonical=json.dumps(records,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()
    return {'schema_version':'k12.source-scope.v1','project_realpath':str(root),'scope':paths,
            'limits':lim,'files':records,'content_manifest_sha256':hashlib.sha256(canonical).hexdigest(),
            'excluded_paths':sorted(skips),'notice':'Scoped byte comparison, not test/quality/authorization proof.'}

def compare(root: Path, manifest: dict) -> dict:
    if manifest.get('schema_version')!='k12.source-scope.v1': raise ValueError('Unknown manifest schema.')
    if str(root.resolve(strict=True))!=manifest['project_realpath']: raise ValueError('Project root differs.')
    before=manifest['files']
    canonical=json.dumps(before,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()
    if hashlib.sha256(canonical).hexdigest()!=manifest['content_manifest_sha256']:
        raise ValueError('Manifest internal hash mismatch.')
    after=capture(root,manifest['scope'],manifest['limits'])['files']
    changed=sorted(k for k in before.keys() & after.keys() if before[k]!=after[k])
    added=sorted(after.keys()-before.keys());removed=sorted(before.keys()-after.keys())
    return {'unchanged':not(changed or added or removed),'modified':changed,'added':added,'removed':removed}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=['capture','verify'])
    p.add_argument('--root',type=Path,required=True);p.add_argument('--scope',type=Path);p.add_argument('--manifest',type=Path)
    a=p.parse_args()
    try:
        if a.mode=='capture':
            if a.scope is None: raise ValueError('capture requires --scope')
            spec=json.loads(a.scope.read_text('utf-8'));result=capture(a.root,spec['paths'],spec.get('limits'))
            code=0
        else:
            if a.manifest is None: raise ValueError('verify requires --manifest')
            result=compare(a.root,json.loads(a.manifest.read_text('utf-8')));code=0 if result['unchanged'] else 1
        print(json.dumps(result,ensure_ascii=False,indent=2));return code
    except (ValueError,OSError,KeyError,TypeError) as e:
        print('FAIL: '+str(e),file=sys.stderr);return 2
if __name__=='__main__':raise SystemExit(main())
