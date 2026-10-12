param([string]$OutputDirectory = (Join-Path $PSScriptRoot 'release\iMouse2'))
$ErrorActionPreference = 'Stop'
$project = $PSScriptRoot
$source = Join-Path $project 'src\iMouse.Console'
$output = [IO.Path]::GetFullPath($OutputDirectory)
New-Item -ItemType Directory -Path $output -Force | Out-Null
$generated = Join-Path $project '.tools\generated'
New-Item -ItemType Directory -Path $generated -Force | Out-Null

# Use the Roslyn compiler bundled with PowerShell 7. No downloaded packages required.
Add-Type -Path (Join-Path $PSHOME 'Microsoft.CodeAnalysis.dll')
Add-Type -Path (Join-Path $PSHOME 'Microsoft.CodeAnalysis.CSharp.dll')
$desktop = 'C:\Program Files\dotnet\shared\Microsoft.WindowsDesktop.App\8.0.14'
$runtime = 'C:\Program Files\dotnet\shared\Microsoft.NETCore.App\8.0.14'
if (!(Test-Path -LiteralPath $desktop)) { throw '.NET 8.0.14 Windows Desktop runtime was not found. Use a .NET 8 SDK to build the .csproj instead.' }

# Compile ordinary XAML at runtime using WPF's parser. Generate typed fields and
# event wiring so the same authored XAML/code can also be built with the .NET SDK.
$xns = [System.Xml.Linq.XNamespace]'http://schemas.microsoft.com/winfx/2006/xaml'
$pns = [System.Xml.Linq.XNamespace]'http://schemas.microsoft.com/winfx/2006/xaml/presentation'
$xdoc = [System.Xml.Linq.XDocument]::Load((Join-Path $source 'MainWindow.xaml'))
$xdoc.Root.Attribute($xns + 'Class').Remove()
$events = @('Click','TextChanged','SelectionChanged','Checked','Unchecked','MouseLeftButtonDown','MouseLeftButtonUp','LostMouseCapture')
$wiring = [Collections.Generic.List[string]]::new()
$index = 0
foreach ($element in $xdoc.Descendants()) {
    foreach ($event in $events) {
        $attribute = $element.Attribute($event)
        if ($null -ne $attribute) {
            $name = $element.Attribute($xns + 'Name')
            if ($null -eq $name) { $index++; $element.SetAttributeValue($xns + 'Name', "GeneratedEvent$index"); $name = $element.Attribute($xns + 'Name') }
            $wiring.Add("$($name.Value).$event += $($attribute.Value);")
            $attribute.Remove()
        }
    }
}
$fields = [Collections.Generic.List[string]]::new()
$assignments = [Collections.Generic.List[string]]::new()
foreach ($element in $xdoc.Descendants()) {
    $name = $element.Attribute($xns + 'Name')
    $template = @($element.Ancestors() | Where-Object { $_.Name.LocalName -in @('ControlTemplate','DataTemplate') })
    if ($null -ne $name -and $template.Count -eq 0) {
        $fields.Add("internal $($element.Name.LocalName) $($name.Value) = null!;")
        $assignments.Add("$($name.Value) = ($($element.Name.LocalName))shell.FindName(""$($name.Value)"");")
    }
}
$xdoc.Save((Join-Path $generated 'MainWindow.runtime.xaml'))
$appDoc = [System.Xml.Linq.XDocument]::Load((Join-Path $source 'App.xaml'))
$dictionary = [System.Xml.Linq.XElement]::new($pns + 'ResourceDictionary')
$dictionary.SetAttributeValue([System.Xml.Linq.XNamespace]::Xmlns + 'x', $xns.NamespaceName)
foreach ($element in $appDoc.Root.Element($pns + 'Application.Resources').Elements()) { $dictionary.Add([System.Xml.Linq.XElement]::new($element)) }
$dictionary.Save((Join-Path $generated 'Resources.runtime.xaml'))
$bootstrap = @"
global using System;
global using System.Collections.Generic;
global using System.Linq;
global using System.Threading;
global using System.Threading.Tasks;
using System.IO;
using System.Reflection;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Markup;
namespace IMouse2;
public partial class MainWindow {
$($fields -join "`n")
private void InitializeComponent() {
  BeginInit();
  using var stream = Assembly.GetExecutingAssembly().GetManifestResourceStream("MainWindow.xaml")!;
  var shell = (Window)XamlReader.Load(stream);
  $($assignments -join "`n")
  var content = shell.Content; shell.Content = null;
  NameScope.SetNameScope(this, NameScope.GetNameScope(shell));
  Title = shell.Title; Width = shell.Width; Height = shell.Height;
  MinWidth = shell.MinWidth; MinHeight = shell.MinHeight;
  Background = shell.Background; Foreground = shell.Foreground;
  FontFamily = shell.FontFamily; FontSize = shell.FontSize;
  WindowStartupLocation = shell.WindowStartupLocation;
  Content = content;
  $($wiring -join "`n")
  EndInit();
}
}
public partial class App {
 [STAThread] public static void Main() {
   var app = new App();
   using var stream = Assembly.GetExecutingAssembly().GetManifestResourceStream("Resources.xaml")!;
   app.Resources = (ResourceDictionary)XamlReader.Load(stream);
   app.Run();
 }
}
"@
[IO.File]::WriteAllText((Join-Path $generated 'Bootstrap.g.cs'), $bootstrap)
$parseOptions = [Microsoft.CodeAnalysis.CSharp.CSharpParseOptions]::Default.WithLanguageVersion([Microsoft.CodeAnalysis.CSharp.LanguageVersion]::CSharp12)
$trees = [Collections.Generic.List[Microsoft.CodeAnalysis.SyntaxTree]]::new()
foreach ($file in @(Get-ChildItem -LiteralPath $source -Filter '*.cs') + @(Get-Item -LiteralPath (Join-Path $generated 'Bootstrap.g.cs'))) {
    $trees.Add([Microsoft.CodeAnalysis.CSharp.CSharpSyntaxTree]::ParseText([IO.File]::ReadAllText($file.FullName), $parseOptions, $file.FullName))
}
$references = [Collections.Generic.List[Microsoft.CodeAnalysis.MetadataReference]]::new()
$seen = @{}
foreach ($file in @(Get-ChildItem -LiteralPath $desktop -Filter '*.dll') + @(Get-ChildItem -LiteralPath $runtime -Filter '*.dll')) {
    if ($seen.ContainsKey($file.Name)) { continue }
    try { [Reflection.AssemblyName]::GetAssemblyName($file.FullName) | Out-Null; $references.Add([Microsoft.CodeAnalysis.MetadataReference]::CreateFromFile($file.FullName)); $seen[$file.Name] = $true } catch { if ($_.Exception.ToString() -notmatch 'BadImageFormat|assembly manifest') { throw } }
}
$options = [Microsoft.CodeAnalysis.CSharp.CSharpCompilationOptions]::new([Microsoft.CodeAnalysis.OutputKind]::WindowsApplication).WithOptimizationLevel([Microsoft.CodeAnalysis.OptimizationLevel]::Release).WithNullableContextOptions([Microsoft.CodeAnalysis.NullableContextOptions]::Enable)
$compilation = [Microsoft.CodeAnalysis.CSharp.CSharpCompilation]::Create('iMouse2', $trees, $references, $options)
$resources = [Collections.Generic.List[Microsoft.CodeAnalysis.ResourceDescription]]::new()
$windowResourcePath = Join-Path $generated 'MainWindow.runtime.xaml'
$appResourcePath = Join-Path $generated 'Resources.runtime.xaml'
$resources.Add([Microsoft.CodeAnalysis.ResourceDescription]::new('MainWindow.xaml', [Func[IO.Stream]]{[IO.File]::OpenRead($windowResourcePath)}, $true))
$resources.Add([Microsoft.CodeAnalysis.ResourceDescription]::new('Resources.xaml', [Func[IO.Stream]]{[IO.File]::OpenRead($appResourcePath)}, $true))
$dllStream = [IO.File]::Create((Join-Path $output 'iMouse2.dll'))
try { $result = $compilation.Emit($dllStream, $null, $null, $null, $resources) } finally { $dllStream.Dispose() }
$diagnostics = @($result.Diagnostics | ForEach-Object ToString)
$diagnostics | Set-Content -LiteralPath (Join-Path $generated 'compile.log')
if (!$result.Success) { $diagnostics | Write-Output; throw 'Console compilation failed.' }
@{runtimeOptions=@{tfm='net8.0';frameworks=@(@{name='Microsoft.NETCore.App';version='8.0.0'},@{name='Microsoft.WindowsDesktop.App';version='8.0.0'})}} | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $output 'iMouse2.runtimeconfig.json') -Encoding utf8

# A small .NET Framework Windows launcher makes the app double-clickable and
# reports startup failures rather than leaving an invisible console process.
$launcherSource = @'
using System;
using System.Diagnostics;
using System.IO;
using System.Windows.Forms;
class Launcher {
 [STAThread] static int Main(string[] args) {
  try {
   string folder = AppDomain.CurrentDomain.BaseDirectory;
   string dotnet = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles), "dotnet", "dotnet.exe");
   if (!File.Exists(dotnet)) throw new Exception("Install the .NET 8 Windows Desktop Runtime (x64), then open iMouse2 again.");
   string arguments = "\"" + Path.Combine(folder, "iMouse2.dll") + "\"";
   foreach (string arg in args) {
    if (arg == "--self-test" || arg == "--smoke-test" || arg == "--ui-test") arguments += " " + arg;
    // Live test modes no longer read the saved address, so the service has to come through here.
    else if (arg.StartsWith("--address=", StringComparison.Ordinal)) arguments += " \"" + arg + "\"";
   }
   var start = new ProcessStartInfo(dotnet, arguments) { UseShellExecute = false, CreateNoWindow = true, WorkingDirectory = folder, RedirectStandardError = true };
   using (var process = Process.Start(start)) {
    string error = process.StandardError.ReadToEnd(); process.WaitForExit();
    if (process.ExitCode != 0) {
     File.WriteAllText(Path.Combine(folder, "startup-error.txt"), error);
     if (args.Length == 0) MessageBox.Show("iMouse 2.0 could not start.\n" + error, "iMouse 2.0", MessageBoxButtons.OK, MessageBoxIcon.Error);
    }
    return process.ExitCode;
   }
  } catch(Exception ex) { MessageBox.Show(ex.Message, "iMouse 2.0", MessageBoxButtons.OK, MessageBoxIcon.Error); return 1; }
 }
}
'@
$framework = 'C:\Windows\Microsoft.NET\Framework64\v4.0.30319'
$launcherRefs = [Collections.Generic.List[Microsoft.CodeAnalysis.MetadataReference]]::new()
foreach ($name in @('mscorlib.dll','System.dll','System.Windows.Forms.dll')) { $launcherRefs.Add([Microsoft.CodeAnalysis.MetadataReference]::CreateFromFile((Join-Path $framework $name))) }
$launcherTree = [Microsoft.CodeAnalysis.CSharp.CSharpSyntaxTree]::ParseText($launcherSource)
$launcher = [Microsoft.CodeAnalysis.CSharp.CSharpCompilation]::Create('iMouse2.Launcher', [Microsoft.CodeAnalysis.SyntaxTree[]]@($launcherTree), $launcherRefs, $options.WithNullableContextOptions([Microsoft.CodeAnalysis.NullableContextOptions]::Disable))
$exeStream = [IO.File]::Create((Join-Path $output 'iMouse2.exe'))
try { $result = $launcher.Emit($exeStream) } finally { $exeStream.Dispose() }
if (!$result.Success) { $result.Diagnostics | ForEach-Object ToString | Write-Output; throw 'Launcher compilation failed.' }
Write-Output "Built $output\iMouse2.exe"
Write-Output "Compiler diagnostics: $($diagnostics.Count)"
