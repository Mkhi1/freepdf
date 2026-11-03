use std::fs::File;
use std::io::{BufReader, BufWriter, ErrorKind, Read, Write};
use std::net::{IpAddr, Shutdown, TcpStream};
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::mpsc::{self, RecvTimeoutError};
use std::sync::Arc;
use std::time::{Duration, Instant};

use serde_json::json;

use super::events::{Done, Event, Meter, OfferEvent};
use super::names::{clean_device_name, part_path, random_hex, sanitize_file_name, unique_path};
use super::proto::{self, FileMeta, OfferHeader, ShareError, DECIDE_TIMEOUT, DISK_BUFFER};
use super::relay::relay;
use super::service::Service;

const POLL: Duration = Duration::from_millis(250);
const DRAIN_LIMIT: Duration = Duration::from_secs(10);

enum Decision {
    Accept,
    Decline,
    Timeout,
    Gone,
    TooMany,
}

struct Busy<'a>(&'a AtomicBool);

impl Drop for Busy<'_> {
    fn drop(&mut self) {
        self.0.store(false, Ordering::SeqCst);
    }
}

struct Link<'a> {
    reader: &'a mut BufReader<TcpStream>,
    writer: &'a mut TcpStream,
}

fn refuse(writer: &mut TcpStream, code: &str, message: String) {
    let _ = proto::write_line(writer, &proto::error_reply(&ShareError::new(code, message)));
}

fn busy_message(service: &Service) -> String {
    format!("{} is receiving other files. Try again in a moment.", service.name())
}

pub fn handle_offer(service: &Arc<Service>, mut reader: BufReader<TcpStream>, mut writer: TcpStream, offer: OfferHeader) {
    if service.receiving.load(Ordering::SeqCst) {
        return refuse(&mut writer, "busy", busy_message(service));
    }
    let ip = writer.peer_addr().ok().map(|a| a.ip());
    let offer_id = format!("r{}", random_hex(12));
    let peer = clean_device_name(&offer.from_name).unwrap_or_else(|| "Another PC".to_string());
    let files: Vec<FileMeta> =
        offer.files.iter().map(|f| FileMeta { name: sanitize_file_name(&f.name), size: f.size }).collect();
    match decide(service, &offer_id, &offer.from_id, ip, &peer, &files, &writer) {
        Decision::Accept => {}
        Decision::Decline => return refuse(&mut writer, "declined", format!("{} declined the files.", service.name())),
        Decision::TooMany => return refuse(&mut writer, "busy", busy_message(service)),
        Decision::Timeout => {
            service.emit(Event::OfferClosed(offer_id));
            return refuse(&mut writer, "declined", format!("Nobody accepted the files on {} in time.", service.name()));
        }
        Decision::Gone => return service.emit(Event::OfferClosed(offer_id)),
    }
    if service.receiving.swap(true, Ordering::SeqCst) {
        refuse(&mut writer, "busy", busy_message(service));
        let busy = ShareError::new("busy", "Other files were still arriving. Ask the sender to send these again.");
        return service.emit(done_event(offer_id, peer, &[], Err(busy)));
    }
    let _busy = Busy(&service.receiving);
    receive_accepted(service, Link { reader: &mut reader, writer: &mut writer }, &offer_id, &peer, &files);
}

fn receive_accepted(service: &Service, link: Link<'_>, offer_id: &str, peer: &str, files: &[FileMeta]) {
    let Link { reader, writer } = link;
    let cancel = service.register(offer_id);
    cancel.attach(writer);
    let mut saved = Vec::new();
    let mut meter = Meter::new(service.sink.clone(), offer_id, "receive", peer, proto::total_size(files));
    let outcome = proto::write_line(writer, &json!({ "ok": true }))
        .map_err(|_| ShareError::network(peer))
        .and_then(|_| receive_files(&service.receive_dir, reader, files, &mut meter, &mut saved))
        .map_err(|e| cancel.explain(e));
    finish(writer, reader, &outcome, &saved, &mut meter);
    service.unregister(offer_id);
    service.emit(done_event(offer_id.to_string(), peer.to_string(), &saved, outcome));
}

fn done_event(transfer_id: String, peer_name: String, saved: &[PathBuf], outcome: Result<(), ShareError>) -> Event {
    Event::Done(Done {
        transfer_id,
        direction: "receive",
        peer_name,
        ok: outcome.is_ok(),
        paths: saved.iter().map(|p| p.to_string_lossy().into_owned()).collect(),
        error: outcome.err(),
    })
}

fn decide(
    service: &Service,
    offer_id: &str,
    from_id: &str,
    ip: Option<IpAddr>,
    peer: &str,
    files: &[FileMeta],
    stream: &TcpStream,
) -> Decision {
    if ip.is_some_and(|ip| service.is_trusted_at(from_id, ip)) {
        return Decision::Accept;
    }
    let (tx, rx) = mpsc::channel();
    if !service.add_pending(offer_id, from_id, ip, tx) {
        return Decision::TooMany;
    }
    service.emit(Event::Offer(OfferEvent {
        offer_id: offer_id.to_string(),
        from_id: from_id.to_string(),
        from_name: peer.to_string(),
        files: files.to_vec(),
        total: proto::total_size(files),
    }));
    let deadline = Instant::now() + DECIDE_TIMEOUT;
    let decision = loop {
        match rx.recv_timeout(POLL) {
            Ok(true) => break Decision::Accept,
            Ok(false) => break Decision::Decline,
            Err(RecvTimeoutError::Disconnected) => break Decision::Gone,
            Err(RecvTimeoutError::Timeout) => {}
        }
        if sender_gone(stream) {
            break Decision::Gone;
        }
        if Instant::now() >= deadline {
            break Decision::Timeout;
        }
    };
    // answer() already took the entry and told the UI it was delivered, so
    // honour that answer instead of dropping it.
    if !service.remove_pending(offer_id) && matches!(decision, Decision::Timeout | Decision::Gone) {
        return match rx.recv_timeout(POLL) {
            Ok(true) => Decision::Accept,
            Ok(false) => Decision::Decline,
            Err(_) => decision,
        };
    }
    decision
}

/// The sender sends nothing until we answer, so readable means it hung up.
fn sender_gone(stream: &TcpStream) -> bool {
    if stream.set_nonblocking(true).is_err() {
        return true;
    }
    let mut probe = [0u8; 1];
    let gone = match stream.peek(&mut probe) {
        Ok(0) => true,
        Ok(_) => false,
        Err(e) => e.kind() != ErrorKind::WouldBlock,
    };
    let _ = stream.set_nonblocking(false);
    gone
}

fn finish(
    writer: &mut TcpStream,
    reader: &mut BufReader<TcpStream>,
    outcome: &Result<(), ShareError>,
    saved: &[PathBuf],
    meter: &mut Meter,
) {
    match outcome {
        Ok(()) => {
            meter.finish();
            let names: Vec<String> = saved
                .iter()
                .map(|p| p.file_name().map(|n| n.to_string_lossy().into_owned()).unwrap_or_default())
                .collect();
            let _ = proto::write_line(writer, &json!({ "ok": true, "saved": names }));
        }
        Err(err) if err.code == "verify_failed" || err.code == "disk" => {
            let _ = proto::write_line(writer, &proto::error_reply(err));
            let _ = writer.shutdown(Shutdown::Write);
            drain(reader);
        }
        Err(_) => {}
    }
}

/// Reads until the sender hangs up, so it gets our error line instead of a reset.
pub fn drain(reader: &mut BufReader<TcpStream>) {
    let started = Instant::now();
    let mut sink = vec![0u8; 64 * 1024];
    let _ = reader.get_ref().set_read_timeout(Some(Duration::from_secs(2)));
    while started.elapsed() < DRAIN_LIMIT {
        match reader.read(&mut sink) {
            Ok(0) | Err(_) => break,
            Ok(_) => {}
        }
    }
}

fn receive_files(
    dir: &Path,
    reader: &mut BufReader<TcpStream>,
    files: &[FileMeta],
    meter: &mut Meter,
    saved: &mut Vec<PathBuf>,
) -> Result<(), ShareError> {
    std::fs::create_dir_all(dir).map_err(|e| disk_error(dir, &e))?;
    for meta in files {
        meter.start_file(&meta.name);
        saved.push(receive_one(dir, meta, reader, meter)?);
    }
    Ok(())
}

fn receive_one(dir: &Path, meta: &FileMeta, reader: &mut BufReader<TcpStream>, meter: &mut Meter) -> Result<PathBuf, ShareError> {
    let target = unique_path(dir, &meta.name);
    let part = part_path(&target);
    let checked = write_part(&part, meta.size, reader, meter).and_then(|hash| {
        let mut expected = [0u8; 32];
        reader.read_exact(&mut expected).map_err(|_| ShareError::new("network", lost()))?;
        if hash != expected {
            return Err(ShareError::new(
                "verify_failed",
                format!("{} arrived damaged and was deleted. Send it again.", meta.name),
            ));
        }
        place(&part, dir, &meta.name, target)
    });
    if checked.is_err() {
        let _ = std::fs::remove_file(&part);
    }
    checked
}

/// Moves the finished ".part" file to a free name without ever replacing a
/// file that appeared there meanwhile: a hard link fails when the name is
/// taken. Drives without hard links (FAT, exFAT) fall back to a checked rename.
fn place(part: &Path, dir: &Path, name: &str, first: PathBuf) -> Result<PathBuf, ShareError> {
    let mut target = first;
    loop {
        match std::fs::hard_link(part, &target) {
            Ok(()) => {
                let _ = std::fs::remove_file(part);
                break;
            }
            Err(e) if e.kind() == ErrorKind::AlreadyExists => target = unique_path(dir, name),
            Err(_) => {
                if target.exists() {
                    target = unique_path(dir, name);
                }
                std::fs::rename(part, &target).map_err(|e| disk_error(dir, &e))?;
                break;
            }
        }
    }
    mark_from_network(&target);
    Ok(target)
}

/// Adds the Mark of the Web, so Windows warns before running a received file.
fn mark_from_network(path: &Path) {
    if cfg!(windows) {
        let mut stream = path.as_os_str().to_os_string();
        stream.push(":Zone.Identifier");
        let _ = std::fs::write(stream, "[ZoneTransfer]\r\nZoneId=3\r\n");
    }
}

fn write_part(part: &Path, size: u64, reader: &mut BufReader<TcpStream>, meter: &mut Meter) -> Result<[u8; 32], ShareError> {
    let dir = part.parent().unwrap_or(part);
    let file = File::create(part).map_err(|e| disk_error(dir, &e))?;
    file.set_len(size).map_err(|e| disk_error(dir, &e))?;
    let mut out = BufWriter::with_capacity(DISK_BUFFER, file);
    let mut hasher = blake3::Hasher::new();
    relay(
        size,
        |buf| reader.read_exact(buf).map_err(|_| ShareError::new("network", lost())),
        |buf| {
            hasher.update(buf);
            out.write_all(buf).map_err(|e| disk_error(dir, &e))?;
            meter.add(buf.len());
            Ok(())
        },
    )?;
    out.flush().map_err(|e| disk_error(dir, &e))?;
    Ok(*hasher.finalize().as_bytes())
}

fn lost() -> String {
    "The sending PC stopped or the network dropped. Ask them to send the files again.".to_string()
}

fn disk_error(dir: &Path, err: &std::io::Error) -> ShareError {
    ShareError::new(
        "disk",
        format!("Could not save files in {} ({err}). Check the disk has free space.", dir.display()),
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn place_never_replaces_a_file_that_appeared() {
        let dir = std::env::temp_dir().join(format!("freepdf-place-{}", random_hex(10)));
        std::fs::create_dir_all(&dir).unwrap();
        let first = unique_path(&dir, "r.pdf");
        let part = part_path(&first);
        std::fs::write(&part, b"new").unwrap();
        std::fs::write(&first, b"someone else").unwrap();
        let saved = place(&part, &dir, "r.pdf", first.clone()).unwrap();
        assert_eq!(saved, dir.join("r (2).pdf"));
        assert_eq!(std::fs::read(&first).unwrap(), b"someone else");
        assert_eq!(std::fs::read(&saved).unwrap(), b"new");
        assert!(!part.exists());
        std::fs::remove_dir_all(&dir).unwrap();
    }
}
