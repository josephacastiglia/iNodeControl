using System.Diagnostics;
using System.IO;
using System.Text.Json;
using IMouse2.Kernel;

namespace IMouse2.Harness;

/// <summary>
/// Measures how long the kernel's own /key/sendkey takes per chunk size under CPU load: the real
/// InputRouter with its unchanged per-character timing, on a simulated board (so no HID write time;
/// a real board adds that). Load comes from spinning threads at normal priority. This informs the
/// console's chunk size; it does not prove any size completes under arbitrary load.
/// </summary>
static class ChunkTiming
{
    // Mixed text like an operator's, spaces included (a space strokes 170 ms, other characters 140 ms).
    const string Sample = "The quick brown fox jumps over the lazy dog 0123456789! Pack my box with five dozen liquor jugs. ";

    public static async Task<int> RunAsync(string output, int reps, int[]? sizesArg = null, int[]? multipliers = null)
    {
        int cores = Environment.ProcessorCount;
        int[] sizes = sizesArg ?? [8, 12, 16, 20, 24, 32];
        var loads = (multipliers ?? [0, 1, 2]).Select(m => (Name: m == 0 ? "idle" : $"{m * cores} spinning threads ({m}x cores)", Threads: m * cores)).ToArray();
        string dir = Path.Combine(Path.GetTempPath(), "imouse-chunk-timing-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(dir);
        string file = Path.Combine(dir, "devices.json");
        File.WriteAllText(file, JsonSerializer.Serialize(new[] { new Phone { deviceid = "SIM:01", pid = "F001", uid = "SIM" } }));
        var board = new Board();
        using var input = new InputRouter(new DeviceStore(file), ["F001"], [new PointerCalibration("F001", 500, 1080, 14, 14, 5, 5)], _ => board);
        var rows = new List<object>();
        int offset = 0;
        try
        {
            foreach (var (name, threads) in loads)
            {
                using var stop = new CancellationTokenSource();
                var spinners = Enumerable.Range(0, threads).Select(_ => new Thread(() => { while (!stop.IsCancellationRequested) { } }) { IsBackground = true }).ToList();
                spinners.ForEach(t => t.Start());
                await Task.Delay(500);
                foreach (int size in sizes)
                {
                    var ms = new List<double>();
                    for (int r = 0; r < reps; r++)
                    {
                        string text = string.Concat(Enumerable.Repeat(Sample, 3)).Substring(offset++ % Sample.Length, size);
                        var data = JsonSerializer.SerializeToElement(new { id = "SIM:01", key = text });
                        long t0 = Stopwatch.GetTimestamp();
                        await input.DispatchAsync("/key/sendkey", data);
                        ms.Add(Stopwatch.GetElapsedTime(t0).TotalMilliseconds);
                    }
                    ms.Sort();
                    var row = new { load = name, chars = size, runs = reps, p50_ms = Math.Round(ms[ms.Count / 2]), max_ms = Math.Round(ms[^1]),
                        max_ms_per_char = Math.Round(ms[^1] / size, 1), all_ms = ms.Select(v => Math.Round(v)).ToArray() };
                    rows.Add(row);
                    Console.WriteLine($"{name,-32} {size,3} chars  p50 {row.p50_ms,6} ms  max {row.max_ms,6} ms  ({row.max_ms_per_char} ms/char)");
                }
                stop.Cancel();
                spinners.ForEach(t => t.Join());
            }
        }
        finally { try { Directory.Delete(dir, true); } catch { } }
        File.WriteAllText(output, JsonSerializer.Serialize(new { simulated_board = true, cores, at = DateTime.Now, rows }, new JsonSerializerOptions { WriteIndented = true }));
        Console.WriteLine("results in " + output);
        return 0;
    }
}
