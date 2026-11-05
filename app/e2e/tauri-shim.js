// Injected before the app loads. Makes the page believe it runs inside Tauri and
// sends every command to the bridge, which talks to the real Python engine.
(() => {
  const BRIDGE = "http://127.0.0.1:5181";
  const callbacks = new Map();
  const listeners = new Map(); // event name -> Map(eventId -> callback id)
  let nextId = 1;

  window.__e2e = { picks: [], calls: [], results: [], errors: [] };

  function emit(event, payload) {
    for (const cbId of (listeners.get(event) ?? new Map()).values()) {
      callbacks.get(cbId)?.({ event, id: 0, payload });
    }
  }
  window.__e2e.emit = emit;
  window.__e2e.drop = (paths) => {
    const position = { x: 200, y: 200 };
    emit("tauri://drag-enter", { paths, position });
    emit("tauri://drag-drop", { paths, position });
  };

  const source = new EventSource(`${BRIDGE}/events`);
  source.onmessage = (m) => {
    const { event, payload } = JSON.parse(m.data);
    emit(event, payload);
  };

  async function bridge(cmd, args) {
    const res = await fetch(`${BRIDGE}/invoke`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ cmd, args }),
    });
    const reply = await res.json();
    if (!reply.ok) throw reply.value;
    return reply.value;
  }

  async function invoke(cmd, args = {}) {
    if (cmd === "engine_call" && !["info", "thumb"].includes(args.tool)) {
      window.__e2e.calls.push({ tool: args.tool, args: JSON.parse(JSON.stringify(args.args ?? {})) });
    }
    if (cmd === "plugin:event|listen") {
      const eventId = nextId++;
      if (!listeners.has(args.event)) listeners.set(args.event, new Map());
      listeners.get(args.event).set(eventId, args.handler);
      return eventId;
    }
    if (cmd === "plugin:event|unlisten") {
      listeners.get(args.event)?.delete(args.eventId);
      return null;
    }
    if (cmd === "plugin:event|emit") return emit(args.event, args.payload);
    if (cmd === "plugin:dialog|open") {
      const next = window.__e2e.picks.shift();
      if (next === undefined) return null;
      return args.options?.multiple ? next : next[0];
    }
    if (cmd === "plugin:updater|check") return null;
    if (cmd.startsWith("plugin:process|")) return null;
    const value = await bridge(cmd, args).catch((err) => {
      if (cmd === "engine_call") window.__e2e.results.push({ tool: args.tool, error: err });
      throw err;
    });
    if (cmd === "engine_call" && !["info", "thumb"].includes(args.tool)) window.__e2e.results.push({ tool: args.tool, value });
    return value;
  }

  window.__TAURI_INTERNALS__ = {
    invoke,
    transformCallback(callback, once = false) {
      const id = nextId++;
      callbacks.set(id, (data) => {
        if (once) callbacks.delete(id);
        return callback?.(data);
      });
      return id;
    },
    unregisterCallback(id) { callbacks.delete(id); },
    convertFileSrc(path) { return `${BRIDGE}/file?p=${encodeURIComponent(path)}`; },
    metadata: {
      currentWindow: { label: "main" },
      currentWebview: { windowLabel: "main", label: "main" },
    },
  };
  window.__TAURI_EVENT_PLUGIN_INTERNALS__ = {
    unregisterListener(event, eventId) { listeners.get(event)?.delete(eventId); },
  };
  window.addEventListener("error", (e) => window.__e2e.errors.push(String(e.message)));
  window.addEventListener("unhandledrejection", (e) => window.__e2e.errors.push(String(e.reason?.message ?? e.reason)));
})();
