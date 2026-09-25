// Portal-side validation of remote input. The rack agent re-validates with the same rules
// (rack-agent/src/actions.js); test/action-parity.test.mjs keeps the two in step.
// Only these action types exist. The browser never names a kernel function.

export const FUNCTION_KEYS = Object.freeze(['Home', 'AppSwitch', 'ControlBar', 'Enter', 'Backspace', 'Tab', 'Escape']);
export const MAX_TEXT = 200;
export const MAX_DRAG_POINTS = 24;
export const TEXT_CHUNK = 32;

export class ActionError extends Error {}

const isInt = Number.isInteger;

function point(x, y, size, label = 'Point') {
  if (!isInt(x) || !isInt(y)) throw new ActionError(`${label} must use whole-pixel coordinates.`);
  if (x < 0 || y < 0 || x >= size.width || y >= size.height) throw new ActionError(`${label} is outside the phone screen.`);
  return [x, y];
}

export function textProblem(text) {
  if (typeof text !== 'string' || text.length === 0) return 'Enter some text to type.';
  if (text.length > MAX_TEXT) return `Type at most ${MAX_TEXT} characters at a time.`;
  for (const ch of text) {
    const c = ch.codePointAt(0);
    if (c < 32 || c > 126) return 'Only English (US) letters, numbers, spaces and standard punctuation can be typed.';
  }
  return null;
}

export function validateAction(action, size) {
  if (!action || typeof action !== 'object' || Array.isArray(action)) throw new ActionError('Missing action.');
  if (!size || !(size.width > 1) || !(size.height > 1)) throw new ActionError('Phone screen size is not known yet.');
  switch (action.type) {
    case 'tap': { const [x, y] = point(action.x, action.y, size); return { type: 'tap', x, y }; }
    case 'longPress': {
      const [x, y] = point(action.x, action.y, size);
      const holdMs = action.holdMs === undefined ? 900 : action.holdMs;
      if (!isInt(holdMs) || holdMs < 500 || holdMs > 3000) throw new ActionError('Hold time must be 500-3000 ms.');
      return { type: 'longPress', x, y, holdMs };
    }
    case 'drag': {
      if (!Array.isArray(action.points) || action.points.length < 2 || action.points.length > MAX_DRAG_POINTS)
        throw new ActionError(`A drag needs 2-${MAX_DRAG_POINTS} points.`);
      return { type: 'drag', points: action.points.map((p, i) => {
        if (!Array.isArray(p) || p.length !== 2) throw new ActionError('Invalid drag point.');
        return point(p[0], p[1], size, `Drag point ${i + 1}`);
      }) };
    }
    case 'key':
      if (!FUNCTION_KEYS.includes(action.key)) throw new ActionError('That key is not supported.');
      return { type: 'key', key: action.key };
    case 'text': {
      const problem = textProblem(action.text);
      if (problem) throw new ActionError(problem);
      return { type: 'text', text: action.text };
    }
    case 'resetPointer': return { type: 'resetPointer' };
    default: throw new ActionError('Unsupported action.');
  }
}

export const isCoordinateAction = a => a.type === 'tap' || a.type === 'longPress' || a.type === 'drag';

/** Portal-side wait for the agent's answer, from the kernel's worst-case timings. */
export function commandTimeoutMs(action) {
  if (action.type === 'text') return 15_000 + Math.ceil(action.text.length / TEXT_CHUNK) * 9_000;
  if (action.type === 'drag') return 15_000 + action.points.length * 1_500;
  return 30_000;
}

/** Safe for audit and command history: never contains typed text. */
export function describeAction(a) {
  switch (a?.type) {
    case 'tap': return `Tap at ${a.x}, ${a.y}`;
    case 'longPress': return `Long press at ${a.x}, ${a.y}`;
    case 'drag': return `Swipe from ${a.points[0].join(', ')} to ${a.points.at(-1).join(', ')}`;
    case 'key': return { Home: 'Home', AppSwitch: 'App switcher', ControlBar: 'Control Centre', Enter: 'Return key', Backspace: 'Delete key', Tab: 'Tab key', Escape: 'Escape key' }[a.key];
    case 'text': return `Typed ${a.text.length} character${a.text.length === 1 ? '' : 's'}`;
    case 'resetPointer': return 'Reset pointer';
    default: return 'Action';
  }
}

// ---- outcomes -------------------------------------------------------------------------
export const OUTCOMES = Object.freeze(['succeeded', 'not_sent', 'uncertain']);
const plural = (n, word) => `${n} ${word}${n === 1 ? '' : 's'}`;

/**
 * Customer-facing explanation of an outcome. Success wording is deliberately "sent":
 * the rack confirms the input was delivered, not what the phone did with it.
 */
export function outcomeMessage(action, o) {
  const text = o.text;
  if (o.status === 'succeeded') {
    if (text) return `All ${plural(text.total, 'character')} were sent as keystrokes. Check the phone to confirm the text appeared where you expected.`;
    return 'Sent to the phone. Check the screen for the result.';
  }
  if (o.status === 'not_sent') {
    return {
      not_in_control: 'Nothing was sent: you are not in control of this phone.',
      not_assigned: 'Nothing was sent: this phone is no longer assigned to your account.',
      queue_full: 'Nothing was sent: earlier actions are still running on this phone.',
      duplicate: 'Nothing was sent: this action was already received.',
      stopped_before_start: 'Nothing was sent: the phone was stopped or released before this action started.',
      kernel_refused: 'Nothing was sent: the rack refused the action before sending any input.',
      kernel_unreachable: 'Nothing was sent: the rack software is not responding.',
      rack_offline: 'Nothing was sent: the rack is offline.',
      rack_refused: 'Nothing was sent: the rack refused the request.',
      invalid_action: 'Nothing was sent: the rack could not accept this action.',
    }[o.reason] ?? 'Nothing was sent to the phone.';
  }
  // uncertain
  const why = {
    no_reply: 'The rack did not confirm this action, so it may have run fully, partly or not at all.',
    kernel_failed: 'The rack reported a problem while sending, so part of it may have reached the phone.',
    cancelled_during: 'It was stopped while being sent, so part of it may have reached the phone.',
    interrupted: 'It was stopped partway through.',
    release_failed: 'The final button release was not confirmed.',
    agent_error: 'The rack agent hit an unexpected error while sending.',
  }[o.reason] ?? 'The outcome is not confirmed.';
  let progress = '';
  if (text) {
    progress = ` ${text.confirmed} of ${text.total} characters were confirmed as keystrokes`
      + (text.uncertain ? `, the next ${text.uncertain} are uncertain` : '')
      + (text.notSent ? `, and ${text.notSent} were not sent` : '') + '. Confirmed keystrokes do not prove the text appeared.';
  } else if (o.progress?.total > 1) {
    progress = ` ${o.progress.confirmed} of ${plural(o.progress.total, 'step')} confirmed` + (o.progress.uncertain ? ', 1 uncertain' : '') + (o.progress.notSent ? `, ${o.progress.notSent} not sent` : '') + '.';
  }
  return `${why}${progress} Check the phone before doing anything else. It will not be retried automatically.`;
}
