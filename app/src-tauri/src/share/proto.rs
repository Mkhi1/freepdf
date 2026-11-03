use std::io::{self, BufRead, Write};
use std::net::TcpStream;
use std::time::{Duration, Instant};

use serde::{Deserialize, Serialize};
use serde_json::Value;
use socket2::SockRef;

pub const VERSION: u64 = 1;
pub const DEFAULT_TCP_PORT: u16 = 47821;
pub const DEFAULT_UDP_PORT: u16 = 47820;
pub const MAX_LINE: usize = 64 * 1024;
pub const MAX_FILES: usize = 2000;
pub const CHUNK: usize = 1024 * 1024;
pub const DISK_BUFFER: usize = 4 * 1024 * 1024;
pub const IO_TIMEOUT: Duration = Duration::from_secs(30);
pub const DECIDE_TIMEOUT: Duration = Duration::from_secs(120);
const SOCKET_BUFFER: usize = 4 * 1024 * 1024;

#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct ShareError {
    pub code: String,
    pub message: String,
}

impl ShareError {
    pub fn new(code: &str, message: impl Into<String>) -> Self {
        Self { code: code.to_string(), message: message.into() }
    }

    pub fn network(peer: &str) -> Self {
        Self::new(
            "network",
            format!(
                "The connection to {peer} was lost. Check both PCs are on the same network and try again."
            ),
        )
    }

    pub fn cancelled() -> Self {
        Self::new("cancelled", "The transfer was cancelled.")
    }
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct FileMeta {
    pub name: String,
    pub size: u64,
}

pub fn total_size(files: &[FileMeta]) -> u64 {
    files.iter().fold(0, |sum, f| sum.saturating_add(f.size))
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct OfferHeader {
    pub v: u64,
    pub from_id: String,
    pub from_name: String,
    pub files: Vec<FileMeta>,
}

#[derive(Debug, Deserialize)]
pub struct HelloReply {
    pub id: String,
    pub name: String,
    pub port: u16,
}

pub enum Header {
    Hello,
    Offer(OfferHeader),
}

/// Reads one '\n'-terminated line of at most MAX_LINE bytes. Never consumes
/// past the newline, so file bytes that follow stay in the reader.
pub fn read_line(reader: &mut impl BufRead) -> io::Result<String> {
    read_line_before(reader, None)
}

/// Like `read_line`, but gives up at `deadline`, so a peer that trickles one
/// byte at a time cannot hold the connection open.
pub fn read_line_before(reader: &mut impl BufRead, deadline: Option<Instant>) -> io::Result<String> {
    let mut line = Vec::new();
    loop {
        if deadline.is_some_and(|d| Instant::now() >= d) {
            return Err(io::Error::new(io::ErrorKind::TimedOut, "header took too long"));
        }
        let available = match reader.fill_buf() {
            Ok(buf) => buf,
            Err(e) if e.kind() == io::ErrorKind::Interrupted => continue,
            Err(e) => return Err(e),
        };
        if available.is_empty() {
            return Err(io::Error::new(io::ErrorKind::UnexpectedEof, "connection closed"));
        }
        let (take, done) = match available.iter().position(|&b| b == b'\n') {
            Some(i) => (i + 1, true),
            None => (available.len(), false),
        };
        if line.len() + take > MAX_LINE + 1 {
            return Err(io::Error::new(io::ErrorKind::InvalidData, "header line too long"));
        }
        line.extend_from_slice(&available[..take]);
        reader.consume(take);
        if done {
            line.pop();
            if line.last() == Some(&b'\r') {
                line.pop();
            }
            return String::from_utf8(line)
                .map_err(|_| io::Error::new(io::ErrorKind::InvalidData, "header is not UTF-8"));
        }
    }
}

pub fn write_line(stream: &mut impl Write, value: &Value) -> io::Result<()> {
    let mut line = serde_json::to_vec(value)?;
    line.push(b'\n');
    stream.write_all(&line)?;
    stream.flush()
}

pub fn parse_header(line: &str) -> Result<Header, ShareError> {
    let bad = |what: &str| ShareError::new("bad_args", format!("The request was not understood ({what})."));
    let value: Value = serde_json::from_str(line).map_err(|_| bad("not JSON"))?;
    match value["kind"].as_str() {
        Some("hello") => Ok(Header::Hello),
        Some("offer") => {
            let offer: OfferHeader = serde_json::from_value(value).map_err(|_| bad("bad offer"))?;
            if offer.v != VERSION {
                return Err(ShareError::new(
                    "bad_args",
                    "The other PC runs a different Free PDF version. Update both and try again.",
                ));
            }
            if offer.files.is_empty() || offer.files.len() > MAX_FILES {
                return Err(bad("file count"));
            }
            Ok(Header::Offer(offer))
        }
        _ => Err(bad("unknown kind")),
    }
}

/// Reply line of a receiver: Ok(the line) when "ok" is true, the error otherwise.
pub fn parse_reply(line: &str) -> Result<Value, ShareError> {
    let value: Value = serde_json::from_str(line)
        .map_err(|_| ShareError::new("network", "The other PC sent an unexpected reply. Try again."))?;
    if value["ok"].as_bool() == Some(true) {
        return Ok(value);
    }
    let code = value["code"].as_str().unwrap_or("network");
    let message = value["message"].as_str().unwrap_or("The other PC stopped the transfer.");
    Err(ShareError::new(code, message))
}

pub fn error_reply(err: &ShareError) -> Value {
    serde_json::json!({ "ok": false, "code": err.code, "message": err.message })
}

/// Large kernel buffers keep a fast link full; Nagle stays on for bulk data.
pub fn tune(stream: &TcpStream) {
    let sock = SockRef::from(stream);
    let _ = sock.set_send_buffer_size(SOCKET_BUFFER);
    let _ = sock.set_recv_buffer_size(SOCKET_BUFFER);
    let _ = sock.set_keepalive(true);
}

pub fn set_timeouts(stream: &TcpStream, limit: Option<Duration>) {
    let _ = stream.set_read_timeout(limit);
    let _ = stream.set_write_timeout(limit);
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::{BufReader, Cursor, Read};

    #[test]
    fn line_stops_at_newline_and_keeps_the_rest() {
        let mut reader = BufReader::new(Cursor::new(b"{\"kind\":\"hello\"}\r\nRAWBYTES".to_vec()));
        assert_eq!(read_line(&mut reader).unwrap(), "{\"kind\":\"hello\"}");
        let mut rest = Vec::new();
        reader.read_to_end(&mut rest).unwrap();
        assert_eq!(rest, b"RAWBYTES");
    }

    #[test]
    fn line_limits() {
        let mut ok = vec![b'a'; MAX_LINE];
        ok.push(b'\n');
        let mut reader = BufReader::with_capacity(1000, Cursor::new(ok));
        assert_eq!(read_line(&mut reader).unwrap().len(), MAX_LINE);

        let mut long = vec![b'a'; MAX_LINE + 1];
        long.push(b'\n');
        let mut reader = BufReader::with_capacity(1000, Cursor::new(long));
        assert_eq!(read_line(&mut reader).unwrap_err().kind(), io::ErrorKind::InvalidData);

        let mut reader = BufReader::new(Cursor::new(b"no newline".to_vec()));
        assert_eq!(read_line(&mut reader).unwrap_err().kind(), io::ErrorKind::UnexpectedEof);

        let mut reader = BufReader::new(Cursor::new(vec![0xff, 0xfe, b'\n']));
        assert_eq!(read_line(&mut reader).unwrap_err().kind(), io::ErrorKind::InvalidData);

        let mut reader = BufReader::new(Cursor::new(b"{}\n".to_vec()));
        let past = Some(Instant::now());
        assert_eq!(read_line_before(&mut reader, past).unwrap_err().kind(), io::ErrorKind::TimedOut);
    }

    #[test]
    fn header_parsing() {
        assert!(matches!(parse_header(r#"{"kind":"hello"}"#), Ok(Header::Hello)));
        let offer = r#"{"kind":"offer","v":1,"fromId":"ab","fromName":"PC","files":[{"name":"a","size":3}]}"#;
        match parse_header(offer) {
            Ok(Header::Offer(o)) => {
                assert_eq!(o.from_id, "ab");
                assert_eq!(o.files, vec![FileMeta { name: "a".into(), size: 3 }]);
            }
            _ => panic!("offer not parsed"),
        }
        let code = |l: &str| parse_header(l).err().map(|e| e.code);
        assert_eq!(code("nope").as_deref(), Some("bad_args"));
        assert_eq!(code(r#"{"kind":"x"}"#).as_deref(), Some("bad_args"));
        assert_eq!(code(r#"{"kind":"offer","v":2,"fromId":"a","fromName":"b","files":[{"name":"a","size":1}]}"#).as_deref(), Some("bad_args"));
        assert_eq!(code(r#"{"kind":"offer","v":1,"fromId":"a","fromName":"b","files":[]}"#).as_deref(), Some("bad_args"));
        assert_eq!(code(r#"{"kind":"offer","v":1,"fromId":"a","fromName":"b","files":[{"name":"a","size":-1}]}"#).as_deref(), Some("bad_args"));
    }

    #[test]
    fn reply_parsing() {
        assert!(parse_reply(r#"{"ok":true}"#).is_ok());
        let err = parse_reply(r#"{"ok":false,"code":"declined","message":"No"}"#).unwrap_err();
        assert_eq!(err, ShareError::new("declined", "No"));
        assert_eq!(parse_reply("garbage").unwrap_err().code, "network");
    }
}
