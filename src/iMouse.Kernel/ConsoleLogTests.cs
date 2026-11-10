using System.Text;

namespace IMouse2.Kernel;

/// <summary>--console-log: the detached kernel's console output, kept to a bounded size on disk.</summary>
internal static class ConsoleLogTests
{
    public static async Task RunAsync(Action<bool, string> check)
    {
        string folder = Path.Combine(Path.GetTempPath(), "imouse-console-log-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(folder);
        static long Size(string path) => File.Exists(path) ? new FileInfo(path).Length : 0;
        static string[] Lines(string path)
        {
            if (!File.Exists(path)) return [];
            using var stream = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite | FileShare.Delete);
            using var reader = new StreamReader(stream, Encoding.UTF8);
            return reader.ReadToEnd().Split(Environment.NewLine, StringSplitOptions.RemoveEmptyEntries);
        }
        static int FirstByte(string path)
        {
            using var stream = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite | FileShare.Delete);
            return stream.ReadByte();
        }
        const long cap = 2000;
        try
        {
            // As before: output is appended to what an earlier kernel left, as UTF-8 without a byte-order mark.
            string path = Path.Combine(folder, "kernel.console.txt");
            File.WriteAllText(path, "earlier kernel" + Environment.NewLine, new UTF8Encoding(false));
            using (var log = new ConsoleLogFile(path, cap))
            {
                log.WriteLine("Kernel pid 1 started é."); log.Write("part"); log.Write('!'); log.WriteLine();
                check(Lines(path).SequenceEqual(new[] { "earlier kernel", "Kernel pid 1 started é.", "part!" }) && FirstByte(path) == 'e',
                    "Console output is appended to the existing log at once, as UTF-8 without a byte-order mark");

                // Past the cap the file is set aside as .1 and a new one begun; nothing older than that is kept.
                var written = new List<string>();
                long largest = 0;
                for (int i = 0; i < 400; i++)
                {
                    string line = $"line {i:0000} /mouse/move";
                    log.WriteLine(line); written.Add(line);
                    largest = Math.Max(largest, Size(path) + Size(path + ".1"));
                }
                check(File.Exists(path + ".1") && Size(path) <= cap && Size(path + ".1") <= cap, "Past its cap the log is set aside as .1 and a new file begun; neither exceeds the cap");
                check(largest <= 2 * cap, "The log and its one predecessor never take more than twice the cap on disk");
                var kept = Lines(path + ".1").Concat(Lines(path)).Where(l => l.StartsWith("line ")).ToArray();
                check(kept.Length > 0 && kept.SequenceEqual(written.TakeLast(kept.Length)) && kept.Last() == "line 0399 /mouse/move",
                    "What is kept is the most recent output, whole lines in order, with nothing split across the two files");
                check(Lines(path).First().Contains("continues") && Lines(path).First().Contains(".1"), "A new file begins by saying where the earlier output went");

                // A reader that holds the file without allowing a rename (Get-Content -Wait does) must not stop the cap.
                using (var reader = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite))
                {
                    for (int i = 0; i < 400; i++) log.WriteLine($"held {i:0000} /mouse/move");
                    check(Size(path) <= cap, "With a reader blocking the rename the log is started again in place and still stays under the cap");
                }
                log.WriteLine("after the reader left");
                check(Lines(path).Last() == "after the reader left", "Writing goes on after the reader leaves");

                // A log that cannot be written must never stop the kernel.
                string busy = Path.Combine(folder, "busy.txt");
                using var blocked = new ConsoleLogFile(busy, cap);
                blocked.WriteLine("first");
                blocked.Dispose();
                using (var exclusive = new FileStream(busy, FileMode.Open, FileAccess.ReadWrite, FileShare.None))
                {
                    bool threw = false; ConsoleLogFile? shut = null;
                    try { shut = new ConsoleLogFile(busy, cap); shut.WriteLine("while locked"); } catch (Exception) { threw = true; }
                    check(!threw, "A log file another process has locked does not throw into the kernel");
                    exclusive.Dispose();
                    shut!.WriteLine("after the lock"); shut.Dispose();
                }
                check(Lines(busy).SequenceEqual(new[] { "first", "after the lock" }), "Output written while the file was locked is dropped, and logging resumes when it is free");
            }

            // Out and Error share the writer from many threads: every line arrives whole.
            string shared = Path.Combine(folder, "shared.txt");
            static string Line(int thread, int i) => $"thread {thread} line {i:000} " + new string((char)('a' + thread), 40);
            using (var log = new ConsoleLogFile(shared, 1024 * 1024))
            {
                var one = TextWriter.Synchronized(log); var two = TextWriter.Synchronized(log);
                await Task.WhenAll(Enumerable.Range(0, 8).Select(t => Task.Run(() =>
                {
                    for (int i = 0; i < 200; i++) (t % 2 == 0 ? one : two).WriteLine(Line(t, i));
                })));
            }
            var expected = Enumerable.Range(0, 8).SelectMany(t => Enumerable.Range(0, 200).Select(i => Line(t, i))).Order(StringComparer.Ordinal);
            check(Lines(shared).Order(StringComparer.Ordinal).SequenceEqual(expected),
                "Lines written through Out and Error at once from several threads all arrive whole, none interleaved");
        }
        finally { Directory.Delete(folder, recursive: true); }
    }
}
