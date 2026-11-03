use std::net::{Shutdown, TcpStream};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

use serde::Serialize;
use serde_json::Value;

use super::proto::{FileMeta, ShareError};

const PROGRESS_EVERY: Duration = Duration::from_millis(100);

#[derive(Debug, Clone, PartialEq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct Peer {
    pub id: String,
    pub name: String,
    pub address: String,
    pub manual: bool,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct OfferEvent {
    pub offer_id: String,
    pub from_id: String,
    pub from_name: String,
    pub files: Vec<FileMeta>,
    pub total: u64,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct Progress {
    pub transfer_id: String,
    pub direction: &'static str,
    pub peer_name: String,
    pub done: u64,
    pub total: u64,
    pub bytes_per_sec: u64,
    pub file: String,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct Done {
    pub transfer_id: String,
    pub direction: &'static str,
    pub peer_name: String,
    pub ok: bool,
    pub paths: Vec<String>,
    pub error: Option<ShareError>,
}

#[derive(Debug, Clone)]
pub enum Event {
    Peers(Vec<Peer>),
    Offer(OfferEvent),
    OfferClosed(String),
    Progress(Progress),
    Done(Done),
}

impl Event {
    pub fn name(&self) -> &'static str {
        match self {
            Event::Peers(_) => "share-peers",
            Event::Offer(_) => "share-offer",
            Event::OfferClosed(_) => "share-offer-closed",
            Event::Progress(_) => "share-progress",
            Event::Done(_) => "share-done",
        }
    }

    pub fn payload(&self) -> Value {
        let value = match self {
            Event::Peers(p) => serde_json::to_value(p),
            Event::Offer(o) => serde_json::to_value(o),
            Event::OfferClosed(id) => Ok(serde_json::json!({ "offerId": id })),
            Event::Progress(p) => serde_json::to_value(p),
            Event::Done(d) => serde_json::to_value(d),
        };
        value.unwrap_or(Value::Null)
    }
}

/// Where the share engine reports what happens. The app forwards to the UI;
/// tests collect into a channel.
pub type Sink = Arc<dyn Fn(Event) + Send + Sync>;

/// Throttled progress for one transfer: at most one event per 100 ms, plus 100%.
pub struct Meter {
    sink: Sink,
    base: Progress,
    started: Instant,
    last: Instant,
}

impl Meter {
    pub fn new(sink: Sink, transfer_id: &str, direction: &'static str, peer: &str, total: u64) -> Self {
        let now = Instant::now();
        let base = Progress {
            transfer_id: transfer_id.to_string(),
            direction,
            peer_name: peer.to_string(),
            done: 0,
            total,
            bytes_per_sec: 0,
            file: String::new(),
        };
        Self { sink, base, started: now, last: now.checked_sub(PROGRESS_EVERY).unwrap_or(now) }
    }

    /// Starts the speed clock over, so time spent waiting for Accept is not counted.
    pub fn restart(&mut self) {
        self.started = Instant::now();
    }

    pub fn start_file(&mut self, name: &str) {
        self.base.file = name.to_string();
        if self.last.elapsed() >= PROGRESS_EVERY {
            self.emit();
        }
    }

    pub fn add(&mut self, bytes: usize) {
        self.base.done += bytes as u64;
        if self.last.elapsed() >= PROGRESS_EVERY {
            self.emit();
        }
    }

    pub fn finish(&mut self) {
        self.base.done = self.base.total;
        self.emit();
    }

    fn emit(&mut self) {
        self.last = Instant::now();
        let secs = self.started.elapsed().as_secs_f64();
        self.base.bytes_per_sec = if secs > 0.0 { (self.base.done as f64 / secs) as u64 } else { 0 };
        (self.sink)(Event::Progress(self.base.clone()));
    }
}

/// Stops a running transfer from another thread by shutting its socket down.
#[derive(Default)]
pub struct Cancel {
    flag: AtomicBool,
    stream: Mutex<Option<TcpStream>>,
}

impl Cancel {
    pub fn attach(&self, stream: &TcpStream) {
        let clone = stream.try_clone().ok();
        *self.stream.lock().unwrap_or_else(|e| e.into_inner()) = clone;
        if self.is_cancelled() {
            let _ = stream.shutdown(Shutdown::Both);
        }
    }

    pub fn cancel(&self) {
        self.flag.store(true, Ordering::SeqCst);
        if let Some(stream) = self.stream.lock().unwrap_or_else(|e| e.into_inner()).as_ref() {
            let _ = stream.shutdown(Shutdown::Both);
        }
    }

    pub fn is_cancelled(&self) -> bool {
        self.flag.load(Ordering::SeqCst)
    }

    /// Cancelling turns any later network failure into a plain "cancelled".
    pub fn explain(&self, err: ShareError) -> ShareError {
        if self.is_cancelled() {
            ShareError::cancelled()
        } else {
            err
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::atomic::AtomicUsize;

    #[test]
    fn meter_throttles_per_file_events() {
        let count = Arc::new(AtomicUsize::new(0));
        let seen = Arc::clone(&count);
        let sink: Sink = Arc::new(move |_| {
            seen.fetch_add(1, Ordering::SeqCst);
        });
        let mut meter = Meter::new(sink, "t", "send", "PC", 2000);
        for i in 0..2000 {
            meter.start_file(&format!("{i}.pdf"));
            meter.add(1);
        }
        meter.finish();
        assert!(count.load(Ordering::SeqCst) < 20, "sent {} events", count.load(Ordering::SeqCst));
    }
}
