import unittest
import ticker

class FieldSpots(unittest.TestCase):
    def coordinate(self, text, off, defense):
        if text == '50': return 50
        team, yards = text.rsplit(' ',1)
        return 100-int(yards) if team == off else int(yards)

    def test_reported_midfield_crossing(self):
        self.assertEqual(ticker._spot(64.5,'MIN','GB'),'MIN 36')
        self.assertEqual(ticker._spot(38.5,'MIN','GB'),'GB 39')
        self.assertEqual(ticker._display_gain(64.5,26),25)

    def test_narration_does_not_mutate_recorded_yards(self):
        from types import SimpleNamespace
        p=dict(type='complete',yardline=64.5,yards=26,down=2,ydstogo=10,clock=80)
        result=ticker.play_line(SimpleNamespace(player=lambda pid:None),p,'MIN','GB')
        self.assertIn('25 yards',result['text'])
        self.assertEqual(p['yards'],26)

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
