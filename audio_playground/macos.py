"""macOS-only tweaks that Qt cannot apply on its own."""

from __future__ import annotations

import ctypes
import ctypes.util
import sys


def set_bundle_name(name: str) -> None:
    """Rename the process in the Dock and menu bar.

    Unbundled Python apps inherit "Python" from the interpreter's own bundle,
    so patch the main bundle's info dictionary before Qt reads it.
    """
    if sys.platform != "darwin":
        return
    try:
        library = ctypes.util.find_library("objc")
        if library is None:
            return
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

        get_class = lambda cls: ctypes.c_void_p(objc.objc_getClass(cls.encode()))
        selector = lambda sel: ctypes.c_void_p(objc.sel_registerName(sel.encode()))
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
