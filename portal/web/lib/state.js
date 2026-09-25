// Session-wide state and formatting helpers.
export const state = { me: null, timezone: 'UTC', phones: [] };

export function formatTime(ts, { date = false } = {}) {
  if (!ts) return '—';
  const opts = { hour: '2-digit', minute: '2-digit', second: '2-digit', timeZone: state.timezone };
  if (date) Object.assign(opts, { month: 'short', day: 'numeric' });
  return new Intl.DateTimeFormat(undefined, opts).format(new Date(ts));
}

export function timezoneLabel() {
  const parts = new Intl.DateTimeFormat('en', { timeZone: state.timezone, timeZoneName: 'short' }).formatToParts(new Date());
  const short = parts.find(p => p.type === 'timeZoneName')?.value ?? '';
  return `${state.timezone.replace(/_/g, ' ')}${short ? ` (${short})` : ''}`;
}

export const isStaff = () => state.me?.role === 'staff';
export const isCustomerAdmin = () => state.me?.role === 'customer_admin';
