mod commands;
mod config;
mod engine;
mod hub;
mod smoke;

use std::sync::Arc;
use std::time::Duration;

use tauri::{Manager, RunEvent};

use hub::Hub;

/// Failsafe: if the UI never reports its first paint, still show the window.
fn show_after_delay(app: tauri::AppHandle) {
    std::thread::spawn(move || {
        std::thread::sleep(Duration::from_secs(8));
        if let Some(window) = app.get_webview_window("main") {
            if !window.is_visible().unwrap_or(true) {
                let _ = window.show();
            }
        }
    });
}

pub fn run() {
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_opener::init())
        .invoke_handler(tauri::generate_handler![
            commands::engine_call,
            commands::engine_cancel,
            commands::startup_file,
            commands::ui_ready
        ])
        .setup(|app| {
            let hub = Arc::new(Hub::new(app.handle()));
            app.manage(Arc::clone(&hub));
            if config::is_smoke() {
                smoke::run(app.handle().clone(), hub);
            } else {
                show_after_delay(app.handle().clone());
            }
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("could not build the app");

    app.run(|handle, event| {
        if let RunEvent::Exit = event {
            if let Some(hub) = handle.try_state::<Arc<Hub>>() {
                hub.shutdown();
            }
        }
    });
}
