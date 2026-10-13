"""Make an isolated buffer-alias regression; never modify production files."""
from pathlib import Path
import shutil

record = Path(__file__).resolve().parent
repo = record.parents[1]
target = record / 'negative-alias-source'
target.mkdir()
sources = ('src/iMouse.Kernel/FrameStore.cs', 'src/iMouse.Kernel/AirplaySupervisor.cs',
           'src/iMouse.Console/FrameMetrics.cs', 'tools/frame_tests/Program.cs',
           'tools/frame_tests/ScreenshotHttpTests.cs')
for name in sources:
    shutil.copy2(repo / name, target / Path(name).name)
frame = target / 'FrameStore.cs'
text = frame.read_text(encoding='utf-8-sig')
needle = 'await send(delivery, copy.AsMemory(0, length), token);'
assert text.count(needle) == 1
frame.write_text(text.replace(needle, 'await send(delivery, _current.AsMemory(0, length), token);'), encoding='utf-8')
(target / 'FrameTests.csproj').write_text('<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net8.0</TargetFramework><ImplicitUsings>enable</ImplicitUsings><Nullable>enable</Nullable></PropertyGroup></Project>', encoding='utf-8')
print('Prepared isolated mutation: send a producer-owned buffer instead of the retained copy.')
