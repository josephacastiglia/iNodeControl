// Maps pointer positions on the preview to the phone's source image coordinates, the
// same space the kernel's input uses (its calibrated image, e.g. 500×1080). The preview
// is letterboxed with object-fit: contain and may be a downscaled JPEG, so the mapping
// uses the displayed box, the JPEG's aspect ratio and the source size separately.
// Pure functions: unit-tested in Node (test/coords.test.mjs).

/** Where the picture actually sits inside its box after `object-fit: contain`. */
export function contentRect(boxWidth, boxHeight, imageWidth, imageHeight) {
  if (!(boxWidth > 0 && boxHeight > 0 && imageWidth > 0 && imageHeight > 0)) return null;
  const scale = Math.min(boxWidth / imageWidth, boxHeight / imageHeight);
  const width = imageWidth * scale, height = imageHeight * scale;
  return { left: (boxWidth - width) / 2, top: (boxHeight - height) / 2, width, height };
}

/**
 * @param {number} x pointer x relative to the box
 * @param {number} y pointer y relative to the box
 * @param {{width:number,height:number}} box displayed element size
 * @param {{width:number,height:number}} picture displayed image intrinsic size (JPEG)
 * @param {{width:number,height:number}} source kernel image size
 * @param {boolean} clamp pull outside points to the nearest edge (drags) instead of rejecting (taps)
 */
export function toSource(x, y, box, picture, source, clamp = false) {
  const r = contentRect(box.width, box.height, picture.width, picture.height);
  if (!r || !(source.width > 0 && source.height > 0)) return null;
  let u = (x - r.left) / r.width, v = (y - r.top) / r.height;
  if (!clamp && (u < 0 || v < 0 || u >= 1 || v >= 1)) return null;
  u = Math.min(Math.max(u, 0), 0.999999); v = Math.min(Math.max(v, 0), 0.999999);
  return { x: Math.min(source.width - 1, Math.floor(u * source.width)), y: Math.min(source.height - 1, Math.floor(v * source.height)) };
}

/** Inverse mapping, for drawing feedback at a source coordinate. */
export function fromSource(sx, sy, box, picture, source) {
  const r = contentRect(box.width, box.height, picture.width, picture.height);
  if (!r) return null;
  return { x: r.left + (sx + 0.5) / source.width * r.width, y: r.top + (sy + 0.5) / source.height * r.height };
}

/** Keeps the first and last point and evenly samples the rest down to `max` points. */
export function simplifyPath(points, max = 24) {
  const dedup = points.filter((p, i) => i === 0 || p[0] !== points[i - 1][0] || p[1] !== points[i - 1][1]);
  if (dedup.length <= max) return dedup;
  const out = [];
  for (let i = 0; i < max; i++) out.push(dedup[Math.round(i * (dedup.length - 1) / (max - 1))]);
  return out;
}

/**
 * Turns a finished pointer gesture into one supported action.
 * Small movement: tap, or long press if held. Otherwise a drag along the path.
 */
export function classifyGesture(points, heldMs, { slop = 10, longPressMs = 500 } = {}) {
  if (!points.length) return null;
  const [x0, y0] = points[0];
  const moved = points.some(([x, y]) => Math.hypot(x - x0, y - y0) > slop);
  if (!moved) {
    if (heldMs >= longPressMs) return { type: 'longPress', x: x0, y: y0, holdMs: Math.min(3000, Math.max(500, Math.round(heldMs))) };
    return { type: 'tap', x: x0, y: y0 };
  }
  const path = simplifyPath(points);
  return path.length >= 2 ? { type: 'drag', points: path } : { type: 'tap', x: x0, y: y0 };
}

/** Preset swipes as drags across the middle of the screen (70% of the shorter axis travel). */
export function presetSwipe(direction, source) {
  const cx = Math.floor(source.width / 2), cy = Math.floor(source.height / 2);
  const dx = Math.floor(source.width * 0.35), dy = Math.floor(source.height * 0.3);
  const ends = { up: [[cx, cy + dy], [cx, cy - dy]], down: [[cx, cy - dy], [cx, cy + dy]], left: [[cx + dx, cy], [cx - dx, cy]], right: [[cx - dx, cy], [cx + dx, cy]] }[direction];
  if (!ends) return null;
  const [[x1, y1], [x2, y2]] = ends;
  const steps = 6;
  return { type: 'drag', points: Array.from({ length: steps + 1 }, (_, i) => [Math.round(x1 + (x2 - x1) * i / steps), Math.round(y1 + (y2 - y1) * i / steps)]) };
}

/** Mirrors the kernel's accepted keyboard alphabet (US ASCII 32–126). */
export function textProblem(text, max = 200) {
  if (!text) return 'Enter some text to type.';
  if (text.length > max) return `Type at most ${max} characters at a time.`;
  for (const ch of text) { const c = ch.codePointAt(0); if (c < 32 || c > 126) return `“${ch}” can’t be typed. Use English (US) letters, numbers, spaces and standard punctuation.`; }
  return null;
}
