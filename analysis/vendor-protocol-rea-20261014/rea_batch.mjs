// Offline MCP client. Requests are explicit and saved; no vendor execution.
import fs from 'node:fs/promises';
import path from 'node:path';
import { pathToFileURL, fileURLToPath } from 'node:url';
const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, '../../..', '.tooling/imouse-rea-20261014');
const modules = path.join(root, 'rea/node_modules');
const {Client} = await import(pathToFileURL(path.join(modules, '@modelcontextprotocol/client/dist/index.mjs')));
const {StdioClientTransport} = await import(pathToFileURL(path.join(modules, '@modelcontextprotocol/client/dist/stdio.mjs')));
const transport = new StdioClientTransport({command: process.execPath, args:[path.join(modules,'rea-agents/scripts/rea.mjs'),'mcp'], env:{...process.env,
  GHIDRA_INSTALL_DIR:path.join(root,'ghidra/ghidra_12.1.4_PUBLIC'),
  JAVA_HOME:path.join(root,'jdk/jdk-21.0.12.1+1'), REA_ANALYSIS_PROVIDER:'ghidra'}, stderr:'pipe'});
const client = new Client({name:'imouse-offline-audit',version:'1.0.0'}, {capabilities:{}});
const stderr = [];
transport.stderr?.on('data',data=>stderr.push(String(data)));
try {
  await client.connect(transport);
  const catalog = await client.listTools();
  await fs.writeFile(path.join(here,'rea-tool-catalog.json'),JSON.stringify(catalog,null,2));
  if (!process.argv[2]) {
    console.log(JSON.stringify(catalog.tools.filter(t=>/^(open_binary|close_binary|list_procedures|analyze_function|batch_decompile|procedure_references|search_strings|read_bytes|export_evidence_bundle|binary_session)$/.test(t.name)).map(t=>({name:t.name,inputSchema:t.inputSchema})),null,2));
  } else {
    const batch = JSON.parse(await fs.readFile(process.argv[2],'utf8'));
    for (const item of batch) {
      if (!/^(open_binary|close_binary|list_procedures|analyze_function|batch_decompile|procedure_references|search_strings|read_bytes|export_evidence_bundle|binary_session)$/.test(item.tool)) throw new Error('Tool outside static audit allowlist');
      if (path.basename(item.output) !== item.output) throw new Error('Output must be a basename');
      console.log('START '+item.output);
      const result = await client.callTool({name:item.tool,arguments:item.args??{}},undefined,{timeout:600000});
      await fs.writeFile(path.join(here,item.output),JSON.stringify(result,null,2));
      console.log('DONE '+item.output+' error='+!!result.isError);
      if (result.isError) throw new Error('Static analysis tool failed: '+item.tool+' (see '+item.output+')');
    }
  }
} finally {
  await client.close();
  await fs.writeFile(path.join(here,'rea-client-stderr.txt'),stderr.join(''));
}
