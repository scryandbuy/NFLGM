"""
WEATHER AND THE BUILDING.

Every game is played somewhere in some month. Domes have no weather. The
rest draw temperature, precipitation and wind from the home city's climate
for that month, and the conditions can turn at the half. The building itself
adds two things: crowd noise, which costs the road team false starts and
slows its in-game adjustments in the loud houses, and altitude in Denver,
which taxes the road team's stamina.

Effects are multipliers the engine reads from one ENV object set at
kickoff (plays.ENV, game.ENV): drops, fumbles, deep completion, kick range,
punt distance, run lean, the road team's pre-snap flags and adjustment
speed, and stamina cost.

Real anchors: NFL 2013-2024 by month, rain in about 9% of outdoor games and
snow in about 3% (mostly December and January, in the cold cities); wind
over 15 mph in about 12% of outdoor games; a 40+ yard kick made about 8
points less often in 15+ mph wind or hard rain; drop rate about 1.4x in
rain and 1.7x in snow; fumbles about 1.3x in rain; passing depth falls
about 0.4 air yards in heavy weather.
"""
import numpy as np

# dome or fixed roof: no weather at all
DOMES = {'ARI', 'ATL', 'DAL', 'DET', 'HOU', 'IND', 'LV', 'LA', 'MIN', 'NO'}

# monthly climate by home club: (mean high F for Sep..Jan, rain chance Sep..Jan,
# snow chance Nov..Jan, wind chance of 15+ mph). Stadiums with retractable
# roofs are in DOMES above because they close in weather.
CLIMATE = {
    'BUF': dict(temp=(70, 57, 46, 34, 30), rain=(.10, .11, .12, .06, .05), snow=(.06, .22, .28), wind=.20),
    'GB':  dict(temp=(70, 56, 41, 28, 24), rain=(.09, .09, .09, .03, .02), snow=(.07, .20, .25), wind=.16),
    'CHI': dict(temp=(73, 60, 46, 34, 31), rain=(.09, .09, .09, .04, .03), snow=(.05, .17, .22), wind=.22),
    'CLE': dict(temp=(72, 60, 48, 37, 33), rain=(.10, .10, .12, .06, .05), snow=(.05, .18, .24), wind=.18),
    'PIT': dict(temp=(73, 61, 49, 38, 35), rain=(.10, .10, .11, .07, .06), snow=(.03, .12, .18), wind=.12),
    'NE':  dict(temp=(72, 61, 50, 40, 36), rain=(.10, .11, .11, .09, .08), snow=(.03, .12, .18), wind=.16),
    'NYJ': dict(temp=(75, 64, 53, 43, 39), rain=(.10, .10, .10, .08, .07), snow=(.02, .08, .12), wind=.14),
    'NYG': dict(temp=(75, 64, 53, 43, 39), rain=(.10, .10, .10, .08, .07), snow=(.02, .08, .12), wind=.14),
    'PHI': dict(temp=(77, 66, 55, 45, 41), rain=(.10, .09, .09, .07, .06), snow=(.02, .07, .11), wind=.12),
    'BAL': dict(temp=(79, 67, 56, 46, 42), rain=(.10, .09, .09, .07, .06), snow=(.01, .05, .09), wind=.10),
    'WAS': dict(temp=(80, 68, 57, 47, 43), rain=(.10, .09, .09, .07, .06), snow=(.01, .05, .08), wind=.10),
    'CIN': dict(temp=(78, 65, 52, 41, 37), rain=(.09, .09, .10, .07, .06), snow=(.02, .09, .14), wind=.10),
    'KC':  dict(temp=(80, 67, 53, 41, 38), rain=(.09, .09, .08, .04, .03), snow=(.03, .10, .14), wind=.16),
    'DEN': dict(temp=(78, 65, 52, 44, 45), rain=(.06, .05, .04, .02, .02), snow=(.10, .16, .16), wind=.14),
    'SEA': dict(temp=(70, 60, 51, 46, 47), rain=(.14, .24, .34, .36, .34), snow=(.01, .04, .05), wind=.08),
    'SF':  dict(temp=(72, 71, 64, 58, 58), rain=(.02, .05, .16, .22, .24), snow=(0, 0, 0), wind=.14),
    'LAC': dict(temp=(78, 74, 69, 64, 65), rain=(.01, .03, .06, .10, .12), snow=(0, 0, 0), wind=.06),
    'TEN': dict(temp=(83, 72, 59, 49, 46), rain=(.08, .08, .10, .09, .09), snow=(.01, .04, .07), wind=.08),
    'JAX': dict(temp=(86, 79, 71, 64, 63), rain=(.16, .10, .07, .06, .07), snow=(0, 0, 0), wind=.08),
    'MIA': dict(temp=(88, 85, 80, 76, 75), rain=(.20, .16, .10, .07, .06), snow=(0, 0, 0), wind=.10),
    'TB':  dict(temp=(89, 84, 78, 72, 70), rain=(.20, .10, .06, .06, .06), snow=(0, 0, 0), wind=.08),
    'CAR': dict(temp=(83, 73, 63, 54, 51), rain=(.09, .08, .08, .08, .08), snow=(0, .02, .04), wind=.06),
    'NO':  dict(temp=(87, 79, 70, 63, 62), rain=(.14, .09, .09, .10, .10), snow=(0, 0, 0), wind=.06),
    'LV':  dict(temp=(95, 82, 67, 57, 58), rain=(.02, .02, .02, .03, .03), snow=(0, 0, 0), wind=.10),
}
DEFAULT_CLIMATE = dict(temp=(75, 63, 52, 42, 40), rain=(.09, .09, .09, .07, .06), snow=(.02, .08, .12), wind=.12)

# the loud houses: crowd noise costs the road team (false-start multiplier,
# adjustment delay in plays). Anchored on 2-point real home edge, more here.
NOISE = {'KC': 1.35, 'SEA': 1.35, 'NO': 1.30, 'BUF': 1.25, 'DEN': 1.20, 'GB': 1.20, 'PHI': 1.20, 'BAL': 1.15,
         'MIN': 1.15, 'LV': 1.05, 'DAL': 1.10, 'PIT': 1.15, 'CIN': 1.10, 'CLE': 1.10, 'JAX': 1.05, 'LAC': 1.00, 'LA': 1.00}
ALTITUDE = {'DEN': 1.06}     # stamina cost multiplier on the road team

WEEK_MONTH = lambda week: 0 if week <= 4 else 1 if week <= 8 else 2 if week <= 13 else 3 if week <= 17 else 4


class Env:
    """Conditions for one game, and the multipliers the engine reads."""
    def __init__(self, home='', week=1, dome=False, temp=70, rain=0.0, snow=0.0, wind=0.0, noise=1.0, altitude=1.0):
        self.home, self.week, self.dome = home, week, dome
        self.temp, self.rain, self.snow, self.wind = temp, rain, snow, wind   # rain/snow 0..1 intensity, wind mph
        self.noise, self.altitude = noise, altitude
        self.turned = None            # what changed at the half, if anything
        self.compute()

    def compute(self):
        wet = self.rain + 1.4 * self.snow
        self.drop_mult = 1.0 + 0.40 * self.rain + 0.70 * self.snow
        self.fumble_mult = 1.0 + 0.30 * self.rain + 0.35 * self.snow
        self.deep_mult = 1.0 - 0.10 * wet - 0.012 * max(0.0, self.wind - 10.0)
        self.kick_mult = 1.0 - 0.06 * wet - 0.009 * max(0.0, self.wind - 10.0) - (0.03 if self.temp < 32 else 0.0)
        self.punt_mult = 1.0 - 0.04 * wet - 0.010 * max(0.0, self.wind - 10.0)
        self.run_lean = 0.06 * wet + 0.004 * max(0.0, self.wind - 10.0)   # added to the run share
        self.road_false_start = self.noise
        self.road_adjust_delay = 1.0 + 0.6 * (self.noise - 1.0)
        self.road_stamina = self.altitude

    def turn(self, rng, home_abbr):
        """The half: weather moves. Rain builds or clears, snow starts or stops."""
        if self.dome: return
        m = WEEK_MONTH(self.week); c = CLIMATE.get(home_abbr, DEFAULT_CLIMATE)
        before = self.describe()
        r = rng.random()
        if self.rain > 0 and r < 0.35: self.rain = 0.0
        elif self.snow > 0 and r < 0.30: self.snow = 0.0
        elif self.rain == 0 and self.snow == 0 and m >= 2 and r < 0.6 * (c['snow'][m - 2] if m >= 2 else 0): self.snow = float(rng.uniform(0.4, 1.0))
        elif self.rain == 0 and self.snow == 0 and r < 0.5 * c['rain'][m]: self.rain = float(rng.uniform(0.3, 1.0))
        self.wind = float(np.clip(self.wind + rng.normal(0, 3), 0, 35))
        self.compute()
        after = self.describe()
        if after != before: self.turned = (before, after)

    def describe(self):
        if self.dome: return 'dome'
        parts = []
        if self.snow >= 0.6: parts.append('heavy snow')
        elif self.snow > 0: parts.append('snow')
        elif self.rain >= 0.7: parts.append('heavy rain')
        elif self.rain > 0: parts.append('rain')
        if self.wind >= 20: parts.append(f'wind {self.wind:.0f} mph')
        elif self.wind >= 15: parts.append('breezy')
        if self.temp <= 20: parts.append(f'{self.temp:.0f}°F, bitter')
        elif self.temp <= 32: parts.append(f'{self.temp:.0f}°F, freezing')
        elif self.temp >= 90: parts.append(f'{self.temp:.0f}°F, hot')
        return ', '.join(parts) if parts else f'clear, {self.temp:.0f}°F'

    def to_dict(self):
        return dict(home=self.home, week=self.week, dome=self.dome, temp=round(self.temp), rain=round(self.rain, 2), snow=round(self.snow, 2),
                    wind=round(self.wind), noise=self.noise, altitude=self.altitude, conditions=self.describe(), turned=self.turned)


def draw(home_abbr, week, rng, neutral=False):
    """Conditions at kickoff for a game in this building this week."""
    if home_abbr in DOMES:
        return Env(home_abbr, week, dome=True, temp=70, noise=NOISE.get(home_abbr, 1.0) if not neutral else 1.0)
    m = WEEK_MONTH(week); c = CLIMATE.get(home_abbr, DEFAULT_CLIMATE)
    temp = float(rng.normal(c['temp'][m], 7))
    rain = snow = 0.0
    if m >= 2 and rng.random() < 1.7 * c['snow'][m - 2] and temp < 42:
        snow = float(rng.uniform(0.3, 1.0))
    elif rng.random() < c['rain'][m]:
        rain = float(rng.uniform(0.3, 1.0))
    wind = float(abs(rng.normal(8, 5)))
    if rng.random() < c['wind']: wind = float(rng.uniform(15, 28))
    return Env(home_abbr, week, dome=False, temp=temp, rain=rain, snow=snow, wind=wind,
               noise=1.0 if neutral else NOISE.get(home_abbr, 1.0), altitude=1.0 if neutral else ALTITUDE.get(home_abbr, 1.0))


CLEAR = Env('', 1, dome=True)
