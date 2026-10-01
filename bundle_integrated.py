"""Verify the reviewed source snapshot, rebuild, test, and bundle one release."""
import argparse
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def run(*args):
    subprocess.run(args, cwd=ROOT, check=True)


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT, text=True).strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bundle', type=Path)
    parser.add_argument('--snapshot', type=Path, required=True)
    parser.add_argument('--ledger', type=Path, default=ROOT / 'integration_source_ledger.json')
    args = parser.parse_args()
    branch = git('branch', '--show-current')
    if branch != 'codex/complete-integration-20260930':
        parser.error(f'Wrong integration branch: {branch}')
    if git('status', '--porcelain'):
        parser.error('Commit or account for every change in this checkout first.')
    run(sys.executable, 'integration_gate.py', 'verify', str(args.snapshot),
        '--ledger', str(args.ledger))
    run(sys.executable, 'build_web.py')
    if git('status', '--porcelain'):
        parser.error('The browser build changed tracked assets; commit and review it first.')
    run(sys.executable, '-m', 'unittest', 'test_defensive_returns',
        'test_defensive_return_ui', 'test_defensive_return_register',
        'test_practice_integration', 'test_extension_cap_view')
    run('node', '--check', 'docs/app.js')
    for test in sorted(ROOT.glob('test_*.cjs')):
        run('node', test.name)
    run(sys.executable, 'integration_gate.py', 'verify', str(args.snapshot),
        '--ledger', str(args.ledger))
    if git('status', '--porcelain'):
        parser.error('Checkout changed during release checks.')
    output = args.bundle.resolve()
    if output.exists():
        parser.error(f'Bundle already exists: {output}')
    output.parent.mkdir(parents=True, exist_ok=True)
    run('git', 'bundle', 'create', str(output), f'refs/heads/{branch}')
    run('git', 'bundle', 'verify', str(output))
    print(f'Ready: {output}\nBranch: {branch}\nCommit: {git("rev-parse", "--short", "HEAD")}')


if __name__ == '__main__':
    main()
