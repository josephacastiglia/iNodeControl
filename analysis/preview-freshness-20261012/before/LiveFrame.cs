using System.Windows;
using System.Windows.Media;
using System.Windows.Media.Imaging;

namespace IMouse2;

/// <summary>
/// One frame converted to top-down pixel order, ready to hand to a WriteableBitmap.
/// Produced on a worker thread so the UI thread only does the final copy.
/// </summary>
public sealed class PreparedFrame
{
    public byte[] Pixels = [];
    public int Width, Height, Stride, Bits;
    public PixelFormat Format => Bits == 32 ? PixelFormats.Bgra32 : PixelFormats.Bgr24;
}

/// <summary>
/// Turns the raw BMP frames from /pic/screenshot?binary=true into a reusable
/// WriteableBitmap.
///
/// Two things matter for smoothness and both are handled here rather than by the
/// caller. First, the conversion is split: <see cref="Prepare"/> runs on a worker
/// thread and does the row-flip (the service sends bottom-up DIBs), while
/// <see cref="Present"/> does nothing but a single WritePixels on the UI thread.
/// Second, buffers are pooled. At 30 fps a 500x1080 frame is about 1.6 MB, so
/// allocating per frame would hand the garbage collector 45 MB/s and cause exactly
/// the periodic hitching this class exists to avoid.
/// </summary>
public sealed class LiveFrame
{
    private WriteableBitmap? _bitmap;
    private readonly Stack<byte[]> _pool = new();
    private readonly object _poolLock = new();

    public BitmapSource? Source => _bitmap;
    public int Width { get; private set; }
    public int Height { get; private set; }
    public long Frames { get; private set; }

    public static bool LooksLikeBmp(ReadOnlySpan<byte> data) => data.Length > 54 && data[0] == 0x42 && data[1] == 0x4D;
    public static bool LooksLikeBmp(byte[] data) => LooksLikeBmp(data.AsSpan());

    private byte[] Rent(int size)
    {
        lock (_poolLock)
        {
            while (_pool.Count > 0)
            {
                var buffer = _pool.Pop();
                if (buffer.Length >= size) return buffer;
            }
        }
        return new byte[size];
    }

    /// <summary>Returns a frame's buffer once it has been drawn, so it can be filled again.</summary>
    public void Recycle(PreparedFrame? frame)
    {
        if (frame?.Pixels is not { Length: > 0 }) return;
        lock (_poolLock) { if (_pool.Count < 4) _pool.Push(frame.Pixels); }
    }

    public PreparedFrame? Prepare(byte[] data) => Prepare(data.AsSpan(), 0);

    /// <summary>
    /// Worker-thread half: validates the BMP and flips it into top-down order.
    ///
    /// <paramref name="maxHeight"/> shrinks the picture on the way through. Wall tiles are
    /// shown a couple of hundred pixels tall, so carrying a full 500x1080 frame through
    /// the compositor for each of them is work nobody can see. Whole blocks of source
    /// pixels are averaged into each output pixel rather than point-sampled: at a five-fold
    /// reduction, picking one pixel in twenty-five makes a phone screen unreadable, while
    /// averaging keeps it legible enough to tell at a glance whether a phone is in step.
    /// Pass 0 to keep the picture at full size. Reduction is by a whole factor, so asking
    /// for more than half the source height leaves the frame at full size rather than
    /// scaling it slightly - which is correct, if not obvious: a fractional box average
    /// would cost more than it saves.
    /// </summary>
    public PreparedFrame? Prepare(ReadOnlySpan<byte> data, int maxHeight = 0)
    {
        if (!LooksLikeBmp(data)) return null;
        int offset = BitConverter.ToInt32(data[10..]);
        int width = BitConverter.ToInt32(data[18..]);
        int rawHeight = BitConverter.ToInt32(data[22..]);
        int bits = BitConverter.ToInt16(data[28..]);
        int height = Math.Abs(rawHeight);
        bool bottomUp = rawHeight > 0;
        if (width <= 0 || height <= 0 || width > 20000 || height > 20000) return null;
        if (bits != 24 && bits != 32) return null;
        if (offset < 54 || offset > data.Length) return null;

        int bytesPerPixel = bits / 8;
        int sourceStride = (width * bytesPerPixel + 3) & ~3;
        if ((long)offset + (long)sourceStride * height > data.Length) return null;

        int step = maxHeight > 0 && height > maxHeight ? Math.Max(1, height / maxHeight) : 1;
        if (step > 1) return Reduce(data, offset, width, height, sourceStride, bytesPerPixel, bottomUp, step);

        int targetStride = width * bytesPerPixel;
        var frame = new PreparedFrame
        {
            Width = width, Height = height, Stride = targetStride, Bits = bits,
            Pixels = Rent(targetStride * height)
        };
        for (int row = 0; row < height; row++)
        {
            int sourceRow = bottomUp ? height - 1 - row : row;
            data.Slice(offset + sourceRow * sourceStride, targetStride).CopyTo(frame.Pixels.AsSpan(row * targetStride));
        }
        return frame;
    }

    /// <summary>Box-averages step x step source blocks into each output pixel, flipping as it goes.</summary>
    private PreparedFrame? Reduce(ReadOnlySpan<byte> data, int offset, int width, int height,
                                  int sourceStride, int bytesPerPixel, bool bottomUp, int step)
    {
        int outW = width / step, outH = height / step;
        if (outW <= 0 || outH <= 0) return null;
        int targetStride = outW * 3;
        var frame = new PreparedFrame
        {
            Width = outW, Height = outH, Stride = targetStride, Bits = 24,
            Pixels = Rent(targetStride * outH)
        };
        var pixels = frame.Pixels;
        int divisor = step * step;
        for (int oy = 0; oy < outH; oy++)
        {
            int target = oy * targetStride;
            for (int ox = 0; ox < outW; ox++)
            {
                int b = 0, g = 0, r = 0;
                for (int dy = 0; dy < step; dy++)
                {
                    int sourceY = oy * step + dy;
                    int row = bottomUp ? height - 1 - sourceY : sourceY;
                    int at = offset + row * sourceStride + ox * step * bytesPerPixel;
                    for (int dx = 0; dx < step; dx++)
                    {
                        b += data[at]; g += data[at + 1]; r += data[at + 2];
                        at += bytesPerPixel;
                    }
                }
                pixels[target] = (byte)(b / divisor);
                pixels[target + 1] = (byte)(g / divisor);
                pixels[target + 2] = (byte)(r / divisor);
                target += 3;
            }
        }
        return frame;
    }

    /// <summary>UI-thread half: one copy into the bitmap the Image is already bound to.</summary>
    public bool Present(PreparedFrame frame)
    {
        if (frame.Width <= 0 || frame.Height <= 0) return false;
        if (_bitmap is null || _bitmap.PixelWidth != frame.Width || _bitmap.PixelHeight != frame.Height || _bitmap.Format != frame.Format)
        {
            _bitmap = new WriteableBitmap(frame.Width, frame.Height, 96, 96, frame.Format, null);
            Width = frame.Width; Height = frame.Height;
        }
        _bitmap.WritePixels(new Int32Rect(0, 0, frame.Width, frame.Height), frame.Pixels, frame.Stride, 0);
        Frames++;
        return true;
    }

    public void Reset()
    {
        _bitmap = null; Width = 0; Height = 0; Frames = 0;
        lock (_poolLock) _pool.Clear();
    }

    /// <summary>
    /// Is this the same picture as last time? The service answers a poll in a few
    /// milliseconds whether or not the mirror advanced, so without this the app would
    /// redraw identical frames continuously.
    ///
    /// This compares every byte. Sampling scattered bytes was tried first and is wrong:
    /// the smallest changes that matter here are tiny — the pointer dot is a few pixels
    /// across — and a sparse probe steps straight over them, so real frames would be
    /// dropped. SequenceEqual is vectorised, and comparing 1.6 MB costs far less than
    /// the fetch that produced it.
    /// </summary>
    public static bool SameAsPrevious(ReadOnlySpan<byte> previous, ReadOnlySpan<byte> current) =>
        previous.Length > 0 && previous.SequenceEqual(current);
    public static bool SameAsPrevious(byte[]? previous, byte[] current) =>
        previous is not null && SameAsPrevious(previous.AsSpan(), current.AsSpan());
}

/// <summary>
/// Compares a small box between two raw BMP frames. Auto-bind uses this to tell which
/// phone reacted to a pointer move: the iOS pointer is a small, low-contrast dot, so a
/// whole-frame diff drowns it in ordinary screen noise, but a box around the exact
/// coordinate the pointer was sent to picks it out reliably.
/// </summary>
public static class FrameRegion
{
    public static double MeanDifference(byte[] a, byte[] b, int centreX, int centreY, int radius)
    {
        if (!TryHeader(a, out int offA, out int w, out int h, out int bppA)) return 0;
        if (!TryHeader(b, out int offB, out int w2, out int h2, out int bppB)) return 0;
        if (w != w2 || h != h2 || bppA != bppB) return 0;

        int bytes = bppA / 8, stride = (w * bytes + 3) & ~3;
        int x0 = Math.Max(0, centreX - radius), x1 = Math.Min(w - 1, centreX + radius);
        int y0 = Math.Max(0, centreY - radius), y1 = Math.Min(h - 1, centreY + radius);
        if (x1 <= x0 || y1 <= y0) return 0;

        long total = 0; int count = 0;
        for (int y = y0; y <= y1; y++)
        {
            // Stored rows are bottom-up; the caller thinks in top-down coordinates.
            int row = h - 1 - y;
            int baseA = offA + row * stride, baseB = offB + row * stride;
            if (baseA + x1 * bytes + 2 >= a.Length || baseB + x1 * bytes + 2 >= b.Length) return 0;
            for (int x = x0; x <= x1; x++)
            {
                int ia = baseA + x * bytes, ib = baseB + x * bytes;
                total += Math.Abs(a[ia] - b[ib]) + Math.Abs(a[ia + 1] - b[ib + 1]) + Math.Abs(a[ia + 2] - b[ib + 2]);
                count += 3;
            }
        }
        return count == 0 ? 0 : (double)total / count;
    }

    private static bool TryHeader(byte[] d, out int offset, out int width, out int height, out int bits)
    {
        offset = width = height = bits = 0;
        if (d is null || d.Length < 54 || d[0] != 0x42 || d[1] != 0x4D) return false;
        offset = BitConverter.ToInt32(d, 10);
        width = BitConverter.ToInt32(d, 18);
        height = Math.Abs(BitConverter.ToInt32(d, 22));
        bits = BitConverter.ToInt16(d, 28);
        return width > 0 && height > 0 && (bits == 24 || bits == 32) && offset >= 54 && offset < d.Length;
    }
}
