// Outcome vocabulary shared by the phone view, group results and activity log.
//   succeeded  the rack confirmed the input was sent (not that the phone showed the result)
//   not_sent   confirmed nothing reached the phone; the only state that may be retried
//   uncertain  may have run fully, partly or not at all; never retried automatically
export const OUTCOME_WORDS = {
  succeeded: 'Sent', not_sent: 'Not sent', uncertain: 'Uncertain — check phone', sending: 'Sending…', skipped: 'Skipped',
};
export const OUTCOME_KIND = { succeeded: 'ok', not_sent: 'warn', uncertain: 'bad', skipped: 'warn' };

/** Short progress note for a command row, e.g. "64/100 characters confirmed". */
export function progressNote(c) {
  if (c.status === 'succeeded' || c.status === 'sending') return '';
  const total = c.chars_total ?? c.text?.total, ok = c.chars_confirmed ?? c.text?.confirmed, unsure = c.chars_uncertain ?? c.text?.uncertain;
  if (total && (ok || unsure)) return `${ok}/${total} characters confirmed${unsure ? `, ${unsure} uncertain` : ''}`;
  const stT = c.steps_total ?? c.progress?.total, stOk = c.steps_confirmed ?? c.progress?.confirmed;
  if (stT > 1 && stOk) return `${stOk}/${stT} steps confirmed`;
  return '';
}
