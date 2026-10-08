"""Generate controlled live-engine fixtures for test_draft_broadcast.cjs.

Run with Python, then node test_draft_broadcast.cjs. No user save is read or changed.
"""
import json
from pathlib import Path
from test_draft_runtime import DraftRuntimeTests
from session import Session


def main():
    DraftRuntimeTests.setUpClass()
    session = Session.load(DraftRuntimeTests.initial)
    output = Path('outputs/draft-broadcast')
    output.mkdir(parents=True, exist_ok=True)

    def write(name, view):
        (output / (name + '.json')).write_text(json.dumps(view), encoding='utf-8')

    write('initial', session.draft_view('draft_day'))
    session.draft.auto = False
    for _ in range(4):
        session.draft.sim_pick()
    view = session.draft_view('draft_day')
    for row in view['order']:
        if row['done']:
            assert session.L.player(row['pid']).name == row['name']
    write('progress', view)
    restored = Session.load(session.save()).draft_view('draft_day')
    assert [(q['sel'], q.get('pid')) for q in view['order']] == [
        (q['sel'], q.get('pid')) for q in restored['order']]
    write('reload', restored)
    print('Real draft selections, drafted player identities, and save/reload board verified.')


if __name__ == '__main__':
    main()
