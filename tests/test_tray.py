"""Offline unit tests for ytm_winamp.tray (no display, no real Winamp)."""
import sys
import types

import pytest

from ytm_winamp import tray


class FakeUser32:
    """Records SendMessageW calls; fakes one Winamp window."""

    def __init__(self, hwnd=0, state=0, title=""):
        self.hwnd = hwnd
        self.state = state
        self.title = title
        self.sent = []
        self.class_name = None

    def FindWindowW(self, class_name, window_name):
        self.class_name = class_name
        return self.hwnd

    def SendMessageW(self, hwnd, msg, wparam, lparam):
        self.sent.append((hwnd, msg, wparam, lparam))
        if msg == tray.WM_USER and lparam == tray.IPC_ISPLAYING:
            return self.state
        return 0

    def GetWindowTextLengthW(self, hwnd):
        return len(self.title)

    def GetWindowTextW(self, hwnd, buf, count):
        buf.value = self.title
        return len(self.title)


@pytest.fixture
def fake_u32(monkeypatch):
    fake = FakeUser32(hwnd=1234)
    monkeypatch.setattr(tray, "_U32", fake)
    return fake


def test_parse_window_title_playing():
    assert tray.parse_window_title(
        "23. Modern Talking - Cheri Cheri Lady - Winamp") == \
        "Modern Talking - Cheri Cheri Lady"


def test_parse_window_title_strips_status_suffixes():
    assert tray.parse_window_title("1. A - B - Winamp [Paused]") == "A - B"
    assert tray.parse_window_title("1. A - B - Winamp [Stopped]") == "A - B"


def test_parse_window_title_idle():
    assert tray.parse_window_title("Winamp") == ""
    assert tray.parse_window_title("") == ""


def test_parse_window_title_keeps_dots_in_title():
    assert tray.parse_window_title("Cher - Believe - Winamp") == "Cher - Believe"


def test_find_winamp_window_uses_class_name(fake_u32):
    assert tray.find_winamp_window() == 1234
    assert fake_u32.class_name == "Winamp v1.x"


def test_find_winamp_window_missing(fake_u32):
    fake_u32.hwnd = 0
    assert tray.find_winamp_window() == 0


def test_send_command_no_window(fake_u32):
    fake_u32.hwnd = 0
    assert tray.next_track() is False
    assert fake_u32.sent == []


def test_send_command_wm_command(fake_u32):
    assert tray.send_command(999) is True
    assert fake_u32.sent == [(1234, tray.WM_COMMAND, 999, 0)]


def test_command_wrappers(fake_u32):
    tray.previous_track()
    tray.play()
    tray.pause()
    tray.stop()
    tray.next_track()
    commands = [wparam for _, _, wparam, _ in fake_u32.sent]
    assert commands == [40044, 40045, 40046, 40047, 40048]


def test_play_state(fake_u32):
    fake_u32.state = 1
    assert tray.play_state() == tray.STATE_PLAYING
    fake_u32.state = 3
    assert tray.play_state() == tray.STATE_PAUSED
    fake_u32.state = 0
    assert tray.play_state() == tray.STATE_STOPPED


def test_play_state_no_winamp(fake_u32):
    fake_u32.hwnd = 0
    assert tray.play_state() == tray.STATE_NO_WINAMP


def _commands(fake):
    """Only the WM_COMMAND sends, ignoring IPC_ISPLAYING state queries."""
    return [wparam for _, msg, wparam, _ in fake.sent if msg == tray.WM_COMMAND]


def test_toggle_playback_pauses_when_playing(fake_u32):
    fake_u32.state = 1
    tray.toggle_playback()
    assert _commands(fake_u32) == [tray.CMD_PAUSE]


def test_toggle_playback_plays_when_paused_or_stopped(fake_u32):
    fake_u32.state = 3
    tray.toggle_playback()
    fake_u32.state = 0
    tray.toggle_playback()
    assert _commands(fake_u32) == [tray.CMD_PLAY, tray.CMD_PLAY]


def test_now_playing(fake_u32):
    fake_u32.title = "7. Cher - Believe - Winamp"
    assert tray.now_playing() == "Cher - Believe"
    assert tray.now_playing_text() == "Now playing: Cher - Believe"


def test_now_playing_nothing(fake_u32):
    fake_u32.title = "Winamp"
    assert tray.now_playing() == ""
    assert tray.now_playing_text() == "Now playing: (nothing)"
    fake_u32.hwnd = 0
    assert tray.now_playing() == ""


def test_icon_path_env_override(monkeypatch):
    monkeypatch.setenv("YTM_WINAMP_ICON", r"C:\icons\custom.png")
    assert str(tray.icon_path()) == r"C:\icons\custom.png"


def test_icon_path_default_exists(monkeypatch):
    monkeypatch.delenv("YTM_WINAMP_ICON", raising=False)
    monkeypatch.delattr(sys, "frozen", raising=False)
    assert tray.icon_path().is_file()  # docs/icon.png ships in the repo


def test_load_icon_image():
    image = tray.load_icon_image()
    assert image.size[0] > 0


def test_open_bridge_log(monkeypatch, tmp_path):
    log = tmp_path / "ytm-winamp-bridge.log"
    opened = []
    monkeypatch.setattr(tray, "BRIDGE_LOG", log)
    monkeypatch.setattr("os.startfile", opened.append, raising=False)
    assert tray.open_bridge_log() == log
    assert log.is_file()  # created so the viewer never gets a missing file
    assert opened == [log]


def _fake_era_modules(monkeypatch, era, winamp):
    """Swap the era/winamp names on the package; from-imports then see fakes
    regardless of which modules earlier tests already imported."""
    import ytm_winamp

    monkeypatch.setattr(ytm_winamp, "era", era, raising=False)
    monkeypatch.setattr(ytm_winamp, "winamp", winamp, raising=False)


def test_launch_era_radio_background_thread(monkeypatch):
    played = []
    _fake_era_modules(
        monkeypatch,
        era=types.SimpleNamespace(
            era_tracks=lambda count: (["track"] * count, "note")),
        winamp=types.SimpleNamespace(
            DEFAULT_PORT=8797,
            play=lambda tracks, port: played.append((tracks, port))))
    thread = tray.launch_era_radio(count=3)
    thread.join(timeout=5)
    assert played == [(["track"] * 3, 8797)]


def test_launch_era_radio_swallows_failures(monkeypatch):
    def boom(count):
        raise RuntimeError("no network")

    _fake_era_modules(
        monkeypatch,
        era=types.SimpleNamespace(era_tracks=boom),
        winamp=types.SimpleNamespace(DEFAULT_PORT=8797, play=None))
    tray.launch_era_radio().join(timeout=5)  # must not raise


def test_build_menu_structure(fake_u32):
    from pystray import Menu

    menu = tray.build_menu()
    assert isinstance(menu, Menu)
    items = list(menu.items)
    assert len(items) == 9  # 7 entries + 2 separators
    texts = [str(item.text) for item in items]
    assert texts[0] == "Now playing: (nothing)"
    assert texts[1:4] == ["Play", "Previous", "Next"]
    assert texts[5:7] == ["Era radio", "Open bridge log"]
    assert texts[8] == "Quit"
    assert not items[0].enabled  # now-playing line is read-only
    assert items[1].enabled


def test_build_menu_dynamic_labels(fake_u32):
    fake_u32.state = 1
    fake_u32.title = "3. Aqua - Barbie Girl - Winamp"
    items = list(tray.build_menu().items)
    assert str(items[0].text) == "Now playing: Aqua - Barbie Girl"
    assert str(items[1].text) == "Pause"  # playing -> offered action is Pause


def test_menu_actions_drive_winamp(fake_u32):
    items = list(tray.build_menu().items)
    items[2](None)  # Previous
    items[3](None)  # Next
    commands = [wparam for _, _, wparam, _ in fake_u32.sent]
    assert commands == [tray.CMD_PREVIOUS, tray.CMD_NEXT]


def test_menu_quit_stops_icon(fake_u32):
    class FakeIcon:
        stopped = False

        def stop(self):
            self.stopped = True

    icon = FakeIcon()
    list(tray.build_menu().items)[8](icon)
    assert icon.stopped
