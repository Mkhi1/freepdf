use std::sync::Arc;
use std::time::Duration;

use serde_json::{json, Value};
use tauri::AppHandle;

use crate::engine::Engine;
use crate::hub::Hub;

const LIMIT: Duration = Duration::from_secs(90);

fn ping(engine: &Engine, id: &str) -> Value {
    match engine.call(id, "ping", &json!({}), Some(LIMIT)) {
        Ok(v) => json!({
            "engine": engine.name(),
            "ok": true,
            "version": v["summary"]["version"],
            "tools": v["summary"]["tools"]
        }),
        Err(e) => json!({ "engine": engine.name(), "ok": false, "code": e.code, "message": e.message }),
    }
}

/// Pings both engines without ever showing the window, writes the outcome and exits.
pub fn run(app: AppHandle, hub: Arc<Hub>) {
    std::thread::spawn(move || {
        let viewer = ping(&hub.viewer, "smoke-viewer");
        let jobs = ping(&hub.jobs, "smoke-jobs");
        let ok = viewer["ok"] == true && jobs["ok"] == true;
        let startup = crate::config::startup_pdf();
        let report = json!({ "ok": ok, "viewer": viewer, "jobs": jobs, "startup_pdf": startup });
        if let Some(path) = std::env::var_os("FREEPDF_SMOKE_OUT") {
            let _ = std::fs::write(path, serde_json::to_vec_pretty(&report).unwrap_or_default());
        }
        hub.shutdown();
        app.exit(if ok { 0 } else { 1 });
    });
}
