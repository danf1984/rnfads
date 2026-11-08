#!/usr/bin/python3
"""Schermo del NAS: finestra a tutto schermo con l'interfaccia (http://127.0.0.1:8090), dentro cage.
Apre solo pagine del NAS e delle sue app (127.0.0.1): i link esterni vengono ignorati. Se l'interfaccia non risponde riprova da sola."""
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("WebKit", "6.0")
from gi.repository import GLib, Gtk, WebKit  # noqa: E402

HOME = "http://127.0.0.1:8090/"
# Il NAS e le sue app (http://127.0.0.1:<porta>, es. Jellyfin su :8096); niente siti esterni
ALLOWED = ("http://127.0.0.1:", "http://localhost:", "about:", "blob:", "data:")


def on_policy(view, decision, dtype):
    T = WebKit.PolicyDecisionType
    if dtype in (T.NAVIGATION_ACTION, T.NEW_WINDOW_ACTION):
        uri = decision.get_navigation_action().get_request().get_uri() or ""
        if not uri.startswith(ALLOWED):
            decision.ignore()
            return True
        if dtype == T.NEW_WINDOW_ACTION:     # target="_blank": stessa finestra
            view.load_uri(uri)
            decision.ignore()
            return True
    return False


def on_create(view, action):
    """window.open / target="_blank": la pagina si apre nella stessa finestra (se è del NAS)."""
    uri = action.get_request().get_uri() or ""
    if uri.startswith(ALLOWED):
        view.load_uri(uri)
    return None


def on_failed(view, event, uri, error):
    GLib.timeout_add_seconds(4, lambda: (view.load_uri(HOME), False)[1])
    return False


def activate(app):
    win = Gtk.ApplicationWindow(application=app, title="RNFADS")
    view = WebKit.WebView()
    s = view.get_settings()
    s.set_enable_developer_extras(False)
    s.set_javascript_can_open_windows_automatically(True)   # window.open dell'interfaccia: aperto nella stessa finestra
    s.set_hardware_acceleration_policy(WebKit.HardwareAccelerationPolicy.NEVER)
    view.connect("decide-policy", on_policy)
    view.connect("load-failed", on_failed)
    view.connect("create", on_create)
    win.set_child(view)
    # cage dà già tutta la superficie dello schermo alla finestra; fullscreen() prima che la finestra sia
    # mostrata fa fallire cage 0.2 (wlr_xdg_surface_schedule_configure): non serve
    win.present()
    view.load_uri(HOME)


app = Gtk.Application(application_id="it.rnfads.Schermo")
app.connect("activate", activate)
app.run(None)
