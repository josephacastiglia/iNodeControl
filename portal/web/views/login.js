import { h } from '../lib/dom.js';
import { post } from '../lib/api.js';

export function loginView(onSignedIn) {
  const email = h('input', { type: 'email', name: 'email', autocomplete: 'username', required: true });
  const password = h('input', { type: 'password', name: 'password', autocomplete: 'current-password', required: true });
  const error = h('p', { class: 'error-text', role: 'alert' });
  const submit = h('button', { class: 'btn btn-primary btn-block', type: 'submit' }, 'Sign in');
  const form = h('form', { class: 'login-card', novalidate: true },
    h('a', { class: 'brand', href: '#' }, h('img', { src: '/assets/favicon.svg', alt: '' }), h('span', {}, h('b', {}, 'NodeTheory'), h('small', {}, 'Portal'))),
    h('div', {}, h('h2', {}, 'Sign in to your phones'), h('p', { class: 'muted small', style: 'margin-top:6px' }, 'Use the account NodeTheory set up for your team.')),
    h('label', { class: 'field' }, 'Email', email),
    h('label', { class: 'field' }, 'Password', password),
    error, submit,
    h('p', { class: 'muted small' }, 'Trouble signing in? Contact your NodeTheory account manager.'));
  form.addEventListener('submit', async e => {
    e.preventDefault();
    error.textContent = '';
    submit.disabled = true;
    try {
      await post('/api/auth/login', { email: email.value, password: password.value });
      password.value = '';
      await onSignedIn();
    } catch (err) {
      error.textContent = err.message;
      submit.disabled = false;
      password.focus();
    }
  });
  const el = h('div', { class: 'login' },
    h('section', { class: 'login-hero dark' },
      h('div', { class: 'eyebrow', style: 'color:var(--muted)' }, '+ Hosted iPhones for social publishing'),
      h('div', {}, h('h1', {}, 'More accounts.', h('span', {}, 'One dashboard.')),
        h('p', {}, 'See every phone in your network live, take control of one when you need it, and hand it back when you’re done.')),
      h('p', { class: 'small', style: 'color:var(--muted-light)' }, '© NodeTheory')),
    h('section', { class: 'login-panel' }, form));
  setTimeout(() => email.focus(), 0);
  return { el };
}
