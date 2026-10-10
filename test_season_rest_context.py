import unittest
from types import SimpleNamespace as N
from season_rest_context import contexts


def fixture():
    teams = {'Z': N(conf='Other', division='Other Solo')}
    schedule = []
    for d, wins in enumerate(((14,12,0,0),(11,9,0,0),(8,6,0,0),(4,0,0,0))):
        for i, count in enumerate(wins):
            a = f'{d}{i}'
            teams[a] = N(conf='Test', division=f'Test {d}')
            schedule.extend((w+1,a,'Z',20 if w<count else 0,10) for w in range(16))
            schedule.append((18,a,'Z',None,None))
    return N(teams=teams,schedule=schedule)


class SeasonRestContextTests(unittest.TestCase):
    def test_locked_division_and_wildcard_seeds(self):
        got=contexts(fixture(),18)
        self.assertEqual(got['00'],dict(mode='locked',week=18,seed=1))
        self.assertEqual(got['01'],dict(mode='locked',week=18,seed=5))
        self.assertEqual(got['21'],dict(mode='locked',week=18,seed=7))
        self.assertEqual(got['02']['mode'],'eliminated')

    def test_possible_tie_does_not_lock_seed(self):
        league=fixture()
        # Give the second division leader enough remaining games to tie #1.
        league.schedule.extend((18,'10','Z',None,None) for _ in range(3))
        self.assertIsNone(contexts(league,18)['00']['mode'])

    def test_early_season_and_playoffs_disabled(self):
        for got in (contexts(fixture(),14),contexts(fixture(),19,True)):
            self.assertTrue(all(v['mode'] is None for v in got.values()))

    def test_schedule_not_stale_team_record(self):
        league=fixture()
        for t in league.teams.values(): t.record=[17,0,0]
        self.assertEqual(contexts(league,18)['02']['mode'],'eliminated')

    def test_context_survives_state_snapshot_and_old_snapshot_clears(self):
        from season import SeasonRunner
        from test_coaching_perspective import state
        st=state()
        st.season_rest=dict(mode='locked', week=18, seed=2)
        saved=SeasonRunner._state_data(st)
        other=state()
        SeasonRunner._restore_state(other,saved)
        self.assertEqual(other.season_rest,st.season_rest)
        other.season_rest['seed']=3
        self.assertEqual(saved['season_rest']['seed'],2)
        del saved['season_rest']
        SeasonRunner._restore_state(other,saved)
        self.assertEqual(other.season_rest,{})

    def test_no_results_no_elimination_or_locks(self):
        league=fixture()
        league.schedule=[(w,a,h,None,None) for w,a,h,ap,hp in league.schedule]
        self.assertTrue(all(v['mode'] is None for v in contexts(league,18).values()))


if __name__=='__main__': unittest.main()

