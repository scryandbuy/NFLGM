const fs = require('fs'), vm = require('vm'), assert = require('node:assert/strict');
const src = fs.readFileSync('docs/app.js', 'utf8');
class Element {
  constructor(tag, attrs = {}) {
    this.tag = tag; this.attrs = {...attrs}; this.children = []; this.parentElement = null;
    this.style = {}; this.offsetWidth = 200; this.offsetHeight = 45; this.isConnected = true;
    const classes = new Set();
    this.classList = {add: x => classes.add(x), remove: x => classes.delete(x), contains: x => classes.has(x)};
  }
  append(node) {
    if (node.parentElement) node.parentElement.children = node.parentElement.children.filter(x => x !== node);
    this.children.push(node); node.parentElement = this;
  }
  getAttribute(key) { return this.attrs[key] ?? null; }
  setAttribute(key, value) { this.attrs[key] = value; }
  removeAttribute(key) { delete this.attrs[key]; }
  contains(node) { return !!node && (node === this || this.children.some(c => c.contains(node))); }
  closest(selector) {
    if (selector === 'dialog' ? this.tag === 'dialog' : this.getAttribute('data-tip') !== null) return this;
    return this.parentElement?.closest(selector) || null;
  }
  getBoundingClientRect() { return {left: 20, top: 20, bottom: 45, width: 80}; }
}
const listeners = {};
const listen = (kind, fn) => (listeners[kind] ||= []).push(fn);
const body = new Element('body');
const ctx = {el: (tag, attrs) => new Element(tag, attrs),
  document: {body, addEventListener: listen},
  window: {innerWidth: 800, innerHeight: 600, addEventListener: listen}};
vm.createContext(ctx);
vm.runInContext(src.slice(src.indexOf('// One viewport-level tooltip'), src.indexOf('// weeks 19 to 22')), ctx);
const tip = body.children[0];
const emit = (type, target, extras = {}) => (listeners[type] || []).forEach(fn => fn({target, clientX: 790, clientY: 590, ...extras}));
const control = new Element('button', {'data-tip': 'Identity description', 'aria-describedby': 'existing-help'});
body.append(control);
for (let i = 0; i < 3; i++) { emit('mouseover', control); emit('focusin', control); }
assert.equal(body.children.filter(n => n.attrs.role === 'tooltip').length, 1);
assert.equal(tip.textContent, 'Identity description');
assert.equal(control.attrs['aria-describedby'], 'existing-help floating-tooltip');
assert.ok(tip.classList.contains('visible'));
assert.ok(parseFloat(tip.style.left) <= 592);
emit('keydown', control, {key: 'Escape'});
assert.ok(!tip.classList.contains('visible'));
assert.equal(control.attrs['aria-describedby'], 'existing-help');
// The deepest hovered hint replaces its parent's hint; neither can create a second popup.
const child = new Element('span', {'data-tip': 'Specific detail'}); control.append(child);
emit('mouseover', control); emit('mouseover', child);
assert.equal(tip.textContent, 'Specific detail');
assert.equal(control.attrs['aria-describedby'], 'existing-help');
const dialog = new Element('dialog'); body.append(dialog);
const offer = new Element('button', {'data-tip': 'Staff offer'}); dialog.append(offer);
emit('focusin', offer);
assert.equal(tip.parentElement, dialog); assert.equal(tip.textContent, 'Staff offer');
emit('close', dialog);
assert.equal(tip.parentElement, body); assert.ok(!tip.classList.contains('visible'));
assert.equal(offer.getAttribute('aria-describedby'), null);
emit('mouseover', control); emit('hashchange', body);
assert.ok(!tip.classList.contains('visible'));
emit('mouseover', control); control.isConnected = false; emit('mousemove', body);
assert.ok(!tip.classList.contains('visible'));
// Sweep every shipped rendering source for old concurrent tooltip implementations.
assert.equal((src.match(/role: 'tooltip'/g) || []).length, 1);
assert.ok(!src.includes('showFoTip'));
assert.ok(!/\btitle:\s*(?:'Card'|'Extend'|'Trade Block'|'Trade')/.test(src));
assert.ok(!/content:\s*attr\(data-tip\)/.test(fs.readFileSync('docs/style.css', 'utf8')));
assert.ok(!/\btitle=/.test(fs.readFileSync('docs/index.html', 'utf8')));
console.log('Single-tooltip checks passed: hover/focus, nesting, accessibility, dialog top layer, dismissal, and legacy sweep.');
