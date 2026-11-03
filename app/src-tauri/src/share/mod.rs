//! Nearby devices: send files straight to another PC running Free PDF on the
//! same network. UDP broadcast finds peers, one TCP connection per transfer
//! carries the files, BLAKE3 checks every byte.

mod discovery;
mod events;
mod names;
mod proto;
mod receive;
mod relay;
mod send;
mod service;
mod store;
#[cfg(test)]
mod tests;

use std::path::PathBuf;
use std::sync::Arc;

use serde::Serialize;
use tauri::{AppHandle, Emitter, Manager, State};

pub use events::Peer;
pub use proto::ShareError;

use events::{Event, Sink};
use proto::{DEFAULT_TCP_PORT, DEFAULT_UDP_PORT};
use service::{Options, Service};

pub struct ShareState(Option<Arc<Service>>);

type Share<'a> = State<'a, ShareState>;

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
pub struct Info {
    id: String,
    name: String,
    port: u16,
    addresses: Vec<String>,
    receive_dir: String,
}

/// Starts discovery and the transfer listener. A failure leaves the feature
/// off with a clear message instead of stopping the app.
pub fn start(app: &AppHandle) -> ShareState {
    let handle = app.clone();
    let sink: Sink = Arc::new(move |event: Event| {
        let _ = handle.emit(event.name(), event.payload());
    });
    let options = Options {
        tcp_port: DEFAULT_TCP_PORT,
        udp_port: Some(DEFAULT_UDP_PORT),
        receive_dir: receive_dir(app),
        store_path: app.path().app_config_dir().ok().map(|dir| dir.join("share.json")),
    };
    ShareState(Service::start(options, sink).ok())
}

pub fn disabled() -> ShareState {
    ShareState(None)
}

fn receive_dir(app: &AppHandle) -> PathBuf {
    let downloads = std::env::var_os("USERPROFILE")
        .map(|home| PathBuf::from(home).join("Downloads"))
        .filter(|dir| dir.is_dir())
        .or_else(|| app.path().download_dir().ok())
        .unwrap_or_else(std::env::temp_dir);
    downloads.join("Free PDF")
}

fn service<'a>(state: &'a Share<'_>) -> Result<&'a Arc<Service>, ShareError> {
    state.0.as_ref().ok_or_else(|| {
        ShareError::new(
            "network",
            "Nearby devices could not start. Restart Free PDF; if it keeps happening, allow it in Windows Firewall.",
        )
    })
}

/// Runs disk and network work off the UI thread.
async fn blocking<T: Send + 'static>(
    state: Share<'_>,
    work: impl FnOnce(Arc<Service>) -> Result<T, ShareError> + Send + 'static,
) -> Result<T, ShareError> {
    let service = Arc::clone(service(&state)?);
    tauri::async_runtime::spawn_blocking(move || work(service))
        .await
        .map_err(|_| ShareError::new("network", "Nearby devices stopped unexpectedly. Try again."))?
}

#[tauri::command]
pub async fn share_info(state: Share<'_>) -> Result<Info, ShareError> {
    blocking(state, |service| {
        Ok(Info {
            id: service.id(),
            name: service.name(),
            port: service.port,
            addresses: discovery::local_ipv4s(),
            receive_dir: service.receive_dir.to_string_lossy().into_owned(),
        })
    })
    .await
}

#[tauri::command]
pub fn share_peers(state: Share<'_>) -> Vec<Peer> {
    state.0.as_ref().map(|s| s.peers()).unwrap_or_default()
}

#[tauri::command]
pub async fn share_set_name(state: Share<'_>, name: String) -> Result<(), ShareError> {
    blocking(state, move |service| service.set_name(&name)).await
}

#[tauri::command]
pub async fn share_add_peer(state: Share<'_>, address: String) -> Result<Peer, ShareError> {
    blocking(state, move |service| service.add_peer(&address)).await
}

#[tauri::command]
pub async fn share_send(state: Share<'_>, peer_id: String, paths: Vec<String>) -> Result<String, ShareError> {
    blocking(state, move |service| service.send(&peer_id, &paths)).await
}

#[tauri::command]
pub fn share_cancel(state: Share<'_>, transfer_id: String) -> bool {
    state.0.as_ref().is_some_and(|s| s.cancel(&transfer_id))
}

#[tauri::command]
pub fn share_answer(state: Share<'_>, offer_id: String, accept: bool, trust: bool) -> bool {
    state.0.as_ref().is_some_and(|s| s.answer(&offer_id, accept, trust))
}
