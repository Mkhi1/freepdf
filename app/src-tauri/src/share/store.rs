use std::path::{Path, PathBuf};

use serde::{Deserialize, Serialize};

use super::names::{clean_device_name, default_device_name, random_hex};

/// What this device remembers between runs, kept in share.json.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Saved {
    pub id: String,
    pub name: String,
    #[serde(default)]
    pub trusted: Vec<String>,
}

impl Saved {
    fn fresh() -> Self {
        Self { id: random_hex(16), name: default_device_name(), trusted: Vec::new() }
    }

    fn is_valid(&self) -> bool {
        self.id.len() == 16 && self.id.chars().all(|c| c.is_ascii_hexdigit())
    }
}

pub struct Store {
    path: Option<PathBuf>,
}

impl Store {
    /// `None` keeps everything in memory, which tests use.
    pub fn new(path: Option<PathBuf>) -> Self {
        Self { path }
    }

    pub fn load(&self) -> Saved {
        let loaded = self.path.as_deref().and_then(read);
        match loaded {
            Some(mut saved) if saved.is_valid() => {
                saved.name = clean_device_name(&saved.name).unwrap_or_else(default_device_name);
                saved
            }
            _ => {
                let saved = Saved::fresh();
                let _ = self.save(&saved);
                saved
            }
        }
    }

    pub fn save(&self, saved: &Saved) -> std::io::Result<()> {
        let Some(path) = &self.path else { return Ok(()) };
        if let Some(dir) = path.parent() {
            std::fs::create_dir_all(dir)?;
        }
        let tmp = path.with_extension("json.tmp");
        std::fs::write(&tmp, serde_json::to_vec_pretty(saved)?)?;
        std::fs::rename(&tmp, path)
    }
}

fn read(path: &Path) -> Option<Saved> {
    let bytes = std::fs::read(path).ok()?;
    serde_json::from_slice(&bytes).ok()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn creates_then_reloads_the_same_identity() {
        let dir = std::env::temp_dir().join(format!("freepdf-store-{}", random_hex(10)));
        let store = Store::new(Some(dir.join("share.json")));
        let mut first = store.load();
        assert_eq!(first.id.len(), 16);
        first.trusted.push("abcdef0123456789".into());
        first.name = "Desk".into();
        store.save(&first).unwrap();
        let again = store.load();
        assert_eq!(again.id, first.id);
        assert_eq!(again.name, "Desk");
        assert_eq!(again.trusted, first.trusted);
        std::fs::remove_dir_all(&dir).unwrap();
    }
}
