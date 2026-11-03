use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::{SystemTime, UNIX_EPOCH};

const MAX_NAME: usize = 180;
const RESERVED: [&str; 22] = [
    "CON", "PRN", "AUX", "NUL", "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8",
    "COM9", "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9",
];

static COUNTER: AtomicU64 = AtomicU64::new(0);

/// A random-looking hex id. Mixes the clock, the process and a counter, so two
/// calls never collide inside one process and two PCs almost never do.
pub fn random_hex(len: usize) -> String {
    let nanos = SystemTime::now().duration_since(UNIX_EPOCH).map(|d| d.as_nanos()).unwrap_or(0);
    let mut hasher = blake3::Hasher::new();
    hasher.update(&nanos.to_le_bytes());
    hasher.update(&std::process::id().to_le_bytes());
    hasher.update(&COUNTER.fetch_add(1, Ordering::Relaxed).to_le_bytes());
    hasher.update(std::env::var("COMPUTERNAME").unwrap_or_default().as_bytes());
    let hex = hasher.finalize().to_hex();
    hex[..len.min(64)].to_string()
}

pub fn default_device_name() -> String {
    std::env::var("COMPUTERNAME")
        .ok()
        .map(|n| n.trim().to_string())
        .filter(|n| !n.is_empty())
        .unwrap_or_else(|| "Free PDF device".to_string())
}

/// A device name the user typed, trimmed and limited to 1..=40 characters.
pub fn clean_device_name(name: &str) -> Option<String> {
    let name: String = name.trim().chars().filter(|c| !c.is_control()).collect();
    let count = name.chars().count();
    (1..=40).contains(&count).then_some(name)
}

/// Turns a name from the network into a safe single file name for Windows.
pub fn sanitize_file_name(raw: &str) -> String {
    let base = raw.rsplit(['/', '\\']).next().unwrap_or("");
    let cleaned: String = base
        .chars()
        .filter(|c| !c.is_control() && !matches!(c, '<' | '>' | ':' | '"' | '|' | '?' | '*'))
        .collect();
    let mut name = shorten(cleaned.trim());
    name = name.trim_end_matches(['.', ' ']).trim_start().to_string();
    if name.is_empty() {
        return "file".to_string();
    }
    let stem = name.split('.').next().unwrap_or("").trim_end();
    if RESERVED.iter().any(|r| r.eq_ignore_ascii_case(stem)) {
        name = format!("_{name}");
    }
    name
}

/// Windows counts a name in UTF-16 units (255 at most, and we add " (n)" and
/// ".part"), so long names lose the end of their stem but keep the extension.
fn shorten(name: &str) -> String {
    let units = |s: &str| s.encode_utf16().count();
    if units(name) <= MAX_NAME {
        return name.to_string();
    }
    let (stem, ext) = match split_ext(name) {
        (stem, ext) if units(ext) <= 16 => (stem, ext),
        _ => (name, ""),
    };
    let mut room = MAX_NAME - units(ext);
    let mut kept: String = stem
        .chars()
        .take_while(|c| match room.checked_sub(c.len_utf16()) {
            Some(left) => {
                room = left;
                true
            }
            None => false,
        })
        .collect();
    kept.push_str(ext);
    kept
}

fn split_ext(name: &str) -> (&str, &str) {
    match name.rfind('.') {
        Some(i) if i > 0 => (&name[..i], &name[i..]),
        _ => (name, ""),
    }
}

pub fn part_path(path: &Path) -> PathBuf {
    let mut os = path.as_os_str().to_os_string();
    os.push(".part");
    PathBuf::from(os)
}

/// First free path for `name` in `dir`: "name.ext", then "name (2).ext", ...
/// A path is taken when the file or its ".part" sibling exists.
pub fn unique_path(dir: &Path, name: &str) -> PathBuf {
    let (stem, ext) = split_ext(name);
    let taken = |p: &Path| p.exists() || part_path(p).exists();
    let first = dir.join(name);
    if !taken(&first) {
        return first;
    }
    (2u64..)
        .map(|n| dir.join(format!("{stem} ({n}){ext}")))
        .find(|p| !taken(p))
        .expect("an unused name always exists")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn sanitize_strips_directories_and_bad_chars() {
        assert_eq!(sanitize_file_name("..\\..\\Windows\\evil.exe"), "evil.exe");
        assert_eq!(sanitize_file_name("a/b/c.pdf"), "c.pdf");
        assert_eq!(sanitize_file_name("re<po>rt:?*\"|.pdf"), "report.pdf");
        assert_eq!(sanitize_file_name("tab\there\u{0}.txt"), "tabhere.txt");
    }

    #[test]
    fn sanitize_handles_reserved_and_empty() {
        assert_eq!(sanitize_file_name("CON"), "_CON");
        assert_eq!(sanitize_file_name("nul.txt"), "_nul.txt");
        assert_eq!(sanitize_file_name("console.txt"), "console.txt");
        assert_eq!(sanitize_file_name(""), "file");
        assert_eq!(sanitize_file_name("..."), "file");
        assert_eq!(sanitize_file_name("dir/"), "file");
        assert_eq!(sanitize_file_name("name. . "), "name");
    }

    #[test]
    fn sanitize_keeps_unicode_and_limits_length() {
        assert_eq!(sanitize_file_name("تقرير مالي.pdf"), "تقرير مالي.pdf");
        let long = "x".repeat(500);
        assert_eq!(sanitize_file_name(&long).chars().count(), MAX_NAME);
        let emoji = format!("{}.pdf", "😀".repeat(150));
        let short = sanitize_file_name(&emoji);
        assert!(short.encode_utf16().count() <= MAX_NAME);
        assert!(short.ends_with("😀.pdf"));
    }

    #[test]
    fn device_name_rules() {
        assert_eq!(clean_device_name("  Office PC "), Some("Office PC".to_string()));
        assert_eq!(clean_device_name("   "), None);
        assert_eq!(clean_device_name(&"a".repeat(41)), None);
        assert!(clean_device_name(&"ب".repeat(40)).is_some());
    }

    #[test]
    fn unique_path_counts_up_and_respects_part_files() {
        let dir = std::env::temp_dir().join(format!("freepdf-names-{}", random_hex(10)));
        std::fs::create_dir_all(&dir).unwrap();
        assert_eq!(unique_path(&dir, "a.pdf"), dir.join("a.pdf"));
        std::fs::write(dir.join("a.pdf"), b"1").unwrap();
        assert_eq!(unique_path(&dir, "a.pdf"), dir.join("a (2).pdf"));
        std::fs::write(dir.join("a (2).pdf.part"), b"1").unwrap();
        assert_eq!(unique_path(&dir, "a.pdf"), dir.join("a (3).pdf"));
        std::fs::write(dir.join(".env"), b"1").unwrap();
        assert_eq!(unique_path(&dir, ".env"), dir.join(".env (2)"));
        std::fs::remove_dir_all(&dir).unwrap();
    }

    #[test]
    fn random_ids_differ() {
        let a = random_hex(16);
        assert_eq!(a.len(), 16);
        assert_ne!(a, random_hex(16));
    }
}
