using System.Net;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Windows;
using System.Windows.Interop;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using System.IO;

namespace IMouse2;

public partial class CarouselTransferWindow
{
    private sealed class TransferHandler : HttpMessageHandler
    {
        internal Dictionary<string, object?>? Session;
        internal readonly List<string> Requests = [];
        internal int Starts;
        internal bool LoseStartResponse;
        protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken token)
        {
            string path = request.RequestUri!.AbsolutePath;
            Requests.Add(request.Method + " " + path);
            if (request.Method == HttpMethod.Post && path == "/api/farm/transfers")
            {
                Starts++;
                var data = JsonSerializer.Deserialize<Dictionary<string, JsonElement>>(await request.Content!.ReadAsStringAsync(token))!;
                Session = data.ToDictionary(kv => kv.Key, kv => (object?)kv.Value);
                Session["state"] = "serving";
                Session["url"] = "http://192.168.1.2:9916/t/test-only/";
                Session["secondsRemaining"] = 1200;
                Session["imagesDelivered"] = Array.Empty<string>();
                Session["slideCount"] = 3;
                Session["videoRequests"] = 0;
                Session["instagramStatus"] = "unverified";
                if (LoseStartResponse) throw new HttpRequestException("Response lost after listener started");
            }
            else if (request.Method == HttpMethod.Post && path.EndsWith("/stop") && Session is not null)
            {
                Session["state"] = "closed"; Session["url"] = null; Session["secondsRemaining"] = 0;
            }
            return new(HttpStatusCode.OK) { Content = new StringContent(JsonSerializer.Serialize(new { protocolVersion = 2, transfer = Session }), Encoding.UTF8, "application/json") };
        }
    }

    internal static async Task CheckHeadlessAsync(Action<string, bool> check)
    {
        var handler = new TransferHandler();
        using var http = new HttpClient(handler);
        var api = new FarmApiClient(http, "http://transfer-test.invalid");
        var draft = new CarouselDraft { Id = Guid.NewGuid().ToString(), Revision = 7, Title = "Transfer acceptance", Slides = [new(), new(), new()] };
        var window = new CarouselTransferWindow(api, draft);
        CarouselTransferWindow? reopened = null;
        try
        {
            check("Transfer cannot start until the backend's current session is checked", !window.StartButton.IsEnabled);
            await window.RunAsync(window.RefreshAsync);
            check("Transfer opens without starting a listener or sending input", window.StartButton.IsEnabled && handler.Starts == 0 && handler.Requests.Count == 1);
            window.BindBox.Text = "192.168.1.2"; window.ClientBox.Text = "192.168.1.3"; window.AccountBox.Text = "@test.account";
            handler.LoseStartResponse = true;
            await window.RunAsync(window.StartAsync);
            check("Lost transfer response disables start and requires status recovery", !window.StartButton.IsEnabled && !window._known && handler.Starts == 1);
            await window.RunAsync(window.RefreshAsync);
            check("Status recovers the existing transfer without another start", handler.Starts == 1 && window._active && window.StopButton.IsEnabled && window.UrlBox.Text.Contains("/t/test-only/"));
            check("Transfer locks addresses and account while serving", !window.Setup.IsEnabled && !window.StartButton.IsEnabled);
            handler.Session!["imagesDelivered"] = new[] { "01.jpg", "02.jpg", "03.jpg" };
            await window.RunAsync(window.RefreshAsync);
            check("Complete image delivery never claims Instagram saved a draft", window.DeliveryText.Text.Contains("3 / 3") && window.DeliveryText.Text.Contains("unverified"));
            reopened = new CarouselTransferWindow(api, new CarouselDraft { Id = draft.Id, Revision = 8, Title = "Edited revision" });
            await reopened.RunAsync(reopened.RefreshAsync);
            check("Reopened transfer identifies a different saved revision and does not replace it", reopened.StatusText.Text.Contains("different saved draft/revision") && !reopened.StartButton.IsEnabled && handler.Starts == 1);
            await reopened.RunAsync(reopened.StartAsync);
            check("Starting again while a recovered transfer is active does not send a start", handler.Starts == 1);
            var content = (FrameworkElement)window.Content;
            content.Measure(new Size(640, 700)); content.Arrange(new Rect(0, 0, 640, 700)); content.UpdateLayout();
            var bitmap = new RenderTargetBitmap(640, 700, 96, 96, PixelFormats.Pbgra32);
            var background = new DrawingVisual();
            using (var draw = background.RenderOpen()) draw.DrawRectangle(window.Background, null, new Rect(0, 0, 640, 700));
            bitmap.Render(background); bitmap.Render(content);
            var encoder = new PngBitmapEncoder(); encoder.Frames.Add(BitmapFrame.Create(bitmap));
            string qa = Path.Combine(AppContext.BaseDirectory, "qa"); Directory.CreateDirectory(qa);
            using (var output = File.Create(Path.Combine(qa, "carousel-transfer-headless.png"))) encoder.Save(output);
            check("Transfer view renders without desktop control or a native window", content.IsArrangeValid && new WindowInteropHelper(window).Handle == IntPtr.Zero && !window.IsVisible);
            await reopened.RunAsync(reopened.StopAsync);
            check("Stop removes the expiring link and enables a new explicit transfer", !reopened._active && reopened.UrlBox.Text == "" && reopened.StartButton.IsEnabled);
            handler.Session!["state"] = "interrupted";
            handler.Session["error"] = "Backend restarted. Check the phone.";
            await window.RunAsync(window.RefreshAsync);
            check("Backend restart is reported without silently restarting transfer", window.StatusText.Text.Contains("interrupted") && window.UrlBox.Text == "" && handler.Starts == 1);
            check("Transfer UI only uses media-session routes, never input or publishing", handler.Requests.All(r => r.Contains("/api/farm/transfers")));
            var videoData = JsonSerializer.SerializeToElement(new { id = Guid.NewGuid().ToString(), revision = 1, title = "Draft-only video", platform = "YouTube" });
            var videoWindow = new CarouselTransferWindow(api, videoData);
            try
            {
                handler.LoseStartResponse = false;
                await videoWindow.RunAsync(videoWindow.RefreshAsync);
                videoWindow.BindBox.Text = "192.168.1.2"; videoWindow.ClientBox.Text = "192.168.1.3"; videoWindow.AccountBox.Text = "test.account";
                await videoWindow.RunAsync(videoWindow.StartAsync);
                check("Video transfer starts the video media kind, separate from carousel", handler.Session!["kind"] is JsonElement kind && kind.GetString() == "video");
                handler.Session!["videoRequests"] = 4;
                await videoWindow.RunAsync(videoWindow.RefreshAsync);
                check("Partial video requests never imply a saved app draft", videoWindow.DeliveryText.Text.Contains("4 video requests (may be partial)") && videoWindow.DeliveryText.Text.Contains("unverified"));
                check("Video instructions identify the platform and forbid upload", videoWindow.AccountLabel.Text == "YouTube account" && videoWindow.PhoneInstructions.Text.Contains("Do not tap Post, Share or Upload"));
                await videoWindow.RunAsync(videoWindow.StopAsync);
                check("Video transfer shares confirmed Stop and link cleanup", !videoWindow._active && videoWindow.UrlBox.Text == "");
            }
            finally { videoWindow._closing = true; videoWindow._timer.Stop(); videoWindow.Close(); }
        }
        finally
        {
            window._closing = true; window._timer.Stop(); window.Close();
            if (reopened is not null) { reopened._closing = true; reopened._timer.Stop(); reopened.Close(); }
        }
    }
}
