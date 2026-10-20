using System.IO;
using System.Net.Http;
using System.Reflection;
using System.Security.Cryptography;
using System.Text.Json;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Interop;
using System.Windows.Threading;

// Headless driver for the native X draft handler. It calls the same Start
// handler as the button without showing a window. dryRun checks the assembly,
// route and zero window handles with no HTTP request. A live run needs the
// prepared private backend on 9915; it never reuses an attempt folder. The live
// output names the bound X handle, so it belongs in the private run folder.
internal static class Program
{
    const BindingFlags Members=BindingFlags.Instance|BindingFlags.NonPublic|BindingFlags.Public;
    static T Field<T>(object o,string name)=>(T)o.GetType().GetField(name,Members)!.GetValue(o)!;
    static async Task Call(object o,string name)
    {
        Func<Task> call=()=>(Task)o.GetType().GetMethod(name,Members)!.Invoke(o,null)!;
        await (Task)o.GetType().GetMethod("RunAsync",Members)!.Invoke(o,[call])!;
        Field<DispatcherTimer>(o,"_poll").Stop();
    }
    [STAThread] static int Main(string[] args)
    {
        if(args.Length!=1)return 2;
        var options=JsonDocument.Parse(File.ReadAllBytes(args[0])).RootElement.Clone();
        string output=options.GetProperty("output").GetString()!;
        bool dry=options.TryGetProperty("dryRun",out var dryValue)&&dryValue.GetBoolean();
        if(Directory.Exists(output))throw new InvalidOperationException("Never reuse an attempt folder.");
        Directory.CreateDirectory(output);
        var app=new Application{ShutdownMode=ShutdownMode.OnExplicitShutdown};
        app.Dispatcher.BeginInvoke(async()=>
        {
            Window? window=null;int code=0;
            var checks=new List<object>();
            void Write(string name,object value)=>File.WriteAllText(Path.Combine(output,name),JsonSerializer.Serialize(value,new JsonSerializerOptions{WriteIndented=true}));
            void Check(string name,bool pass){checks.Add(new{name,pass});Write("checks.json",checks);if(!pass)throw new InvalidOperationException(name);}
            try
            {
                string assembly=options.GetProperty("assembly").GetString()!;
                Check("Prepared candidate assembly",Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(assembly))).ToLowerInvariant()==options.GetProperty("nativeSha256").GetString());
                using var http=new HttpClient{Timeout=TimeSpan.FromSeconds(15)};
                string backend="http://127.0.0.1:9915";
                var loaded=Assembly.LoadFrom(assembly);
                object api=Activator.CreateInstance(loaded.GetType("IMouse2.FarmApiClient",true)!,Members,null,[http,backend],null)!;
                string data=options.GetProperty("dataDirectory").GetString()!;
                if(Directory.Exists(data))throw new InvalidOperationException("Never reuse a native data folder or its pending request.");
                Directory.CreateDirectory(data);
                // (api, dataFolder, draftId, revision, title, createNew, inspectCreationId, reel, tiktok, x)
                window=(Window)Activator.CreateInstance(loaded.GetType("IMouse2.FarmDraftRunWindow",true)!,Members,null,
                    [api,data,options.GetProperty("draftId").GetString()!,options.GetProperty("revision").GetInt32(),"X acceptance",true,null,false,false,true],null)!;
                Check("No desktop window handle",new WindowInteropHelper(window).Handle==IntPtr.Zero);
                Check("X route, capability and bookmark",Field<string>(window,"_route")=="/api/farm/x-creations"&&Field<string>(window,"_capability")=="xCreation"&&Field<string>(window,"_bookmarkPath").EndsWith("farm-pending-x-creation.json"));
                if(dry){Write("result.json",new{dryRun=true,http=false,phoneInput=false});return;}
                using var health=JsonDocument.Parse(await http.GetStringAsync(backend+"/health"));
                var cap=health.RootElement.GetProperty("xCreation");
                Check("Exact isolated source and draft-only C24C X scope on the account signed in first",health.RootElement.GetProperty("sourceHash").GetString()==options.GetProperty("backendSourceHash").GetString()
                    &&cap.GetProperty("enabled").GetBoolean()&&cap.GetProperty("device").GetString()=="C24C"&&cap.GetProperty("account").ValueKind==JsonValueKind.Null
                    &&cap.GetProperty("accountPolicy").GetString()=="first_signed_in"&&cap.GetProperty("format").GetString()=="x_video"&&!cap.GetProperty("publishing").GetBoolean()&&!cap.GetProperty("messaging").GetBoolean());
                await Call(window,"InitializeAsync");
                Write("initial-status.json",new{status=Field<TextBlock>(window,"_status").Text});
                Check("Native X button is eligible",Field<Button>(window,"_start").IsEnabled);
                await Call(window,"StartAsync");
                Check("One durable pending X request",Field<object?>(window,"_pending") is not null);
                var end=DateTime.UtcNow.AddMinutes(16);
                while(!Field<bool>(window,"_terminal")&&DateTime.UtcNow<end)
                {
                    await Task.Delay(1800);await Call(window,"RecoverAsync");
                    Write("status.json",new{status=Field<TextBlock>(window,"_status").Text,utc=DateTime.UtcNow});
                }
                Check("Bounded terminal result",Field<bool>(window,"_terminal"));
                string id=Field<string>(window,"_shownId");
                string raw=await http.GetStringAsync(backend+"/api/farm/x-creations/"+id);File.WriteAllText(Path.Combine(output,"result.json"),raw);
                var result=JsonDocument.Parse(raw).RootElement.GetProperty("run");
                var workflow=result.GetProperty("workflow");
                string? bound=workflow.TryGetProperty("account",out var account)&&account.ValueKind==JsonValueKind.String?account.GetString():null;
                Check("X draft saved, independently reopened, played and kept",result.GetProperty("savedDraftVerified").GetBoolean()&&workflow.GetProperty("createdDraftVerified").GetBoolean());
                Check("Creation and the separate check used the same bound X account",!string.IsNullOrEmpty(bound)&&workflow.GetProperty("verification").GetProperty("account").GetString()==bound
                    &&workflow.GetProperty("accountBinding").GetProperty("method").GetString()=="side_menu_handle");
                Check("Native completion and bookmark agree",Field<object?>(window,"_pending") is null&&Field<TextBlock>(window,"_status").Text.Contains("NEW X DRAFT CREATED AND VERIFIED"));
                Check("No publication, messaging or desktop control",!result.GetProperty("publishing").GetBoolean()&&!result.GetProperty("messaging").GetBoolean()&&new WindowInteropHelper(window).Handle==IntPtr.Zero);
            }
            catch(Exception error){code=1;Write("failure.json",new{error=error.ToString(),utc=DateTime.UtcNow});}
            finally
            {
                if(window is not null)
                {
                    if(!dry&&!Field<bool>(window,"_terminal")&&Field<object?>(window,"_pending") is not null)try{await Call(window,"StopAsync");}catch{}
                    window.GetType().GetField("_terminal",Members)!.SetValue(window,true);Field<DispatcherTimer>(window,"_poll").Stop();window.Close();
                }
                app.Shutdown(code);
            }
        });
        return app.Run();
    }
}
