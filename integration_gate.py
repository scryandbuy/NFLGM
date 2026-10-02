"""Detect source-branch or worktree changes between integration review and bundling.

Usage from the integration checkout:
  python integration_gate.py snapshot outputs/integration-sources.json
  python integration_gate.py verify outputs/integration-sources.json --ledger integration_source_ledger.json

The snapshot records branch tips, unmatched source commits, and hashes of every
modified or untracked file in the other worktrees. Verification fails when any
source changes after review or a commit lacks an explicit disposition. It also
checks that the integration branch contains the current GitHub main commit.
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
    unique_commits = {}
    for branch in refs:
        for row in git('cherry', '-v', target, branch).splitlines():
            if row.startswith('+ '):
                _, sha, subject = row.split(' ', 2)
                unique_commits.setdefault(sha, {'subject': subject, 'branches': []})['branches'].append(branch)
    return {'target_branch': target, 'source_refs': refs,
            'source_worktrees': checkouts, 'unique_commits': unique_commits}


def verify_ledger(commits, ledger_path):
    if not ledger_path:
        raise SystemExit('A source commit ledger is required for verification.')
    short_ledger = json.loads(ledger_path.read_text(encoding='utf-8'))
    ledger = {}
    for prefix, record in short_ledger.items():
        matches = [sha for sha in commits if sha.startswith(prefix)]
        if len(matches) != 1:
            raise SystemExit(f'Ledger prefix {prefix!r} matches {len(matches)} source commits.')
        ledger[matches[0]] = record
    missing = sorted(set(commits) - set(ledger))
    stale = sorted(set(ledger) - set(commits))
    invalid = []
    for sha, record in ledger.items():
        if record.get('status') not in ('integrated', 'superseded', 'generated') or not record.get('reason'):
            invalid.append(sha)
            continue
        incorporated = record.get('incorporated_as')
        if record['status'] == 'integrated':
            if not incorporated or subprocess.run(['git', 'merge-base', '--is-ancestor', incorporated, 'HEAD']).returncode:
                invalid.append(sha)
    if missing or stale or invalid:
        print(f'Unreviewed commits: {missing}')
        print(f'Stale ledger entries: {stale}')
        print(f'Invalid dispositions: {invalid}')
        raise SystemExit(1)
    print(f'Source ledger passed: {len(commits)} unmatched source commits reviewed.')


def verify_upstream(ref, url):
    try:
        upstream = git('rev-parse', '--verify', ref + '^{commit}')
    except subprocess.CalledProcessError as exc:
        raise SystemExit(f'Fetch GitHub main into {ref} before verifying.') from exc
    if subprocess.run(['git', 'merge-base', '--is-ancestor', upstream, 'HEAD']).returncode:
        raise SystemExit(f'Integration branch does not contain {ref} ({upstream[:12]}).')
    try:
        remote = git('-c', 'http.sslBackend=openssl', 'ls-remote', url, 'refs/heads/main')
    except subprocess.CalledProcessError as exc:
        raise SystemExit('Could not check current GitHub main; release verification is incomplete.') from exc
    rows = [line.split()[0] for line in remote.splitlines() if line.strip()]
    if len(rows) != 1 or rows[0] != upstream:
        raise SystemExit(f'GitHub main changed: fetched {upstream[:12]}, current {rows[0][:12] if rows else "missing"}.')
    print(f'GitHub main ancestry passed: {upstream[:12]} is in the integration branch.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('snapshot', 'verify'))
    parser.add_argument('path', type=Path)
    parser.add_argument('--target', default='codex/complete-integration-20260930')
    parser.add_argument('--ledger', type=Path)
    parser.add_argument('--upstream-ref', default='refs/remotes/github/main')
    parser.add_argument('--upstream-url', default='https://github.com/scryandbuy/NFLGM.git')
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
        for section in ('source_refs', 'source_worktrees', 'unique_commits'):
            before, after = expected.get(section, {}), actual.get(section, {})
            changed = sorted(key for key in set(before) | set(after) if before.get(key) != after.get(key))
            if changed:
                print(f'{section} changed since review:')
                for key in changed:
                    print(f'  {key}: {str(before.get(key))[:100]} -> {str(after.get(key))[:100]}')
        raise SystemExit(1)
    verify_ledger(actual['unique_commits'], args.ledger)
    verify_upstream(args.upstream_ref, args.upstream_url)
    print('Integration gate passed: no source branch or worktree changed since review.')


if __name__ == '__main__':
    main()
