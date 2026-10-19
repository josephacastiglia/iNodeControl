using System.Net;
using System.Net.Http;
using System.Text;

namespace IMouse2;

internal static class BindingPolicyTests
{
    private sealed class ReadOnlyHandler : HttpMessageHandler
    {
        internal readonly List<string> Requests = [];
        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken ct)
        {
            Requests.Add(request.Method + " " + request.RequestUri!.AbsolutePath);
            if (request.Method != HttpMethod.Get) throw new InvalidOperationException("Unexpected write in read-only binding check");
            return Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK)
            {
                Content = new StringContent("{\"status\":200,\"data\":{\"code\":0,\"list\":[]}}", Encoding.UTF8, "application/json")
            });
        }
    }

    internal static async Task RunAsync(Action<string, bool> check)
    {
        var handler = new ReadOnlyHandler();
        await using var owned = new ApiClient("http://localhost:9923", handler, ownership: true);
        check("Ownership mode makes board assignments view-only before any request", !owned.LiveBindingEnabled && handler.Requests.Count == 0);
        var board = new Board("720A", "ABCD", "TEST-BOARD", 2);
        async Task Refused(string name, Func<Task> action)
        {
            ApiException? refusal = null;
            try { await action(); }
            catch (ApiException ex) { refusal = ex; }
            check(name, refusal is { Code: 41 } && refusal.Message == ApiClient.LiveBindingUnavailable);
        }
        await Refused("Binding a board explains the saved-setup requirement", () => owned.BindAsync("TEST:01", board));
        await Refused("Unbinding a board uses the same view-only policy", () => owned.UnbindAsync("TEST:01"));
        await Refused("The general command path cannot bypass the binding policy",
            () => owned.CommandAsync("/device/set", new() { ["id"] = "TEST:01", ["uid"] = "TEST-BOARD" }));
        check("Refused binding actions send no POST, discovery request or lease acquisition", handler.Requests.Count == 0);
        check("View-only binding mode still reads the phone list", (await owned.DevicesAsync()).Count == 0);
        check("View-only binding mode still reads the board list", (await owned.BoardsAsync()).Count == 0);
        check("Assignment inspection uses only the two read-only routes", handler.Requests.SequenceEqual(new[] { "GET /api/device/get", "GET /api/config/usb/get" }));

        var legacyHandler = new TestHandler();
        using var legacy = new ApiClient("http://localhost:9923", legacyHandler, ownership: false);
        check("Explicit legacy mode retains its binding behavior without changing another client's policy", legacy.LiveBindingEnabled && !owned.LiveBindingEnabled);
        await legacy.BindAsync("TEST:01", board);
        await legacy.UnbindAsync("TEST:01");
        check("Legacy binding still sends the selected board and explicit unbind", legacyHandler.Commands.Count == 2
            && legacyHandler.Commands[0].GetProperty("data").GetProperty("uid").GetString() == board.Uid
            && legacyHandler.Commands[1].GetProperty("data").GetProperty("uid").GetString() == "");
    }
}
