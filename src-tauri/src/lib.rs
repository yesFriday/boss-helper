use tauri::{
    menu::{Menu, MenuItem},
    tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
    Manager, WindowEvent,
};
use tauri_plugin_shell::ShellExt;
use std::time::Duration;

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_opener::init())
        .setup(|app| {
            let handle = app.handle().clone();

            // 1. 启动 Python Sidecar 后台服务
            tauri::async_runtime::spawn(async move {
                println!("[Tauri] 正在启动 Python Sidecar 进程...");
                match handle.shell().sidecar("boss_backend") {
                    Ok(sidecar) => {
                        let (mut _rx, _child) = sidecar
                            .args(["--port", "8010"])
                            .spawn()
                            .expect("无法启动 Python Sidecar 子进程");
                        
                        println!("[Tauri] Sidecar 进程已成功拉起");
                        
                        // 轮询检查 Python 后端 health endpoint
                        let client = reqwest::Client::new();
                        for i in 1..=30 {
                            tokio::time::sleep(Duration::from_millis(500)).await;
                            if let Ok(res) = client.get("http://127.0.0.1:8010/api/health").send().await {
                                if res.status().is_success() {
                                    println!("[Tauri] Python 后端服务在尝试第 {} 次时已准备就绪！", i);
                                    break;
                                }
                            }
                        }
                    }
                    Err(e) => {
                        eprintln!("[Tauri Error] Sidecar 配置或可执行文件未找到: {:?}", e);
                    }
                }
            });

            // 2. 创建系统托盘菜单
            let show_item = MenuItem::with_id(app, "show", "显示主界面", true, None::<&str>)?;
            let quit_item = MenuItem::with_id(app, "quit", "彻底退出", true, None::<&str>)?;
            let tray_menu = Menu::with_items(app, &[&show_item, &quit_item])?;

            let _tray = TrayIconBuilder::new()
                .menu(&tray_menu)
                .tooltip("BOSS直聘智能求职助手")
                .on_menu_event(|app, event| match event.id.as_ref() {
                    "show" => {
                        if let Some(window) = app.get_webview_window("main") {
                            let _ = window.show();
                            let _ = window.unminimize();
                            let _ = window.set_focus();
                        }
                    }
                    "quit" => {
                        // 请求 Python 后端优雅关机
                        let _ = std::thread::spawn(|| {
                            let _ = reqwest::blocking::Client::new()
                                .post("http://127.0.0.1:8010/api/system/shutdown")
                                .timeout(Duration::from_secs(2))
                                .send();
                        });
                        std::thread::sleep(Duration::from_millis(300));
                        app.exit(0);
                    }
                    _ => {}
                })
                .on_tray_icon_event(|tray, event| {
                    if let TrayIconEvent::Click {
                        button: MouseButton::Left,
                        button_state: MouseButtonState::Up,
                        ..
                    } = event
                    {
                        let app = tray.app_handle();
                        if let Some(window) = app.get_webview_window("main") {
                            if window.is_visible().unwrap_or(false) {
                                let _ = window.hide();
                            } else {
                                let _ = window.show();
                                let _ = window.set_focus();
                            }
                        }
                    }
                })
                .build(app)?;

            Ok(())
        })
        .on_window_event(|window, event| {
            // 拦截关闭窗口事件，改为隐藏至托盘
            if let WindowEvent::CloseRequested { api, .. } = event {
                api.prevent_close();
                let _ = window.hide();
            }
        })
        .run(tauri::generate_context!())
        .expect("Tauri 应用运行发生异常");
}
