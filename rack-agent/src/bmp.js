// Kernel frames are uncompressed, bottom-up, 24-bit BMPs (see FrameStore.ValidateBmp
// in src/iMouse.Kernel). This module validates that exact layout and converts it to
// top-down RGBA for JPEG encoding, optionally area-averaged down to a smaller width.

export class BmpError extends Error {}

export function parseBmp(buf) {
  if (!Buffer.isBuffer(buf) || buf.length < 54 || buf[0] !== 0x42 || buf[1] !== 0x4d)
    throw new BmpError('Not a BMP image.');
  const fileSize = buf.readInt32LE(2);
  const offset = buf.readInt32LE(10);
  const headerSize = buf.readInt32LE(14);
  const width = buf.readInt32LE(18);
  const height = buf.readInt32LE(22);
  const planes = buf.readInt16LE(26);
  const bpp = buf.readInt16LE(28);
  const compression = buf.readInt32LE(30);
  if (fileSize !== buf.length || offset !== 54 || headerSize !== 40 || planes !== 1 || bpp !== 24 || compression !== 0)
    throw new BmpError('Expected an uncompressed 24-bit BMP.');
  if (width < 1 || height < 1 || width > 4096 || height > 4096)
    throw new BmpError('Invalid BMP dimensions.');
  const stride = (width * 3 + 3) & ~3;
  if (54 + stride * height !== buf.length) throw new BmpError('Invalid BMP stride.');
  return { width, height, stride, pixels: buf.subarray(54) };
}

/**
 * Converts to top-down RGBA at `targetWidth` (aspect preserved). Downscaling averages
 * every source pixel that falls in each output pixel, so thin UI lines survive.
 */
export function bmpToRgba(bmp, targetWidth = bmp.width) {
  const { width: sw, height: sh, stride, pixels } = bmp;
  const tw = Math.max(1, Math.min(sw, Math.round(targetWidth)));
  const th = Math.max(1, Math.round(sh * tw / sw));
  const out = Buffer.allocUnsafe(tw * th * 4);
  if (tw === sw && th === sh) {
    for (let y = 0; y < sh; y++) {
      let s = (sh - 1 - y) * stride, d = y * sw * 4;
      for (let x = 0; x < sw; x++, s += 3, d += 4) {
        out[d] = pixels[s + 2]; out[d + 1] = pixels[s + 1]; out[d + 2] = pixels[s]; out[d + 3] = 255;
      }
    }
    return { data: out, width: tw, height: th };
  }
  const sumR = new Float64Array(tw), sumG = new Float64Array(tw), sumB = new Float64Array(tw), count = new Float64Array(tw);
  const colOf = new Int32Array(sw);
  for (let x = 0; x < sw; x++) colOf[x] = Math.min(tw - 1, Math.floor(x * tw / sw));
  let ty = 0;
  for (let y = 0; y < sh; y++) {
    const rowTarget = Math.min(th - 1, Math.floor(y * th / sh));
    if (rowTarget !== ty) { flush(ty); ty = rowTarget; }
    let s = (sh - 1 - y) * stride;
    for (let x = 0; x < sw; x++, s += 3) {
      const c = colOf[x];
      sumB[c] += pixels[s]; sumG[c] += pixels[s + 1]; sumR[c] += pixels[s + 2]; count[c]++;
    }
  }
  flush(ty);
  return { data: out, width: tw, height: th };

  function flush(row) {
    let d = row * tw * 4;
    for (let c = 0; c < tw; c++, d += 4) {
      const n = count[c] || 1;
      out[d] = sumR[c] / n; out[d + 1] = sumG[c] / n; out[d + 2] = sumB[c] / n; out[d + 3] = 255;
      sumR[c] = sumG[c] = sumB[c] = count[c] = 0;
    }
  }
}

/** Cheap signature of a frame's pixels: used only to skip re-encoding identical pictures. */
export function frameSignature(bmp) {
  const p = bmp.pixels;
  let h = 2166136261 ^ p.length;
  for (let i = 0; i < p.length; i += 61) { h ^= p[i]; h = Math.imul(h, 16777619); }
  return h >>> 0;
}

/** Builds a bottom-up 24-bit BMP from a top-down RGB painter. Used by the simulator and tests. */
export function makeBmp(width, height, rgbTopDown) {
  const stride = (width * 3 + 3) & ~3;
  const buf = Buffer.alloc(54 + stride * height);
  buf.write('BM', 0, 'ascii');
  buf.writeInt32LE(buf.length, 2);
  buf.writeInt32LE(54, 10);
  buf.writeInt32LE(40, 14);
  buf.writeInt32LE(width, 18);
  buf.writeInt32LE(height, 22);
  buf.writeInt16LE(1, 26);
  buf.writeInt16LE(24, 28);
  for (let y = 0; y < height; y++) {
    const s = y * width * 3, d = 54 + (height - 1 - y) * stride;
    for (let x = 0; x < width; x++) {
      buf[d + x * 3] = rgbTopDown[s + x * 3 + 2];
      buf[d + x * 3 + 1] = rgbTopDown[s + x * 3 + 1];
      buf[d + x * 3 + 2] = rgbTopDown[s + x * 3];
    }
  }
  return buf;
}
