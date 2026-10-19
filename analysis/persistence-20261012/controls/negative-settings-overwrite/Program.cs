int passed = 0;
void Check(string name, bool ok) { if (!ok) throw new Exception("FAIL: " + name); Console.WriteLine("PASS: " + name); passed++; }
if (args.Length != 1 || args[0] is not ("settings" or "bindings")) return 2;
if (args[0] == "settings") IMouse2.SettingsPersistenceTests.Run(Check);
else IMouse2.Kernel.DeviceStoreTests.Run((ok, name) => Check(name, ok));
Console.WriteLine($"{passed} persistence checks passed; temporary files only.");
return 0;
