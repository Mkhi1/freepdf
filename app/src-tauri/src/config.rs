use std::path::{Path, PathBuf};

/// How to start one engine process: the packaged runtime next to the exe,
/// or the development folders when that runtime is not there.
#[derive(Clone)]
pub struct Launch {
    pub python: PathBuf,
    pub cwd: PathBuf,
    pub resources: Option<PathBuf>,
}

pub fn is_smoke() -> bool {
    std::env::var("FREEPDF_SMOKE").map(|v| v == "1").unwrap_or(false)
}

/// The PDF Windows asked us to open, from the right-click menu or "Open with".
pub fn startup_pdf() -> Option<String> {
    std::env::args_os()
        .skip(1)
        .map(PathBuf::from)
        .find(|path| is_pdf(path))
        .map(|path| path.to_string_lossy().into_owned())
}

fn is_pdf(path: &Path) -> bool {
    path.is_file() && path.extension().is_some_and(|ext| ext.eq_ignore_ascii_case("pdf"))
}

pub fn launch() -> Launch {
    match runtime_dir() {
        Some(dir) if std::env::var_os("FREEPDF_PY").is_none() => Launch {
            python: runtime_python(&dir),
            cwd: dir.join("engine"),
            resources: Some(dir.join("res")),
        },
        _ => Launch { python: python_path(), cwd: engine_dir(), resources: None },
    }
}

fn runtime_python(dir: &Path) -> PathBuf {
    dir.join("python").join("Scripts").join("python.exe")
}

fn runtime_dir() -> Option<PathBuf> {
    let dir = exe_dir()?.join("runtime");
    runtime_python(&dir).is_file().then_some(dir)
}

fn exe_dir() -> Option<PathBuf> {
    Some(std::env::current_exe().ok()?.parent()?.to_path_buf())
}

/// The engine package the installer copies next to the exe.
fn installed_engine() -> Option<PathBuf> {
    let dir = exe_dir()?.join("engine");
    dir.join("freepdf_engine").is_dir().then_some(dir)
}

fn dev_root() -> PathBuf {
    std::env::var_os("LOCALAPPDATA")
        .map(|p| PathBuf::from(p).join("FreePDF-dev"))
        .unwrap_or_else(|| PathBuf::from("FreePDF-dev"))
}

fn python_path() -> PathBuf {
    if let Some(p) = std::env::var_os("FREEPDF_PY") {
        return PathBuf::from(p);
    }
    dev_root().join("venv").join("Scripts").join("python.exe")
}

fn engine_dir() -> PathBuf {
    if let Some(p) = std::env::var_os("FREEPDF_ENGINE") {
        return PathBuf::from(p);
    }
    if let Some(dir) = installed_engine() {
        return dir;
    }
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("..").join("..").join("engine")
}
