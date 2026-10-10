"""Deterministic third-person reporting from completed game evidence. No simulation changes."""
from stadium_names import TEAM_NAMES


def build(league, home, away, res):
    import game_recap as GR
    names = {'home': TEAM_NAMES.get(home, home), 'away': TEAM_NAMES.get(away, away)}
    scores = {s: int(res[s]) for s in names}
    winner = max(scores, key=scores.get)
    loser = 'away' if winner == 'home' else 'home'
    tied = scores[winner] == scores[loser]
    margin = scores[winner] - scores[loser]
    drives = res.get('drives', [])
    rows = {s: GR.plays(res, s) for s in names}
    stats = {s: GR.stats(rows[s]) for s in names}
    running = dict(home=0, away=0)
    events = []
    for side, drive in drives:
        points = getattr(drive, 'points', 0) or 0
        if not points: continue
        scoring = side if points > 0 else ('away' if side == 'home' else 'home')
        running[scoring] += abs(int(points))
        events.append(dict(side=scoring, score=dict(running), drive=drive))
    verified = bool(events) and running == scores
    overtime = bool(res.get('overtime') or any(getattr(d, 'start_quarter', 1) > 4 for _, d in drives))
    score = f"{scores[winner]}–{scores[loser]}"
    deficit = max((e['score'][loser] - e['score'][winner] for e in events), default=0) if verified else 0
    lead = max((e['score'][winner] - e['score'][loser] for e in events), default=0) if verified else 0
    if tied:
        headline = f"{names['home']} and {names['away']} finish level at {score}"
        opening = f"Neither team found a winning edge as {names['home']} and {names['away']} finished tied at {score}{' after overtime' if overtime else ''}."
    elif deficit >= 10:
        headline = f"{names[winner]} rallies past {names[loser]}, {score}"
        opening = f"{names[winner]} overturned a {deficit}-point deficit to beat {names[loser]} {score}{' in overtime' if overtime else ''}."
    elif lead >= 14 and margin <= 8:
        headline = f"{names[winner]} holds off {names[loser]} for {score} win"
        opening = f"{names[winner]} built a {lead}-point lead, but {names[loser]} fought back to make the finish close. The final margin was {score}."
    elif margin >= 17:
        headline = f"{names[winner]} pulls away from {names[loser]}, {score}"
        opening = f"{names[winner]} finished with a {margin}-point cushion in a {score} victory over {names[loser]}."
    else:
        headline = f"{names[winner]} edges {names[loser]}, {score}" if margin <= 8 else f"{names[winner]} beats {names[loser]}, {score}"
        opening = f"{names[winner]} came away with a {score} win over {names[loser]}{' in overtime' if overtime else ''}."
    paragraphs = [opening]
    if rows['home'] or rows['away']:
        leader = max(stats, key=lambda s: stats[s]['yards']); other = 'away' if leader == 'home' else 'home'
        line = f"{names[leader]} gained {stats[leader]['yards']:.0f} scrimmage yards to {names[other]}'s {stats[other]['yards']:.0f}."
        if not tied and leader != winner:
            line += f" The yardage advantage was not enough to secure the win."
        counts = {s: stats[s]['turnovers'] + GR.return_summary(res,s)['lost'] for s in names}
        trouble = max(counts, key=counts.get)
        if counts[trouble]:
            n = counts[trouble]
            line += f" {names[trouble]} also surrendered possession {n} {'time' if n == 1 else 'times'} through turnovers."
        paragraphs.append(line)
    if verified:
        half = dict(home=0, away=0)
        for event in events:
            d = event['drive']
            if getattr(d, 'quarter', 5) <= 2:
                half = event['score']
        if half['home'] != half['away']:
            front = max(half, key=half.get); back = 'away' if front=='home' else 'home'
            line = f"{names[front]} took a {half[front]}–{half[back]} lead into halftime."
            if not tied and front != winner:
                line += f" {names[winner]} turned the game around after the break."
            elif not tied and half[front]-half[back] > margin and margin<=8:
                line += f" {names[back]} narrowed the gap in the second half, forcing the leader to work for the finish."
            paragraphs.append(line)
    # Describe an actual highlight; never count nullified scores or attach a
    # receiver's identity to a return by a different player.
    highlights = [(float(p.get('yards',0) or 0),s,p) for s in names for p in rows[s]
                  if p.get('touchdown') and not p.get('defensive_td') and not p.get('fumble_lost')
                  and p.get('type') in ('complete','run','scramble')]
    if highlights:
        yards, side, play = max(highlights, key=lambda x:x[0])
        if yards >= 20:
            pid = play.get('target') if play['type']=='complete' else play.get('carrier') or play.get('passer')
            player = league.player(pid) if pid and hasattr(league,'player') else None
            who = player.name if player else names[side]
            action = 'touchdown reception' if play['type']=='complete' and player else 'touchdown pass' if play['type']=='complete' else 'touchdown run'
            paragraphs.append(f"{who} supplied one of the game's biggest plays with a {yards:.0f}-yard {action}.")
    if verified and not tied:
        # Final permanent lead, rather than the last score (which may be the loser).
        clinch = next((e for i,e in enumerate(events) if e['score'][winner]>e['score'][loser]
                       and all(x['score'][winner]>x['score'][loser] for x in events[i:])),None)
        if clinch:
            d=clinch['drive'];clock=getattr(d,'clock',None);q=getattr(d,'quarter',None)
            if q and (q>=5 or q==4 and clock is not None and clock<=900):
                stage='in overtime' if q>=5 else 'in the fourth quarter'
                paragraphs.append(f"{names[winner]} went ahead for good {stage}, taking a {clinch['score'][winner]}–{clinch['score'][loser]} lead.")
    if verified and not tied and margin<=8 and len(events)>=2:
        last = events[-1]
        d=last['drive']; clock=getattr(d,'clock',None)
        if getattr(d,'quarter',0)==4 and clock is not None and 0<=clock<=600:
            who=last['side']; other='away' if who=='home' else 'home'
            remaining=f"{int(clock)//60}:{int(clock)%60:02d}"
            if who==loser:
                paragraphs.append(f"{names[loser]} scored again with {remaining} remaining, closing to {scores[winner]}–{scores[loser]}. The comeback remained alive, but they still needed another possession.")
            elif not any('went ahead for good' in x for x in paragraphs):
                paragraphs.append(f"{names[winner]} added its final points with {remaining} remaining, making the score {score}.")
    if verified:
        for i in range(len(drives)-1,0,-1):
            side,d=drives[i];previous_side,previous=drives[i-1]
            lost=[p for p in getattr(previous,'log',[]) if not p.get('nullified')
                  and (p.get('type')=='interception' or p.get('fumble_lost'))]
            if (side != previous_side and lost and getattr(d,'points',0)>0
                    and getattr(d,'start',100)<=40 and getattr(d,'quarter',0)==4):
                kind='an interception' if lost[-1].get('type')=='interception' else 'a recovered fumble'
                score_kind='a touchdown' if d.points>=6 else 'a field goal' if d.points==3 else 'points'
                paragraphs.insert(min(3,len(paragraphs)), f"A short field proved valuable for {names[side]} in the fourth quarter. They turned {kind} into {score_kind}, taking advantage of the opening.")
                break
    missed = {s:sum(p.get('type')=='field_goal' and not p.get('made') and not p.get('nullified')
                   for side,d in drives if side==s for p in getattr(d,'log',[])) for s in names}
    kicker = max(missed, key=missed.get)
    if missed[kicker] >= 2:
        paragraphs.append(f"{names[kicker]} left further chances unused with {missed[kicker]} missed field goals.")
    if drives and not tied:
        side, final = drives[-1];log=[p for p in getattr(final,'log',[]) if not p.get('nullified')]
        if side==winner and any(p.get('type')=='kneel' for p in log):
            conversions=[p for p in log if p.get('type') in ('run','scramble') and p.get('down')==3 and GR.converted(p)]
            if conversions:
                paragraphs.append(f"With the game still to close out, {names[winner]} converted on third down on the ground during its final possession, then finished with a kneel.")
            else:
                paragraphs.append(f"{names[winner]} finished in possession and knelt to run out the remaining time.")
        elif side==loser and str(getattr(final,'result','')).lower() in ('downs','turnover on downs'):
            paragraphs.append(f"{names[loser]}'s final possession ended on downs, leaving the comeback unfinished.")
    return dict(version=1, headline=headline, paragraphs=paragraphs)
