"""
THE IDENTITY CATALOG, 2026.

One entry per club: the man in charge (coach and GM fused, since the game
makes them one), what he runs, how he calls it, and how he builds. Drawn
from the 2026 staffs (Wikipedia coordinator lists, Sep 2026), early-2026
tendency data (Sharp Football: coverage, blitz, box, personnel, weeks 1-2)
and the coaching trees and roster records behind them (RotoPat's 2026 GM
rankings and the public record). Where the staff is new in 2026 the tendency
is the man's tree and his last stop, marked 'projected'.

Every axis is on the scale the engine uses, so a GM object can be built
straight from an entry, and the 30 men in the coaching pool and every
newgen are blends of these.

AXES
  offence
    blocking      'zone' | 'gap' | 'mixed'        the run scheme
    personnel     '11' | '12' | '13' | '21' | 'multiple'   the base grouping
    pass_lean     0..1   run-heavy .. pass-heavy, neutral .50
    play_action   0..1   how much of the pass game is PA
    motion        0..1
    tempo         0..1   slow .. fast
    deep          0..1   deep-ball appetite
    fourth_down   0..1   go-for-it appetite
  defence
    front         '4-3' | '3-4' | 'multiple'      one-gap, two-gap, both
    coverage      0..1   zone .. man
    shell         0..1   single-high .. two-high
    blitz         0..1
    box           0..1   light .. heavy
  roster (the GM dials that already exist, 0..1)
    youth, pick_lens, contract_focus, risk, patience, aggression,
    dev_belief, board_trust, need_inflation, restructure_depth, scouting
  tags            the words a commentator would use
  confidence      'known' | 'projected'
"""

CATALOG = {
 'ARI': dict(coach='Mike LaFleur', gm='Monti Ossenfort', tree='McVay/Shanahan',
   offence=dict(blocking='zone', personnel='11', pass_lean=.52, play_action=.55, motion=.65, tempo=.5, deep=.5, fourth_down=.5),
   defence=dict(front='4-3', coverage=.05, shell=.75, blitz=.25, box=.4),        # Rallis: Gannon's two-high zone
   roster=dict(youth=.6, pick_lens=.5, contract_focus=.5, risk=.5, patience=.4, aggression=.45, dev_belief=.5, board_trust=.55, need_inflation=.5, restructure_depth=.4, scouting=.4),
   tags=['premium positions early', 'talent-poor roster', 'hot seat', 'Love at 3'], confidence='projected'),
 'ATL': dict(coach='Kevin Stefanski', gm='Ian Cunningham', tree='Shanahan wide zone / Eagles front office',
   offence=dict(blocking='zone', personnel='12', pass_lean=.45, play_action=.7, motion=.5, tempo=.35, deep=.45, fourth_down=.5),
   defence=dict(front='4-3', coverage=.2, shell=.4, blitz=.25, box=.45),          # Ulbrich
   roster=dict(youth=.55, pick_lens=.35, contract_focus=.6, risk=.5, patience=.55, aggression=.55, dev_belief=.55, board_trust=.7, need_inflation=.4, restructure_depth=.5, scouting=.6),
   tags=['new regime', 'Roseman-school analytics', 'methodical offence', 'Matt Ryan president'], confidence='projected'),
 'BAL': dict(coach='Jesse Minter', gm='Eric DeCosta', tree='Macdonald/Harbaugh defence',
   offence=dict(blocking='mixed', personnel='12', pass_lean=.48, play_action=.6, motion=.55, tempo=.5, deep=.5, fourth_down=.65),
   defence=dict(front='multiple', coverage=.2, shell=.7, blitz=.35, box=.3),       # disguise, two-high, sim pressure
   roster=dict(youth=.6, pick_lens=.3, contract_focus=.7, risk=.4, patience=.8, aggression=.4, dev_belief=.7, board_trust=.85, need_inflation=.25, restructure_depth=.4, scouting=.8),
   tags=['draft and develop', 'trades down', 'compensatory picks', 'trenches', 'patient', 'never short-handed'], confidence='projected'),
 'BUF': dict(coach='Joe Brady', gm='Brandon Beane', tree='Bills offence / Fangio defence (Leonhard)',
   offence=dict(blocking='zone', personnel='multiple', pass_lean=.55, play_action=.45, motion=.5, tempo=.55, deep=.55, fourth_down=.6),
   defence=dict(front='4-3', coverage=.15, shell=.65, blitz=.3, box=.4),
   roster=dict(youth=.4, pick_lens=.7, contract_focus=.35, risk=.6, patience=.35, aggression=.75, dev_belief=.45, board_trust=.5, need_inflation=.7, restructure_depth=.85, scouting=.5),
   tags=['aggressive trader', 'over-the-hill pass rushers', 'cap gymnastics', 'win-now around Allen'], confidence='projected'),
 'CAR': dict(coach='Dave Canales', gm='Dan Morgan', tree='Shanahan/Carroll offence, Fangio defence (Evero)',
   offence=dict(blocking='zone', personnel='11', pass_lean=.48, play_action=.6, motion=.5, tempo=.45, deep=.45, fourth_down=.45),
   defence=dict(front='3-4', coverage=.08, shell=.65, blitz=.45, box=.35),
   roster=dict(youth=.5, pick_lens=.55, contract_focus=.4, risk=.5, patience=.55, aggression=.6, dev_belief=.55, board_trust=.5, need_inflation=.6, restructure_depth=.5, scouting=.5),
   tags=['spends in free agency on defence', 'first-rounders on offence for the QB', 'building around a question at QB'], confidence='known'),
 'CHI': dict(coach='Ben Johnson', gm='Ryan Poles', tree='Detroit offence / Dennis Allen defence',
   offence=dict(blocking='mixed', personnel='12', pass_lean=.52, play_action=.7, motion=.8, tempo=.5, deep=.6, fourth_down=.75),
   defence=dict(front='4-3', coverage=.6, shell=.35, blitz=.55, box=.4),          # man 40%, blitz 35%
   roster=dict(youth=.55, pick_lens=.45, contract_focus=.55, risk=.5, patience=.5, aggression=.55, dev_belief=.55, board_trust=.6, need_inflation=.5, restructure_depth=.45, scouting=.55),
   tags=['motion and play-action', 'aggressive on fourth down', 'offensive line spending', 'man-coverage defence'], confidence='known'),
 'CIN': dict(coach='Zac Taylor', gm='Duke Tobin', tree='McVay offence',
   offence=dict(blocking='zone', personnel='11', pass_lean=.62, play_action=.4, motion=.45, tempo=.5, deep=.6, fourth_down=.5),
   defence=dict(front='multiple', coverage=.4, shell=.45, blitz=.2, box=.3),       # Golden
   roster=dict(youth=.5, pick_lens=.6, contract_focus=.7, risk=.35, patience=.5, aggression=.4, dev_belief=.45, board_trust=.55, need_inflation=.55, restructure_depth=.3, scouting=.5),
   tags=['no guarantees', 'cheap free agency', 'average drafting', 'win-now with Burrow', 'owner in the room'], confidence='known'),
 'CLE': dict(coach='Todd Monken', gm='Andrew Berry', tree='Ravens/Georgia offence',
   offence=dict(blocking='zone', personnel='11', pass_lean=.55, play_action=.5, motion=.5, tempo=.6, deep=.65, fourth_down=.55),
   defence=dict(front='4-3', coverage=.3, shell=.4, blitz=.2, box=.6),            # Rutenberg
   roster=dict(youth=.6, pick_lens=.25, contract_focus=.5, risk=.5, patience=.55, aggression=.5, dev_belief=.6, board_trust=.7, need_inflation=.35, restructure_depth=.6, scouting=.55),
   tags=['analytics room', 'draft volume', 'trades', 'placeholder quarterbacks', 'Watson hangover'], confidence='projected'),
 'DAL': dict(coach='Brian Schottenheimer', gm='Jerry & Stephen Jones', tree='Cowboys offence / Fangio defence (Parker)',
   offence=dict(blocking='mixed', personnel='11', pass_lean=.6, play_action=.4, motion=.45, tempo=.5, deep=.55, fourth_down=.5),
   defence=dict(front='4-3', coverage=.2, shell=.55, blitz=.5, box=.35),
   roster=dict(youth=.45, pick_lens=.6, contract_focus=.3, risk=.55, patience=.4, aggression=.45, dev_belief=.45, board_trust=.55, need_inflation=.5, restructure_depth=.7, scouting=.55),
   tags=['stars and scrubs', 'late extensions', 'quiet in free agency', 'owner-GM', 'alienate half the core, overpay the other'], confidence='known'),
 'DEN': dict(coach='Sean Payton', gm='George Paton', tree='Saints offence / Vance Joseph defence',
   offence=dict(blocking='mixed', personnel='11', pass_lean=.55, play_action=.55, motion=.6, tempo=.5, deep=.5, fourth_down=.6),
   defence=dict(front='3-4', coverage=.35, shell=.5, blitz=.7, box=.55),          # blitz 45%, heavy box
   roster=dict(youth=.3, pick_lens=.8, contract_focus=.3, risk=.6, patience=.2, aggression=.8, dev_belief=.35, board_trust=.35, need_inflation=.8, restructure_depth=.9, scouting=.5),
   tags=['veteran-laden', 'built in free agency', 'trades picks', 'restructures', 'lives in the now'], confidence='known'),
 'DET': dict(coach='Dan Campbell', gm='Brad Holmes', tree='Lions culture / Petzing heavy offence / Glenn defence',
   offence=dict(blocking='gap', personnel='12', pass_lean=.48, play_action=.6, motion=.6, tempo=.5, deep=.5, fourth_down=.85),
   defence=dict(front='4-3', coverage=.35, shell=.45, blitz=.5, box=.25),         # light box 63%, blitz 32%
   roster=dict(youth=.55, pick_lens=.45, contract_focus=.5, risk=.55, patience=.6, aggression=.6, dev_belief=.6, board_trust=.75, need_inflation=.35, restructure_depth=.45, scouting=.7),
   tags=['character and toughness', 'trenches', 'trades up for his guys', 'most aggressive fourth-down team'], confidence='known'),
 'GB': dict(coach='Matt LaFleur', gm='Brian Gutekunst', tree='Shanahan wide zone / Gannon two-high',
   offence=dict(blocking='zone', personnel='12', pass_lean=.5, play_action=.7, motion=.6, tempo=.5, deep=.5, fourth_down=.5),
   defence=dict(front='4-3', coverage=.08, shell=.85, blitz=.4, box=.45),         # man 8%, middle open 77%
   roster=dict(youth=.8, pick_lens=.4, contract_focus=.75, risk=.3, patience=.9, aggression=.2, dev_belief=.7, board_trust=.8, need_inflation=.3, restructure_depth=.25, scouting=.7),
   tags=['draft volume', 'youth', 'rarely spends in free agency', 'depth over stars', 'Parsons the exception'], confidence='known'),
 'HOU': dict(coach='DeMeco Ryans', gm='Nick Caserio', tree='Shanahan-tree offence (Caley) / Ryans one-gap defence',
   offence=dict(blocking='zone', personnel='11', pass_lean=.52, play_action=.55, motion=.55, tempo=.5, deep=.5, fourth_down=.5),
   defence=dict(front='4-3', coverage=.15, shell=.25, blitz=.15, box=.55),        # zone 79%, middle closed 78%, blitz 16%
   roster=dict(youth=.5, pick_lens=.5, contract_focus=.55, risk=.5, patience=.5, aggression=.7, dev_belief=.5, board_trust=.6, need_inflation=.5, restructure_depth=.5, scouting=.65),
   tags=['wheeler dealer on draft weekend', 'extends early', 'solid across the board', 'Stroud question'], confidence='known'),
 'IND': dict(coach='Shane Steichen', gm='Chris Ballard', tree='Eagles RPO offence / Anarumo defence',
   offence=dict(blocking='zone', personnel='11', pass_lean=.5, play_action=.45, motion=.5, tempo=.55, deep=.5, fourth_down=.55),
   defence=dict(front='multiple', coverage=.85, shell=.35, blitz=.7, box=.6),      # man 47%, blitz 45%
   roster=dict(youth=.6, pick_lens=.4, contract_focus=.6, risk=.4, patience=.7, aggression=.35, dev_belief=.6, board_trust=.7, need_inflation=.35, restructure_depth=.35, scouting=.6),
   tags=['draft and develop', 'free-agency averse', 'no franchise quarterback', 'the Gardner gamble', 'shadow zone'], confidence='known'),
 'JAX': dict(coach='Liam Coen', gm='James Gladstone', tree='McVay/Rams offence and front office',
   offence=dict(blocking='zone', personnel='12', pass_lean=.5, play_action=.65, motion=.7, tempo=.5, deep=.5, fourth_down=.55),
   defence=dict(front='4-3', coverage=.25, shell=.55, blitz=.3, box=.2),          # light box, low blitz
   roster=dict(youth=.6, pick_lens=.25, contract_focus=.5, risk=.7, patience=.6, aggression=.7, dev_belief=.6, board_trust=.3, need_inflation=.4, restructure_depth=.4, scouting=.4),
   tags=['off the consensus board', 'trades up (Hunter)', 'Rams-school long view', 'ego after 13 wins'], confidence='known'),
 'KC': dict(coach='Andy Reid', gm='Brett Veach', tree='Reid spread / Spagnuolo pressure',
   offence=dict(blocking='mixed', personnel='12', pass_lean=.58, play_action=.45, motion=.7, tempo=.5, deep=.5, fourth_down=.6),
   defence=dict(front='4-3', coverage=.4, shell=.5, blitz=.5, box=.35),           # Spagnuolo: disguise and pressure
   roster=dict(youth=.5, pick_lens=.6, contract_focus=.35, risk=.6, patience=.45, aggression=.75, dev_belief=.55, board_trust=.55, need_inflation=.55, restructure_depth=.85, scouting=.6),
   tags=['aggressive trader', 'cap restructures', 'champagne problems', 'defence in the draft', 'receivers a weakness'], confidence='known'),
 'LV': dict(coach='Klint Kubiak', gm='John Spytek', tree='Shanahan/Kubiak wide zone',
   offence=dict(blocking='zone', personnel='21', pass_lean=.45, play_action=.75, motion=.55, tempo=.4, deep=.45, fourth_down=.45),   # 2-RB 52%, fullback
   defence=dict(front='4-3', coverage=.15, shell=.5, blitz=.15, box=.35),         # Leonard: Graham tree, low blitz
   roster=dict(youth=.55, pick_lens=.5, contract_focus=.5, risk=.5, patience=.5, aggression=.55, dev_belief=.5, board_trust=.5, need_inflation=.5, restructure_depth=.5, scouting=.5),
   tags=['second try', 'Brady owner-legend', 'under-centre run game', 'Crosby situation'], confidence='projected'),
 'LAC': dict(coach='Jim Harbaugh', gm='Joe Hortiz', tree='Harbaugh power / McDaniel motion / Minter two-high (O\'Leary)',
   offence=dict(blocking='gap', personnel='21', pass_lean=.45, play_action=.6, motion=.7, tempo=.45, deep=.45, fourth_down=.55),  # 2-RB 35%
   defence=dict(front='3-4', coverage=.15, shell=.7, blitz=.3, box=.45),
   roster=dict(youth=.55, pick_lens=.45, contract_focus=.7, risk=.35, patience=.7, aggression=.3, dev_belief=.6, board_trust=.75, need_inflation=.3, restructure_depth=.3, scouting=.7),
   tags=['methodical', 'trenches', 'the 53rd man matters', 'cheap free agency', 'coach\'s people in the building'], confidence='known'),
 'LAR': dict(coach='Sean McVay', gm='Les Snead', tree='McVay',
   offence=dict(blocking='zone', personnel='13', pass_lean=.55, play_action=.7, motion=.7, tempo=.5, deep=.55, fourth_down=.55),   # 13 personnel 38%
   defence=dict(front='3-4', coverage=.1, shell=.6, blitz=.15, box=.15),          # Shula: two-high, blitz 11%, light box
   roster=dict(youth=.5, pick_lens=.2, contract_focus=.5, risk=.7, patience=.5, aggression=.75, dev_belief=.6, board_trust=.6, need_inflation=.35, restructure_depth=.6, scouting=.7),
   tags=['firsts for stars (McDuffie)', 'days two and three drafting', 'too smart for their own good', 'changes his mind fast on offence'], confidence='known'),
 'MIA': dict(coach='Jeff Hafley', gm='Jon-Eric Sullivan', tree='Packers defence / Shanahan offence (Slowik)',
   offence=dict(blocking='zone', personnel='21', pass_lean=.48, play_action=.6, motion=.7, tempo=.5, deep=.5, fourth_down=.5),     # 2-RB 30%
   defence=dict(front='4-3', coverage=.25, shell=.35, blitz=.3, box=.65),         # heavy box 45%
   roster=dict(youth=.75, pick_lens=.4, contract_focus=.7, risk=.35, patience=.8, aggression=.25, dev_belief=.65, board_trust=.75, need_inflation=.3, restructure_depth=.3, scouting=.65),
   tags=['Green Bay chill', 'draft and develop', 'wholesale reset', 'Packers model'], confidence='projected'),
 'MIN': dict(coach="Kevin O'Connell", gm='Nolan Teasley', tree='McVay offence / Flores pressure',
   offence=dict(blocking='zone', personnel='multiple', pass_lean=.55, play_action=.6, motion=.65, tempo=.5, deep=.6, fourth_down=.55),   # 21/22 36%
   defence=dict(front='3-4', coverage=.02, shell=.6, blitz=1.0, box=.55),         # blitz 74%, zone behind it, disguise
   roster=dict(youth=.55, pick_lens=.55, contract_focus=.55, risk=.45, patience=.65, aggression=.45, dev_belief=.6, board_trust=.65, need_inflation=.4, restructure_depth=.6, scouting=.75),
   tags=['scouting background after the data guy', 'Seattle model', 'consensus-building', 'Flores blitzes everyone'], confidence='projected'),
 'NE': dict(coach='Mike Vrabel', gm='Eliot Wolf', tree='Vrabel/Titans physical / Packers front office',
   offence=dict(blocking='mixed', personnel='12', pass_lean=.5, play_action=.55, motion=.5, tempo=.45, deep=.5, fourth_down=.5),
   defence=dict(front='3-4', coverage=.3, shell=.55, blitz=.7, box=.45),          # blitz 44%, sub 92%
   roster=dict(youth=.5, pick_lens=.5, contract_focus=.5, risk=.5, patience=.5, aggression=.65, dev_belief=.55, board_trust=.65, need_inflation=.55, restructure_depth=.45, scouting=.6),
   tags=['free-agency spending spree on defence 2025', 'right coach changes everything', 'scandal risk on the sideline'], confidence='known'),
 'NO': dict(coach='Kellen Moore', gm='Mickey Loomis', tree='Eagles/Cowboys offence / Fangio-Staley defence',
   offence=dict(blocking='zone', personnel='11', pass_lean=.58, play_action=.45, motion=.6, tempo=.7, deep=.5, fourth_down=.55),
   defence=dict(front='3-4', coverage=.02, shell=.3, blitz=.25, box=.4),          # Staley
   roster=dict(youth=.4, pick_lens=.6, contract_focus=.2, risk=.5, patience=.6, aggression=.45, dev_belief=.45, board_trust=.6, need_inflation=.5, restructure_depth=1.0, scouting=.55),
   tags=['void years and restructures', 'loyalty', 'short on young talent', 'offensive-minded coach, thin defence'], confidence='known'),
 'NYG': dict(coach='John Harbaugh', gm='Joe Schoen (Harbaugh has final say)', tree='Ravens',
   offence=dict(blocking='gap', personnel='21', pass_lean=.42, play_action=.6, motion=.5, tempo=.4, deep=.5, fourth_down=.7),     # 2-RB 51%, 22 personnel 20%
   defence=dict(front='multiple', coverage=.35, shell=.75, blitz=.25, box=.4),      # Wilson
   roster=dict(youth=.55, pick_lens=.4, contract_focus=.55, risk=.45, patience=.6, aggression=.5, dev_belief=.6, board_trust=.7, need_inflation=.4, restructure_depth=.45, scouting=.65),
   tags=['former Ravens everywhere', 'run-first, fullback and two backs', 'coach with personnel power', 'Reese and Mauigoa'], confidence='projected'),
 'NYJ': dict(coach='Aaron Glenn', gm='Darren Mougey', tree='Lions defence / Reich offence',
   offence=dict(blocking='mixed', personnel='12', pass_lean=.5, play_action=.5, motion=.45, tempo=.45, deep=.45, fourth_down=.45),
   defence=dict(front='4-3', coverage=.3, shell=.55, blitz=.4, box=.1),           # light box 78%, sub 90%
   roster=dict(youth=.4, pick_lens=.6, contract_focus=.4, risk=.55, patience=.3, aggression=.6, dev_belief=.45, board_trust=.45, need_inflation=.7, restructure_depth=.6, scouting=.45),
   tags=['most desperate situation in the league', 'veteran quarterback stopgap', 'systemic rot', 'seat hot'], confidence='known'),
 'PHI': dict(coach='Nick Sirianni', gm='Howie Roseman', tree='Eagles RPO / Fangio two-high',
   offence=dict(blocking='mixed', personnel='11', pass_lean=.45, play_action=.5, motion=.6, tempo=.5, deep=.5, fourth_down=.7),   # 11 personnel 75%, run with Barkley, tush push
   defence=dict(front='4-3', coverage=.35, shell=.7, blitz=.35, box=.25),         # Fangio: light box 57%
   roster=dict(youth=.55, pick_lens=.2, contract_focus=.6, risk=.55, patience=.6, aggression=.7, dev_belief=.6, board_trust=.8, need_inflation=.3, restructure_depth=.75, scouting=.9),
   tags=['best drafter in the league', 'trenches', 'extends early', 'pays up for stars in trades', 'never wallows in a mistake', 'void years'], confidence='known'),
 'PIT': dict(coach='Mike McCarthy', gm='Omar Khan', tree='West Coast / Patrick Graham defence',
   offence=dict(blocking='zone', personnel='11', pass_lean=.55, play_action=.45, motion=.5, tempo=.45, deep=.5, fourth_down=.4),
   defence=dict(front='multiple', coverage=.0, shell=.55, blitz=.05, box=.4),      # zone 100%, blitz 8% early
   roster=dict(youth=.35, pick_lens=.65, contract_focus=.7, risk=.3, patience=.5, aggression=.35, dev_belief=.45, board_trust=.6, need_inflation=.55, restructure_depth=.35, scouting=.6),
   tags=['the Steeler Way', 'organisation over any one man', 'never blew it up', 'now win-now for a 42-year-old'], confidence='projected'),
 'SF': dict(coach='Kyle Shanahan', gm='John Lynch', tree='Shanahan',
   offence=dict(blocking='zone', personnel='21', pass_lean=.47, play_action=.75, motion=.85, tempo=.5, deep=.5, fourth_down=.5),   # 2-RB 52%, fullback
   defence=dict(front='4-3', coverage=.1, shell=.5, blitz=.15, box=.5),           # Morris
   roster=dict(youth=.45, pick_lens=.35, contract_focus=.4, risk=.65, patience=.5, aggression=.7, dev_belief=.45, board_trust=.25, need_inflation=.4, restructure_depth=.6, scouting=.4),
   tags=['ignores the consensus board', 'AI in the draft room', 'buys proven veterans (McCaffrey, Williams)', 'play-caller first, personnel second'], confidence='known'),
 'SEA': dict(coach='Mike Macdonald', gm='John Schneider', tree='Macdonald defence / Shanahan offence (Fleury)',
   offence=dict(blocking='zone', personnel='21', pass_lean=.5, play_action=.65, motion=.6, tempo=.5, deep=.5, fourth_down=.55),   # 2-RB 32%
   defence=dict(front='multiple', coverage=.05, shell=.8, blitz=.35, box=.15),      # zone 92%, two-high, sim pressure, light box
   roster=dict(youth=.6, pick_lens=.35, contract_focus=.55, risk=.6, patience=.6, aggression=.7, dev_belief=.65, board_trust=.85, need_inflation=.3, restructure_depth=.5, scouting=.85),
   tags=['bold', 'trusts his board', 'empowers the coach', 'draft volume', 'champions'], confidence='known'),
 'TB': dict(coach='Todd Bowles', gm='Jason Licht', tree='Bowles pressure',
   offence=dict(blocking='zone', personnel='11', pass_lean=.55, play_action=.45, motion=.5, tempo=.55, deep=.5, fourth_down=.5),    # 11 personnel 84%
   defence=dict(front='3-4', coverage=.5, shell=.3, blitz=.75, box=.4),           # man 30%, blitz 46%, sub 73%
   roster=dict(youth=.45, pick_lens=.55, contract_focus=.6, risk=.4, patience=.6, aggression=.35, dev_belief=.5, board_trust=.7, need_inflation=.4, restructure_depth=.5, scouting=.65),
   tags=['solid drafter', 'extends his own', 'few splashes', 'ageing defence', 'needs something big'], confidence='known'),
 'TEN': dict(coach='Robert Saleh', gm='Mike Borgonzi', tree='Saleh one-gap / Daboll spread',
   offence=dict(blocking='zone', personnel='11', pass_lean=.55, play_action=.45, motion=.5, tempo=.55, deep=.5, fourth_down=.5),    # 3+ WR 84%
   defence=dict(front='4-3', coverage=.1, shell=.45, blitz=.3, box=.55),          # zone 83%, wide-9
   roster=dict(youth=.6, pick_lens=.5, contract_focus=.5, risk=.5, patience=.5, aggression=.6, dev_belief=.55, board_trust=.55, need_inflation=.55, restructure_depth=.45, scouting=.5),
   tags=['rebuild', 'free-agency spree for a young QB', 'coach and GM from different searches'], confidence='projected'),
 'WAS': dict(coach='Dan Quinn', gm='Adam Peters', tree='Quinn multiple / Kingsbury-tree spread (Blough)',
   offence=dict(blocking='zone', personnel='11', pass_lean=.58, play_action=.4, motion=.55, tempo=.6, deep=.55, fourth_down=.65),  # 3+ WR 73%
   defence=dict(front='4-3', coverage=.1, shell=.75, blitz=.55, box=.3),          # blitz 36%, middle open 67%
   roster=dict(youth=.45, pick_lens=.6, contract_focus=.4, risk=.7, patience=.35, aggression=.8, dev_belief=.5, board_trust=.55, need_inflation=.7, restructure_depth=.6, scouting=.55),
   tags=['went all-in and got burned', 'back to basics', 'young star quarterback', 'deficit spending on picks'], confidence='known'),
}

# ------------------------------------------------------------ the archetypes
# The eight men the pool and the newgens are blended from. Each is a point
# in the same space; a real man is a weighted mix of two or three, plus
# noise. Names are the shorthand a commentator would use.
ARCHETYPES = {
 'shanahan_tree':  dict(offence=dict(blocking='zone', personnel='21', pass_lean=.47, play_action=.75, motion=.8, tempo=.5, deep=.5, fourth_down=.5)),
 'mcvay_tree':     dict(offence=dict(blocking='zone', personnel='11', pass_lean=.55, play_action=.65, motion=.7, tempo=.5, deep=.55, fourth_down=.55)),
 'reid_spread':    dict(offence=dict(blocking='mixed', personnel='12', pass_lean=.58, play_action=.45, motion=.7, tempo=.5, deep=.5, fourth_down=.6)),
 'harbaugh_power': dict(offence=dict(blocking='gap', personnel='21', pass_lean=.42, play_action=.6, motion=.5, tempo=.4, deep=.5, fourth_down=.65)),
 'air_raid_spread':dict(offence=dict(blocking='zone', personnel='11', pass_lean=.62, play_action=.35, motion=.5, tempo=.7, deep=.6, fourth_down=.55)),
 'fangio_two_high':dict(defence=dict(front='3-4', coverage=.1, shell=.8, blitz=.25, box=.3)),
 'seattle_cover3': dict(defence=dict(front='4-3', coverage=.15, shell=.25, blitz=.2, box=.5)),
 'pressure_man':   dict(defence=dict(front='multiple', coverage=.7, shell=.35, blitz=.7, box=.5)),
 'flores_blitz':   dict(defence=dict(front='3-4', coverage=.05, shell=.6, blitz=1.0, box=.55)),
 'draft_develop':  dict(roster=dict(youth=.75, pick_lens=.35, contract_focus=.7, risk=.35, patience=.85, aggression=.3, dev_belief=.7, board_trust=.8, need_inflation=.3, restructure_depth=.3, scouting=.7)),
 'win_now_trader': dict(roster=dict(youth=.3, pick_lens=.75, contract_focus=.3, risk=.65, patience=.25, aggression=.85, dev_belief=.35, board_trust=.4, need_inflation=.8, restructure_depth=.9, scouting=.5)),
 'analytics_room': dict(roster=dict(youth=.6, pick_lens=.2, contract_focus=.7, risk=.5, patience=.65, aggression=.55, dev_belief=.6, board_trust=.75, need_inflation=.3, restructure_depth=.55, scouting=.6)),
 'scouts_gut':     dict(roster=dict(youth=.5, pick_lens=.7, contract_focus=.45, risk=.55, patience=.5, aggression=.55, dev_belief=.5, board_trust=.35, need_inflation=.65, restructure_depth=.5, scouting=.6)),
 'owner_meddler':  dict(roster=dict(youth=.45, pick_lens=.6, contract_focus=.3, risk=.55, patience=.4, aggression=.45, dev_belief=.45, board_trust=.5, need_inflation=.55, restructure_depth=.7, scouting=.5)),
}
