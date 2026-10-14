internal static class CaptureArguments
{
    internal static bool TryParse(string[] args, out int seconds)
    {
        seconds = 0;
        return args.Length == 4 && args[0] == "--pid" && args[1] == "C24C" && args[2] == "--seconds"
            && int.TryParse(args[3], out seconds) && seconds is >= 1 and <= 120;
    }
    internal static void Test()
    {
        foreach (string[] args in new[] {
            new[] { "--pid", "C241", "--seconds", "1" },
            new[] { "--pid", "C24C,C241", "--seconds", "1" },
            new[] { "--pid", "C24C", "--seconds", "0" },
            new[] { "--pid", "C24C", "--seconds", "121" },
            new[] { "--pid", "C24C" } })
            if (TryParse(args, out _)) throw new Exception("Unsafe capture arguments accepted");
        if (!TryParse(["--pid", "C24C", "--seconds", "25"], out int seconds) || seconds != 25)
            throw new Exception("Valid C24C capture arguments rejected");
    }
}
