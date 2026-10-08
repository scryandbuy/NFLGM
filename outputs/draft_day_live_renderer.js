  const cur = v.current, available = draftAvailableView(v);
  const clockTheme = teamTheme(cur.team), userTheme = teamTheme(v.rail.club);
  const next = v.mine_next?.[0];
  page.append(el('header', {class:'dd-title c12'}, el('div', {}, el('small', {}, `${v.year_next || v.rail.year} PLAYER DRAFT`), el('h1', {}, 'Draft Day')),
    el('div', {class:'dd-user'}, crest(v.rail.club, 38), el('div', {}, v.rail.club.name, el('small', {}, 'YOUR DRAFT ROOM')))));
  page.append(el('section', {class:'dd-clock c12', 'aria-label':'On the clock', style:`--clock-team:${clockTheme.base};--clock-accent:${clockTheme.accent};--draft-user:${userTheme.base}`},
    el('div', {class:'dd-clock-team'}, el('div', {class:'dd-emblem'}, showAbbr(cur.team.abbr)), el('div', {},
      el('small', {class:'dd-live'}, v.on_user ? 'YOU ARE ON THE CLOCK' : 'ON THE CLOCK'), el('h2', {}, cur.team.name), el('p', {}, cur.needs?.length ? `Needs: ${cur.needs.join(' · ')}` : ''))),
    el('div', {class:'dd-overall'}, el('small', {}, `ROUND ${cur.round}`), el('strong', {}, cur.sel), el('span', {}, 'OVERALL PICK')),
    el('div', {class:'dd-next'}, el('small', {}, 'YOUR NEXT PICK'), el('strong', {}, next ? next.sel : '—', next ? el('sup', {}, ord(next.sel)) : ''),
      el('p', {}, !next ? 'No picks remaining' : v.on_user ? 'Make your selection' : v.picks_away == null ? '' : `${v.picks_away} ${v.picks_away === 1 ? 'pick' : 'picks'} away`))));
  const actions = el('div', {class:'dd-actions c12'}, el('div', {},
    el('button', {class:'btn', 'data-tip':v.on_user ? 'Use your saved priorities, then let the GM weigh scouting and roster needs. Respects Do Not Draft.' : 'Simulate exactly one pick', onclick:()=>{offersCache=null;act('sim_pick_one');}}, v.on_user ? 'Auto Pick' : 'Next Pick'),
    el('button', {class:'btn go', disabled:v.on_user ? '' : null, onclick:()=>act('sim_to_me')}, 'Sim to Your Pick'),
    el('button', {class:'btn', disabled:v.on_user ? null : '', 'data-tip':'Gather offers for this pick', onclick:()=>{const r=pyJSON("SESSION.draft_act('offers')");notify(r);if(r.ok){offersCache=r.offers;reload();}}}, 'Trade Down')),
    el('div', {}, el('button', {class:'btn quiet', disabled:v.on_user ? '' : null, 'data-tip':'Sim to the end of this round, or to your pick if it comes first', onclick:()=>act('sim_round')}, 'Sim Round'),
      el('button', {class:'btn quiet', onclick:()=>{if(confirm('Run the rest of the draft? Automatic picks follow your saved priorities, then the GM weighs scouting and roster needs. Do Not Draft players are excluded.'))act('sim_draft');}}, 'Sim Draft')));
  page.append(actions);
  const layout=el('div',{class:'dd-layout c12'}), left=el('section',{class:'dd-board'}), right=el('section',{class:'dd-available'});
  left.append(el('h2',{},'Draft Board'));
  const rounds=[...new Set(v.order.map(q=>q.round))], nowRound=cur.round;
  if(boardRound==null || !rounds.includes(boardRound))boardRound=nowRound;
  const tabs=el('div',{class:'dd-rounds',role:'group','aria-label':'Draft round'});
  for(const round of rounds)tabs.append(el('button',{class:'btn', 'aria-pressed':String(boardRound===round), 'aria-label':`Round ${round}`,onclick:()=>{boardRound=round;renderDraftDay(v);}},`Rd ${round}`));
  left.append(tabs);
  const board=el('div',{class:'dd-grid','aria-label':`Round ${boardRound} picks`});
  const detail=el('section',{class:'dd-detail','aria-live':'polite'});
  const pickPlayer=r=>{if(v.on_user && confirm(`Draft ${r.name}, ${r.pos}, ${r.home_state} at ${cur.slot}?`))act('pick',`pid=${JSON.stringify(r.pid)}`);};
  const selectedKey=`${available.key}:${available.source}`;
  let selected=available.rows.find(r=>r.pid===draftDaySelections.get(selectedKey)) || available.top;
  const showProspect=r=>{
    selected=r;draftDaySelections.set(selectedKey,r.pid);
    for(const row of right.querySelectorAll('.dd-candidate'))row.setAttribute('aria-pressed',String(row.dataset.pid===r.pid));
    const copy=el('div',{class:'dd-detail-copy'},el('small',{},'ON YOUR RADAR'),el('a',{class:'dd-detail-name',href:'#club/player/'+r.pid},r.name),el('p',{},[r.pos,r.home_state,r.proj_range ? `Projected ${r.proj_range}` : null].filter(Boolean).join(' · ')));
    detail.replaceChildren(el('div',{class:'dd-position'},r.pos),copy,el('div',{class:'dd-estimate'},el('small',{},'EST. OVERALL'),ovrCell(r.mine)));
    const controls=el('div',{class:'dd-detail-actions'},el('a',{class:'btn',href:'#club/player/'+r.pid},'Prospect Card'));
    if(v.on_user)controls.append(el('button',{class:'btn go',onclick:()=>pickPlayer(r)},`Draft ${surname(r.name)}`));
    detail.append(controls);
  };
  const showPick=q=>{
    const copy=el('div',{class:'dd-detail-copy'},el('small',{},`PICK ${q.sel} · ${q.team.name}`));
    if(q.done){copy.append(q.pid ? el('a',{class:'dd-detail-name',href:'#club/player/'+q.pid},q.name) : el('strong',{class:'dd-detail-name'},q.name),el('p',{},q.pos));}
    else copy.append(el('strong',{class:'dd-detail-name'},q.now?'On the clock':q.mine?'Your pick':'Upcoming pick'),el('p',{},q.original?`Acquired from ${showAbbr(q.original)}`:''));
    detail.replaceChildren(crest(q.team,45),copy);
    if(!q.done&&!q.mine)detail.append(el('button',{class:'btn',onclick:()=>{tradeState={other:q.team.abbr,a:[],b:[q.id],keep:true,draft:true};location.hash='#personnel/trades';}},'Trade for This Pick'));
    if(q.now&&q.mine&&selected)detail.append(el('button',{class:'btn go',onclick:()=>showProspect(selected)},'Choose a Player'));
  };
  for(const q of v.order.filter(q=>q.round===boardRound)){
    const theme=teamTheme(q.team);
    const sq=el('button',{type:'button',class:'dd-tile'+(q.done?' done':'')+(q.now?' now':'')+(q.mine?' mine':''),style:`--pick-team:${theme.base};--pick-accent:${theme.accent}`, 'aria-label':`Pick ${q.sel}, ${q.team.name}, ${q.done ? q.name+', '+q.pos : q.now ? 'on the clock' : q.mine ? 'your pick' : 'upcoming'}`,onclick:()=>showPick(q)},
      el('span',{class:'dd-tile-head'},el('strong',{},showAbbr(q.team.abbr)),el('span',{},q.sel)),
      el('span',{class:'dd-tile-name'},q.done?surname(q.name):q.now?'On the clock':q.mine?'Your pick':''),
      el('span',{class:'dd-tile-sub'},[q.done?q.pos:null,q.original?`from ${showAbbr(q.original)}`:null].filter(Boolean).join(' · ')));
    board.append(sq);
  }
  left.append(board,detail);
  if(available.read)left.append(el('div',{class:'dd-read'},el('small',{},'DRAFT ROOM'),el('p',{},available.read)));
  if(v.on_user && offersCache?.length){
    const offers=el('section',{class:'dd-offers'},el('h2',{},'Trade Offers'));
    for(const o of offersCache)offers.append(el('article',{class:'dd-offer'},el('h3',{},o.team.name),el('p',{},`${o.summary.join(' and ')} for pick ${cur.sel}`),el('div',{},
      el('button',{class:'btn go',onclick:()=>{offersCache=null;act('accept_offer',`i=${o.i}`);}},'Accept'),
      el('button',{class:'btn',onclick:()=>{location.hash='#personnel/trades';}},'Counter'),
      el('button',{class:'btn quiet',onclick:()=>{offersCache=offersCache.filter(x=>x.i!==o.i);reload();}},'Decline'))));
    left.append(offers);
  }else if(v.on_user && offersCache && !offersCache.length)left.append(el('p',{class:'dd-no-offers'},'No trade offers for this pick.'));
  right.append(el('h2',{},'Best Available'));
  const sourceTabs=el('div',{class:'dd-sources',role:'group','aria-label':'Best available board'});
  for(const [source,label]of [['mine','Your Board'],['consensus','Consensus']])sourceTabs.append(el('button',{class:'btn','aria-pressed':String(available.source===source),'data-tip':source==='mine'?'Your saved order, followed by your scouts’ rankings; Do Not Draft players excluded.':'League-wide ranking. Estimated overall is still your scouts’ read.',onclick:()=>{draftAvailableSources.set(available.key,source);renderDraftDay(v);}},label));
  right.append(sourceTabs,el('div',{class:'dd-list-label'},el('span',{},'PROSPECT'),el('span',{},'EST. OVR')));
  const list=el('div',{class:'dd-candidates'});
  for(const r of available.rows.slice(0,12))list.append(el('button',{type:'button',class:'dd-candidate','data-pid':r.pid,'aria-pressed':String(selected?.pid===r.pid),'aria-label':`${r.name}, ${r.pos}, estimated overall ${r.mine}, projected ${r.proj_range}`,onclick:()=>showProspect(r)},
    el('span',{class:'dd-rank'},available.source==='consensus'?(r.cons_rank??'—'):r.board_no),el('span',{class:'dd-position'},r.pos),
    el('span',{class:'dd-candidate-copy'},el('strong',{},surname(r.name)),el('small',{},[r.home_state,r.proj_range].filter(Boolean).join(' · '))),el('span',{class:'dd-rating'},ovrCell(r.mine))));
  if(!available.rows.length)list.append(el('p',{class:'empty'},'No eligible prospects remain on this board.'));
  right.append(list,el('div',{class:'dd-needs'},el('span',{},'YOUR NEEDS'),...(v.my_needs||[]).slice(0,3).map(n=>el('strong',{},n))),el('div',{class:'dd-board-link'},el('a',{class:'btn',href:'#draft/board'},'Open Your Board')));
  // The full explanation is available on demand; it does not crowd the list.
  right.append(el('details',{class:'dd-source-help'},el('summary',{},'About this board'),el('p',{},available.note)));
  if(selected)showProspect(selected);else detail.replaceChildren(el('p',{},'Select a pick to view its details.'));
  layout.append(left,right);page.append(layout);
}
