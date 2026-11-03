use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::Arc;
use std::time::Duration;

use serde_json::Value;
use tauri::AppHandle;

use crate::config;
use crate::engine::{Engine, Reply};

const VIEWER_TOOLS: [&str; 4] = ["info", "thumb", "page_text", "search"];

/// Two engine processes: the viewer stays instant, jobs run one at a time.
pub struct Hub {
    pub viewer: Engine,
    pub jobs: Engine,
    counter: AtomicU64,
}

impl Hub {
    pub fn new(app: &AppHandle) -> Self {
        let launch = config::launch();
        Self {
            viewer: Engine::new("viewer", launch.clone(), app.clone()),
            jobs: Engine::new("jobs", launch, app.clone()),
            counter: AtomicU64::new(1),
        }
    }

    fn route(&self, tool: &str) -> &Engine {
        if VIEWER_TOOLS.contains(&tool) {
            &self.viewer
        } else {
            &self.jobs
        }
    }

    pub fn next_id(&self) -> String {
        format!("c{}", self.counter.fetch_add(1, Ordering::Relaxed))
    }

    pub fn call(&self, id: &str, tool: &str, args: &Value, timeout: Option<Duration>) -> Reply {
        self.route(tool).call(id, tool, args, timeout)
    }

    pub fn cancel(&self, id: &str) -> bool {
        self.viewer.cancel(id) || self.jobs.cancel(id)
    }

    /// Starts both processes on a background thread so the window is never held up.
    pub fn warm_up(hub: Arc<Hub>) {
        std::thread::spawn(move || {
            let _ = hub.viewer.ensure_started();
            let _ = hub.jobs.ensure_started();
        });
    }

    pub fn shutdown(&self) {
        self.viewer.shutdown();
        self.jobs.shutdown();
    }
}
