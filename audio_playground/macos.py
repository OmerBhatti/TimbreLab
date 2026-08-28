"""macOS-only tweaks that Qt cannot apply on its own."""

from __future__ import annotations

import ctypes
import ctypes.util
import sys


def _runtime():
    """Return (signature builder, class lookup, selector lookup), or None."""
    library = ctypes.util.find_library("objc")
    if library is None:
        return None
    objc = ctypes.cdll.LoadLibrary(library)
    objc.objc_getClass.restype = ctypes.c_void_p
    objc.objc_getClass.argtypes = [ctypes.c_char_p]
    objc.sel_registerName.restype = ctypes.c_void_p
    objc.sel_registerName.argtypes = [ctypes.c_char_p]
    msg_send = ctypes.cast(objc.objc_msgSend, ctypes.c_void_p).value

    def signature(restype, *argtypes):
        prototype = ctypes.CFUNCTYPE(
            restype, ctypes.c_void_p, ctypes.c_void_p, *argtypes
        )
        return prototype(msg_send)

    def get_class(name: str) -> ctypes.c_void_p:
        return ctypes.c_void_p(objc.objc_getClass(name.encode()))

    def selector(name: str) -> ctypes.c_void_p:
        return ctypes.c_void_p(objc.sel_registerName(name.encode()))

    return signature, get_class, selector


def set_bundle_name(name: str) -> None:
    """Rename the process in the Dock and menu bar.

    Unbundled Python apps inherit "Python" from the interpreter's own bundle,
    so patch the main bundle's info dictionary before Qt reads it.
    """
    if sys.platform != "darwin":
        return
    try:
        runtime = _runtime()
        if runtime is None:
            return
        signature, get_class, selector = runtime
        call = signature(ctypes.c_void_p)
        make_string = signature(ctypes.c_void_p, ctypes.c_char_p)
        set_object = signature(None, ctypes.c_void_p, ctypes.c_void_p)

        ns_string = get_class("NSString")

        def to_ns(text: str) -> ctypes.c_void_p:
            return ctypes.c_void_p(
                make_string(ns_string, selector("stringWithUTF8String:"), text.encode())
            )

        bundle = ctypes.c_void_p(
            call(get_class("NSBundle"), selector("mainBundle"))
        )
        info = ctypes.c_void_p(call(bundle, selector("infoDictionary")))
        if not info:
            return
        set_object(
            info, selector("setObject:forKey:"), to_ns(name), to_ns("CFBundleName")
        )
    except Exception:  # pragma: no cover - cosmetic only, never block startup
        return


def style_titlebar(window_id: int, rgb: tuple[float, float, float]) -> None:
    """Blend the macOS titlebar into the app's own dark chrome.

    Qt cannot restyle the native frame, so force the dark system appearance and
    paint the titlebar with the window background color instead.
    """
    if sys.platform != "darwin":
        return
    try:
        runtime = _runtime()
        if runtime is None:
            return
        signature, get_class, selector = runtime
        call = signature(ctypes.c_void_p)
        call_str = signature(ctypes.c_void_p, ctypes.c_char_p)
        call_obj = signature(ctypes.c_void_p, ctypes.c_void_p)
        call_void_obj = signature(None, ctypes.c_void_p)
        call_bool = signature(None, ctypes.c_bool)
        color_of = signature(
            ctypes.c_void_p,
            ctypes.c_double,
            ctypes.c_double,
            ctypes.c_double,
            ctypes.c_double,
        )

        ns_string = get_class("NSString")
        name = ctypes.c_void_p(
            call_str(
                ns_string,
                selector("stringWithUTF8String:"),
                b"NSAppearanceNameDarkAqua",
            )
        )
        appearance = ctypes.c_void_p(
            call_obj(get_class("NSAppearance"), selector("appearanceNamed:"), name)
        )
        application = ctypes.c_void_p(
            call(get_class("NSApplication"), selector("sharedApplication"))
        )
        if appearance and application:
            call_void_obj(application, selector("setAppearance:"), appearance)

        view = ctypes.c_void_p(window_id)
        window = ctypes.c_void_p(call(view, selector("window")))
        if not window:
            return
        red, green, blue = rgb
        color = ctypes.c_void_p(
            color_of(
                get_class("NSColor"),
                selector("colorWithSRGBRed:green:blue:alpha:"),
                red,
                green,
                blue,
                1.0,
            )
        )
        call_bool(window, selector("setTitlebarAppearsTransparent:"), True)
        if color:
            call_void_obj(window, selector("setBackgroundColor:"), color)
    except Exception:  # pragma: no cover - cosmetic only, never block startup
        return
