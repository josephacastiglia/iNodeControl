import { h, replace } from './lib/dom.js';
import { get, post, setCsrf, whenSignedOut, ApiError } from './lib/api.js';
import { state, isStaff } from './lib/state.js';
import { loginView } from './views/login.js';
import { overviewView } from './views/overview.js';
import { phonesView } from './views/phones.js';
import { phoneView } from './views/phone.js';
import { activityView } from './views/activity.js';
import { staffView } from './views/staff.js';

const root = document.getElementById('app');
let current = null;          // { destroy() } of the active view
let keeper = null;

whenSignedOut.current = () => { state.me = null; stopKeeper(); render(); };

function customerRoutes() {
  return [
    { path: /^\/overview$/, title: 'Overview', view: overviewView, nav: 'overview' },
    { path: /^\/phones$/, title: 'Phones', view: phonesView, nav: 'phones' },
    { path: /^\/phones\/([\w-]+)$/, title: 'Phone', view: phoneView, nav: 'phones' },
    { path: /^\/activity$/, title: 'Activity', view: activityView, nav: 'activity' },
  ];
}
function staffRoutes() {
  return [{ path: /^\/staff(?:\/(racks|phones|customers|emergency|audit))?$/, title: 'Staff console', view: staffView, nav: 'staff' }];
}

async function boot() {
  try {
    const me = await get('/api/me');
    state.me = me.user;
    state.timezone = me.user.timezone || 'UTC';
    setCsrf(me.csrf);
  } catch (err) {
    if (!(err instanceof ApiError) || err.status !== 401) console.error(err);
    state.me = null;
  }
  render();
}

function currentPath() { return location.hash.replace(/^#/, '') || ''; }

function render() {
  current?.destroy?.();
  current = null;
  if (!state.me) {
    current = loginView(async () => { await boot(); });
    return replace(root, current.el);
  }
  const routes = isStaff() ? staffRoutes() : customerRoutes();
  let path = currentPath();
  let match = null, route = null;
  for (const r of routes) { match = r.path.exec(path); if (match) { route = r; break; } }
  if (!route) { location.hash = isStaff() ? '#/staff/racks' : '#/overview'; return; }
  const shell = buildShell(route.nav);
  replace(root, shell.el);
  shell.setTitle(route.title);
  current = route.view({ params: match.slice(1), setTitle: shell.setTitle, setActions: shell.setActions, setBanner: shell.setBanner });
  replace(shell.content, current.el);
  if (!isStaff()) startKeeper();
}

function buildShell(active) {
  const title = h('h1', {}, '');
  const actions = h('div', { class: 'topbar-actions' });
  const banner = h('div', { class: 'sim-banner', hidden: true, role: 'note' });
  const content = h('main', { class: 'content', id: 'main', tabindex: '-1' });
  const link = (nav, href, label) => h('a', { href, 'aria-current': active === nav ? 'page' : null, onclick: () => shellEl.classList.remove('nav-open') }, label);
  const nav = isStaff()
    ? h('nav', { class: 'nav', 'aria-label': 'Staff' }, h('div', { class: 'nav-label' }, 'Staff console'),
        link('staff', '#/staff/racks', 'Racks'), link('staff-phones', '#/staff/phones', 'Phones'), link('staff-customers', '#/staff/customers', 'Customers'),
        link('staff-emergency', '#/staff/emergency', 'Emergency stop'), link('staff-audit', '#/staff/audit', 'Audit log'))
    : h('nav', { class: 'nav', 'aria-label': 'Main' },
        link('overview', '#/overview', 'Overview'), link('phones', '#/phones', 'Phones'), link('activity', '#/activity', 'Activity'),
        h('div', { class: 'nav-label' }, 'Coming next'),
        h('span', { class: 'nav-soon', title: 'Account registry arrives in the next release.' }, h('a', { 'aria-disabled': 'true', tabindex: '-1' }, 'Accounts · soon')),
        h('span', { class: 'nav-soon', title: 'Content library arrives in a later release.' }, h('a', { 'aria-disabled': 'true', tabindex: '-1' }, 'Content · soon')),
        h('span', { class: 'nav-soon', title: 'Scheduling and automations arrive in a later release.' }, h('a', { 'aria-disabled': 'true', tabindex: '-1' }, 'Automations · soon')));
  const signOut = h('button', { class: 'btn btn-ghost btn-sm', type: 'button', onclick: async () => {
    await releaseAll(false);
    try { await post('/api/auth/logout'); } catch { /* already signed out */ }
    state.me = null; stopKeeper(); render();
  } }, 'Sign out');
  const shellEl = h('div', { class: 'shell' },
    h('aside', { class: 'sidebar dark' },
      h('a', { class: 'brand', href: isStaff() ? '#/staff/racks' : '#/overview' }, h('img', { src: '/assets/favicon.svg', alt: '' }),
        h('span', {}, h('b', {}, 'NodeTheory'), h('small', {}, isStaff() ? 'Staff' : 'Portal'))),
      nav,
      h('div', { class: 'sidebar-foot' }, h('div', {}, h('b', {}, state.me.name), h('br'), state.me.customerName ?? 'NodeTheory staff'), signOut)),
    h('div', { class: 'main' },
      banner,
      h('header', { class: 'topbar' },
        h('div', { style: 'display:flex;align-items:center;gap:12px;min-width:0' },
          h('button', { class: 'btn btn-ghost btn-sm menu-toggle', type: 'button', 'aria-label': 'Open menu', onclick: () => shellEl.classList.toggle('nav-open') }, '☰'),
          title),
        actions),
      content));
  // Staff sub-navigation shares one route; mark the right item.
  if (isStaff()) {
    const sub = currentPath().split('/')[2] ?? 'racks';
    for (const a of shellEl.querySelectorAll('.nav a')) a.setAttribute('aria-current', a.getAttribute('href') === `#/staff/${sub}` ? 'page' : 'false');
  }
  return {
    el: shellEl, content,
    setTitle: t => { title.textContent = t; document.title = `${t} · NodeTheory Portal`; },
    setActions: (...els) => replace(actions, ...els),
    setBanner: text => { banner.hidden = !text; banner.textContent = text ?? ''; },
  };
}

// ---- control keeper: heartbeats for every phone this user controls ----------------
function startKeeper() {
  if (keeper) return;
  const beat = async () => {
    try {
      const { phones } = await get('/api/phones');
      state.phones = phones;
      await Promise.all(phones.filter(p => p.input.state === 'yours').map(p => post(`/api/phones/${p.id}/control/heartbeat`).catch(() => null)));
    } catch { /* next beat */ }
  };
  keeper = setInterval(beat, 10_000);
}
function stopKeeper() { clearInterval(keeper); keeper = null; }

async function releaseAll(keepalive) {
  const mine = state.phones.filter(p => p.input.state === 'yours').map(p => p.id);
  if (mine.length) await post('/api/groups/release', { phoneIds: mine }, { keepalive }).catch(() => null);
}
// Closing the tab hands phones back instead of waiting for the heartbeat timeout.
window.addEventListener('pagehide', () => { if (state.me && !isStaff()) releaseAll(true); });
window.addEventListener('hashchange', render);
boot();
