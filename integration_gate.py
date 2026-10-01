"""Detect source-branch or worktree changes between integration review and bundling.

Usage from the integration checkout:
  python integration_gate.py snapshot outputs/integration-sources.json
  python integration_gate.py verify outputs/integration-sources.json

The snapshot is taken only after reviewing each source branch's commits. This
gate catches new commits, modified files, and untracked files after that review;
it does not substitute for deciding which source changes belong in the build.
"""

import argparse
import hashlib
import json
import subprocess
from pathlib import Path


def git(*args, cwd=None):
    return subprocess.check_output(['git', *args], cwd=cwd, text=True).strip()


def worktrees():
    result = []
    current = {}
    for line in git('worktree', 'list', '--porcelain').splitlines() + ['']:
        if not line:
            if current.get('worktree'):
                result.append(current)
            current = {}
        elif ' ' in line:
            key, value = line.split(' ', 1)
            current[key] = value
    return result


def file_hash(path):
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def inventory(target):
    refs = {}
    for line in git('for-each-ref', '--format=%(refname:short) %(objectname)', 'refs/heads').splitlines():
        name, sha = line.split(' ', 1)
        if name != target:
            refs[name] = sha
    checkouts = {}
    for item in worktrees():
        root = Path(item['worktree'])
        if not root.is_dir() or item.get('branch') == 'refs/heads/' + target:
            continue
        names = subprocess.check_output(
            ['git', 'ls-files', '-m', '-d', '-o', '--exclude-standard', '-z'], cwd=root
        ).decode('utf-8').split('\0')
        checkouts[str(root)] = {
            'head': git('rev-parse', 'HEAD', cwd=root),
            'files': {name: file_hash(root / name) for name in names if name},
        }
    return {'target_branch': target, 'source_refs': refs, 'source_worktrees': checkouts}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('snapshot', 'verify'))
    parser.add_argument('path', type=Path)
    parser.add_argument('--target', default='codex/post-study-integration-20260930')
    args = parser.parse_args()
    if git('branch', '--show-current') != args.target:
        parser.error('Run this from the integration branch.')
    if git('status', '--porcelain'):
        parser.error('The integration checkout has uncommitted or untracked files.')
    actual = inventory(args.target)
    if args.mode == 'snapshot':
        args.path.parent.mkdir(parents=True, exist_ok=True)
        args.path.write_text(json.dumps(actual, indent=2, sort_keys=True) + '\n', encoding='utf-8')
        print(f'Source snapshot saved: {len(actual["source_refs"])} branches, '
              f'{len(actual["source_worktrees"])} worktrees.')
        return
    expected = json.loads(args.path.read_text(encoding='utf-8'))
    if actual != expected:
        for section in ('source_refs', 'source_worktrees'):
            before, after = expected.get(section, {}), actual.get(section, {})
            changed = sorted(key for key in set(before) | set(after) if before.get(key) != after.get(key))
            if changed:
                print(f'{section} changed since review:')
                for key in changed:
                    print(f'  {key}: {str(before.get(key))[:100]} -> {str(after.get(key))[:100]}')
        raise SystemExit(1)
    print('Integration gate passed: no source branch or worktree changed since review.')


if __name__ == '__main__':
    main()
