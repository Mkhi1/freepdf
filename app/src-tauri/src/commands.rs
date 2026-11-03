use std::sync::Arc;

use serde_json::Value;
use tauri::{AppHandle, Manager, State};

use crate::config::{is_smoke, startup_pdf};
use crate::engine::EngineError;
use crate::hub::Hub;

type HubState<'a> = State<'a, Arc<Hub>>;

#[tauri::command]
pub async fn engine_call(
    hub: HubState<'_>,
    tool: String,
    args: Value,
    id: Option<String>,
) -> Result<Value, EngineError> {
    let hub = Arc::clone(hub.inner());
    let id = id.unwrap_or_else(|| hub.next_id());
    tauri::async_runtime::spawn_blocking(move || hub.call(&id, &tool, &args, None))
        .await
        .map_err(|_| EngineError::new("tool_failed", "The request was interrupted. Try again."))?
}

#[tauri::command]
pub fn engine_cancel(hub: HubState<'_>, id: String) -> bool {
    hub.cancel(&id)
}

#[tauri::command]
pub fn startup_file() -> Option<String> {
    startup_pdf()
}

/// Called by the UI after its first paint. Shows the window and warms the engines.
#[tauri::command]
pub fn ui_ready(app: AppHandle, hub: HubState<'_>) {
    if is_smoke() {
        return;
    }
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.show();
        let _ = window.set_focus();
    }
    Hub::warm_up(Arc::clone(hub.inner()));
}
