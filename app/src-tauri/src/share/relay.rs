use std::sync::mpsc::sync_channel;

use super::proto::{ShareError, CHUNK};

const POOL: usize = 4;

/// Moves exactly `size` bytes in 1 MiB chunks. `fill` runs on a helper thread
/// and `drain` on this one, so disk, hashing and network work overlap instead
/// of taking turns. Files of one chunk or less skip the thread.
pub fn relay(
    size: u64,
    mut fill: impl FnMut(&mut [u8]) -> Result<(), ShareError> + Send,
    mut drain: impl FnMut(&[u8]) -> Result<(), ShareError>,
) -> Result<(), ShareError> {
    if size == 0 {
        return Ok(());
    }
    if size <= CHUNK as u64 {
        let mut buf = vec![0u8; size as usize];
        fill(&mut buf)?;
        return drain(&buf);
    }
    std::thread::scope(|scope| {
        let (full_tx, full_rx) = sync_channel::<Vec<u8>>(POOL);
        let (empty_tx, empty_rx) = sync_channel::<Vec<u8>>(POOL);
        for _ in 0..POOL {
            let _ = empty_tx.send(Vec::with_capacity(CHUNK));
        }
        let producer = scope.spawn(move || {
            let mut left = size;
            while left > 0 {
                let Ok(mut buf) = empty_rx.recv() else { return Ok(()) };
                let want = left.min(CHUNK as u64) as usize;
                buf.resize(want, 0);
                fill(&mut buf)?;
                left -= want as u64;
                if full_tx.send(buf).is_err() {
                    return Ok(());
                }
            }
            Ok(())
        });
        let mut drained = Ok(());
        for buf in full_rx.iter() {
            if let Err(e) = drain(&buf) {
                drained = Err(e);
                break;
            }
            let _ = empty_tx.send(buf);
        }
        drop(empty_tx);
        drop(full_rx);
        let produced = producer
            .join()
            .unwrap_or_else(|_| Err(ShareError::new("network", "The transfer stopped unexpectedly. Try again.")));
        drained.and(produced)
    })
}
#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn relays_every_byte_in_order() {
        let size = (CHUNK as u64) * 3 + 12345;
        let mut next = 0u8;
        let mut seen = Vec::new();
        relay(
            size,
            |buf| {
                for b in buf.iter_mut() {
                    *b = next;
                    next = next.wrapping_add(1);
                }
                Ok(())
            },
            |buf| {
                seen.extend_from_slice(buf);
                Ok(())
            },
        )
        .unwrap();
        assert_eq!(seen.len() as u64, size);
        assert!(seen.iter().enumerate().all(|(i, &b)| b == i as u8));
    }

    #[test]
    fn reports_errors_from_either_side() {
        let fail = |_: &mut [u8]| Err(ShareError::new("disk", "x"));
        let err = relay(10, fail, |_| Ok(())).unwrap_err();
        assert_eq!(err.code, "disk");
        let size = (CHUNK as u64) * 20;
        let err = relay(size, |_| Ok(()), |_| Err(ShareError::new("network", "y"))).unwrap_err();
        assert_eq!(err.code, "network");
    }
}
