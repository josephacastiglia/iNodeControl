// Preview streams. Grid tiles use short polls (at most one small request per tile every
// ~1.5 s, only while visible); the focused phone uses a long-poll that returns as soon as
// a newer frame exists. Neither can queue old frames: each request asks for "newer than
// what I have", and the server only ever keeps the latest frame.

import { whenSignedOut } from './api.js';

async function fetchFrame(url, signal) {
  const res = await fetch(url, { credentials: 'same-origin', signal });
  if (res.status === 401) { whenSignedOut.current?.(); throw new Error('signed out'); }
  if (res.status === 204) return null;
  if (!res.ok) throw new Error(`frame ${res.status}`);
  return {
    blob: await res.blob(),
    seq: Number(res.headers.get('x-frame-seq')),
    source: { width: Number(res.headers.get('x-source-width')), height: Number(res.headers.get('x-source-height')) },
    ageMs: Number(res.headers.get('x-frame-age-ms')),
  };
}

function showBlob(img, blob) {
  const url = URL.createObjectURL(blob);
  const old = img.dataset.url;
  img.onload = () => { if (old) URL.revokeObjectURL(old); };
  img.src = url;
  img.dataset.url = url;
}

/** Low-rate preview for a grid tile. */
export function gridPreview(base, img, { intervalMs = 1500, onFrame = () => {} } = {}) {
  let seq = 0, stopped = false, visible = true, timer;
  const abort = new AbortController();
  const io = new IntersectionObserver(entries => { visible = entries.some(e => e.isIntersecting); });
  io.observe(img);
  const tick = async () => {
    if (stopped) return;
    if (visible && document.visibilityState === 'visible') {
      try {
        const f = await fetchFrame(`${base}?tier=grid&after=${seq}&wait=0`, abort.signal);
        if (f) { seq = f.seq; showBlob(img, f.blob); onFrame(f); }
      } catch { /* retried on the next tick */ }
    }
    if (!stopped) timer = setTimeout(tick, intervalMs + Math.random() * 300);
  };
  timer = setTimeout(tick, Math.random() * 400);
  return { stop() { stopped = true; clearTimeout(timer); abort.abort(); io.disconnect(); if (img.dataset.url) URL.revokeObjectURL(img.dataset.url); } };
}

/** Responsive preview for the focused phone. */
export function focusPreview(base, img, { onFrame = () => {}, onIdle = () => {} } = {}) {
  let seq = -1, stopped = false;
  const abort = new AbortController();
  const arrivals = [];
  const stats = { fps: 0, ageMs: 0, source: null };
  (async () => {
    while (!stopped) {
      if (document.visibilityState !== 'visible') { await new Promise(r => setTimeout(r, 500)); continue; }
      try {
        const f = await fetchFrame(`${base}?tier=focus&after=${Math.max(seq, 0)}`, abort.signal);
        if (f) {
          seq = f.seq;
          showBlob(img, f.blob);
          const now = performance.now();
          arrivals.push(now);
          while (arrivals.length && now - arrivals[0] > 3000) arrivals.shift();
          stats.fps = arrivals.length > 1 ? (arrivals.length - 1) / ((now - arrivals[0]) / 1000) : 0;
          stats.ageMs = f.ageMs; stats.source = f.source;
          onFrame(f, stats);
        } else {
          if (seq < 0) seq = 0;
          onIdle(stats);
        }
      } catch {
        if (stopped) return;
        await new Promise(r => setTimeout(r, 2000));
      }
    }
  })();
  return { stats, stop() { stopped = true; abort.abort(); if (img.dataset.url) URL.revokeObjectURL(img.dataset.url); } };
}
