using System.Buffers.Binary;
using System.Net;
using System.Security.Cryptography;
using System.Text.Json;
using IMouse2.Kernel;

// Uses production frame decoding, atomic transfer and metadata serialization.
// No HID code, board enumeration, receiver process or desktop window is involved.
static class FarmEvidenceProbe
{
    public static async Task<int> ExportAsync(string output)
    {
        if (string.IsNullOrWhiteSpace(output) || File.Exists(output)) throw new ArgumentException("Choose a new evidence file.");
        await using var rig = new Rig();
        byte[] frame = Bmp();
        await rig.Send(frame);
        var records = new List<object>();
        await Sample("recent-paired-delivery", 40, 350, "recent", false);
        await Sample("quiet-delivery", 2100, 0, "stale", false);
        await rig.Send(frame);
        await Sample("processing-delay", 0, 2000, "stale", false);
        await rig.Send(frame);
        await Sample("immutable-frame-while-producer-advances", 10, 50, "recent", true);
        Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(output))!);
        await File.WriteAllTextAsync(output, JsonSerializer.Serialize(records, new JsonSerializerOptions { WriteIndented = true }));
        Console.WriteLine($"PASS exported {records.Count} production frame evidence cases. No hardware or network used.");
        return 0;

        async Task Sample(string name, int age, int processing, string expected, bool advance)
        {
            rig.Clock.Advance(age);
            var before = Status(rig.Store.Delivery);
            Dictionary<string, string>? headers = null;
            string? digest = null;
            var result = await rig.Store.TransferFrameAsync("fake", async (delivery, bytes, _) =>
            {
                var collection = new WebHeaderCollection(); FrameStore.WriteMetadata(delivery, collection);
                headers = collection.AllKeys.ToDictionary(key => key, key => collection[key]!);
                var original = SHA256.HashData(bytes.Span);
                if (advance) { var next = Bmp(); next[^1] = 99; await rig.Send(next); }
                rig.Clock.Advance(processing);
                if (!original.AsSpan().SequenceEqual(SHA256.HashData(bytes.Span))) throw new Exception("In-flight bytes changed.");
                digest = Convert.ToHexString(original);
            }, CancellationToken.None);
            if (result != FrameWriteResult.Written) throw new Exception("Frame transfer failed.");
            records.Add(new { name, before, after = Status(rig.Store.Delivery), headers, elapsedMs = processing, expected, sha256 = digest });
        }
    }
    static object Status(FrameDelivery frame) => new { deviceid = "fake", receiver_pid = 1234, receiver_restarts = 0,
        live = frame.Available, frames = frame.Sequence, frame_session = frame.Session };
    static byte[] Bmp()
    {
        byte[] data = new byte[70]; data[0] = (byte)'B'; data[1] = (byte)'M';
        BinaryPrimitives.WriteInt32LittleEndian(data.AsSpan(2), data.Length);
        BinaryPrimitives.WriteInt32LittleEndian(data.AsSpan(10), 54); BinaryPrimitives.WriteInt32LittleEndian(data.AsSpan(14), 40);
        BinaryPrimitives.WriteInt32LittleEndian(data.AsSpan(18), 2); BinaryPrimitives.WriteInt32LittleEndian(data.AsSpan(22), 2);
        BinaryPrimitives.WriteInt16LittleEndian(data.AsSpan(26), 1); BinaryPrimitives.WriteInt16LittleEndian(data.AsSpan(28), 24);
        return data;
    }
}
