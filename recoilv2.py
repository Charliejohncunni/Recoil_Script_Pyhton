import time
import random
import threading
import ctypes

import keyboard
import win32api
import win32con
import win32gui
import dearpygui.dearpygui as dpg
import keyauth


# -------------------------
# Shared settings
# -------------------------

settings = {
    "enabled": False,
    "window_title": "",
    "strength": 3.0,
    "horizontal": 0.0,
    "delay": 0.012,
    "random_jitter": 0.3,
    "require_right_click": False,

    # Overlay settings
    "overlay_x": 30,
    "overlay_y": 30,
    "overlay_width": 180,
    "overlay_height": 50,
}

lock = threading.Lock()
running = True
overlay_hwnd = None


# -------------------------
# Helper functions
# -------------------------

def is_key_down(vk_code: int) -> bool:
    return win32api.GetAsyncKeyState(vk_code) < 0


def get_active_window_title() -> str:
    hwnd = win32gui.GetForegroundWindow()
    return win32gui.GetWindowText(hwnd)


def allowed_window_active() -> bool:
    with lock:
        required_title = settings["window_title"].strip().lower()

    if not required_title:
        return True

    active_title = get_active_window_title().lower()
    return required_title in active_title


def move_mouse(dx: int, dy: int):
    win32api.mouse_event(win32con.MOUSEEVENTF_MOVE, dx, dy, 0, 0)


# -------------------------
# Overlay code
# -------------------------

def overlay_wnd_proc(hwnd, msg, wparam, lparam):
    if msg == win32con.WM_PAINT:
        hdc, paint_struct = win32gui.BeginPaint(hwnd)

        try:
            rect = win32gui.GetClientRect(hwnd)

            with lock:
                enabled = settings["enabled"]

            text = "ENABLED" if enabled else "DISABLED"
            text_color = win32api.RGB(0, 255, 80) if enabled else win32api.RGB(255, 70, 70)

            # Background box
            bg_brush = win32gui.CreateSolidBrush(win32api.RGB(20, 20, 20))
            win32gui.FillRect(hdc, rect, bg_brush)
            win32gui.DeleteObject(bg_brush)

            # Font fix: use ctypes instead of win32gui.CreateFont
            font = ctypes.windll.gdi32.CreateFontW(
                -26,  # font height
                0,
                0,
                0,
                win32con.FW_BOLD,
                0,
                0,
                0,
                win32con.DEFAULT_CHARSET,
                win32con.OUT_DEFAULT_PRECIS,
                win32con.CLIP_DEFAULT_PRECIS,
                win32con.DEFAULT_QUALITY,
                win32con.DEFAULT_PITCH | win32con.FF_DONTCARE,
                "Segoe UI"
            )

            old_font = win32gui.SelectObject(hdc, font)

            win32gui.SetBkMode(hdc, win32con.TRANSPARENT)
            win32gui.SetTextColor(hdc, text_color)

            win32gui.DrawText(
                hdc,
                text,
                -1,
                rect,
                win32con.DT_CENTER | win32con.DT_VCENTER | win32con.DT_SINGLELINE
            )

            win32gui.SelectObject(hdc, old_font)
            win32gui.DeleteObject(font)

        finally:
            win32gui.EndPaint(hwnd, paint_struct)

        return 0

    if msg == win32con.WM_DESTROY:
        return 0

    return win32gui.DefWindowProc(hwnd, msg, wparam, lparam)


def create_overlay_window():
    global overlay_hwnd

    hinst = win32api.GetModuleHandle(None)
    class_name = "OfflineAntiRecoilStatusOverlay"

    wnd_class = win32gui.WNDCLASS()
    wnd_class.hInstance = hinst
    wnd_class.lpszClassName = class_name
    wnd_class.lpfnWndProc = overlay_wnd_proc
    wnd_class.hbrBackground = win32gui.GetStockObject(win32con.BLACK_BRUSH)

    try:
        win32gui.RegisterClass(wnd_class)
    except win32gui.error:
        pass

    with lock:
        x = settings["overlay_x"]
        y = settings["overlay_y"]
        width = settings["overlay_width"]
        height = settings["overlay_height"]

    ex_style = (
        win32con.WS_EX_TOPMOST |
        win32con.WS_EX_LAYERED |
        win32con.WS_EX_TRANSPARENT |
        win32con.WS_EX_TOOLWINDOW
    )

    style = win32con.WS_POPUP

    hwnd = win32gui.CreateWindowEx(
        ex_style,
        class_name,
        None,
        style,
        x,
        y,
        width,
        height,
        None,
        None,
        hinst,
        None
    )

    overlay_hwnd = hwnd

    # 210 = slightly transparent
    win32gui.SetLayeredWindowAttributes(
        hwnd,
        0,
        210,
        win32con.LWA_ALPHA
    )

    win32gui.ShowWindow(hwnd, win32con.SW_SHOW)
    win32gui.UpdateWindow(hwnd)

    return hwnd


def move_overlay_window():
    if overlay_hwnd is None:
        return

    with lock:
        x = int(settings["overlay_x"])
        y = int(settings["overlay_y"])
        width = int(settings["overlay_width"])
        height = int(settings["overlay_height"])

    win32gui.SetWindowPos(
        overlay_hwnd,
        win32con.HWND_TOPMOST,
        x,
        y,
        width,
        height,
        win32con.SWP_NOACTIVATE
    )


def overlay_loop():
    hwnd = create_overlay_window()

    while running:
        win32gui.PumpWaitingMessages()
        win32gui.InvalidateRect(hwnd, None, True)
        time.sleep(0.1)

    try:
        win32gui.DestroyWindow(hwnd)
    except win32gui.error:
        pass


# -------------------------
# Anti-recoil loop
# -------------------------

def recoil_loop():
    while running:
        with lock:
            enabled = settings["enabled"]
            strength = settings["strength"]
            horizontal = settings["horizontal"]
            delay = settings["delay"]
            jitter = settings["random_jitter"]
            require_right_click = settings["require_right_click"]

        if not enabled:
            time.sleep(0.05)
            continue

        if not allowed_window_active():
            time.sleep(0.05)
            continue

        left_clicking = is_key_down(win32con.VK_LBUTTON)
        right_clicking = is_key_down(win32con.VK_RBUTTON)

        if left_clicking and (not require_right_click or right_clicking):
            random_x = random.uniform(-jitter, jitter)
            random_y = random.uniform(-jitter, jitter)

            dx = int(horizontal + random_x)
            dy = int(strength + random_y)

            move_mouse(dx, dy)
            time.sleep(delay)
        else:
            time.sleep(0.01)


# -------------------------
# GUI callbacks
# -------------------------

def update_status():
    with lock:
        enabled = settings["enabled"]

    status = "ON" if enabled else "OFF"

    if dpg.does_item_exist("status_text"):
        dpg.set_value("status_text", f"Status: {status}")


def set_enabled(sender, app_data):
    with lock:
        settings["enabled"] = bool(app_data)

    update_status()


def set_window_title(sender, app_data):
    with lock:
        settings["window_title"] = app_data


def set_strength(sender, app_data):
    with lock:
        settings["strength"] = float(app_data)


def set_horizontal(sender, app_data):
    with lock:
        settings["horizontal"] = float(app_data)


def set_delay(sender, app_data):
    with lock:
        settings["delay"] = float(app_data)


def set_jitter(sender, app_data):
    with lock:
        settings["random_jitter"] = float(app_data)


def set_require_right_click(sender, app_data):
    with lock:
        settings["require_right_click"] = bool(app_data)


def set_overlay_x(sender, app_data):
    with lock:
        settings["overlay_x"] = int(app_data)

    move_overlay_window()


def set_overlay_y(sender, app_data):
    with lock:
        settings["overlay_y"] = int(app_data)

    move_overlay_window()


def toggle_enabled():
    with lock:
        settings["enabled"] = not settings["enabled"]
        enabled = settings["enabled"]

    if dpg.does_item_exist("enabled_checkbox"):
        dpg.set_value("enabled_checkbox", enabled)

    update_status()


def update_active_window_text():
    while running:
        title = get_active_window_title()

        if dpg.does_item_exist("active_window_text"):
            dpg.set_value("active_window_text", f"Active window: {title}")

        time.sleep(0.5)


# -------------------------
# Dear PyGui setup
# -------------------------

def build_gui():
    dpg.create_context()

    with dpg.window(label="Offline Anti-Recoil Tool", width=560, height=520):
        dpg.add_text("Offline-only recoil compensation")
        dpg.add_text("Toggle with F8")
        dpg.add_separator()

        dpg.add_text("Status: OFF", tag="status_text")

        dpg.add_checkbox(
            label="Enabled",
            tag="enabled_checkbox",
            default_value=False,
            callback=set_enabled
        )

        dpg.add_input_text(
            label="Allowed window title",
            hint="Example: My Offline Game",
            callback=set_window_title
        )

        dpg.add_text("Leave this empty if you do not want window checking.")
        dpg.add_text("Active window: ", tag="active_window_text")

        dpg.add_separator()

        dpg.add_slider_float(
            label="Vertical strength",
            default_value=3.0,
            min_value=0.0,
            max_value=20.0,
            callback=set_strength
        )

        dpg.add_slider_float(
            label="Horizontal pull",
            default_value=0.0,
            min_value=-10.0,
            max_value=10.0,
            callback=set_horizontal
        )

        dpg.add_slider_float(
            label="Delay between pulls",
            default_value=0.012,
            min_value=0.001,
            max_value=0.05,
            format="%.3f",
            callback=set_delay
        )

        dpg.add_slider_float(
            label="Random jitter",
            default_value=0.3,
            min_value=0.0,
            max_value=3.0,
            callback=set_jitter
        )

        dpg.add_checkbox(
            label="Only activate while right click is held",
            default_value=False,
            callback=set_require_right_click
        )

        dpg.add_separator()
        dpg.add_text("Overlay position")

        dpg.add_slider_int(
            label="Overlay X",
            default_value=30,
            min_value=0,
            max_value=2500,
            callback=set_overlay_x
        )

        dpg.add_slider_int(
            label="Overlay Y",
            default_value=30,
            min_value=0,
            max_value=1400,
            callback=set_overlay_y
        )

        dpg.add_separator()

        dpg.add_text("Suggested starting settings:")
        dpg.add_text("Strength: 2 to 5")
        dpg.add_text("Delay: 0.010 to 0.016")
        dpg.add_text("Jitter: 0.1 to 0.5")

    dpg.create_viewport(title="Offline Anti-Recoil Tool", width=580, height=560)
    dpg.setup_dearpygui()
    dpg.show_viewport()


# -------------------------
# Main
# -------------------------

def main():
    global running

    try:
        # Create the GUI first so Dear PyGui exists before any threads use it
        build_gui()

        keyboard.add_hotkey("f8", toggle_enabled)

        recoil_thread = threading.Thread(target=recoil_loop, daemon=True)
        recoil_thread.start()

        active_window_thread = threading.Thread(target=update_active_window_text, daemon=True)
        active_window_thread.start()

        overlay_thread = threading.Thread(target=overlay_loop, daemon=True)
        overlay_thread.start()

        dpg.start_dearpygui()

    except Exception:
        import traceback

        error_text = traceback.format_exc()

        print("\nSCRIPT CRASHED:\n")
        print(error_text)

        with open("crash_log.txt", "w", encoding="utf-8") as file:
            file.write(error_text)

        input("\nPress Enter to close...")

    finally:
        running = False
        keyboard.unhook_all()

        if overlay_hwnd is not None:
            try:
                win32gui.PostMessage(overlay_hwnd, win32con.WM_CLOSE, 0, 0)
            except win32gui.error:
                pass

        try:
            dpg.destroy_context()
        except Exception:
            pass


if __name__ == "__main__":
    main()