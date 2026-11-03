use std::collections::HashMap;
use std::io::{BufReader, ErrorKind};
use std::net::{IpAddr, SocketAddr, TcpListener, TcpStream, ToSocketAddrs};
use std::path::PathBuf;
use std::sync::atomic::{AtomicBool, AtomicUsize, Ordering};
use std::sync::mpsc::Sender;
use std::sync::{Arc, Mutex, MutexGuard};
use std::time::{Duration, Instant};

use serde_json::json;

use super::events::{Cancel, Event, Peer, Sink};
use super::names::{clean_device_name, random_hex};
use super::proto::{self, Header, HelloReply, ShareError, DEFAULT_TCP_PORT, MAX_LINE};
use super::store::{Saved, Store};
use super::{discovery, receive, send};

const PROBE_TIMEOUT: Duration = Duration::from_secs(3);
const HEADER_TIMEOUT: Duration = Duration::from_secs(10);
const MAX_CONNECTIONS: usize = 32;
const MAX_PENDING: usize = 4;
const MAX_DISCOVERED: usize = 64;

pub struct Options {
    pub tcp_port: u16,
    /// `None` turns discovery off; peers can still be added by address.
    pub udp_port: Option<u16>,
    pub receive_dir: PathBuf,
    pub store_path: Option<PathBuf>,
}

pub struct PeerEntry {
    pub peer: Peer,
    pub seen: Instant,
}

pub struct Service {
    pub port: u16,
    pub receive_dir: PathBuf,
    pub sink: Sink,
    pub receiving: AtomicBool,
    store: Store,
    saved: Mutex<Saved>,
    peers: Mutex<HashMap<String, PeerEntry>>,
    active: Mutex<HashMap<String, Arc<Cancel>>>,
    pending: Mutex<HashMap<String, Pending>>,
    connections: AtomicUsize,
}

struct Pending {
    from_id: String,
    ip: Option<IpAddr>,
    tx: Sender<bool>,
}

/// Frees a connection slot when its handler ends.
struct Slot<'a>(&'a AtomicUsize);

impl Drop for Slot<'_> {
    fn drop(&mut self) {
        self.0.fetch_sub(1, Ordering::SeqCst);
    }
}

fn lock<T>(m: &Mutex<T>) -> MutexGuard<'_, T> {
    m.lock().unwrap_or_else(|e| e.into_inner())
}

fn bind(port: u16) -> std::io::Result<TcpListener> {
    TcpListener::bind(("0.0.0.0", port)).or_else(|e| {
        if port == 0 {
            Err(e)
        } else {
            TcpListener::bind(("0.0.0.0", 0))
        }
    })
}

impl Service {
    pub fn start(options: Options, sink: Sink) -> std::io::Result<Arc<Service>> {
        let listener = bind(options.tcp_port)?;
        let port = listener.local_addr()?.port();
        let store = Store::new(options.store_path);
        let saved = store.load();
        let service = Arc::new(Service {
            port,
            receive_dir: options.receive_dir,
            sink,
            receiving: AtomicBool::new(false),
            store,
            saved: Mutex::new(saved),
            peers: Mutex::new(HashMap::new()),
            active: Mutex::new(HashMap::new()),
            pending: Mutex::new(HashMap::new()),
            connections: AtomicUsize::new(0),
        });
        let accepting = Arc::clone(&service);
        std::thread::spawn(move || accept_loop(accepting, listener));
        if let Some(udp) = options.udp_port {
            discovery::start(Arc::clone(&service), udp);
        }
        Ok(service)
    }

    pub fn id(&self) -> String {
        lock(&self.saved).id.clone()
    }

    pub fn name(&self) -> String {
        lock(&self.saved).name.clone()
    }

    pub fn emit(&self, event: Event) {
        (self.sink)(event);
    }

    pub fn set_name(&self, name: &str) -> Result<(), ShareError> {
        let name = clean_device_name(name)
            .ok_or_else(|| ShareError::new("bad_args", "Use a device name of 1 to 40 characters."))?;
        let mut saved = lock(&self.saved);
        saved.name = name;
        self.persist(&saved)
    }

    fn persist(&self, saved: &Saved) -> Result<(), ShareError> {
        self.store.save(saved).map_err(|e| {
            ShareError::new("disk", format!("Could not save the sharing settings ({e}). Check the disk is not full."))
        })
    }

    pub fn is_trusted(&self, id: &str) -> bool {
        lock(&self.saved).trusted.iter().any(|t| t == id)
    }

    pub fn trust(&self, id: &str) {
        let mut saved = lock(&self.saved);
        if !saved.trusted.iter().any(|t| t == id) {
            saved.trusted.push(id.to_string());
            let _ = self.persist(&saved);
        }
    }

    pub fn peers(&self) -> Vec<Peer> {
        let mut list: Vec<Peer> = lock(&self.peers).values().map(|e| e.peer.clone()).collect();
        list.sort_by(|a, b| a.name.to_lowercase().cmp(&b.name.to_lowercase()).then(a.id.cmp(&b.id)));
        list
    }

    /// Device ids travel in clear, so a trusted id only counts when the offer
    /// comes from the address that device is known at.
    pub fn is_trusted_at(&self, id: &str, ip: IpAddr) -> bool {
        let known_here = lock(&self.peers)
            .get(id)
            .and_then(|e| e.peer.address.parse::<SocketAddr>().ok())
            .is_some_and(|addr| addr.ip() == ip);
        known_here && self.is_trusted(id)
    }

    /// Adds or refreshes a peer. Returns whether the visible list changed.
    /// Announces never move a known device to another address (anyone can
    /// claim an id); an entry that stops hearing from its address expires.
    pub fn upsert_peer(&self, peer: Peer) -> bool {
        let mut peers = lock(&self.peers);
        match peers.get_mut(&peer.id) {
            Some(entry) if !peer.manual && entry.peer.address != peer.address => false,
            Some(entry) => {
                let next = Peer { manual: entry.peer.manual || peer.manual, ..peer };
                let changed = entry.peer != next;
                *entry = PeerEntry { peer: next, seen: Instant::now() };
                changed
            }
            None => {
                let discovered = peers.values().filter(|e| !e.peer.manual).count();
                if !peer.manual && discovered >= MAX_DISCOVERED {
                    return false;
                }
                peers.insert(peer.id.clone(), PeerEntry { peer, seen: Instant::now() });
                true
            }
        }
    }

    pub fn knows_peer(&self, id: &str) -> bool {
        lock(&self.peers).contains_key(id)
    }

    /// Drops discovered peers not heard from within `limit`. Returns whether any left.
    pub fn prune_peers(&self, limit: Duration) -> bool {
        let mut peers = lock(&self.peers);
        let before = peers.len();
        peers.retain(|_, e| e.peer.manual || e.seen.elapsed() < limit);
        peers.len() != before
    }

    pub fn emit_peers(&self) {
        self.emit(Event::Peers(self.peers()));
    }

    pub fn add_peer(&self, address: &str) -> Result<Peer, ShareError> {
        let addr = parse_address(address)?;
        let hello = probe(addr)?;
        if hello.id == self.id() {
            return Err(ShareError::new("bad_args", "That address is this PC. Enter the address of the other PC."));
        }
        let peer = Peer {
            id: hello.id,
            name: clean_device_name(&hello.name).unwrap_or_else(|| "Free PDF device".to_string()),
            address: SocketAddr::new(addr.ip(), hello.port).to_string(),
            manual: true,
        };
        self.upsert_peer(peer.clone());
        self.emit_peers();
        Ok(peer)
    }

    pub fn send(self: &Arc<Self>, peer_id: &str, paths: &[String]) -> Result<String, ShareError> {
        let peer = lock(&self.peers)
            .get(peer_id)
            .map(|e| e.peer.clone())
            .ok_or_else(|| ShareError::new("peer_not_found", "That device is no longer nearby. Check it is still on and try again."))?;
        let job = send::Job::prepare(self.id(), self.name(), peer, paths)?;
        let transfer_id = format!("s{}", random_hex(12));
        let cancel = self.register(&transfer_id);
        let service = Arc::clone(self);
        let id = transfer_id.clone();
        std::thread::spawn(move || {
            send::run(&service, &id, job, &cancel);
            service.unregister(&id);
        });
        Ok(transfer_id)
    }

    pub fn register(&self, transfer_id: &str) -> Arc<Cancel> {
        let cancel = Arc::new(Cancel::default());
        lock(&self.active).insert(transfer_id.to_string(), Arc::clone(&cancel));
        cancel
    }

    pub fn unregister(&self, transfer_id: &str) {
        lock(&self.active).remove(transfer_id);
    }

    pub fn cancel(&self, transfer_id: &str) -> bool {
        match lock(&self.active).get(transfer_id) {
            Some(cancel) => {
                cancel.cancel();
                true
            }
            None => false,
        }
    }

    /// Queues an offer for the user. Refuses when a few already wait, or one
    /// from the same address does, so nobody can flood the dialog.
    pub fn add_pending(&self, offer_id: &str, from_id: &str, ip: Option<IpAddr>, tx: Sender<bool>) -> bool {
        let mut pending = lock(&self.pending);
        if pending.len() >= MAX_PENDING || pending.values().any(|p| p.ip == ip) {
            return false;
        }
        pending.insert(offer_id.to_string(), Pending { from_id: from_id.to_string(), ip, tx });
        true
    }

    /// Returns false when answer() took the entry first.
    pub fn remove_pending(&self, offer_id: &str) -> bool {
        lock(&self.pending).remove(offer_id).is_some()
    }

    pub fn answer(&self, offer_id: &str, accept: bool, trust: bool) -> bool {
        let Some(Pending { from_id, tx, .. }) = lock(&self.pending).remove(offer_id) else { return false };
        if accept && trust {
            self.trust(&from_id);
        }
        tx.send(accept).is_ok()
    }
}

pub fn parse_address(address: &str) -> Result<SocketAddr, ShareError> {
    let bad = || ShareError::new("bad_args", "Enter an address like 192.168.1.20 or 192.168.1.20:47821.");
    let text = address.trim();
    if text.is_empty() {
        return Err(bad());
    }
    if let Ok(addr) = text.parse::<SocketAddr>() {
        return Ok(addr);
    }
    if let Ok(ip) = text.parse::<std::net::IpAddr>() {
        return Ok(SocketAddr::new(ip, DEFAULT_TCP_PORT));
    }
    let with_port = if text.contains(':') { text.to_string() } else { format!("{text}:{DEFAULT_TCP_PORT}") };
    with_port.to_socket_addrs().ok().and_then(|mut a| a.find(|a| a.is_ipv4())).ok_or_else(bad)
}

fn probe(addr: SocketAddr) -> Result<HelloReply, ShareError> {
    let unreachable = || {
        ShareError::new(
            "unreachable",
            format!("No Free PDF answered at {addr}. Check Free PDF is open on that PC and the address is right."),
        )
    };
    let mut stream = TcpStream::connect_timeout(&addr, PROBE_TIMEOUT).map_err(|_| unreachable())?;
    proto::set_timeouts(&stream, Some(PROBE_TIMEOUT));
    proto::write_line(&mut stream, &json!({ "kind": "hello" })).map_err(|_| unreachable())?;
    let line = proto::read_line(&mut BufReader::new(stream)).map_err(|_| unreachable())?;
    serde_json::from_str(&line).map_err(|_| unreachable())
}

fn accept_loop(service: Arc<Service>, listener: TcpListener) {
    for stream in listener.incoming() {
        match stream {
            Ok(stream) => {
                if service.connections.fetch_add(1, Ordering::SeqCst) >= MAX_CONNECTIONS {
                    service.connections.fetch_sub(1, Ordering::SeqCst);
                    continue;
                }
                let service = Arc::clone(&service);
                std::thread::spawn(move || {
                    let _slot = Slot(&service.connections);
                    handle_connection(&service, stream);
                });
            }
            Err(e) if e.kind() == ErrorKind::Interrupted => continue,
            Err(_) => std::thread::sleep(Duration::from_millis(50)),
        }
    }
}

fn handle_connection(service: &Arc<Service>, stream: TcpStream) {
    proto::tune(&stream);
    proto::set_timeouts(&stream, Some(HEADER_TIMEOUT));
    let Ok(read_half) = stream.try_clone() else { return };
    // Large reads bypass this buffer, so a small one costs no speed.
    let mut reader = BufReader::with_capacity(MAX_LINE, read_half);
    let mut writer = stream;
    let header = match proto::read_line_before(&mut reader, Some(Instant::now() + HEADER_TIMEOUT)) {
        Ok(line) => proto::parse_header(&line),
        Err(_) => Err(ShareError::new("bad_args", "The request header was missing, too slow or too long.")),
    };
    proto::set_timeouts(&writer, Some(proto::IO_TIMEOUT));
    match header {
        Ok(Header::Hello) => {
            let reply = json!({ "id": service.id(), "name": service.name(), "port": service.port });
            let _ = proto::write_line(&mut writer, &reply);
        }
        Ok(Header::Offer(offer)) => receive::handle_offer(service, reader, writer, offer),
        Err(err) => {
            let _ = proto::write_line(&mut writer, &proto::error_reply(&err));
            let _ = writer.shutdown(std::net::Shutdown::Write);
            receive::drain(&mut reader);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn addresses_default_the_port() {
        assert_eq!(parse_address("10.0.0.5").unwrap().to_string(), "10.0.0.5:47821");
        assert_eq!(parse_address(" 10.0.0.5:9000 ").unwrap().to_string(), "10.0.0.5:9000");
        assert_eq!(parse_address("").unwrap_err().code, "bad_args");
        assert_eq!(parse_address("10.0.0.5:abc").unwrap_err().code, "bad_args");
    }
}
