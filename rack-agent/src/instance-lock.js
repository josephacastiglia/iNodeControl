import fs from 'node:fs';

// One rack agent per kernel. Two agents on the same kernel would both poll it and fight
// over the portal connection. The lock file holds the owner's PID; a lock left behind by a
// process that no longer exists is taken over.

const alive = pid => {
  try { process.kill(pid, 0); return true; } catch (err) { return err.code === 'EPERM'; }
};

/** Returns a release function, or throws if another live agent holds the lock. */
export function acquireInstanceLock(file) {
  for (let attempt = 0; attempt < 2; attempt++) {
    try {
      const fd = fs.openSync(file, 'wx');
      fs.writeSync(fd, String(process.pid));
      fs.closeSync(fd);
      return () => {
        try { if (fs.readFileSync(file, 'utf8').trim() === String(process.pid)) fs.unlinkSync(file); } catch { /* already gone */ }
      };
    } catch (err) {
      if (err.code !== 'EEXIST') throw err;
      const pid = Number.parseInt(fs.readFileSync(file, 'utf8'), 10);
      if (pid && pid !== process.pid && alive(pid))
        throw new Error(`Another rack agent is already running for this kernel (PID ${pid}). Stop it first. Lock file: ${file}`);
      fs.rmSync(file, { force: true });
    }
  }
  throw new Error(`Could not take the rack agent lock ${file}.`);
}
