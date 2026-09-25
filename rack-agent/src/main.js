#!/usr/bin/env node
// NodeTheory rack agent entry point. Runs on the Windows rack PC next to the kernel.
//
// Configuration (environment variables, or a JSON file passed with --config):
//   NT_PORTAL_URL           wss://portal.example.com/agent   (outbound only)
//   NT_AGENT_CREDENTIAL     "<agentId>.<secret>" issued once by portal staff admin
//   NT_AGENT_CREDENTIAL_FILE path to a file containing that credential (preferred)
//   NT_KERNEL_URL           http://127.0.0.1:9913/api/ (default; must be loopback)
//
// The credential is never logged. Revoking it in the portal disconnects this agent.

import fs from 'node:fs';
import { HttpKernel } from './kernel/http-kernel.js';
import { EncoderPool } from './encoder-pool.js';
import { RackAgent, AGENT_VERSION } from './agent.js';

function loadConfig() {
  const i = process.argv.indexOf('--config');
  const file = i >= 0 ? JSON.parse(fs.readFileSync(process.argv[i + 1], 'utf8')) : {};
  const env = process.env;
  const credential = (file.credentialFile ?? env.NT_AGENT_CREDENTIAL_FILE)
    ? fs.readFileSync(file.credentialFile ?? env.NT_AGENT_CREDENTIAL_FILE, 'utf8').trim()
    : (file.credential ?? env.NT_AGENT_CREDENTIAL ?? '');
  const dot = credential.indexOf('.');
  if (dot <= 0) throw new Error('Set NT_AGENT_CREDENTIAL_FILE (or NT_AGENT_CREDENTIAL) to the credential issued by the portal.');
  return {
    portalUrl: file.portalUrl ?? env.NT_PORTAL_URL ?? '',
    kernelUrl: file.kernelUrl ?? env.NT_KERNEL_URL ?? 'http://127.0.0.1:9913/api/',
    agentId: credential.slice(0, dot),
    secret: credential.slice(dot + 1),
  };
}

const log = {
  info: (...a) => console.log(new Date().toISOString(), ...a),
  warn: (...a) => console.warn(new Date().toISOString(), 'WARN', ...a),
  error: (...a) => console.error(new Date().toISOString(), 'ERROR', ...a),
};

const config = loadConfig();
if (!config.portalUrl) throw new Error('Set NT_PORTAL_URL to the portal agent address (wss://.../agent).');
const kernel = new HttpKernel({ baseUrl: config.kernelUrl });
const encoder = new EncoderPool();
const agent = new RackAgent({ kernel, encoder, portalUrl: config.portalUrl, agentId: config.agentId, secret: config.secret, log });

log.info(`NodeTheory rack agent ${AGENT_VERSION}. Kernel ${config.kernelUrl}. Agent ${config.agentId}.`);
const cap = await kernel.capability().catch(err => ({ compatible: false, reason: err.message, simulated: false }));
if (cap.simulated) log.warn('The kernel reports itself as a SIMULATOR. No real phones are connected.');
if (!cap.compatible) log.warn(`Input disabled until the kernel is compatible: ${cap.reason}`);
await agent.start();

let stopping = false;
async function shutdown() {
  if (stopping) return;
  stopping = true;
  log.info('Stopping: releasing phones and closing the portal link.');
  await agent.stop();
  await encoder.close();
  process.exit(0);
}
process.on('SIGINT', shutdown);
process.on('SIGTERM', shutdown);
