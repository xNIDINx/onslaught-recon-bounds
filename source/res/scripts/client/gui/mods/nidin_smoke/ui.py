# -*- coding: utf-8 -*-
"""Load the passive barrel indicator into the battle Scaleform application."""

from frameworks.wulf import WindowLayer
from gui.Scaleform.framework import ScopeTemplates, ViewSettings, g_entitiesFactories
from gui.Scaleform.framework.entities.View import View
from gui.Scaleform.framework.managers.loaders import SFViewLoadParams
from helpers import dependency
from skeletons.gui.app_loader import GuiGlobalSpaceID, IAppLoader


MOD_ID = 'nidin.onslaught_recon_bounds.contour'
VIEW_ALIAS = MOD_ID + '.hook'
SWF_FILE = 'nidinSmokeContour.swf'

_hookViewsByApp = {}
_requestsByApp = {}
_appLoader = None


def _log(message):
    print '[nidin.onslaught_recon_bounds.contour] %s' % message


class _LoadRequest(object):
    """Keep a pending load distinct from a populated view; retry on failure."""

    def __init__(self, appKey, loader):
        self.appKey = appKey
        self.loader = loader
        loader.onViewLoadError += self._onError
        loader.onViewLoadCanceled += self._onCanceled

    def close(self):
        if _requestsByApp.get(self.appKey) is self:
            del _requestsByApp[self.appKey]
        if self.loader is not None:
            self.loader.onViewLoadError -= self._onError
            self.loader.onViewLoadCanceled -= self._onCanceled
            self.loader = None

    def _onError(self, viewKey, message, item):
        if viewKey.alias == VIEW_ALIAS:
            self.close()
            _log('error: %s' % message)

    def _onCanceled(self, viewKey, item):
        if viewKey.alias == VIEW_ALIAS:
            self.close()


def _releaseRequest(appKey):
    request = _requestsByApp.get(appKey)
    if request is not None:
        request.close()


class NidinSmokeContourView(View):

    def _populate(self):
        super(NidinSmokeContourView, self)._populate()
        # View.app is a weakref.proxy; IAppLoader returns the real application.
        # Both expose the same loader object, so their keys must use that.
        appKey = self._nidinAppKey = id(self.app.loaderManager)
        _releaseRequest(appKey)
        _hookViewsByApp[appKey] = self
        _log('loaded')
        _publish(self)

    def _dispose(self):
        appKey = getattr(self, '_nidinAppKey', None)
        if _hookViewsByApp.get(appKey) is self:
            del _hookViewsByApp[appKey]
        super(NidinSmokeContourView, self)._dispose()


def _registerView():
    if g_entitiesFactories.getSettings(VIEW_ALIAS) is not None:
        return
    # OVERLAY is the native multi-view container. SERVICE_LAYOUT would evict
    # other service mods, including the WotStat view and settings helpers.
    g_entitiesFactories.addSettings(ViewSettings(
        VIEW_ALIAS, NidinSmokeContourView, SWF_FILE,
        WindowLayer.OVERLAY, None, ScopeTemplates.GLOBAL_SCOPE, False,
        canDrag=False, canClose=False, isModal=False, isCentered=False))


def _ensureBattleHook():
    app = _appLoader.getDefBattleApp()
    if app is None:
        return
    # The application can exist before its loader is initialized. The BATTLE
    # space event will reconcile it once more after onGUIInitialized.
    loader = app.loaderManager
    if loader is None:
        return
    appKey = id(loader)
    for oldKey in list(_requestsByApp):
        if oldKey != appKey:
            _releaseRequest(oldKey)
    if appKey in _hookViewsByApp or appKey in _requestsByApp:
        return
    request = _LoadRequest(appKey, loader)
    _requestsByApp[appKey] = request
    try:
        app.loadView(SFViewLoadParams(VIEW_ALIAS))
    except Exception as error:
        request.close()
        _log('error: load failed: %r' % error)


def _onGUIInitialized():
    if _appLoader.getSpaceID() in (GuiGlobalSpaceID.BATTLE_LOADING, GuiGlobalSpaceID.BATTLE):
        _ensureBattleHook()


def _onGUISpaceEntered(spaceID):
    if spaceID == GuiGlobalSpaceID.BATTLE:
        _ensureBattleHook()
    elif spaceID != GuiGlobalSpaceID.BATTLE_LOADING:
        # The native application owns disposal. Release only our references
        # and pending-load listeners when leaving the battle application.
        for appKey in list(_requestsByApp):
            _releaseRequest(appKey)
        _hookViewsByApp.clear()


_registerView()
_appLoader = dependency.instance(IAppLoader)
_appLoader.onGUIInitialized += _onGUIInitialized
_appLoader.onGUISpaceEntered += _onGUISpaceEntered
_log('registered')

_payload = []

def _publish(view):
    if view._isDAAPIInited():
        view.flashObject.as_setContours(_payload)

def set_contours(lines, bounds, colors):
    global _payload
    (left, bottom), (right, top) = bounds
    if right <= left or top <= bottom:
        return
    _payload = [{'color': colors[team], 'points': [coordinate
        for p in points for coordinate in ((p[0]-left)/(right-left), (top-p[2])/(top-bottom))]}
        for team, points in lines]
    _ensureBattleHook()
    for view in list(_hookViewsByApp.values()):
        _publish(view)

def clear():
    global _payload
    _payload = []
    for view in list(_hookViewsByApp.values()):
        _publish(view)