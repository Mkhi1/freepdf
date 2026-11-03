//! Two share instances in one process over 127.0.0.1, each with its own port
//! and temp folders.

use std::io::{BufReader, Read, Write};
use std::net::{IpAddr, Ipv4Addr, TcpStream};
use std::path::{Path, PathBuf};
use std::sync::mpsc::{self, Receiver};
use std::sync::Arc;
use std::time::{Duration, Instant};

use serde_json::json;

use super::discovery::handle_announce;
use super::events::{Done, Event, Sink};
use super::names::random_hex;
use super::proto;
use super::service::{Options, Service};

const WAIT: Duration = Duration::from_secs(30);

struct Node {
    service: Arc<Service>,
    events: Receiver<Event>,
    root: PathBuf,
}

impl Node {
    /// `accept`: how this node answers offers; `None` leaves them unanswered.
    fn start(accept: Option<bool>) -> Node {
        let root = std::env::temp_dir().join(format!("freepdf-share-{}", random_hex(12)));
        std::fs::create_dir_all(&root).unwrap();
        let (raw_tx, raw_rx) = mpsc::channel::<Event>();
        let sink: Sink = Arc::new(move |event| {
            let _ = raw_tx.send(event);
        });
        let options = Options { tcp_port: 0, udp_port: None, receive_dir: root.join("inbox"), store_path: None };
        let service = Service::start(options, sink).unwrap();
        let (tx, events) = mpsc::channel();
        let answering = Arc::clone(&service);
        std::thread::spawn(move || {
            for event in raw_rx {
                if let (Event::Offer(offer), Some(yes)) = (&event, accept) {
                    answering.answer(&offer.offer_id, yes, true);
                }
                if tx.send(event).is_err() {
                    break;
                }
            }
        });
        Node { service, events, root }
    }

    fn inbox(&self) -> PathBuf {
        self.root.join("inbox")
    }

    fn address(&self) -> String {
        format!("127.0.0.1:{}", self.service.port)
    }

    fn wait_done(&self) -> (Done, Vec<Event>) {
        let deadline = Instant::now() + WAIT;
        let mut seen = Vec::new();
        while let Some(left) = deadline.checked_duration_since(Instant::now()) {
            match self.events.recv_timeout(left) {
                Ok(Event::Done(done)) => return (done, seen),
                Ok(other) => seen.push(other),
                Err(_) => break,
            }
        }
        panic!("no share-done event within {WAIT:?}");
    }
}

impl Drop for Node {
    fn drop(&mut self) {
        let _ = std::fs::remove_dir_all(&self.root);
    }
}

fn pseudo_random(len: usize, seed: &str) -> Vec<u8> {
    let mut out = vec![0u8; len];
    blake3::Hasher::new().update(seed.as_bytes()).finalize_xof().fill(&mut out);
    out
}

fn write_source(node: &Node, name: &str, bytes: &[u8]) -> String {
    let dir = node.root.join("outbox").join(random_hex(6));
    std::fs::create_dir_all(&dir).unwrap();
    let path = dir.join(name);
    std::fs::write(&path, bytes).unwrap();
    path.to_string_lossy().into_owned()
}

fn leftovers(dir: &Path) -> Vec<String> {
    std::fs::read_dir(dir)
        .map(|it| it.flatten().map(|e| e.file_name().to_string_lossy().into_owned()).collect())
        .unwrap_or_default()
}

#[test]
fn share_sends_files_byte_exact() {
    let a = Node::start(None);
    let b = Node::start(Some(true));
    let peer = a.service.add_peer(&b.address()).unwrap();
    assert_eq!(peer.id, b.service.id());
    assert!(peer.manual);

    let big = pseudo_random(20 * 1024 * 1024 + 777, "big");
    let sources = vec![
        write_source(&a, "empty.txt", b""),
        write_source(&a, "تقرير مالي ٢٠٢٦.pdf", b"%PDF-1.7 arabic name"),
        write_source(&a, "big.bin", &big),
        write_source(&a, "same.txt", b"first"),
        write_source(&a, "same.txt", b"second"),
    ];
    let started = Instant::now();
    let id = a.service.send(&peer.id, &sources).unwrap();
    let (sent, progress) = a.wait_done();
    let secs = started.elapsed().as_secs_f64();
    let (got, _) = b.wait_done();
    println!("share: {:.1} MB in {secs:.3}s = {:.0} MB/s", big.len() as f64 / 1e6, big.len() as f64 / 1e6 / secs);

    assert!(sent.ok, "send failed: {:?}", sent.error);
    assert!(got.ok, "receive failed: {:?}", got.error);
    assert_eq!(sent.transfer_id, id);
    assert_eq!(sent.paths, sources);
    assert!(progress.iter().any(|e| matches!(e, Event::Progress(p) if p.done == p.total)));
    let names: Vec<String> = got.paths.iter().map(|p| Path::new(p).file_name().unwrap().to_string_lossy().into_owned()).collect();
    assert_eq!(names, ["empty.txt", "تقرير مالي ٢٠٢٦.pdf", "big.bin", "same.txt", "same (2).txt"]);
    for (source, saved) in sources.iter().zip(&got.paths) {
        let want = std::fs::read(source).unwrap();
        let have = std::fs::read(saved).unwrap();
        assert_eq!(want, have, "{saved} differs");
        assert_eq!(blake3::hash(&want), blake3::hash(&have));
        assert!(Path::new(saved).starts_with(b.inbox()));
    }
    assert!(leftovers(&b.inbox()).iter().all(|n| !n.ends_with(".part")));

    // Trusted, but B has never seen A at this address: it still asks.
    a.service.send(&peer.id, &sources[1..2]).unwrap();
    assert!(a.wait_done().0.ok);
    let (again, events) = b.wait_done();
    assert!(events.iter().any(|e| matches!(e, Event::Offer(_))));
    assert!(again.paths[0].ends_with("تقرير مالي ٢٠٢٦ (2).pdf"));

    // Trusted and known at that address: no answer needed, never overwrites.
    b.service.add_peer(&a.address()).unwrap();
    a.service.send(&peer.id, &sources[1..2]).unwrap();
    assert!(a.wait_done().0.ok);
    let (third, events) = b.wait_done();
    assert!(!events.iter().any(|e| matches!(e, Event::Offer(_))));
    assert!(third.paths[0].ends_with("تقرير مالي ٢٠٢٦ (3).pdf"));
}

#[test]
fn share_file_changed_while_waiting_is_not_sent_cut_short() {
    let a = Node::start(None);
    let b = Node::start(None);
    let peer = a.service.add_peer(&b.address()).unwrap();
    let source = write_source(&a, "growing.pdf", b"%PDF-1.7 first part");
    a.service.send(&peer.id, &[source.clone()]).unwrap();
    let offer = wait_offer(&b);
    std::fs::OpenOptions::new().append(true).open(&source).unwrap().write_all(b" more").unwrap();
    assert!(b.service.answer(&offer, true, false));
    let (sent, _) = a.wait_done();
    assert_eq!(sent.error.unwrap().code, "disk");
    assert!(!b.wait_done().0.ok);
    assert!(leftovers(&b.inbox()).is_empty(), "left: {:?}", leftovers(&b.inbox()));
}

#[test]
fn share_one_pending_offer_per_address() {
    let b = Node::start(None);
    let offer = json!({ "kind": "offer", "v": 1, "fromId": "feedfacefeedface", "fromName": "Raw", "files": [{ "name": "a", "size": 1 }] });
    let mut first = TcpStream::connect(b.address()).unwrap();
    proto::write_line(&mut first, &offer).unwrap();
    wait_offer(&b);
    let mut second = TcpStream::connect(b.address()).unwrap();
    second.set_read_timeout(Some(WAIT)).unwrap();
    proto::write_line(&mut second, &offer).unwrap();
    let reply = proto::read_line(&mut BufReader::new(second)).unwrap();
    assert_eq!(proto::parse_reply(&reply).unwrap_err().code, "busy");
}

fn wait_offer(node: &Node) -> String {
    let deadline = Instant::now() + WAIT;
    while Instant::now() < deadline {
        if let Ok(Event::Offer(offer)) = node.events.recv_timeout(Duration::from_millis(50)) {
            return offer.offer_id;
        }
    }
    panic!("offer never arrived");
}

#[test]
fn share_declined_offer_reports_declined() {
    let a = Node::start(None);
    let b = Node::start(Some(false));
    let peer = a.service.add_peer(&b.address()).unwrap();
    let source = write_source(&a, "no.pdf", b"nope");
    a.service.send(&peer.id, &[source]).unwrap();
    let (done, _) = a.wait_done();
    assert!(!done.ok);
    assert_eq!(done.error.unwrap().code, "declined");
    assert!(leftovers(&b.inbox()).is_empty());
    assert!(!b.service.is_trusted(&a.service.id()));
}

fn raw_offer(node: &Node, files: serde_json::Value) -> (TcpStream, BufReader<TcpStream>) {
    let mut stream = TcpStream::connect(node.address()).unwrap();
    stream.set_read_timeout(Some(WAIT)).unwrap();
    let offer = json!({ "kind": "offer", "v": 1, "fromId": "feedfacefeedface", "fromName": "Raw", "files": files });
    proto::write_line(&mut stream, &offer).unwrap();
    let mut reader = BufReader::new(stream.try_clone().unwrap());
    let reply = proto::read_line(&mut reader).unwrap();
    assert!(proto::parse_reply(&reply).is_ok(), "offer refused: {reply}");
    (stream, reader)
}

#[test]
fn share_corrupt_hash_is_verify_failed_and_leaves_nothing() {
    let b = Node::start(Some(true));
    let data = pseudo_random(3 * 1024 * 1024 + 5, "bad");
    let (mut stream, mut reader) = raw_offer(&b, json!([{ "name": "bad.bin", "size": data.len() }, { "name": "next.bin", "size": 4 }]));
    stream.write_all(&data).unwrap();
    let mut wrong = *blake3::hash(&data).as_bytes();
    wrong[0] ^= 0xff;
    stream.write_all(&wrong).unwrap();
    let reply = proto::read_line(&mut reader).unwrap();
    assert_eq!(proto::parse_reply(&reply).unwrap_err().code, "verify_failed");
    drop(stream);
    drop(reader);
    let (done, _) = b.wait_done();
    assert!(!done.ok);
    assert_eq!(done.error.unwrap().code, "verify_failed");
    assert!(leftovers(&b.inbox()).is_empty(), "left: {:?}", leftovers(&b.inbox()));
}

#[test]
fn share_dropped_sender_deletes_partial_file() {
    let b = Node::start(Some(true));
    let (mut stream, _reader) = raw_offer(&b, json!([{ "name": "half.bin", "size": 10_000_000 }]));
    stream.write_all(&pseudo_random(4_000_000, "half")).unwrap();
    drop(stream);
    drop(_reader);
    let (done, _) = b.wait_done();
    assert!(!done.ok);
    assert_eq!(done.error.unwrap().code, "network");
    assert!(leftovers(&b.inbox()).is_empty());
}

#[test]
fn share_sanitizes_hostile_names_and_reads_no_more_than_announced() {
    let b = Node::start(Some(true));
    let (mut stream, mut reader) = raw_offer(&b, json!([{ "name": "", "size": 0 }, { "name": "..\\..\\evil.txt", "size": 3 }]));
    stream.write_all(blake3::hash(b"").as_bytes()).unwrap();
    stream.write_all(b"abc").unwrap();
    stream.write_all(blake3::hash(b"abc").as_bytes()).unwrap();
    stream.write_all(b"EXTRA BYTES THE RECEIVER MUST IGNORE").unwrap();
    let reply = proto::parse_reply(&proto::read_line(&mut reader).unwrap()).unwrap();
    assert_eq!(reply["saved"], json!(["file", "evil.txt"]));
    let (done, _) = b.wait_done();
    assert!(done.ok);
    assert_eq!(std::fs::read(b.inbox().join("evil.txt")).unwrap(), b"abc");
    assert_eq!(std::fs::read(b.inbox().join("file")).unwrap(), b"");
}

#[test]
fn share_sender_cancel_reports_cancelled() {
    let a = Node::start(None);
    let b = Node::start(None);
    let peer = a.service.add_peer(&b.address()).unwrap();
    let id = a.service.send(&peer.id, &[write_source(&a, "wait.pdf", b"x")]).unwrap();
    let deadline = Instant::now() + WAIT;
    while !b.events.try_iter().any(|e| matches!(e, Event::Offer(_))) {
        assert!(Instant::now() < deadline, "offer never arrived");
        std::thread::sleep(Duration::from_millis(20));
    }
    assert!(a.service.cancel(&id));
    let (done, _) = a.wait_done();
    assert_eq!(done.error.unwrap().code, "cancelled");
    let closed = b.events.recv_timeout(WAIT).unwrap();
    assert!(matches!(closed, Event::OfferClosed(_)));
}

#[test]
fn share_discovery_tracks_announces() {
    let node = Node::start(None);
    let src = IpAddr::V4(Ipv4Addr::new(192, 168, 1, 7));
    let packet = |id: &str, app: &str| {
        serde_json::to_vec(&json!({ "app": app, "v": 1, "kind": "announce", "id": id, "name": "Desk", "port": 5000 })).unwrap()
    };
    assert!(handle_announce(&node.service, &packet("0123456789abcdef", "freepdf"), src));
    assert!(!handle_announce(&node.service, &packet("0123456789abcdef", "freepdf"), src));
    assert!(!handle_announce(&node.service, &packet(&node.service.id(), "freepdf"), src));
    assert!(!handle_announce(&node.service, &packet("aaaaaaaaaaaaaaaa", "other"), src));
    assert!(!handle_announce(&node.service, b"not json", src));
    assert!(!handle_announce(&node.service, &packet("not-a-device-id!", "freepdf"), src));
    let spoofer = IpAddr::V4(Ipv4Addr::new(192, 168, 1, 66));
    assert!(!handle_announce(&node.service, &packet("0123456789abcdef", "freepdf"), spoofer));
    let peers = node.service.peers();
    assert_eq!(peers.len(), 1);
    assert_eq!(peers[0].address, "192.168.1.7:5000");
    assert!(node.service.prune_peers(Duration::ZERO));
    assert!(node.service.peers().is_empty());
}

#[test]
fn share_rejects_bad_requests() {
    let a = Node::start(None);
    assert_eq!(a.service.send("missing", &["x".into()]).unwrap_err().code, "peer_not_found");
    assert_eq!(a.service.add_peer(&a.address()).unwrap_err().code, "bad_args");
    assert_eq!(a.service.add_peer("127.0.0.1:1").unwrap_err().code, "unreachable");
    assert_eq!(a.service.set_name("  ").unwrap_err().code, "bad_args");
    a.service.set_name(" Laptop ").unwrap();
    assert_eq!(a.service.name(), "Laptop");

    let mut stream = TcpStream::connect(a.address()).unwrap();
    stream.write_all(&vec![b'x'; proto::MAX_LINE + 10]).unwrap();
    stream.write_all(b"\n").unwrap();
    let mut reply = String::new();
    let _ = stream.read_to_string(&mut reply);
    assert_eq!(proto::parse_reply(reply.trim()).unwrap_err().code, "bad_args");
}
