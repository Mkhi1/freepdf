use std::collections::HashMap;
use std::io::{BufRead, BufReader, Write};
use std::os::windows::process::CommandExt;
use std::process::{Child, ChildStdin, ChildStdout, Command, Stdio};
use std::sync::mpsc::{self, Sender};
use std::sync::{Arc, Mutex, MutexGuard};
use std::time::Duration;

use serde::Serialize;
use serde_json::{json, Value};
use tauri::{AppHandle, Emitter};

use crate::config::Launch;

const CREATE_NO_WINDOW: u32 = 0x0800_0000;
const STOPPED: &str =
    "The PDF engine stopped unexpectedly. Try the action again; the engine restarts on its own.";

#[derive(Debug, Clone, Serialize)]
pub struct EngineError {
    pub code: String,
    pub message: String,
}

impl EngineError {
    pub fn new(code: &str, message: impl Into<String>) -> Self {
        Self { code: code.to_string(), message: message.into() }
    }
}

pub type Reply = Result<Value, EngineError>;

/// Calls still waiting for an answer from one engine process.
#[derive(Default)]
struct Pending(Mutex<HashMap<String, Sender<Reply>>>);

impl Pending {
    fn map(&self) -> MutexGuard<'_, HashMap<String, Sender<Reply>>> {
        self.0.lock().unwrap_or_else(|e| e.into_inner())
    }

    fn fail_all(&self) {
        for (_, tx) in self.map().drain() {
            let _ = tx.send(Err(EngineError::new("engine_stopped", STOPPED)));
        }
    }
}

struct Live {
    child: Child,
    stdin: ChildStdin,
    pending: Arc<Pending>,
}

pub struct Engine {
    name: &'static str,
    launch: Launch,
    app: AppHandle,
    live: Mutex<Option<Live>>,
}

impl Engine {
    pub fn new(name: &'static str, launch: Launch, app: AppHandle) -> Self {
        Self { name, launch, app, live: Mutex::new(None) }
    }

    pub fn name(&self) -> &'static str {
        self.name
    }

    fn lock(&self) -> MutexGuard<'_, Option<Live>> {
        self.live.lock().unwrap_or_else(|e| e.into_inner())
    }

    /// Starts the process if it is not running. Safe to call repeatedly.
    pub fn ensure_started(&self) -> Result<(), EngineError> {
        let mut guard = self.lock();
        self.ensure(&mut guard)
    }

    fn ensure(&self, guard: &mut Option<Live>) -> Result<(), EngineError> {
        let alive = match guard.as_mut() {
            Some(live) => matches!(live.child.try_wait(), Ok(None)),
            None => false,
        };
        if !alive {
            *guard = Some(self.spawn()?);
        }
        Ok(())
    }

    fn spawn(&self) -> Result<Live, EngineError> {
        let mut command = Command::new(&self.launch.python);
        if let Some(resources) = &self.launch.resources {
            command.env("FREEPDF_RES", resources);
        }
        let mut child = command
            .args(["-X", "utf8", "-m", "freepdf_engine", self.name])
            .current_dir(&self.launch.cwd)
            .env("PYTHONUTF8", "1")
            .env("PYTHONIOENCODING", "utf-8")
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .creation_flags(CREATE_NO_WINDOW)
            .spawn()
            .map_err(|e| {
                EngineError::new(
                    "engine_missing",
                    format!("Could not start the PDF engine ({}): {e}", self.launch.python.display()),
                )
            })?;
        let stdin = child
            .stdin
            .take()
            .ok_or_else(|| EngineError::new("engine_missing", "The PDF engine has no input."))?;
        let stdout = child
            .stdout
            .take()
            .ok_or_else(|| EngineError::new("engine_missing", "The PDF engine has no output."))?;
        if let Some(mut stderr) = child.stderr.take() {
            std::thread::spawn(move || {
                let _ = std::io::copy(&mut stderr, &mut std::io::sink());
            });
        }
        let pending = Arc::new(Pending::default());
        self.start_reader(stdout, Arc::clone(&pending));
        Ok(Live { child, stdin, pending })
    }

    fn start_reader(&self, stdout: ChildStdout, pending: Arc<Pending>) {
        let app = self.app.clone();
        std::thread::spawn(move || {
            let mut reader = BufReader::new(stdout);
            let mut buf = Vec::new();
            loop {
                buf.clear();
                match reader.read_until(b'\n', &mut buf) {
                    Ok(0) | Err(_) => break,
                    Ok(_) => handle_line(&app, &pending, &String::from_utf8_lossy(&buf)),
                }
            }
            pending.fail_all();
        });
    }

    pub fn call(&self, id: &str, tool: &str, args: &Value, timeout: Option<Duration>) -> Reply {
        let rx = {
            let mut guard = self.lock();
            self.ensure(&mut guard)?;
            let live = guard.as_mut().expect("started above");
            let (tx, rx) = mpsc::channel();
            live.pending.map().insert(id.to_string(), tx);
            let line = format!("{}\n", json!({ "id": id, "tool": tool, "args": args }));
            if live.stdin.write_all(line.as_bytes()).and_then(|_| live.stdin.flush()).is_err() {
                live.pending.map().remove(id);
                let _ = live.child.kill();
                *guard = None;
                return Err(EngineError::new("engine_stopped", STOPPED));
            }
            rx
        };
        let outcome = match timeout {
            Some(limit) => rx.recv_timeout(limit).map_err(|_| ()),
            None => rx.recv().map_err(|_| ()),
        };
        outcome.unwrap_or_else(|_| Err(EngineError::new("engine_stopped", STOPPED)))
    }

    /// Sends a cancel line when this engine owns the call. Returns whether it did.
    pub fn cancel(&self, id: &str) -> bool {
        let mut guard = self.lock();
        let Some(live) = guard.as_mut() else { return false };
        if !live.pending.map().contains_key(id) {
            return false;
        }
        let line = format!("{}\n", json!({ "cancel": id }));
        live.stdin.write_all(line.as_bytes()).and_then(|_| live.stdin.flush()).is_ok()
    }

    pub fn shutdown(&self) {
        if let Some(mut live) = self.lock().take() {
            drop(live.stdin);
            let _ = live.child.kill();
            let _ = live.child.wait();
        }
    }
}

fn handle_line(app: &AppHandle, pending: &Pending, line: &str) {
    let Ok(msg) = serde_json::from_str::<Value>(line.trim()) else { return };
    let id = msg["id"].as_str().unwrap_or("").to_string();
    match msg["type"].as_str() {
        Some("progress") => {
            let _ = app.emit("engine-progress", &msg);
        }
        Some("result") => {
            let reply = json!({ "outputs": msg["outputs"], "summary": msg["summary"] });
            deliver(pending, &id, Ok(reply));
        }
        Some("error") => {
            let code = msg["code"].as_str().unwrap_or("tool_failed");
            let text = msg["message"].as_str().unwrap_or("Something went wrong.");
            deliver(pending, &id, Err(EngineError::new(code, text)));
        }
        _ => {}
    }
}

fn deliver(pending: &Pending, id: &str, reply: Reply) {
    if let Some(tx) = pending.map().remove(id) {
        let _ = tx.send(reply);
    }
}
