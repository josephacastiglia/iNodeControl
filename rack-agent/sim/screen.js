import { glyph, GLYPH_W } from './font5x7.js';
import { makeBmp } from '../src/bmp.js';

// Synthetic iPhone-like screen for the SIMULATOR. It reacts to the same input the real
// phone would get (taps open "apps", Home returns, swipes change pages, text appears),
// so the portal can be exercised end to end. Every frame is stamped "SIMULATOR".

export const APPS = ['NOTES', 'CLIPS', 'SHOP', 'CAMERA', 'MAIL', 'MAPS', 'MUSIC', 'PHOTOS',
  'CLOCK', 'FILES', 'NEWS', 'TV', 'BOOKS', 'HEALTH', 'WALLET', 'NOTES 2', 'STUDIO', 'CAST', 'SOCIAL', 'FEED'];

function hsl(h, s, l) {
  const a = s * Math.min(l, 1 - l);
  const f = n => { const k = (n + h / 30) % 12; return Math.round(255 * (l - a * Math.max(-1, Math.min(k - 3, 9 - k, 1)))); };
  return [f(0), f(8), f(4)];
}

export class SimScreen {
  constructor(width, height, hue) {
    this.w = width; this.h = height; this.hue = hue;
    this.rgb = Buffer.alloc(width * height * 3);
    this.state = { page: 0, app: null, overlay: null, text: '', pointer: null, ripple: null, menu: null };
  }

  iconRect(i) {
    const col = i % 4, row = Math.floor(i / 4);
    const size = Math.round(this.w * 0.16), gapX = (this.w - 4 * size) / 5;
    return { x: Math.round(gapX + col * (size + gapX)), y: Math.round(this.h * 0.11 + row * size * 1.75), size };
  }

  hitIcon(x, y) {
    if (this.state.app || this.state.overlay) return -1;
    for (let i = 0; i < 12; i++) {
      const r = this.iconRect(i);
      if (x >= r.x && x < r.x + r.size && y >= r.y && y < r.y + r.size) return i;
    }
    return -1;
  }

  // ---- input effects -------------------------------------------------------
  tap(x, y, now) {
    const s = this.state;
    s.ripple = { x, y, until: now + 700 };
    s.menu = null;
    if (s.overlay) { s.overlay = null; return; }
    const i = this.hitIcon(x, y);
    if (i >= 0) { s.app = APPS[(s.page * 12 + i) % APPS.length]; s.text = ''; }
  }
  longPress(x, y, now) {
    const i = this.hitIcon(x, y);
    this.state.ripple = { x, y, until: now + 700 };
    if (i >= 0) this.state.menu = { i };
  }
  drag(x1, y1, x2, y2, now) {
    const s = this.state;
    s.ripple = { x: x2, y: y2, until: now + 500 };
    if (!s.app && !s.overlay && Math.abs(x2 - x1) > this.w * 0.2 && Math.abs(x2 - x1) > Math.abs(y2 - y1))
      s.page = Math.max(0, Math.min(2, s.page + (x2 < x1 ? 1 : -1)));
    else if (s.app && y1 > this.h * 0.9 && y2 < y1 - this.h * 0.2) s.app = null;
  }
  key(name) {
    const s = this.state;
    s.menu = null;
    if (name === 'Home') { if (s.overlay) s.overlay = null; else if (s.app) s.app = null; else s.page = 0; }
    else if (name === 'ControlBar') s.overlay = 'control';
    else if (name === 'AppSwitch') s.overlay = 'switcher';
    else if (name === 'Backspace') s.text = s.text.slice(0, -1);
    else if (name === 'Enter') s.text += ' / ';
    else if (name === 'Escape') s.overlay = null;
  }
  type(text) { if (this.state.app) this.state.text = (this.state.text + text).slice(-120); }

  // ---- drawing -------------------------------------------------------------
  fill(x, y, w, h, [r, g, b]) {
    const x0 = Math.max(0, x | 0), y0 = Math.max(0, y | 0), x1 = Math.min(this.w, (x + w) | 0), y1 = Math.min(this.h, (y + h) | 0);
    for (let yy = y0; yy < y1; yy++) {
      let d = (yy * this.w + x0) * 3;
      for (let xx = x0; xx < x1; xx++, d += 3) { this.rgb[d] = r; this.rgb[d + 1] = g; this.rgb[d + 2] = b; }
    }
  }
  text(str, x, y, scale, color) {
    let cx = x;
    for (const ch of str) {
      const rows = glyph(ch);
      for (let r = 0; r < 7; r++) for (let c = 0; c < 5; c++)
        if (rows[r] & (0x10 >> c)) this.fill(cx + c * scale, y + r * scale, scale, scale, color);
      cx += GLYPH_W * scale;
    }
  }
  textWidth(str, scale) { return str.length * GLYPH_W * scale; }
  centered(str, y, scale, color) { this.text(str, Math.round((this.w - this.textWidth(str, scale)) / 2), y, scale, color); }

  render(now, label) {
    const { w, h } = this, s = this.state;
    const bg = hsl((this.hue + s.page * 40) % 360, 0.45, 0.32);
    const bg2 = hsl((this.hue + s.page * 40 + 30) % 360, 0.5, 0.18);
    for (let y = 0; y < h; y++) {
      const t = y / h, c = [0, 1, 2].map(k => Math.round(bg[k] * (1 - t) + bg2[k] * t));
      this.fill(0, y, w, 1, c);
    }
    const white = [245, 245, 242], dim = [200, 200, 200];
    const d = new Date(now);
    this.text(`${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`, 30, 22, 3, white);
    this.fill(w - 150, 20, 130, 26, [242, 76, 65]);
    this.text('SIMULATOR', w - 144, 27, 2, white);

    if (s.app) {
      const c = hsl((APPS.indexOf(s.app) * 47) % 360, 0.55, 0.45);
      this.fill(0, 70, w, h - 70, [248, 248, 245]);
      this.fill(0, 70, w, 110, c);
      this.text(s.app, 28, 110, 5, white);
      this.fill(28, 220, w - 56, 70, [255, 255, 255]);
      this.fill(28, 288, w - 56, 2, c);
      const lines = [];
      for (let i = 0; i < s.text.length; i += 18) lines.push(s.text.slice(i, i + 18));
      if (lines.length === 0) this.text('TYPE HERE', 44, 245, 3, [170, 170, 170]);
      lines.slice(-6).forEach((line, i) => this.text(line, 44, 245 + i * 34, 3, [30, 30, 32]));
      this.fill(w / 2 - 70, h - 22, 140, 6, [60, 60, 60]);
    } else {
      for (let i = 0; i < 12; i++) {
        const r = this.iconRect(i), name = APPS[(s.page * 12 + i) % APPS.length];
        this.fill(r.x, r.y, r.size, r.size, hsl((APPS.indexOf(name) * 47) % 360, 0.55, 0.52));
        this.text(name[0], r.x + r.size / 2 - 12, r.y + r.size / 2 - 17, 5, white);
        const label = name.length > 7 ? name.slice(0, 7) : name;
        this.text(label, Math.round(r.x + (r.size - this.textWidth(label, 2)) / 2), r.y + r.size + 10, 2, white);
        if (s.menu?.i === i) {
          this.fill(r.x - 10, r.y + r.size + 40, 230, 120, [250, 250, 250]);
          this.text('EDIT HOME', r.x + 8, r.y + r.size + 62, 2, [30, 30, 32]);
          this.text('SHARE APP', r.x + 8, r.y + r.size + 92, 2, [30, 30, 32]);
          this.text('REMOVE APP', r.x + 8, r.y + r.size + 122, 2, [220, 50, 40]);
        }
      }
      for (let p = 0; p < 3; p++) this.fill(w / 2 - 34 + p * 26, h * 0.82, 12, 12, p === s.page ? white : [120, 120, 120]);
      this.fill(30, h * 0.855, w - 60, 52, [60, 60, 66]);
      this.centered('SEARCH', h * 0.855 + 18, 2, dim);
      this.fill(20, h * 0.915, w - 40, 76, [70, 70, 76]);
    }
    if (s.overlay === 'control') {
      this.fill(20, 80, w - 40, 420, [30, 30, 34]);
      this.text('CONTROL CENTRE', 40, 100, 3, white);
      for (let i = 0; i < 6; i++) this.fill(40 + (i % 3) * 140, 160 + Math.floor(i / 3) * 150, 120, 120, i % 2 ? [242, 76, 65] : [90, 90, 96]);
    } else if (s.overlay === 'switcher') {
      this.fill(0, 70, w, h - 70, [24, 24, 28]);
      this.text('APP SWITCHER', 40, 100, 3, white);
      for (let i = 0; i < 2; i++) this.fill(60 + i * 200, 200, 180, 400, [80 + i * 40, 80, 90]);
    }
    this.text(label, 30, h - 40, 2, [255, 255, 255]);
    if (s.ripple && s.ripple.until > now) {
      const { x, y } = s.ripple;
      this.fill(x - 26, y - 26, 52, 52, [255, 255, 255]);
      this.fill(x - 20, y - 20, 40, 40, [242, 76, 65]);
    } else s.ripple = null;
    if (s.pointer) {
      this.fill(s.pointer.x - 9, s.pointer.y - 9, 18, 18, [40, 40, 40]);
      this.fill(s.pointer.x - 6, s.pointer.y - 6, 12, 12, [220, 220, 220]);
    }
    return makeBmp(w, h, this.rgb);
  }

  get animating() { return !!this.state.ripple; }
}
