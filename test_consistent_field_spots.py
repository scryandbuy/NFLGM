import unittest
import ticker

class FieldSpots(unittest.TestCase):
    def coordinate(self, text, off, defense):
        if text == '50': return 50
        team, yards = text.rsplit(' ',1)
        return 100-int(yards) if team == off else int(yards)

    def test_reported_midfield_crossing(self):
        self.assertEqual(ticker._spot(64.5,'MIN','GB'),'MIN 36')
        self.assertEqual(ticker._spot(38.5,'MIN','GB'),'GB 38')
        self.assertEqual(ticker._display_gain(64.5,26),26)

    def test_narration_does_not_mutate_recorded_yards(self):
        from types import SimpleNamespace
        p=dict(type='complete',yardline=64.5,yards=26,down=2,ydstogo=10,clock=80)
        result=ticker.play_line(SimpleNamespace(player=lambda pid:None),p,'MIN','GB')
        self.assertIn('26 yards',result['text'])
        self.assertEqual(p['yards'],26)

    def test_touchdown_distance_matches_origin_in_both_directions(self):
        from types import SimpleNamespace
        league=SimpleNamespace(player=lambda pid:None)
        for off, defense in [('GB','CHI'),('CHI','GB')]:
            for spot in (77.5,22.5,49.5,50.5):
                shown=ticker.display_field_position(spot,off,defense)
                for kind in ('complete','run'):
                    play=dict(type=kind,yardline=spot,yards=spot,touchdown=True,down=1,ydstogo=10,clock=36)
                    line=ticker.play_line(league,play,off,defense)
                    self.assertIn(f'{shown} yards' if kind=='complete' else f'from the {shown}',line['text'])
                    self.assertEqual(play['yards'],spot)

    def test_integer_gains_and_penalties_reconcile_both_directions(self):
        for off,defense in [('MIN','GB'),('GB','MIN')]:
            for start in [25.5,49.5,50.5,64.5,75.5]:
                for gain in [-15,-5,0,5,10,20]:
                    finish=start-gain
                    if not 1<=finish<=99: continue
                    a=self.coordinate(ticker._spot(start,off,defense),off,defense)
                    b=self.coordinate(ticker._spot(finish,off,defense),off,defense)
                    self.assertEqual(a-b,ticker._display_gain(start,gain))
                    self.assertEqual(ticker._spot(finish,off,defense),ticker._spot(100-finish,defense,off))

if __name__=='__main__': unittest.main()
