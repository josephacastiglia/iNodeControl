"""Create isolated negative controls; never alter the product checkout or run it."""
from pathlib import Path
import hashlib
import json

repo = Path(__file__).resolve().parents[2]
root = Path(__file__).resolve().parent
files = (
    "src/iMouse.Console/SettingsPersistence.cs",
    "src/iMouse.Console/SettingsPersistenceTests.cs",
    "src/iMouse.Kernel/DeviceStore.cs",
    "src/iMouse.Kernel/DeviceStoreTests.cs",
)
project = '<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net8.0-windows</TargetFramework><ImplicitUsings>enable</ImplicitUsings><Nullable>enable</Nullable></PropertyGroup></Project>'
program = '''int passed = 0;
void Check(string name, bool ok) { if (!ok) throw new Exception("FAIL: " + name); Console.WriteLine("PASS: " + name); passed++; }
if (args.Length != 1 || args[0] is not ("settings" or "bindings")) return 2;
if (args[0] == "settings") IMouse2.SettingsPersistenceTests.Run(Check);
else IMouse2.Kernel.DeviceStoreTests.Run((ok, name) => Check(name, ok));
Console.WriteLine($"{passed} persistence checks passed; temporary files only.");
return 0;
'''
records = {}
for variant in ("control-current", "negative-settings-overwrite", "negative-binding-publish"):
    target = root / "controls" / variant
    target.mkdir(parents=True, exist_ok=False)
    for name in files:
        content = (repo / name).read_bytes()
        if variant == "negative-settings-overwrite" and name.endswith("SettingsPersistence.cs"):
            text = content.decode("utf-8")
            assert text.count("File.Move(temp, path, overwrite: true);") == 1
            content = text.replace("File.Move(temp, path, overwrite: true);", "File.WriteAllBytes(path, bytes);").encode("utf-8")
        if variant == "negative-binding-publish" and name.endswith("DeviceStore.cs"):
            text = content.decode("utf-8")
            newline = "\r\n" if "\r\n" in text else "\n"
            old = "            Save(next);" + newline + "            _phones = next;"
            assert old in text
            # Isolate the old publish-before-save defect while retaining the
            # replacement operation that our lock fixture can deliberately fail.
            content = text.replace(old, "            _phones = next;" + newline + "            Save(next);").encode("utf-8")
        (target / Path(name).name).write_bytes(content)
    (target / "PersistenceChecks.csproj").write_text(project, encoding="utf-8")
    (target / "Program.cs").write_text(program, encoding="utf-8")
    (target / "NuGet.Config").write_text('<configuration><packageSources><clear /></packageSources></configuration>', encoding="utf-8")
    records[variant] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(target.iterdir())}
(root / "control-source-hashes.json").write_text(json.dumps(records, indent=2), encoding="utf-8")
print("Prepared three isolated source copies, with exactly one documented mutation per negative control.")
