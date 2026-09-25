import { parentPort } from 'node:worker_threads';
import jpeg from 'jpeg-js';
import { parseBmp, bmpToRgba } from './bmp.js';

// One job: a kernel BMP plus the preview tiers wanted. Returns one JPEG per tier.
parentPort.on('message', ({ id, bmp, tiers }) => {
  try {
    const parsed = parseBmp(Buffer.from(bmp));
    const out = tiers.map(t => {
      const rgba = bmpToRgba(parsed, t.width);
      const data = jpeg.encode(rgba, t.quality).data;
      return { tier: t.name, width: rgba.width, height: rgba.height, jpeg: data.buffer.slice(data.byteOffset, data.byteOffset + data.length) };
    });
    parentPort.postMessage({ id, ok: true, srcWidth: parsed.width, srcHeight: parsed.height, out }, out.map(o => o.jpeg));
  } catch (err) {
    parentPort.postMessage({ id, ok: false, error: String(err?.message ?? err) });
  }
});
