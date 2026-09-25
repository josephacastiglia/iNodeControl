// The complete set of input the rack agent will perform. The portal sends one of these
// action objects; nothing else reaches the kernel. Each action becomes a fixed plan of
// kernel functions, so the browser can never name a kernel function directly.
//
// Limits come from the kernel source at commit ee445d7:
//  - InputRouter.Validate: coordinates inside the calibrated image, left button only,
//    fn_key from a fixed list, text 1-1000 chars of HidProtocol.Ascii (codes 32-126 here).
//  - InputSessions.ExecuteAsync: every command is cancelled after 8 s, and a failed or
//    cancelled command latches Stop. At 45+60+35 ms per character (90 ms hold for
//    space) one /key/sendkey can type only ~50 characters safely, so text is chunked.

export const FUNCTION_KEYS = Object.freeze(['Home', 'AppSwitch', 'ControlBar', 'Enter', 'Backspace', 'Tab', 'Escape']);
export const TEXT_CHUNK = 32;
export const MAX_TEXT = 200;
export const MAX_DRAG_POINTS = 24;

export class ActionError extends Error {
  constructor(message) { super(message); this.name = 'ActionError'; }
}

const isInt = v => Number.isInteger(v);

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

/**
 * Validates an untrusted action against the phone's source image size and returns a
 * normalized copy. Throws ActionError for anything outside the allowlist.
 */
export function validateAction(action, size) {
  if (!action || typeof action !== 'object') throw new ActionError('Missing action.');
  if (!size || !(size.width > 1) || !(size.height > 1)) throw new ActionError('Phone screen size is not known yet.');
  switch (action.type) {
    case 'tap': {
      const [x, y] = point(action.x, action.y, size);
      return { type: 'tap', x, y };
    }
    case 'longPress': {
      const [x, y] = point(action.x, action.y, size);
      const holdMs = action.holdMs === undefined ? 900 : action.holdMs;
      if (!isInt(holdMs) || holdMs < 500 || holdMs > 3000) throw new ActionError('Hold time must be 500-3000 ms.');
      return { type: 'longPress', x, y, holdMs };
    }
    case 'drag': {
      if (!Array.isArray(action.points) || action.points.length < 2 || action.points.length > MAX_DRAG_POINTS)
        throw new ActionError(`A drag needs 2-${MAX_DRAG_POINTS} points.`);
      const points = action.points.map((p, i) => {
        if (!Array.isArray(p) || p.length !== 2) throw new ActionError('Invalid drag point.');
        return point(p[0], p[1], size, `Drag point ${i + 1}`);
      });
      return { type: 'drag', points };
    }
    case 'key': {
      if (!FUNCTION_KEYS.includes(action.key)) throw new ActionError('That key is not supported.');
      return { type: 'key', key: action.key };
    }
    case 'text': {
      const problem = textProblem(action.text);
      if (problem) throw new ActionError(problem);
      return { type: 'text', text: action.text };
    }
    case 'resetPointer':
      return { type: 'resetPointer' };
    default:
      throw new ActionError('Unsupported action.');
  }
}

/**
 * Kernel plan for a validated action. Steps run in order within one lease; a `sleep`
 * step waits locally; `finally` steps run even if an earlier step fails, unless the
 * phone was stopped (the kernel's Stop already releases held input).
 */
export function planFor(action) {
  switch (action.type) {
    case 'tap': return { steps: [{ fun: '/mouse/click', data: { x: action.x, y: action.y } }] };
    case 'longPress': return {
      steps: [
        { fun: '/mouse/move', data: { x: action.x, y: action.y } },
        { fun: '/mouse/down', data: {} },
        { sleep: action.holdMs },
      ],
      finally: [{ fun: '/mouse/up', data: {} }],
      finallyAfter: 1,
    };
    case 'drag': {
      const [first, ...rest] = action.points;
      return {
        steps: [
          { fun: '/mouse/move', data: { x: first[0], y: first[1] } },
          { fun: '/mouse/down', data: {} },
          ...rest.map(([x, y]) => ({ fun: '/mouse/move', data: { x, y } })),
        ],
        finally: [{ fun: '/mouse/up', data: {} }],
        finallyAfter: 1,
      };
    }
    case 'key': return { steps: [{ fun: '/key/sendkey', data: { fn_key: action.key } }] };
    case 'text': {
      const steps = [];
      for (let i = 0; i < action.text.length; i += TEXT_CHUNK) steps.push({ fun: '/key/sendkey', data: { key: action.text.slice(i, i + TEXT_CHUNK) } });
      return { steps };
    }
    case 'resetPointer': return { steps: [{ fun: '/mouse/reset', data: {} }] };
    default: throw new ActionError('Unsupported action.');
  }
}

/** Safe for logs and audit records: never includes typed text. */
export function describeAction(action) {
  switch (action?.type) {
    case 'tap': return `Tap at ${action.x},${action.y}`;
    case 'longPress': return `Long press at ${action.x},${action.y} (${action.holdMs} ms)`;
    case 'drag': return `Drag ${action.points[0].join(',')} → ${action.points.at(-1).join(',')}`;
    case 'key': return `Key ${action.key}`;
    case 'text': return `Typed ${action.text.length} character${action.text.length === 1 ? '' : 's'}`;
    case 'resetPointer': return 'Reset pointer';
    default: return 'Unknown action';
  }
}
