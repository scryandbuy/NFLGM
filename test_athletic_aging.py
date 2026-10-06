import copy,unittest
import numpy as np
import regression as R
from test_regression_aging import player

def prior_bounded_loss(pos, age, longevity, roll, attr, old_loss):
 years=max(0,int(age)-R.plateau_end(pos))
 if not years:return 0.
 loss=min(1.8,.35+.22*(years-1))*float(np.clip(1/max(.35,longevity),.8,1.2))*float(np.clip(roll,.65,1.35))*(1.1 if attr=='accel_rating' else 1.)
 return min(max(0.,old_loss),loss,2.25 if attr=='accel_rating' else 2.)
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
 def test_targeted_curve_preserves_other_positions_and_never_exceeds_prior_bound(self):
  for pos in ('WR','CB','HB','FS','SS','QB','TE','LT'):
   for age in (24,27,29,31,34,38):
    for roll in (.15,.65,.7,.85,1.,1.35,2.2):
     for attr in ('speed_rating','accel_rating'):
      before=prior_bounded_loss(pos,age,.8,roll,attr,4.)
      after=R.athletic_loss(pos,age,.8,roll,attr,4.)
      self.assertGreaterEqual(after,0)
      self.assertLessEqual(after,before+1e-12)
      if pos not in ('WR','CB'):self.assertEqual(after,before)
 def test_flat_years_and_different_aging_paths(self):
  for pos in ('WR','CB'):
   for age in (28,31,34,36):
    self.assertEqual(R.athletic_loss(pos,age,.8,.6,'speed_rating',5.),0)
    ordinary=R.athletic_loss(pos,age,1.,1.,'speed_rating',5.)
    early=R.athletic_loss(pos,age,.7,1.3,'speed_rating',5.)
    durable=R.athletic_loss(pos,age,1.5,.9,'speed_rating',5.)
    self.assertLess(durable,ordinary)
    self.assertGreater(early,ordinary)
   self.assertLess(R.athletic_loss(pos,31,1.,1.,'speed_rating',5.),
                   R.athletic_loss(pos,36,1.,1.,'speed_rating',5.))
if __name__=='__main__':unittest.main()
