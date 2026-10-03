const fs = require('fs'), vm = require('vm'), assert = require('node:assert/strict');
const src = fs.readFileSync('docs/app.js', 'utf8');
const code = src.slice(src.indexOf('function surname('), src.indexOf('\n', src.indexOf('function surname('))) + '\n' +
  src.slice(src.indexOf('function playerMention('), src.indexOf('function messageText(')) +
  src.slice(src.indexOf('let depthPkg ='), src.indexOf('// ---------------------------------------------------------------- Personnel'));
class Element {
  constructor(tag, attrs = {}, ...children) {
    this.tag = tag; this.attrs = attrs; this.children = children.filter(x => x != null);
    this.style = {setProperty() {}}; this.listeners = {};
    this.classList = {add() {}, remove() {}};
  }
  append(...children) { this.children.push(...children); }
  addEventListener(event, fn) { this.listeners[event] = fn; }
  querySelectorAll() { return []; }
  set innerHTML(value) { this.children = []; }
}
const nodes = {'#page': new Element('main'), '#nav': new Element('nav'), '#crumb': new Element('span')};
const ctx = {console, Map, JSON, encodeURIComponent, location: {},
  $: key => nodes[key], el: (...args) => new Element(...args),
  renderRail() {}, secondRow() {}, clubNav() { return []; },
  clubSelect() { return new Element('select'); }, teamTheme() { return {base: '#203731', accent: '#ffb612'}; }};
vm.createContext(ctx); vm.runInContext(code, ctx);
function descendants(node) {
  return node instanceof Element ? [node, ...node.children.flatMap(descendants)] : [];
}
const teams = [...fs.readFileSync('stadium_names.py', 'utf8').split('TEAM_NAMES = ')[1]
  .split('}')[0].matchAll(/'([A-Z]+)': '([^']+)'/g)].map(m => [m[1], m[2]]);
assert.equal(teams.length, 32);
let checked = 0;
for (const [abbr, teamName] of teams) {
  for (const side of ['offense', 'defense', 'specialists']) {
    for (const mine of [true, false]) {
      vm.runInContext(`depthSide = '${side}'`, ctx);
      const players = [
        {pid: 'ardarius', name: "Ar'Darius Washington"},
        {pid: 'parker', name: 'Parker Washington'},
        {pid: 'houston', name: 'James Houston'},
        {pid: 'cleveland', name: 'Ezra Cleveland'},
        {pid: 'rookie / 1', name: 'Test ' + teamName},
        {pid: 'suffix', name: 'Marvin Mims Jr.'},
        {pid: 'other', name: 'Jordan Love'}
      ].map((p, i) => ({...p, start: i === 0, ovr: 80, fit: 0}));
      const slots = [{pos: 'QB', title: 'Players', group: 'Secondary', slots: players}];
      ctx.renderDepth({mine, club_abbr: abbr, rail: {club: {abbr, name: teamName}},
        sides: {offense: slots, defense: slots, specialists: slots}, pins: {}, packages: ['Base'],
        package: 'Base', coach_front: '4-3', defense_shape: '4-3'});
      const plates = descendants(nodes['#page']).filter(e => e.attrs.class?.startsWith('plate3'));
      assert.equal(plates.length, players.length);
      plates.forEach((plate, i) => {
        const links = descendants(plate).filter(e => e.tag === 'a');
        assert.equal(links.length, 1, `${abbr}/${side}: every name has a single explicit link`);
        assert.equal(links[0].attrs.href, '#club/player/' + encodeURIComponent(players[i].pid));
        assert.equal(links[0].children[0], ctx.surname(players[i].name));
        let stopped = false;
        links[0].attrs.onclick({stopPropagation() { stopped = true; }});
        assert.ok(stopped);
        assert.equal(plate.attrs.draggable, String(mine));
        assert.equal(typeof plate.listeners.drop, 'function');
        plate.listeners.dblclick();
        assert.equal(ctx.location.hash, '#club/player/' + players[i].pid);
        checked++;
      });
    }
  }
}
// Explicit anchors are excluded from automatic name-to-team linking.
assert.match(src.slice(src.indexOf('const NameLinks ='), src.indexOf('function notify(')), /const ignored = 'a,/);
console.log(`Depth links: ${checked} player entries across 32 teams, all 3 sides, user/CPU charts; duplicate surnames and drag behavior verified.`);
