using System.Net.Http;
using System.Text;
using System.Text.Json;

namespace IMouse2;

internal sealed class FarmRequestRejectedException(string message, int? statusCode = null) : InvalidOperationException(message)
{
    internal int? StatusCode { get; } = statusCode;
}

/// <summary>Versioned farm API. HTTP errors and application failures never look like completion.</summary>
internal sealed class FarmApiClient(HttpClient http, string address)
{
    internal async Task<JsonElement> SendAsync(string path, object? body = null)
    {
        using var request = new HttpRequestMessage(body is null ? HttpMethod.Get : HttpMethod.Post, address + path);
        if (body is not null)
            request.Content = new StringContent(JsonSerializer.Serialize(body), Encoding.UTF8, "application/json");
        using var response = await http.SendAsync(request).ConfigureAwait(false);
        using var document = JsonDocument.Parse(await response.Content.ReadAsStringAsync().ConfigureAwait(false));
        var root = document.RootElement;
        if (!response.IsSuccessStatusCode || root.TryGetProperty("error", out _))
            throw new FarmRequestRejectedException(root.TryGetProperty("error", out var error)
                ? error.GetString() ?? "Farm request refused" : $"Farm request failed: HTTP {(int)response.StatusCode}", (int)response.StatusCode);
        if (!root.TryGetProperty("protocolVersion", out var version) || version.GetInt32() != 2)
            throw new InvalidOperationException("This farm backend is outdated. Use the matching candidate backend.");
        return root.Clone();
    }
}
