import copy,unittest
import numpy as np
import regression as R
from test_regression_aging import player
def previous_decline(p,rng):
 f=R.curve_factor(p.pos,p.age)
 if f>=1:return
 drop=(1-f)*.17/max(.35,p.longevity)*float(np.clip(rng.normal(1.,.35),.15,2.2))
 for k,v in list(p.ratings.items()):
  if k in R.UNTOUCHED:continue
  w=R.PHYS_WEIGHT.get(k,R.DEFAULT_PHYS);before=v
  if w>0:v*=1-drop*w*(.55 if k in R.PHYS_GROUP else 1.)
  if k in R.MENTAL_GROWS:v*=1+R.MENTAL_GAIN*drop*(1-2*w)
  p.ratings[k]=float(np.clip(v,min(20.,before),99.))
class AthleticAgingTests(unittest.TestCase):
 def test_bounded_and_never_faster_decline(self):
  for pos in ('HB','WR','TE','CB','FS','SS','QB','LT'):
   for age in range(22,42):
    for longevity in (.35,.6,1.,1.5,2.):
     a=player('a',pos,age);a.longevity=longevity;a.ratings.update(speed_rating=90.,accel_rating=90.)
     b=copy.deepcopy(a);ra=np.random.default_rng(7);rb=np.random.default_rng(7)
     previous_decline(a,ra);R.decline(b,rb)
     self.assertEqual(ra.bit_generator.state,rb.bit_generator.state)
     for k in a.ratings:
      if k in ('speed_rating','accel_rating'):
       self.assertGreaterEqual(b.ratings[k]+1e-10,a.ratings[k]);self.assertLessEqual(b.ratings[k],90.)
       self.assertLessEqual(90-b.ratings[k],2.25 if k=='accel_rating' else 2.)
      else:self.assertAlmostEqual(a.ratings[k],b.ratings[k],places=12)
 def test_steady_veteran_loss_and_prime(self):
  for pos in ('HB','WR','CB','TE'):
   losses=[R.athletic_loss(pos,a,1.,1.,'speed_rating',99) for a in range(22,41)]
   self.assertEqual(losses,sorted(losses));self.assertLessEqual(max(losses),2)
 def test_calendar_reference_age_controls_athletic_loss(self):
  current=player('current','HB',30.2)
  reference=copy.deepcopy(current);reference.age=38.2
  current_rng=np.random.default_rng(11);reference_rng=np.random.default_rng(11)
  R.decline(current,current_rng,age=38.2)
  R.decline(reference,reference_rng)
  self.assertEqual(current.ratings,reference.ratings)
  self.assertEqual(current_rng.bit_generator.state,reference_rng.bit_generator.state)
if __name__=='__main__':unittest.main()
