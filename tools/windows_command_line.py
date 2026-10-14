"""Parse a Windows command line without executing it or inspecting any window."""


def command_args(command: str) -> list[str]:
    if not command:
        return []
    import ctypes
    from ctypes import wintypes
    shell = ctypes.WinDLL("shell32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    shell.CommandLineToArgvW.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_int)]
    shell.CommandLineToArgvW.restype = ctypes.POINTER(wintypes.LPWSTR)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    count = ctypes.c_int()
    values = shell.CommandLineToArgvW(command, ctypes.byref(count))
    if not values:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return [values[i] for i in range(count.value)]
    finally:
        kernel.LocalFree(ctypes.cast(values, ctypes.c_void_p))
