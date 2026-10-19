using System.ComponentModel;
using System.Net.Http;
using System.Text;
using System.Text.Json;

namespace IMouse2;

/// <summary>A refusal or failure the service reported. Code is its result code, or -1 when it came from here.</summary>
public sealed class ApiException(string message, int code = -1) : Exception(message)
{
    public int Code { get; } = code;
}

/// <summary>An input command that never left this console: another command's failure or timeout,
/// or a failed ownership renewal, paused its phones while it waited its turn.</summary>
public sealed class InputNotSentException(Exception cause)
    : Exception("Not sent: input was paused by an earlier failure or timeout while this waited.", cause);

/// <summary>How an input sequence ended. Cancelled means this console asked it to stop
/// (Stop, a scope change, disconnect); TimedOut means no answer arrived in time.</summary>
public enum InputEnd { Completed, Cancelled, TimedOut, Failed }

/// <summary>
/// How releasing one phone's possibly held button ended after an input failure. Confirmed means
/// the kernel answered that it closed this console's lease and wrote the button-up report, or had
/// already done so itself. Like every input result it proves the HID write, not what iOS saw.
/// </summary>
public sealed record PhoneCleanup(string Id, bool Confirmed, string Detail);

/// <summary>Managed-input cleanup, not proof of what the phone displayed.</summary>
public sealed record InputCloseResult(IReadOnlyList<PhoneCleanup> Phones, string? Failure = null)
{
    public bool Confirmed => Failure is null && Phones.All(p => p.Confirmed);
    public string Summary => Confirmed
        ? Phones.Count == 0 ? "No managed input leases were held." : "Input release confirmed for this connection."
        : "Input release NOT confirmed: " + string.Join("; ", Phones.Where(p => !p.Confirmed).Select(p => p.Id + ": " + p.Detail)
            .Concat(Failure is null ? [] : new[] { Failure })) + ". Check the affected phones.";
}

/// <summary>
/// The release this console sends at once when a command fails or times out while a button may be
/// down, instead of leaving it held until the lease expires. Elapsed runs from the failure being
/// detected (DetectedAt, a Stopwatch timestamp) to the last answer. Current is false when an
/// operator action or Resume has changed the phones' input state since.
/// </summary>
public sealed record InputCleanup(InputEnd Cause, IReadOnlyList<PhoneCleanup> Phones, TimeSpan Elapsed, long DetectedAt, bool Current)
{
    public bool Confirmed => Phones.All(p => p.Confirmed);
    private string CauseText => Cause == InputEnd.TimedOut ? "request timed out" : "command failed";
    private string Ids => string.Join(", ", Phones.Select(p => p.Id));
    /// <summary>For the activity log.</summary>
    public string Summary => (Current ? "" : "Earlier input failure: ") + (Confirmed
        ? $"Held button released after the {CauseText} on {Ids}; the kernel confirmed it {Elapsed.TotalMilliseconds:0} ms after the failure."
        : $"Button release NOT confirmed after the {CauseText}: " +
          string.Join("; ", Phones.Select(p => p.Id + ": " + (p.Confirmed ? "released" : p.Detail))) +
          ". If the kernel is running it releases the button when the lease expires, within 30 s; Resume input tries the release again.");
    /// <summary>For the input panel, which stays paused until the operator resumes.</summary>
    public string PanelText => $"Input paused: {CauseText}; " +
        (Confirmed ? "held button released (confirmed)" : "button release not confirmed") + ". Check the phone, then choose Resume input.";
}

/// <summary>
/// Outcome of <see cref="ApiClient.SendTextAsync"/>. ConfirmedCharacters counts characters in
/// chunks the kernel answered with code 0: their HID writes finished, which does not prove iOS
/// inserted them. Sent counts chunks that left this console. When Sent &gt; Confirmed, chunk
/// Sent has an unknown outcome and may be partly typed; when they are equal the send ended
/// between chunks and nothing is partial. No chunk after Sent was sent.
/// </summary>
public sealed record TextDelivery(InputEnd End, int ConfirmedCharacters, int Total, int Sent, int Confirmed, int Chunks, Exception? Failure);

public static class JsonValue
{
    public static string Text(JsonElement obj, string name, string fallback = "") =>
        obj.ValueKind == JsonValueKind.Object && obj.TryGetProperty(name, out var v) && v.ValueKind != JsonValueKind.Null ? v.ToString() : fallback;
    public static int Int(JsonElement obj, string name, int fallback = 0) =>
        int.TryParse(Text(obj, name), out var n) ? n : fallback;
}

/// <summary>
/// A control board as reported by /config/usb/get. State 1 means the board is
/// enumerated on the PC only; state 2 means a phone is attached to it. That is
/// the control channel, and it is independent of screen mirroring.
/// </summary>
public sealed record Board(string Vid, string Pid, string Uid, int State)
{
    public bool PhoneAttached => State >= 2;
    public static Board FromJson(JsonElement row) => new(
        JsonValue.Text(row, "vid"), JsonValue.Text(row, "pid"), JsonValue.Text(row, "uid"), JsonValue.Int(row, "state"));
}

public sealed class Device : INotifyPropertyChanged
{
    public string Id { get; init; } = "";
    public string Name { get; init; } = "";
    public string Model { get; init; } = "";
    public string Group { get; init; } = "Ungrouped";
    public string Ip { get; init; } = "";
    public string Os { get; init; } = "";
    public string Hardware { get; init; } = "";
    public bool Online { get; init; }
    public int Width { get; init; }
    public int Height { get; init; }
    public int Rotation { get; init; }
    /// <summary>Mirror stream size in pixels. Screenshots and input use this space.</summary>
    public int ImageWidth { get; init; }
    public int ImageHeight { get; init; }
    /// <summary>Process id of the AirPlay session; non-zero proves the video channel is live.</summary>
    public int AirPid { get; init; }
    /// <summary>mirroring, restarting, failed, or offline. Independent kernel video channel.</summary>
    public string VideoState { get; init; } = "offline";
    public string ReceiverName { get; init; } = "";

    // Set after joining the board list; the control channel is reported separately.
    private int _boardState;
    // Guarded, because this is reassigned for every phone on every five-second poll
    // whether or not it changed, and each unguarded assignment raised three notifications
    // that each ran a full pass over the controls. At a rack of twenty that was sixty
    // pointless UI passes a poll.
    public int BoardState
    {
        get => _boardState;
        set { if (_boardState == value) return; _boardState = value; Notify(nameof(BoardState)); Notify(nameof(ControlStatus)); Notify(nameof(ChannelSummary)); }
    }
    public bool ControlReady => _boardState >= 2;
    public bool VideoReady => Online;
    public string ControlStatus => _boardState >= 2 ? "Control ready" : _boardState == 1 ? "No phone on board" : Hardware.Length == 0 ? "No board bound" : "Board missing";
    public string VideoStatus => VideoState switch
    {
        "mirroring" => "Mirroring",
        "restarting" => "Receiver restarting",
        "failed" => "Receiver failed",
        _ => Online ? "Mirroring" : "Not mirroring"
    };
    public string ChannelSummary => ControlStatus + "  ·  " + VideoStatus;

    public string Status => Online ? "Online" : "Offline";
    public string Subtitle => Model + "  ·  " + Group;
    public string DisplayName => string.IsNullOrWhiteSpace(Name) ? Model + " · " + Id[^Math.Min(5, Id.Length)..] : Name;
    private bool _isChecked;
    public bool IsChecked { get => _isChecked; set { _isChecked = value; Notify(nameof(IsChecked)); } }
    /// <summary>The kernel returns its default group name in Chinese regardless of console language.</summary>
    private static string Translate(string group) => group is "未分组" or "" ? "Ungrouped" : group;
    private void Notify(string name) => PropertyChanged?.Invoke(this, new(name));
    public event PropertyChangedEventHandler? PropertyChanged;
    public static Device FromJson(JsonElement row) => new()
    {
        Id = JsonValue.Text(row, "deviceid"), Name = JsonValue.Text(row, "name", JsonValue.Text(row, "user_name")),
        Model = JsonValue.Text(row, "device_name", "iPhone"), Group = Translate(JsonValue.Text(row, "gname", "Ungrouped")),
        Ip = JsonValue.Text(row, "ip"), Os = JsonValue.Text(row, "version"), Hardware = JsonValue.Text(row, "uid"),
        Online = JsonValue.Int(row, "state") != 0, Width = JsonValue.Int(row, "width"), Height = JsonValue.Int(row, "height"), Rotation = JsonValue.Int(row, "rotate"),
        ImageWidth = JsonValue.Int(row, "imgw"), ImageHeight = JsonValue.Int(row, "imgh"), AirPid = JsonValue.Int(row, "air_pid"),
        VideoState = JsonValue.Text(row, "video_state", JsonValue.Int(row, "state") != 0 ? "mirroring" : "offline"),
        ReceiverName = JsonValue.Text(row,"receiver_name")
    };
}

public sealed class ApiClient : IDisposable, IAsyncDisposable
{
    private readonly HttpClient _http;
    private long _screenshotRequest;
    private readonly InputLeaseClient? _input;
    private readonly object _closeGate = new();
    private readonly TimeSpan _closeTimeout;
    private Task<InputCloseResult>? _closeTask;
    private bool _ownershipVerified;
    public event Action<string>? InputNotice;
    /// <summary>Raised on a pool thread when the release after an input failure has an answer.</summary>
    public event Action<InputCleanup>? InputCleaned;
    public bool UsesInputOwnership => _input is not null;
    // This console's ownership mode uses saved, verified phone/board/receiver
    // assignments. Its kernel deliberately refuses live /device/set changes.
    // This is client policy, not a capability inferred from a reachable port.
    public bool LiveBindingEnabled => !UsesInputOwnership;
    public const string LiveBindingUnavailable = "Board assignments are view-only for this connection. Changes require a verified setup update during maintenance.";
    public const string MirroringActionUnavailable = "Start or stop mirroring on the iPhone using Control Center > Screen Mirroring. Choose that phone's assigned receiver.";
    public const string BoardRestartUnavailable = "Board restart is unavailable in this version. Export diagnostics if control has stopped.";
    public string? UnavailableCommandReason(string function) => !UsesInputOwnership ? null : function switch
    {
        "/device/set" => LiveBindingUnavailable,
        "/device/airplay/connect" or "/device/airplay/disconnect" => MirroringActionUnavailable,
        "/device/usb/restart" => BoardRestartUnavailable,
        _ => null
    };
    public Uri Endpoint { get; }
    public ApiClient(string address, HttpMessageHandler? handler = null, bool? ownership = null, TimeSpan? renewalInterval = null,
        TimeSpan? closeTimeout = null)
    {
        _closeTimeout = closeTimeout ?? TimeSpan.FromSeconds(15);
        if (_closeTimeout <= TimeSpan.Zero || _closeTimeout > TimeSpan.FromSeconds(30))
            throw new ArgumentOutOfRangeException(nameof(closeTimeout), "Cleanup timeout must be positive and no more than 30 seconds.");
        Endpoint = NormalizeEndpoint(address);
        _http = handler is null ? new HttpClient(new HttpClientHandler { UseProxy = false, AllowAutoRedirect = false }) : new HttpClient(handler);
        _http.Timeout = TimeSpan.FromSeconds(8);
        _http.MaxResponseContentBufferSize = 32 * 1024 * 1024;
        if (ownership ?? handler is null)
        {
            _input = new InputLeaseClient(RawCommandAsync, VerifyOwnershipAsync, renewalInterval);
            _input.Notice += message => InputNotice?.Invoke(message);
            _input.Cleaned += cleanup => InputCleaned?.Invoke(cleanup);
        }
    }
    public static Uri NormalizeEndpoint(string address)
    {
        if (!address.Contains("://")) address = "http://" + address;
        if (!Uri.TryCreate(address, UriKind.Absolute, out var uri) || (uri.Scheme != "http" && uri.Scheme != "https") || string.IsNullOrWhiteSpace(uri.Host) || uri.UserInfo.Length > 0 || uri.Query.Length > 0 || uri.Fragment.Length > 0)
            throw new ArgumentException("Enter a service address such as http://127.0.0.1:9911.");
        if (uri.AbsolutePath.Trim('/') is not ("" or "api")) throw new ArgumentException("Use the service address, optionally ending in /api.");
        var b = new UriBuilder(uri) { Path = "/api", Query = "", Fragment = "" };
        if (uri.IsDefaultPort && !address.Contains(":" + uri.Port)) b.Port = 9911;
        return b.Uri;
    }
    public async Task<JsonElement> GetAsync(string function, CancellationToken ct = default)
    {
        using var response = await _http.GetAsync(Endpoint.AbsoluteUri.TrimEnd('/') + function, ct);
        response.EnsureSuccessStatusCode();
        return ReadResult(await response.Content.ReadAsStringAsync(ct));
    }
    private async Task VerifyOwnershipAsync(CancellationToken ct)
    {
        if (_ownershipVerified) return;
        JsonElement status;
        try { status = await GetAsync("/kernel/status", ct).ConfigureAwait(false); }
        catch (Exception ex) when (ex is not OperationCanceledException)
        {
            throw new ApiException("This console needs the ownership-enabled kernel. Input was not sent; keep using the validated desktop app until paired validation.");
        }
        if (JsonValue.Int(status, "input_protocol") != 1 || !status.TryGetProperty("input_leases_required", out var required) || required.ValueKind != JsonValueKind.True)
            throw new ApiException("This console needs the ownership-enabled kernel. Input was not sent; keep using the validated desktop app until paired validation.");
        _ownershipVerified = true;
    }
    public Task<JsonElement> CommandAsync(string function, Dictionary<string, object> data, CancellationToken ct = default)
    {
        if (UnavailableCommandReason(function) is { } reason)
            return Task.FromException<JsonElement>(new ApiException(reason, 41));
        return _input is not null && (function.StartsWith("/mouse/") || function == "/key/sendkey")
            ? _input.CommandAsync(function, data, ct) : RawCommandAsync(function, data, ct);
    }
    private async Task<JsonElement> RawCommandAsync(string function, Dictionary<string, object> data, CancellationToken ct)
    {
        using var body = new StringContent(JsonSerializer.Serialize(new { fun = function, data }), Encoding.UTF8, "application/json");
        using var response = await _http.PostAsync(Endpoint, body, ct);
        response.EnsureSuccessStatusCode();
        return ReadResult(await response.Content.ReadAsStringAsync(ct));
    }
    /// <summary>
    /// Most characters one /key/sendkey carries. The kernel schedules 140 ms of HID timing per
    /// character (170 ms per space) and cancels any command after 8 s, which also stops the phone
    /// until Resume; this client's HTTP timeout is 8 s as well. Under CPU load its delays stretch:
    /// a 32-character chunk ran 8,021 ms live on 26 Sep and was cut, and the kernel's own timing
    /// reached 371 ms a character under oversubscribed load in analysis/input-timeout-candidate-20260925.
    /// 12 characters is about 2 s idle and 4.5 s at that worst rate. No size guarantees completion
    /// under arbitrary load: a chunk that still overruns is reported as timed out and never retried.
    /// </summary>
    public const int TextChunk = 12;
    public static List<string> SplitText(string text) => text.Chunk(TextChunk).Select(c => new string(c)).ToList();
    /// <summary>
    /// Types text as consecutive /key/sendkey commands of at most <see cref="TextChunk"/>
    /// characters, in one input lease. Stops at the first chunk that fails and never resends
    /// it: its outcome is unknown and it may be partly typed. Does not throw once the text is
    /// accepted; the result says how it ended and how far it got.
    /// </summary>
    public async Task<TextDelivery> SendTextAsync(string ids, string text, CancellationToken ct = default)
    {
        if (text.Length == 0) throw new ArgumentException("Enter text to send first.");
        var chunks = SplitText(text);
        var steps = chunks.Select(c => new Dictionary<string, object> { ["id"] = ids, ["key"] = c }).ToList();
        int characters = 0, sent = 0, confirmed = 0;
        void Confirm(int i) { characters += chunks[i].Length; confirmed = i + 1; }
        TextDelivery Result(InputEnd end, Exception? failure) => new(end, characters, text.Length, sent, confirmed, chunks.Count, failure);
        try
        {
            if (_input is not null)
            {
                var (end, failure) = await _input.SequenceAsync("/key/sendkey", steps, i => sent = i + 1, (i, _) => Confirm(i), ct).ConfigureAwait(false);
                return Result(end, failure);
            }
            for (int i = 0; i < steps.Count; i++)
            {
                ct.ThrowIfCancellationRequested();
                sent = i + 1;
                await RawCommandAsync("/key/sendkey", steps[i], ct).ConfigureAwait(false);
                Confirm(i);
            }
            return Result(InputEnd.Completed, null);
        }
        catch (Exception ex)
        {
            // The raw path, or a refusal before the lease client sent anything. As there, a
            // cancellation our token did not request is HttpClient's timeout.
            return Result(ex is not OperationCanceledException ? InputEnd.Failed
                : ct.IsCancellationRequested ? InputEnd.Cancelled : InputEnd.TimedOut, ex);
        }
    }
    public Task StopInputAsync(string ids) => _input?.StopAsync(ids) ?? Task.CompletedTask;
    public Task ResumeInputAsync(string ids) => _input?.ResumeAsync(ids) ?? Task.CompletedTask;
    public Task ReleaseInputAsync(string ids) => _input?.ReleaseAsync(ids) ?? Task.CompletedTask;
    public void ReadyInputScope(string ids) => _input?.ReadyScope(ids);
    public async Task<List<Device>> DevicesAsync(CancellationToken ct = default)
    {
        var data = await GetAsync("/device/get", ct);
        if (!data.TryGetProperty("list", out var rows) || rows.ValueKind != JsonValueKind.Array) throw new ApiException("The service returned an invalid device list.");
        return rows.EnumerateArray().Select(Device.FromJson).Where(x => x.Id.Length > 0).DistinctBy(x => x.Id).ToList();
    }
    public async Task<List<Board>> BoardsAsync(CancellationToken ct = default)
    {
        var data = await GetAsync("/config/usb/get", ct);
        if (!data.TryGetProperty("list", out var rows) || rows.ValueKind != JsonValueKind.Array) return [];
        return rows.EnumerateArray().Select(Board.FromJson).Where(x => x.Uid.Length > 0).ToList();
    }

    /// <summary>
    /// Ties a phone to a control board. vid, pid and the hardware id must all be sent
    /// together, and the kernel only accepts one device at a time for this.
    /// </summary>
    public Task<JsonElement> BindAsync(string deviceId, Board board, CancellationToken ct = default) =>
        CommandAsync("/device/set", new() { ["id"] = deviceId, ["vid"] = board.Vid, ["pid"] = board.Pid, ["uid"] = board.Uid }, ct);

    /// <summary>Clears a phone's board binding, freeing that board for another phone.</summary>
    public Task<JsonElement> UnbindAsync(string deviceId, CancellationToken ct = default) =>
        CommandAsync("/device/set", new() { ["id"] = deviceId, ["vid"] = "", ["pid"] = "", ["uid"] = "" }, ct);

    /// <summary>Moves the pointer. deviceIds may be a comma-separated list; every input
    /// endpoint accepts one, so a mirrored gesture is a single round trip.</summary>
    public Task<JsonElement> MoveAsync(string deviceIds, int x, int y, CancellationToken ct = default) =>
        CommandAsync("/mouse/move", new() { ["id"] = deviceIds, ["x"] = x, ["y"] = y }, ct);

    /// <summary>
    /// Fetches one frame. Raw (uncompressed BMP) is the fast path the live view
    /// uses: the service returns it in about 2 ms versus roughly 40 ms for JPEG,
    /// because no encode step is involved. JPEG stays available for saving and
    /// for slow or remote links where bandwidth matters more than latency.
    /// </summary>
    public async Task<byte[]> ScreenshotAsync(string id, bool jpeg = false, CancellationToken ct = default)
    {
        var url = Endpoint.AbsoluteUri.TrimEnd('/') + "/pic/screenshot?id=" + Uri.EscapeDataString(id) + "&binary=true" + (jpeg ? "&jpg=true" : "");
        using var response = await _http.GetAsync(url, ct);
        response.EnsureSuccessStatusCode();
        var bytes = await response.Content.ReadAsByteArrayAsync(ct);
        if (IsImage(bytes)) return bytes;
        var data = ReadResult(Encoding.UTF8.GetString(bytes));
        var encoded = JsonValue.Text(data, "image");
        try { bytes = Convert.FromBase64String(encoded); } catch (FormatException) { throw new ApiException("The service did not return an image. Start mirroring in iMouse first."); }
        if (!IsImage(bytes)) throw new ApiException("No screen image is available. Start mirroring on the phone.");
        return bytes;
    }
    public const int MaxScreenshotBytes = 64 * 1024 * 1024;
    /// <summary>
    /// Fetches one frame into a reusable buffer instead of a fresh array. Same contract as
    /// <see cref="ScreenshotAsync"/>; see <see cref="FrameBuffer"/> for why it matters.
    /// The full response has one eight-second deadline and a 64 MiB byte limit.
    /// </summary>
    public async Task ScreenshotIntoAsync(string id, bool jpeg, FrameBuffer buffer, CancellationToken ct = default)
    {
        buffer.RequestSerial = Interlocked.Increment(ref _screenshotRequest);
        buffer.Length = 0;
        buffer.Metadata = null; // Reused buffers must never retain another response's evidence.
        long requestStarted = System.Diagnostics.Stopwatch.GetTimestamp();
        // With ResponseHeadersRead, HttpClient's timeout ends at the headers.
        // Keep the same deadline through the complete body; stalled previews must
        // release their request/tile slot even while the connection stays open.
        using var deadline = CancellationTokenSource.CreateLinkedTokenSource(ct);
        deadline.CancelAfter(_http.Timeout);
        var token = deadline.Token;
        var url = Endpoint.AbsoluteUri.TrimEnd('/') + "/pic/screenshot?id=" + Uri.EscapeDataString(id) + "&binary=true" + (jpeg ? "&jpg=true" : "");
        // ResponseHeadersRead, so HttpClient does not buffer the body into an array of its
        // own before handing it over - that would put the allocation straight back.
        using var response = await _http.GetAsync(url, HttpCompletionOption.ResponseHeadersRead, token);
        response.EnsureSuccessStatusCode();
        if (response.Content.Headers.ContentLength > MaxScreenshotBytes)
            throw new ApiException("The screen image exceeds the 64 MiB response limit.");
        if (response.Content.Headers.ContentLength is > 0)
            buffer.Ensure((int)response.Content.Headers.ContentLength.Value);
        try
        {
            using var stream = await response.Content.ReadAsStreamAsync(token);
            int total = 0;
            while (true)
            {
                if (total == MaxScreenshotBytes)
                {
                    // Distinguish an exact-size image from overflow without
                    // growing the reusable buffer beyond its bound.
                    if (await stream.ReadAsync(new byte[1].AsMemory(), token) != 0)
                        throw new ApiException("The screen image exceeds the 64 MiB response limit.");
                    break;
                }
                if (total == buffer.Data.Length) buffer.Ensure(Math.Min(MaxScreenshotBytes, total + (1 << 20)));
                int read = await stream.ReadAsync(buffer.Data.AsMemory(total, Math.Min(buffer.Data.Length, MaxScreenshotBytes) - total), token);
                if (read == 0) break;
                total += read;
                // Ensure copies Length bytes when growing. A chunked response
                // without Content-Length must retain the already-read prefix.
                buffer.Length = total;
            }
            token.ThrowIfCancellationRequested();
            if (!IsImage(buffer.Span))
            {
                // JSON/base64 is a legacy fallback, outside the hot path.
                var data = ReadResult(Encoding.UTF8.GetString(buffer.Data, 0, total));
                byte[] decoded;
                try { decoded = Convert.FromBase64String(JsonValue.Text(data, "image")); }
                catch (FormatException) { throw new ApiException("The service did not return an image. Start mirroring in iMouse first."); }
                if (!IsImage(decoded)) throw new ApiException("No screen image is available. Start mirroring on the phone.");
                buffer.Ensure(decoded.Length);
                decoded.CopyTo(buffer.Data, 0);
                buffer.Length = decoded.Length;
            }
            token.ThrowIfCancellationRequested();
            buffer.Metadata = ScreenshotMetadata.Parse(response.Headers,
                System.Diagnostics.Stopwatch.GetElapsedTime(requestStarted).TotalMilliseconds);
        }
        catch
        {
            buffer.Length = 0; buffer.Metadata = null;
            throw;
        }
    }

    public static bool IsImage(ReadOnlySpan<byte> bytes) => bytes.Length > 8 &&
        ((bytes[0] == 0xFF && bytes[1] == 0xD8) || (bytes[0] == 0x42 && bytes[1] == 0x4D) || (bytes[0] == 0x89 && bytes[1] == 0x50));
    public static bool IsImage(byte[] bytes) => IsImage(bytes.AsSpan());
    public static JsonElement ReadResult(string json)
    {
        try
        {
            using var doc = JsonDocument.Parse(json);
            var root = doc.RootElement;
            if (JsonValue.Int(root, "status", -1) != 200) throw new ApiException("Service error: " + JsonValue.Text(root, "message", "unexpected response"));
            if (!root.TryGetProperty("data", out var data) || data.ValueKind != JsonValueKind.Object) throw new ApiException("The service returned no result data.");
            var code = JsonValue.Int(data, "code", -1);
            if (code != 0) throw new ApiException("Code " + code + ": " + ErrorDescription(code) + " " + JsonValue.Text(data, "message"), code);
            return data.Clone();
        }
        catch (JsonException) { throw new ApiException("The service returned an invalid response. Verify the service address."); }
    }
    private static string ErrorDescription(int code) => code switch
    {
        1 or 7 => "Device not found.", 2 or 23 => "Bind this phone to its control board in iMouse.",
        3 or 13 or 24 => "Check the phone, board and PC connection.", 11 => "Set mouse parameters in iMouse.",
        25 => "Device is offline. Start screen mirroring.", 26 => "Screen capture failed.",
        28 or 29 => "Required phone shortcut/plugin is unavailable.", 30 => "The operation timed out.",
        36 => "Invalid parameters.", 37 => "Sign in through the existing iMouse console.",
        41 => "This command is not supported by the installed service.", _ => "The operation did not complete."
    };
    public void Dispose()
    {
        _ = CloseAsync();
    }
    public async ValueTask DisposeAsync()
    {
        await CloseAsync().ConfigureAwait(false);
    }
    /// <summary>Idempotent, bounded cleanup. Callers must await it before exiting.</summary>
    public Task<InputCloseResult> CloseAsync()
    {
        lock (_closeGate) return _closeTask ??= CloseCoreAsync();
    }
    private async Task<InputCloseResult> CloseCoreAsync()
    {
        InputCloseResult result;
        try
        {
            result = _input is null ? new([])
                : await _input.CloseAsync().WaitAsync(_closeTimeout).ConfigureAwait(false);
        }
        catch (TimeoutException)
        {
            // Disposing HTTP below aborts outstanding network work. A transport that
            // ignores cancellation may finish later; never turn that into a success.
            result = new([], $"cleanup did not finish within {_closeTimeout.TotalSeconds:0.###} seconds");
        }
        catch (Exception ex) { result = new([], "cleanup failed (" + ex.Message + ")"); }
        try { _http.Dispose(); }
        catch (Exception ex) { result = result with { Failure = "HTTP cleanup failed (" + ex.Message + ")" }; }
        return result;
    }
}

public static class CoordinateMapper
{
    // WPF Image uses Uniform: exclude letterbox margins and scale to iOS logical coordinates.
    public static (int X, int Y)? Map(double x, double y, double viewW, double viewH, int imageW, int imageH, int phoneW, int phoneH)
    {
        if (viewW <= 0 || viewH <= 0 || imageW <= 0 || imageH <= 0 || phoneW <= 0 || phoneH <= 0) return null;
        double scale = Math.Min(viewW / imageW, viewH / imageH);
        double w = imageW * scale, h = imageH * scale, left = (viewW - w) / 2, top = (viewH - h) / 2;
        if (x < left || x >= left + w || y < top || y >= top + h) return null;
        return (Math.Clamp((int)((x - left) / w * phoneW), 0, phoneW - 1), Math.Clamp((int)((y - top) / h * phoneH), 0, phoneH - 1));
    }

    /// <summary>
    /// Same mapping, but a point outside the phone is pulled to the nearest edge instead of
    /// being rejected. This is what a gesture in progress needs: a swipe regularly travels
    /// past the edge of the picture, and treating that as "no coordinate" freezes the drag
    /// mid-stroke rather than carrying it to the boundary.
    /// </summary>
    public static (int X, int Y)? MapClamped(double x, double y, double viewW, double viewH, int imageW, int imageH, int phoneW, int phoneH)
    {
        if (viewW <= 0 || viewH <= 0 || imageW <= 0 || imageH <= 0 || phoneW <= 0 || phoneH <= 0) return null;
        double scale = Math.Min(viewW / imageW, viewH / imageH);
        double w = imageW * scale, h = imageH * scale, left = (viewW - w) / 2, top = (viewH - h) / 2;
        if (w <= 0 || h <= 0) return null;
        double cx = Math.Clamp(x, left, left + w - 0.0001);
        double cy = Math.Clamp(y, top, top + h - 0.0001);
        return (Math.Clamp((int)((cx - left) / w * phoneW), 0, phoneW - 1),
                Math.Clamp((int)((cy - top) / h * phoneH), 0, phoneH - 1));
    }
}

/// <summary>
/// A reusable receive buffer for screen frames.
///
/// A 500x1080 frame is about 1.6 MB, well over the 85 KB threshold at which .NET puts an
/// array on the Large Object Heap, so allocating one per fetch makes every frame a
/// large-object allocation. The live view fetches far more frames than it shows, because
/// most polls return a picture identical to the last one, so most of those allocations
/// are thrown away immediately. Measured with a single phone on screen and one tile on
/// the wall: 488 MB/s allocated and 496 gen-2 collections in eight seconds - roughly
/// sixty full collections per second, which is precisely the periodic hitching the frame
/// pipeline is otherwise built to avoid.
///
/// One buffer per pump, refilled in place, removes essentially all of it. The buffer only
/// ever grows, and a screen does not change size, so it settles after the first frame.
/// </summary>
public sealed class FrameBuffer
{
    public byte[] Data { get; private set; } = new byte[1 << 21];
    public int Length { get; internal set; }
    public ScreenshotMetadata? Metadata { get; internal set; }
    public long RequestSerial { get; internal set; }
    public ReadOnlySpan<byte> Span => Data.AsSpan(0, Length);
    public void Ensure(int size)
    {
        if (Data.Length >= size) return;
        var grown = new byte[Math.Max(size, Data.Length * 2)];
        Data.AsSpan(0, Length).CopyTo(grown);
        Data = grown;
    }
}
