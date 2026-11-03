use std::net::{IpAddr, Ipv4Addr, SocketAddr, SocketAddrV4, UdpSocket};
use std::sync::Arc;
use std::time::{Duration, Instant};

use serde::Deserialize;
use serde_json::json;
use socket2::{Domain, Protocol, Socket, Type};

use super::events::Peer;
use super::names::clean_device_name;
use super::service::Service;

const ANNOUNCE_EVERY: Duration = Duration::from_secs(2);
const FORGET_AFTER: Duration = Duration::from_secs(8);
const POLL: Duration = Duration::from_millis(500);

#[derive(Deserialize)]
struct Announce {
    app: String,
    kind: String,
    id: String,
    name: String,
    port: u16,
}

/// Starts announcing and listening. When the port cannot be opened discovery
/// stays off and peers can still be added by address.
pub fn start(service: Arc<Service>, port: u16) {
    let Ok(socket) = bind(port) else { return };
    std::thread::spawn(move || run(&service, &socket, port));
}

fn bind(port: u16) -> std::io::Result<UdpSocket> {
    let socket = Socket::new(Domain::IPV4, Type::DGRAM, Some(Protocol::UDP))?;
    socket.set_reuse_address(true)?;
    socket.set_broadcast(true)?;
    socket.bind(&SocketAddr::from((Ipv4Addr::UNSPECIFIED, port)).into())?;
    let socket: UdpSocket = socket.into();
    socket.set_read_timeout(Some(POLL))?;
    Ok(socket)
}

fn run(service: &Service, socket: &UdpSocket, port: u16) {
    let mut next = Instant::now();
    let mut buf = [0u8; 2048];
    loop {
        if Instant::now() >= next {
            let message = announcement(service);
            for target in targets(port) {
                let _ = socket.send_to(&message, target);
            }
            if service.prune_peers(FORGET_AFTER) {
                service.emit_peers();
            }
            next = Instant::now() + ANNOUNCE_EVERY;
        }
        if let Ok((len, src)) = socket.recv_from(&mut buf) {
            if handle_announce(service, &buf[..len], src.ip()) {
                let _ = socket.send_to(&announcement(service), src);
            }
        }
    }
}

fn announcement(service: &Service) -> Vec<u8> {
    let message = json!({
        "app": "freepdf", "v": 1, "kind": "announce",
        "id": service.id(), "name": service.name(), "port": service.port,
    });
    serde_json::to_vec(&message).unwrap_or_default()
}

/// Records a peer from one packet. Returns true when the peer is new, so the
/// caller answers right away instead of waiting for the next round.
pub fn handle_announce(service: &Service, data: &[u8], src: IpAddr) -> bool {
    let Ok(msg) = serde_json::from_slice::<Announce>(data) else { return false };
    let valid_id = msg.id.len() == 16 && msg.id.chars().all(|c| c.is_ascii_hexdigit());
    if msg.app != "freepdf" || msg.kind != "announce" || !valid_id || msg.id == service.id() || msg.port == 0 {
        return false;
    }
    let name = clean_device_name(&msg.name).unwrap_or_else(|| "Free PDF device".to_string());
    let is_new = !service.knows_peer(&msg.id);
    let peer = Peer { id: msg.id, name, address: SocketAddr::new(src, msg.port).to_string(), manual: false };
    if service.upsert_peer(peer) {
        service.emit_peers();
    }
    is_new
}

fn ipv4_interfaces() -> Vec<if_addrs::Ifv4Addr> {
    if_addrs::get_if_addrs()
        .unwrap_or_default()
        .into_iter()
        .filter_map(|iface| match iface.addr {
            if_addrs::IfAddr::V4(v4) if !v4.ip.is_loopback() => Some(v4),
            _ => None,
        })
        .collect()
}

fn targets(port: u16) -> Vec<SocketAddr> {
    let mut list = vec![SocketAddr::V4(SocketAddrV4::new(Ipv4Addr::BROADCAST, port))];
    for v4 in ipv4_interfaces() {
        let directed = Ipv4Addr::from(u32::from(v4.ip) | !u32::from(v4.netmask));
        let target = SocketAddr::V4(SocketAddrV4::new(directed, port));
        if directed != v4.ip && !list.contains(&target) {
            list.push(target);
        }
    }
    list
}

pub fn local_ipv4s() -> Vec<String> {
    let mut list: Vec<String> = ipv4_interfaces().into_iter().map(|v4| v4.ip.to_string()).collect();
    list.dedup();
    list
}
