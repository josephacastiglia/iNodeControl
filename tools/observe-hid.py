"""Observe outgoing reports in the authorized iMouse service; never replace arguments.

Uses user-mode API instrumentation, not USB ETW. Restricts capture to 9-byte
output reports. The operator must isolate one phone and avoid concurrent input.
"""
import argparse
import json
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).parent / "protocol-deps"))
import frida

SCRIPT = r"""
const names = ['WriteFile', 'HidD_SetOutputReport'];
for (const name of names) {
  const address = Module.findGlobalExportByName(name);
  if (!address) { send({event:'unavailable', name}); continue; }
  Interceptor.attach(address, {
    onEnter(args) {
      const size = args[2].toUInt32();
      if (size !== 9) return;
      const bytes = args[1].readByteArray(size);
      this.report = {event:'output', api:name, handle:args[0].toString(),
        caller:DebugSymbol.fromAddress(this.returnAddress).toString(),
        hex:Array.from(new Uint8Array(bytes)).map(x=>x.toString(16).padStart(2,'0')).join(' ')};
    },
    onLeave(result) {
      if (this.report) send({...this.report, result:result.toInt32(), lastError:this.lastError});
    }
  });
  send({event:'hook', name, address:address.toString()});
}
send({event:'ready', architecture:Process.arch, modules:Process.enumerateModules().map(m=>m.name)});
"""

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--seconds', type=int, default=120)
    ap.add_argument('--output', required=True)
    args = ap.parse_args()
    destination = pathlib.Path(args.output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    sessions = []
    with destination.open('a', encoding='utf-8', buffering=1) as log:
        def record(pid, message, data):
            entry = {'time':time.time(), 'process':pid, 'message':message}
            log.write(json.dumps(entry)+'\n')
            payload = message.get('payload', {})
            if payload.get('event') != 'output':
                print(json.dumps(entry), flush=True)
        try:
            for process in frida.get_local_device().enumerate_processes():
                if process.name.lower() != 'imservice.exe': continue
                try:
                    session = frida.attach(process.pid)
                    script = session.create_script(SCRIPT)
                    script.on('message', lambda m,d,pid=process.pid: record(pid,m,d))
                    script.load()
                    sessions.append((session,script))
                except Exception as e:
                    print(f'Attach {process.pid}: {e}', flush=True)
            if not sessions: return 1
            time.sleep(args.seconds)
        finally:
            for session,script in sessions:
                try: script.unload(); session.detach()
                except Exception: pass
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
