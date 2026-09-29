# -*- coding: utf-8 -*-
"""Merge the area warning with the native lamp at the presentation boundary.

Native show/hide calls, sounds, timers and server state remain independent.
Our presentation calls bypass the observers and cannot become a native reason.
"""
import logging
from functools import wraps
from gui.Scaleform.daapi.view.battle.shared.indicators import SixthSenseIndicator

LOG = logging.getLogger('nidin.onslaught_recon.lamp')
_installed = False
_active = False
_warningVisible = False
_views = {}
_hooks = {}


def _restore_area(view):
    if _active and _warningVisible and view in _views:
        try:
            _hooks['as_showS'][0](view, True)
        except Exception:
            LOG.exception('Cannot show recon lamp')


def set_warning(visible):
    global _warningVisible
    visible = bool(visible) and _active
    if visible == _warningVisible:
        return
    _warningVisible = visible
    for view, native_visible in list(_views.items()):
        if native_visible:
            # Do not restart the native alarm/steady animation or its timer.
            continue
        if visible:
            _restore_area(view)
        else:
            try:
                _hooks['as_hideS'][0](view, True)
            except Exception:
                LOG.exception('Cannot hide recon lamp')


def start():
    global _active
    _active = True


def stop():
    global _active
    set_warning(False)
    _active = False


def _make_hook(name, original):
    @wraps(original)
    def hooked(view, *args, **kwargs):
        if not _installed:
            return original(view, *args, **kwargs)
        if name == '_dispose':
            # Teardown may itself emit hide: never resurrect a closing view.
            _views.pop(view, None)
            return original(view, *args, **kwargs)
        if name == '_populate':
            _views[view] = False
            try:
                result = original(view, *args, **kwargs)
            except Exception:
                _views.pop(view, None)
                raise
            if not _views.get(view, False):
                _restore_area(view)
            return result
        result = original(view, *args, **kwargs)
        if view in _views:
            _views[view] = name != 'as_hideS'
            if name == 'as_hideS':
                # Forward hide unchanged, then restore our independent reason.
                # Both calls complete before the next Flash frame.
                _restore_area(view)
        return result
    return hooked


def install():
    global _installed
    if _installed:
        return
    for name in ('_populate', '_dispose', 'as_showS', 'as_showIndicatorS', 'as_hideS'):
        if name in _hooks:
            continue  # An outer mod still owns this hook chain.
        original = getattr(SixthSenseIndicator, name)
        owned = name in SixthSenseIndicator.__dict__
        wrapped = _make_hook(name, original)
        _hooks[name] = (original, wrapped, owned)
        setattr(SixthSenseIndicator, name, wrapped)
    _installed = True


def uninstall():
    global _installed
    stop()
    _installed = False
    _views.clear()
    for name, (original, wrapped, owned) in list(_hooks.items()):
        current = getattr(SixthSenseIndicator, name)
        if getattr(current, 'im_func', current) is wrapped:
            if owned:
                setattr(SixthSenseIndicator, name, original)
            else:
                delattr(SixthSenseIndicator, name)
            del _hooks[name]
