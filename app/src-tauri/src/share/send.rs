use std::fs::File;
use std::io::{BufRead, BufReader, ErrorKind, Read, Write};
use std::net::{Shutdown, SocketAddr, TcpStream};
use std::path::PathBuf;
use std::sync::mpsc::{self, Receiver};
use std::time::Duration;

use serde_json::{json, Value};

use super::events::{Cancel, Done, Event, Meter, Peer};
use super::proto::{self, FileMeta, ShareError, DECIDE_TIMEOUT, IO_TIMEOUT, MAX_FILES, MAX_LINE};
use super::relay::relay;
use super::service::Service;

const CONNECT_TIMEOUT: Duration = Duration::from_secs(3);
const ACK_GRACE: Duration = Duration::from_secs(3);

pub struct Job {
    peer: Peer,
    paths: Vec<PathBuf>,
    files: Vec<FileMeta>,
    offer: Value,
}

impl Job {
    /// Checks every path before anything goes on the network.
    pub fn prepare(from_id: String, from_name: String, peer: Peer, paths: &[String]) -> Result<Job, ShareError> {
        if paths.is_empty() || paths.len() > MAX_FILES {
            return Err(ShareError::new("bad_args", format!("Choose between 1 and {MAX_FILES} files to send.")));
        }
        let mut files = Vec::with_capacity(paths.len());
        for path in paths {
            let meta = std::fs::metadata(path).ok().filter(|m| m.is_file()).ok_or_else(|| {
                ShareError::new("bad_args", format!("{path} is not a file that can be read. Check it still exists."))
            })?;
            let name = std::path::Path::new(path)
                .file_name()
                .map(|n| n.to_string_lossy().into_owned())
                .unwrap_or_else(|| "file".to_string());
            files.push(FileMeta { name, size: meta.len() });
        }
        let offer = json!({ "kind": "offer", "v": proto::VERSION, "fromId": from_id, "fromName": from_name, "files": files });
        if serde_json::to_vec(&offer).map_or(true, |v| v.len() > MAX_LINE) {
            return Err(ShareError::new("bad_args", "Too many files in one go. Send them in smaller groups."));
        }
        Ok(Job { peer, paths: paths.iter().map(PathBuf::from).collect(), files, offer })
    }
}

pub fn run(service: &Service, transfer_id: &str, job: Job, cancel: &Cancel) {
    let mut meter = Meter::new(service.sink.clone(), transfer_id, "send", &job.peer.name, proto::total_size(&job.files));
    let outcome = transfer(&job, cancel, &mut meter);
    if outcome.is_ok() {
        meter.finish();
    }
    service.emit(Event::Done(Done {
        transfer_id: transfer_id.to_string(),
        direction: "send",
        peer_name: job.peer.name.clone(),
        ok: outcome.is_ok(),
        paths: job.paths.iter().map(|p| p.to_string_lossy().into_owned()).collect(),
        error: outcome.err(),
    }));
}


fn transfer(job: &Job, cancel: &Cancel, meter: &mut Meter) -> Result<(), ShareError> {
    let peer = &job.peer.name;
    let (mut stream, reader) = open(job, cancel).map_err(|e| cancel.explain(e))?;
    meter.restart();
    let ack = watch_replies(reader, stream.try_clone().map_err(|_| ShareError::network(peer))?);
    let sent = send_files(job, &mut stream, meter);
    let reply = match &sent {
        Ok(()) => ack.recv_timeout(IO_TIMEOUT + ACK_GRACE),
        Err(_) => ack.recv_timeout(ACK_GRACE),
    };
    let _ = stream.shutdown(Shutdown::Both);
    match (sent, reply) {
        (_, Ok(Err(refused))) => Err(refused),
        (Err(e), _) => Err(cancel.explain(e)),
        (Ok(()), Ok(Ok(_))) => Ok(()),
        // Every byte went out, so the files may well be there.
        (Ok(()), Err(_)) => Err(ShareError::new(
            "network",
            format!("{peer} did not confirm the files arrived. Check that PC before sending them again."),
        )),
    }
}

/// Connects, sends the offer and waits for the receiver to accept.
fn open(job: &Job, cancel: &Cancel) -> Result<(TcpStream, BufReader<TcpStream>), ShareError> {
    let peer = &job.peer.name;
    let net = |_| ShareError::network(peer);
    let mut stream = connect(&job.peer)?;
    cancel.attach(&stream);
    let _ = stream.set_write_timeout(Some(IO_TIMEOUT));
    let _ = stream.set_read_timeout(Some(DECIDE_TIMEOUT + Duration::from_secs(10)));
    proto::write_line(&mut stream, &job.offer).map_err(net)?;
    let mut reader = BufReader::new(stream.try_clone().map_err(net)?);
    let line = proto::read_line(&mut reader).map_err(|e| match e.kind() {
        ErrorKind::TimedOut | ErrorKind::WouldBlock => {
            ShareError::new("declined", format!("{peer} did not answer in time. Try again when someone is at that PC."))
        }
        _ => ShareError::network(peer),
    })?;
    proto::parse_reply(&line)?;
    let _ = stream.set_read_timeout(Some(IO_TIMEOUT));
    Ok((stream, reader))
}

fn connect(peer: &Peer) -> Result<TcpStream, ShareError> {
    let unreachable = || {
        ShareError::new(
            "unreachable",
            format!("Could not reach {}. Check Free PDF is open on that PC and both are on the same network.", peer.name),
        )
    };
    let addr: SocketAddr = peer.address.parse().map_err(|_| unreachable())?;
    let stream = TcpStream::connect_timeout(&addr, CONNECT_TIMEOUT).map_err(|_| unreachable())?;
    proto::tune(&stream);
    Ok(stream)
}

/// Waits for the receiver's one reply line on its own thread. An early error
/// (bad hash, full disk) shuts the socket so the sender stops at once.
fn watch_replies(mut reader: BufReader<TcpStream>, stream: TcpStream) -> Receiver<Result<Value, ShareError>> {
    let (tx, rx) = mpsc::channel();
    std::thread::spawn(move || {
        let ready = loop {
            match reader.fill_buf() {
                Ok(buf) => break !buf.is_empty(),
                Err(e) if matches!(e.kind(), ErrorKind::TimedOut | ErrorKind::WouldBlock | ErrorKind::Interrupted) => {}
                Err(_) => break false,
            }
        };
        if !ready {
            return;
        }
        let Ok(line) = proto::read_line(&mut reader) else { return };
        let reply = proto::parse_reply(&line);
        if reply.is_err() {
            let _ = stream.shutdown(Shutdown::Both);
        }
        let _ = tx.send(reply);
    });
    rx
}

fn send_files(job: &Job, stream: &mut TcpStream, meter: &mut Meter) -> Result<(), ShareError> {
    let peer = &job.peer.name;
    for (path, meta) in job.paths.iter().zip(&job.files) {
        let unreadable = |e: std::io::Error| {
            ShareError::new("disk", format!("Could not read {} ({e}). Check the file is not open or moved.", meta.name))
        };
        let mut file = File::open(path).map_err(unreadable)?;
        let mut hasher = blake3::Hasher::new();
        meter.start_file(&meta.name);
        relay(
            meta.size,
            |buf| {
                file.read_exact(buf).map_err(unreadable)?;
                hasher.update(buf);
                Ok(())
            },
            |buf| {
                stream.write_all(buf).map_err(|_| ShareError::network(peer))?;
                meter.add(buf.len());
                Ok(())
            },
        )?;
        // A file still being written would arrive cut short yet pass the hash.
        if file.metadata().map_or(true, |m| m.len() != meta.size) {
            return Err(ShareError::new(
                "disk",
                format!("{} changed while it was being sent. Wait until it is saved, then send it again.", meta.name),
            ));
        }
        stream.write_all(hasher.finalize().as_bytes()).map_err(|_| ShareError::network(peer))?;
    }
    stream.flush().map_err(|_| ShareError::network(peer))
}
