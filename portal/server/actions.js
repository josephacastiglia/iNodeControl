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
