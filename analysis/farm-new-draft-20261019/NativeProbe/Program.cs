using System.IO;
using System.Net.Http;
using System.Reflection;
using System.Security.Cryptography;
using System.Text.Json;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Interop;
using System.Windows.Threading;

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
                using var health=JsonDocument.Parse(await http.GetStringAsync(backend+"/health"));
                var cap=health.RootElement.GetProperty("draftCreation");
                Check("Exact isolated source and C24C account",health.RootElement.GetProperty("sourceHash").GetString()==options.GetProperty("backendSourceHash").GetString()&&cap.GetProperty("enabled").GetBoolean()&&cap.GetProperty("device").GetString()=="C24C"&&cap.GetProperty("account").GetString()=="xs.halle.xo"&&!cap.GetProperty("publishing").GetBoolean()&&!cap.GetProperty("messaging").GetBoolean());
                var loaded=Assembly.LoadFrom(assembly);
                object api=Activator.CreateInstance(loaded.GetType("IMouse2.FarmApiClient",true)!,Members,null,[http,backend],null)!;
                string data=options.TryGetProperty("dataDirectory",out var savedData)?savedData.GetString()!:Path.Combine(output,"data");
                window=(Window)Activator.CreateInstance(loaded.GetType("IMouse2.FarmDraftRunWindow",true)!,Members,null,[api,data,options.GetProperty("draftId").GetString()!,options.GetProperty("revision").GetInt32(),"Fresh carousel pilot",true],null)!;
                Directory.CreateDirectory(Path.Combine(output,"data"));
                Check("No desktop window handle",new WindowInteropHelper(window).Handle==IntPtr.Zero);
                await Call(window,"InitializeAsync");
                Write("initial-status.json",new{status=Field<TextBlock>(window,"_status").Text});
                Check("Native create button is eligible",Field<Button>(window,"_start").IsEnabled);
                await Call(window,"StartAsync");
                Check("One durable pending creation",Field<object?>(window,"_pending") is not null);
                var end=DateTime.UtcNow.AddMinutes(15);
                while(!Field<bool>(window,"_terminal")&&DateTime.UtcNow<end)
                {
                    await Task.Delay(1800);await Call(window,"RecoverAsync");
                    Write("status.json",new{status=Field<TextBlock>(window,"_status").Text,utc=DateTime.UtcNow});
                }
                Check("Bounded terminal result",Field<bool>(window,"_terminal"));
                string id=Field<string>(window,"_shownId");
                string raw=await http.GetStringAsync(backend+"/api/farm/draft-creations/"+id);File.WriteAllText(Path.Combine(output,"result.json"),raw);
                var result=JsonDocument.Parse(raw).RootElement.GetProperty("run");
                Check("New media draft saved and independently reopened",result.GetProperty("savedDraftVerified").GetBoolean()&&result.GetProperty("workflow").GetProperty("createdDraftVerified").GetBoolean());
                Check("Native completion and bookmark agree",Field<object?>(window,"_pending") is null&&Field<TextBlock>(window,"_status").Text.Contains("NEW PHONE DRAFT CREATED AND VERIFIED"));
                Check("No publication messaging or desktop control",!result.GetProperty("publishing").GetBoolean()&&!result.GetProperty("messaging").GetBoolean()&&new WindowInteropHelper(window).Handle==IntPtr.Zero);
            }
            catch(Exception error){code=1;Write("failure.json",new{error=error.ToString(),utc=DateTime.UtcNow});}
            finally
            {
                if(window is not null)
                {
                    if(!Field<bool>(window,"_terminal")&&Field<object?>(window,"_pending") is not null)try{await Call(window,"StopAsync");}catch{}
                    window.GetType().GetField("_terminal",Members)!.SetValue(window,true);Field<DispatcherTimer>(window,"_poll").Stop();window.Close();
                }
                app.Shutdown(code);
            }
        });
        return app.Run();
    }
}
