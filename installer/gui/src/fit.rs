//! The window fits a small screen (1920 x 1080 at 200 %: 960 x 540 logical). Its fixed size (min = max, ui/app.slint)
//! is cut to its monitor's size at the window's scale, less the margins, and to any smaller size a compositor gives it
//! (KDE's bounds, sway's clamp to the screen). Slint then resizes the window, and Hyprland, which ignores the window's
//! own resize, shrinks a floating window to its maximum. The fixed size only shrinks: a compositor answering an older
//! request with 1066 x 600 does not grow it back.
//!
//! KDE's cut is read before Slint sees the events that bring it: at any scale but 1, Slint 1.18.1 then asks again for
//! the size the window had before it opened, and the fixed size has to be there to hold it. X11 and Windows have no cut.

use slint::ComponentHandle;
use slint::winit_030::{CustomApplicationHandler, EventResult, WinitWindowAccessor, winit};
use winit::event::WindowEvent;
use winit::event_loop::ActiveEventLoop;

/// What the panels, the title bar and the window's frame take from the monitor (logical px): no API gives it before
/// the window is placed. Across, also Slint's rounding to whole pixels at a fractional scale.
const MARGIN_W: f64 = 16.0;
const MARGIN_H: f64 = 96.0;

pub struct Fit;

fn refit(w: &winit::window::Window, resend: bool) {
    // Wayland: no current monitor before the window is mapped
    let (Some(ui), Some(m)) = (
        crate::UI.with_borrow(|u| u.as_ref().and_then(|u| u.upgrade())),
        w.current_monitor().or_else(|| w.available_monitors().next()),
    ) else {
        return;
    };
    let sf = w.scale_factor();
    let now = w.inner_size().to_logical::<f64>(sf);
    // Wayland gives the panel's own mode, not rotated: a handheld's portrait panel shown landscape (Steam Deck:
    // 800 x 1280)
    let px = m.size();
    let screen_w = px.width.max(px.height) as f64 / sf - MARGIN_W;
    let screen_h = px.width.min(px.height) as f64 / sf - MARGIN_H;
    let (fixed_w, fixed_h) = (ui.get_fixed_width() as f64, ui.get_fixed_height() as f64);
    // 1 px for the physical rounding
    let side = |now: f64, fixed: f64, screen: f64| (if now + 1.0 < fixed { now } else { fixed }).min(screen);
    let new_w = side(now.width, fixed_w, screen_w);
    let new_h = side(now.height, fixed_h, screen_h);
    if new_w < fixed_w || new_h < fixed_h {
        ui.set_fixed_width(new_w as f32);
        ui.set_fixed_height(new_h as f32);
    }
    // a window manager answering an older request (KDE on Wayland, Windows) gets the fixed size again, once Slint
    // has seen the event in hand
    if resend && (now.width > new_w + 1.0 || now.height > new_h + 1.0) {
        let ui = ui.as_weak();
        slint::Timer::single_shot(std::time::Duration::ZERO, move || {
            if let Some(ui) = ui.upgrade() {
                ui.window().set_size(slint::LogicalSize::new(new_w as f32, new_h as f32));
            }
        });
    }
}

impl CustomApplicationHandler for Fit {
    // KDE's cut, before Slint's timers undo it. Not while winit has a scale Slint has not seen yet (Hyprland gives
    // it after the first frame): Slint would turn the fixed size to pixels at its old scale
    fn new_events(&mut self, _: &ActiveEventLoop, _: winit::event::StartCause) -> EventResult {
        if let Some(ui) = crate::UI.with_borrow(|u| u.as_ref().and_then(|u| u.upgrade())) {
            let sf = ui.window().scale_factor() as f64;
            ui.window().with_winit_window(|w| {
                if (w.scale_factor() - sf).abs() < 0.001 {
                    refit(w, false)
                }
            });
        }
        EventResult::Propagate
    }

    fn window_event(
        &mut self,
        _: &ActiveEventLoop,
        _: winit::window::WindowId,
        winit_window: Option<&winit::window::Window>,
        _: Option<&slint::Window>,
        event: &WindowEvent,
    ) -> EventResult {
        if let (WindowEvent::Resized(_) | WindowEvent::ScaleFactorChanged { .. }, Some(w)) = (event, winit_window) {
            refit(w, matches!(event, WindowEvent::Resized(_)));
        }
        EventResult::Propagate
    }
}
