//! Hoard's window: a Tauri shell around Hoard's own server (hoard-server, compiled by Nuitka, in the app's
//! resources). The shell starts it with --shell and the two talk over its standard input and output, one JSON
//! message to a line (hoard/shell.py says what each means). Hoard decides everything as it does in its own
//! pywebview window: the shell only shows its page, and passes on the close button and the system's pickers.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::io::{BufRead, BufReader, Write};
use std::process::{ChildStdin, Command, Stdio};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};

use serde_json::{json, Value};
use tauri::{AppHandle, Manager, RunEvent, Url, WebviewUrl, WebviewWindowBuilder, WindowEvent};
use tauri_plugin_dialog::{DialogExt, MessageDialogKind};
use tauri_plugin_opener::OpenerExt;
use tauri_plugin_updater::{Update, UpdaterExt};
use tauri_plugin_window_state::{AppHandleExt, StateFlags};

/// What starts each of Hoard's lines to the shell (anything else it prints is not for the shell).
const MARK: &str = "\u{1e}hoard:";
/// The public key Hoard's updates are signed with (shell/updater.pub, made once with `tauri signer generate`; its
/// private half is a secret of the release workflow's, never in the repository). Empty: this build can't update
/// itself, and Hoard says where to download the next one instead.
const UPDATE_KEY: &str = include_str!("../updater.pub");
/// Where an update and its manifest may come from: Hoard's own releases.
const RELEASES: &str = "https://github.com/Soloflighter1010/Hoard-Asset-Manager/releases/download/";
/// A link the page opens in a new window (or a target=_blank link), sent here by LINKS to open in your browser.
const OPEN_HOST: &str = "hoard-open.invalid";
/// The page's links that would open a new window open in your browser instead, as in Hoard's pywebview window.
const LINKS: &str = r#"(() => {
  const out = u => { try { location.assign("https://hoard-open.invalid/?u=" + encodeURIComponent(new URL(u, location.href).href)); } catch (e) {} };
  window.open = u => { if (u) out(u); return null; };
  document.addEventListener("click", e => {
    const a = e.target && e.target.closest && e.target.closest("a[href]");
    if (a && a.target && a.target !== "_self" && !e.defaultPrevented) { e.preventDefault(); out(a.href); }
  }, true);
})();"#;

/// Hoard's server, as the shell knows it.
struct Server {
    stdin: Mutex<Option<ChildStdin>>,
    origin: Mutex<Option<String>>, // its page's address (http://127.0.0.1:port): the window stays on it
    opened: AtomicBool,            // its page has been shown
    leaving: AtomicBool,           // Hoard is quitting (or has stopped): the window may close, the app end
    update: Mutex<Option<(Update, Vec<u8>)>>, // an update downloaded and checked against its signature
    updating: AtomicBool,          // one is being downloaded
    install: AtomicBool,           // Hoard is quitting for it: install it once Hoard has stopped, then open again
}

/// Can this copy update itself? Not without the updates' key, and never in the Flatpak, which Flatpak updates (its
/// files are the .deb's, so Tauri's updater would take it for one).
fn updates_here() -> bool {
    !UPDATE_KEY.trim().is_empty()
        && std::env::var_os("FLATPAK_ID").is_none()
        && !std::path::Path::new("/.flatpak-info").exists()
}

/// Download the update Hoard chose (that version, from that release's manifest) and check it against its signature,
/// while Hoard carries on. Hoard is told how far it's got; once it's here, Hoard quits, and it's installed.
async fn get_update(app: &AppHandle, server: &Server, manifest: &str, version: &str) -> Result<(), String> {
    if !updates_here() {
        return Err("this copy of Hoard doesn't update itself".into());
    }
    if !manifest.starts_with(RELEASES) {
        return Err("that isn't one of Hoard's releases".into());
    }
    let endpoint = Url::parse(manifest).map_err(|e| e.to_string())?;
    let wanted = version.to_string();
    // Hoard has decided this is the one (its channel, a beta or not): Tauri's own numbers can't tell betas apart
    let updater = app
        .updater_builder()
        .endpoints(vec![endpoint])
        .map_err(|e| e.to_string())?
        .version_comparator(move |_, remote| remote.version.to_string() == wanted)
        .build()
        .map_err(|e| e.to_string())?;
    let update = updater
        .check()
        .await
        .map_err(|e| e.to_string())?
        .ok_or_else(|| format!("the release has no Hoard {version} for this computer"))?;
    if !update.download_url.as_str().starts_with(RELEASES) {
        return Err("the update isn't one of Hoard's releases".into());
    }
    let (mut got, mut said) = (0u64, 0u64);
    let bytes = update
        .download(
            |chunk, total| {
                got += chunk as u64;
                if got - said >= 1 << 20 || Some(got) == total {   // (a megabyte at a time)
                    said = got;
                    server.tell(json!({"event": "update", "state": "downloading", "got": got, "total": total}));
                }
            },
            || {},
        )
        .await   // (checked against its signature as it ends: one that doesn't match is refused)
        .map_err(|e| e.to_string())?;
    *server.update.lock().unwrap() = Some((update, bytes));
    Ok(())
}

impl Server {
    /// One event to Hoard.
    fn tell(&self, event: Value) {
        if let Some(stdin) = self.stdin.lock().unwrap().as_mut() {
            let _ = writeln!(stdin, "{event}").and_then(|_| stdin.flush());
        }
    }
}

/// Where the window may go: the shell's own page, and Hoard's (anything else opens in your browser).
fn stays(server: &Server, url: &Url) -> bool {
    match url.scheme() {
        "tauri" | "about" | "data" | "blob" => return true,
        _ => {}
    }
    if url.host_str() == Some("tauri.localhost") {
        return true;
    }
    let origin = server.origin.lock().unwrap();
    origin.as_deref() == Some(url.origin().ascii_serialization().as_str())
}

/// Open a link in your browser: an http(s) one only.
fn open_outside(app: &AppHandle, url: &Url) {
    let target = if url.host_str() == Some(OPEN_HOST) {
        url.query_pairs().find(|(k, _)| k == "u").and_then(|(_, v)| Url::parse(&v).ok())
    } else {
        Some(url.clone())
    };
    if let Some(target) = target.filter(|u| u.scheme() == "https" || u.scheme() == "http") {
        let _ = app.opener().open_url(target.as_str(), None::<&str>);
    }
}

/// One message from Hoard (hoard/shell.py lists them).
fn handle(app: &AppHandle, server: &Arc<Server>, message: Value) {
    let Some(window) = app.get_webview_window("main") else { return };
    match message["do"].as_str() {
        Some("open") => {
            if let Some(url) = message["url"].as_str().and_then(|u| Url::parse(u).ok()) {
                *server.origin.lock().unwrap() = Some(url.origin().ascii_serialization());
                let _ = window.navigate(url);
                let _ = window.show();
                let _ = window.set_focus();
                server.opened.store(true, Ordering::SeqCst);
            }
        }
        Some("show") => {
            let _ = window.unminimize();
            let _ = window.show();
            let _ = window.set_focus();
        }
        Some("minimize") => {
            let _ = window.minimize();
        }
        Some("hide") => {
            server.leaving.store(true, Ordering::SeqCst);
            let _ = app.save_window_state(StateFlags::all() & !StateFlags::VISIBLE);
            let _ = window.hide();
        }
        Some("js") => {
            if let Some(code) = message["code"].as_str() {
                let _ = window.eval(code);
            }
        }
        Some("pick") => {
            let (app, server) = (app.clone(), server.clone());
            let id = message["id"].clone();
            let folder = message["kind"].as_str() != Some("file");
            let start = message["start"].as_str().unwrap_or("").to_string();
            std::thread::spawn(move || {   // (the picker waits for you: Hoard's other messages carry on)
                let mut dialog = app.dialog().file();
                if let Some(window) = app.get_webview_window("main") {
                    dialog = dialog.set_parent(&window);
                }
                if !start.is_empty() {
                    dialog = dialog.set_directory(&start);
                }
                let picked = if folder { dialog.blocking_pick_folder() } else { dialog.blocking_pick_file() };
                let path = picked.and_then(|p| p.into_path().ok()).map(|p| p.to_string_lossy().into_owned());
                server.tell(json!({"event": "picked", "id": id, "path": path}));
            });
        }
        Some("update") => {   // get the update Hoard chose, and say when it's here (or why not)
            if server.updating.swap(true, Ordering::SeqCst) {
                return;   // (Hoard asks for one at a time)
            }
            let (app, server) = (app.clone(), server.clone());
            let manifest = message["url"].as_str().unwrap_or("").to_string();
            let version = message["version"].as_str().unwrap_or("").to_string();
            tauri::async_runtime::spawn(async move {
                let event = match get_update(&app, &server, &manifest, &version).await {
                    Ok(()) => json!({"event": "update", "state": "ready"}),
                    Err(why) => json!({"event": "update", "state": "failed", "why": why}),
                };
                server.updating.store(false, Ordering::SeqCst);
                server.tell(event);
            });
        }
        Some("install") => {   // Hoard is quitting for the update: install it once Hoard has stopped
            server.install.store(true, Ordering::SeqCst);
        }
        _ => {}
    }
}

/// Install the update Hoard quit for, then open the new Hoard. On Windows its setup takes over (and opens Hoard
/// when it's done), so this ends here; elsewhere the app is replaced where it is, and started again.
fn install_update(app: &AppHandle, server: &Server) -> bool {
    if !server.install.load(Ordering::SeqCst) {
        return false;
    }
    let Some((update, bytes)) = server.update.lock().unwrap().take() else { return false };
    match update.install(&bytes) {
        Ok(()) => app.restart(),
        Err(why) => {
            app.dialog()
                .message(format!("Hoard's update couldn't be installed ({why}). Open Hoard again to carry on with \
                                  this version, or download the new one from its release."))
                .title("Hoard")
                .kind(MessageDialogKind::Error)
                .blocking_show();
            false
        }
    }
}

/// Start Hoard's server and listen to it. When it stops, so does the shell (after saying why, if it never opened).
fn start_server(app: &AppHandle, server: &Arc<Server>) -> Result<(), String> {
    let folder = app.path().resource_dir().map_err(|e| e.to_string())?.join("server");
    let program = folder.join(if cfg!(windows) { "hoard-server.exe" } else { "hoard-server" });
    let mut command = Command::new(&program);
    command.arg("--shell").current_dir(&folder).stdin(Stdio::piped()).stdout(Stdio::piped()).stderr(Stdio::null());
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        command.creation_flags(0x0800_0000); // CREATE_NO_WINDOW
    }
    let mut child = command.spawn().map_err(|e| format!("{}: {e}", program.display()))?;
    *server.stdin.lock().unwrap() = child.stdin.take();
    server.tell(json!({"event": "hello", "updates": updates_here()}));   // (what this shell can do for Hoard)
    let stdout = child.stdout.take().ok_or("no output from Hoard's server")?;
    {
        let (app, server) = (app.clone(), server.clone());
        std::thread::spawn(move || {
            for line in BufReader::new(stdout).lines() {
                let Ok(line) = line else { break };
                if let Some(message) = line.strip_prefix(MARK).and_then(|m| serde_json::from_str::<Value>(m).ok()) {
                    handle(&app, &server, message);
                }
            }
        });
    }
    let (app, server) = (app.clone(), server.clone());
    std::thread::spawn(move || {
        let status = child.wait();
        server.leaving.store(true, Ordering::SeqCst);
        if install_update(&app, &server) {
            return;
        }
        let failed = !matches!(&status, Ok(s) if s.success());
        if failed && !server.opened.load(Ordering::SeqCst) {   // (one that ended well never opened: a second start)
            app.dialog()
                .message("Hoard couldn't start. Its log, in Hoard's app-data folder (logs), says why.")
                .title("Hoard")
                .kind(MessageDialogKind::Error)
                .blocking_show();
        }
        app.exit(0);
    });
    Ok(())
}

fn main() {
    let server = Arc::new(Server {
        stdin: Mutex::new(None),
        origin: Mutex::new(None),
        opened: AtomicBool::new(false),
        leaving: AtomicBool::new(false),
        update: Mutex::new(None),
        updating: AtomicBool::new(false),
        install: AtomicBool::new(false),
    });
    let mut builder = tauri::Builder::default();
    if updates_here() {   // (only where this copy can update itself: with the updates' key, and not the Flatpak)
        builder = builder.plugin(tauri_plugin_updater::Builder::new().pubkey(UPDATE_KEY.trim()).build());
    }
    let app = builder
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_opener::init())
        .plugin(
            tauri_plugin_window_state::Builder::default()
                .with_state_flags(StateFlags::all() & !StateFlags::VISIBLE) // (it shows once Hoard's page is ready)
                .build(),
        )
        .manage(server.clone())
        .setup(move |app| {
            let handle = app.handle().clone();
            let (watch, open) = (server.clone(), app.handle().clone());
            WebviewWindowBuilder::new(app, "main", WebviewUrl::App("index.html".into()))
                .title("Hoard")
                .inner_size(1440.0, 920.0)
                .min_inner_size(900.0, 600.0)
                .visible(false)
                .background_color(tauri::window::Color(0x22, 0x1c, 0x17, 0xff))
                .initialization_script(LINKS)
                .on_navigation(move |url| {
                    if stays(&watch, url) {
                        return true;
                    }
                    open_outside(&open, url);
                    false
                })
                .on_download(|_, _| false) // (Hoard saves what it makes itself, as in its own window)
                // Hoard's page does its own drag and drop: a product onto another, a project into a folder,
                // saved pages dropped in from outside. Tauri's handler would take every drag for itself, and on
                // Windows the page then saw none of them (issue #313).
                .disable_drag_drop_handler()
                .build()?;
            if let Err(why) = start_server(&handle, &server) {
                handle
                    .dialog()
                    .message(format!("Hoard couldn't start its server ({why})."))
                    .title("Hoard")
                    .kind(MessageDialogKind::Error)
                    .blocking_show();
                handle.exit(1);
            }
            Ok(())
        })
        .on_window_event(|window, event| {
            if let WindowEvent::CloseRequested { api, .. } = event {
                let server = window.state::<Arc<Server>>();
                if !server.leaving.load(Ordering::SeqCst) {
                    api.prevent_close(); // (Hoard decides: the taskbar, asking about a task, or quitting)
                    server.tell(json!({"event": "closing", "quitting": false}));
                }
            }
        })
        .build(tauri::generate_context!())
        .expect("Hoard's window couldn't start");
    app.run(|app, event| {
        if let RunEvent::ExitRequested { api, code, .. } = event {
            let server = app.state::<Arc<Server>>();
            if code.is_none() && !server.leaving.load(Ordering::SeqCst) {
                api.prevent_exit(); // Command-Q on a Mac: Hoard decides, as Quit Hoard does
                server.tell(json!({"event": "closing", "quitting": true}));
            }
        }
    });
}
