// Stands in for the Rust shell during end-to-end tests: starts the real Python
// engines hidden, relays calls over HTTP, streams progress, and serves files.
import { spawn } from "node:child_process";
import { createReadStream, existsSync, statSync } from "node:fs";
import { createServer } from "node:http";
import { extname, join, resolve } from "node:path";
import { createInterface } from "node:readline";

const ROOT = resolve(import.meta.dirname, "..", "..");
const PYTHON = process.env.FREEPDF_PY ?? join(process.env.LOCALAPPDATA, "FreePDF-dev", "venv", "Scripts", "python.exe");
const PORT = Number(process.env.BRIDGE_PORT ?? 5181);
const VIEWER_TOOLS = new Set(["info", "thumb", "page_text", "search"]);
const TYPES = { ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".svg": "image/svg+xml", ".pdf": "application/pdf" };

const sseClients = new Set();
function broadcast(event, payload) {
  const line = `data: ${JSON.stringify({ event, payload })}\n\n`;
  for (const res of sseClients) res.write(line);
}

function startEngine(role) {
  const child = spawn(PYTHON, ["-X", "utf8", "-m", "freepdf_engine", role], {
    cwd: join(ROOT, "engine"),
    env: { ...process.env, PYTHONUTF8: "1", PYTHONIOENCODING: "utf-8" },
    stdio: ["pipe", "pipe", "pipe"],
    windowsHide: true,
  });
  const pending = new Map();
  const stderr = [];
  child.stderr.on("data", (chunk) => stderr.push(chunk.toString()));
  createInterface({ input: child.stdout }).on("line", (line) => {
    let msg;
    try { msg = JSON.parse(line); } catch { return; }
    if (msg.type === "progress") return broadcast("engine-progress", msg);
    const done = pending.get(msg.id);
    if (!done) return;
    pending.delete(msg.id);
    if (msg.type === "result") done({ ok: true, value: { outputs: msg.outputs, summary: msg.summary } });
    else done({ ok: false, value: { code: msg.code ?? "tool_failed", message: msg.message ?? "Something went wrong." } });
  });
  child.on("exit", () => {
    for (const done of pending.values()) done({ ok: false, value: { code: "engine_stopped", message: "Engine stopped." } });
    pending.clear();
  });
  return {
    pending,
    stderr,
    call(id, tool, args) {
      return new Promise((done) => {
        pending.set(id, done);
        child.stdin.write(`${JSON.stringify({ id, tool, args })}\n`);
      });
    },
    cancel(id) {
      if (!pending.has(id)) return false;
      child.stdin.write(`${JSON.stringify({ cancel: id })}\n`);
      return true;
    },
    stop() { child.kill(); },
  };
}

const engines = { viewer: startEngine("viewer"), jobs: startEngine("jobs") };
const opened = [];
let counter = 0;

const SHARE = {
  share_info: () => ({ ok: true, value: { id: "self", name: "Test PC", port: 47800, addresses: ["192.168.1.10"], receiveDir: "C:/Users/Test/Downloads/Free PDF" } }),
  share_peers: () => ({ ok: true, value: [] }),
  share_set_name: () => ({ ok: true, value: null }),
  share_add_peer: (a) => ({ ok: false, value: { code: "unreachable", message: `No Free PDF answered at ${a.address}.` } }),
  share_send: () => ({ ok: true, value: "t1" }),
  share_cancel: () => ({ ok: true, value: true }),
  share_answer: () => ({ ok: true, value: true }),
};

async function handleInvoke(cmd, args) {
  if (cmd === "engine_call") {
    const engine = VIEWER_TOOLS.has(args.tool) ? engines.viewer : engines.jobs;
    return engine.call(args.id ?? `b${++counter}`, args.tool, args.args ?? {});
  }
  if (cmd === "engine_cancel") return { ok: true, value: engines.viewer.cancel(args.id) || engines.jobs.cancel(args.id) };
  if (cmd === "startup_file") return { ok: true, value: null };
  if (cmd === "ui_ready") return { ok: true, value: null };
  if (cmd.startsWith("plugin:opener|")) {
    opened.push({ cmd, args });
    return { ok: true, value: null };
  }
  if (SHARE[cmd]) return SHARE[cmd](args);
  return { ok: false, value: { code: "unknown_command", message: `Bridge does not know ${cmd}` } };
}

function readBody(req) {
  return new Promise((done) => {
    const parts = [];
    req.on("data", (c) => parts.push(c));
    req.on("end", () => done(Buffer.concat(parts).toString("utf8")));
  });
}

function cors(res) {
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader("Access-Control-Allow-Headers", "content-type");
}

const server = createServer(async (req, res) => {
  cors(res);
  const url = new URL(req.url, `http://localhost:${PORT}`);
  if (req.method === "OPTIONS") return res.end();
  if (url.pathname === "/events") {
    res.writeHead(200, { "Content-Type": "text/event-stream", "Cache-Control": "no-cache" });
    res.write(": ok\n\n");
    sseClients.add(res);
    return req.on("close", () => sseClients.delete(res));
  }
  if (url.pathname === "/file") {
    const path = url.searchParams.get("p") ?? "";
    if (!existsSync(path) || !statSync(path).isFile()) { res.statusCode = 404; return res.end(); }
    res.setHeader("Content-Type", TYPES[extname(path).toLowerCase()] ?? "application/octet-stream");
    return createReadStream(path).pipe(res);
  }
  if (url.pathname === "/opened") {
    res.setHeader("Content-Type", "application/json");
    return res.end(JSON.stringify(opened));
  }
  if (url.pathname === "/stderr") {
    res.setHeader("Content-Type", "application/json");
    return res.end(JSON.stringify({ viewer: engines.viewer.stderr.join(""), jobs: engines.jobs.stderr.join("") }));
  }
  if (url.pathname === "/invoke" && req.method === "POST") {
    const { cmd, args } = JSON.parse(await readBody(req));
    const reply = await handleInvoke(cmd, args ?? {});
    res.setHeader("Content-Type", "application/json");
    return res.end(JSON.stringify(reply));
  }
  res.statusCode = 404;
  res.end();
});

server.listen(PORT, "127.0.0.1");
function shutdown() {
  engines.viewer.stop();
  engines.jobs.stop();
  process.exit(0);
}
process.on("SIGINT", shutdown);
process.on("SIGTERM", shutdown);
