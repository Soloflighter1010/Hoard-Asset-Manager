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
use tauri_plugin_window_state::{AppHandleExt, StateFlags};

/// What starts each of Hoard's lines to the shell (anything else it prints is not for the shell).
const MARK: &str = "\u{1e}hoard:";
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
        _ => {}
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
    });
    let app = tauri::Builder::default()
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
