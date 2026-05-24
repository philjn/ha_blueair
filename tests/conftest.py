"""Test harness for ha_blueair.

ha_blueair is normally imported inside a running Home Assistant; the test
suite does NOT spin one up — it installs lightweight stubs in
``sys.modules`` for every ``homeassistant.*`` import the modules under
test touch. We add the workspace root to ``sys.path`` so the
``custom_components.ha_blueair.*`` namespace resolves.

Stubs are intentionally minimal — just enough surface to let the imports
resolve and the new reset code be exercised. Anything outside that
scope should NOT be added here; add a dedicated stub in a focused test
instead.
"""
from __future__ import annotations

import functools
import os
import sys
import types
from enum import Enum


_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_HERE)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)


def _stub(name: str, **attrs: object) -> types.ModuleType:
    """Register a synthetic module if the real one is missing."""
    if name in sys.modules:
        return sys.modules[name]
    mod = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(mod, k, v)
    sys.modules[name] = mod
    return mod


# Real propcache may be available; fall back to functools.cached_property.
try:  # pragma: no cover
    import propcache  # noqa: F401
except ModuleNotFoundError:
    _stub("propcache", cached_property=functools.cached_property)


# ---- homeassistant stubs ---------------------------------------------------
try:  # pragma: no cover
    import homeassistant  # noqa: F401
except ModuleNotFoundError:

    class _EntityCategory(Enum):
        CONFIG = "config"
        DIAGNOSTIC = "diagnostic"

    class _Platform(Enum):
        BINARY_SENSOR = "binary_sensor"
        BUTTON = "button"
        CLIMATE = "climate"
        FAN = "fan"
        HUMIDIFIER = "humidifier"
        LIGHT = "light"
        SENSOR = "sensor"
        SWITCH = "switch"

    class _HomeAssistantError(Exception):
        """Stub for homeassistant.exceptions.HomeAssistantError."""

    class _HomeAssistant: ...

    class _DataUpdateCoordinator:
        def __init__(self, *args, **kwargs): ...

        async def async_request_refresh(self): ...

    class _CoordinatorEntity:
        def __init__(self, coordinator, *args, **kwargs):
            self.coordinator = coordinator

        def async_write_ha_state(self): ...

        def __class_getitem__(cls, item):
            return cls

    class _Debouncer:
        def __init__(self, *args, **kwargs): ...

    class _ButtonEntity:
        async def async_press(self): ...

    class _ButtonEntityDescription:
        def __init__(self, key=None, name=None, icon=None, entity_category=None):
            self.key = key
            self.name = name
            self.icon = icon
            self.entity_category = entity_category

    _stub("homeassistant")
    _stub("homeassistant.core", HomeAssistant=_HomeAssistant)
    _stub(
        "homeassistant.exceptions",
        HomeAssistantError=_HomeAssistantError,
        ConfigEntryNotReady=type("ConfigEntryNotReady", (Exception,), {}),
    )
    _stub(
        "homeassistant.const",
        EntityCategory=_EntityCategory,
        Platform=_Platform,
        CONF_USERNAME="username",
        CONF_PASSWORD="password",
        CONF_REGION="region",
        PERCENTAGE="%",
        CONCENTRATION_MICROGRAMS_PER_CUBIC_METER="µg/m³",
        CONCENTRATION_PARTS_PER_MILLION="ppm",
    )
    _stub("homeassistant.components")
    _stub(
        "homeassistant.components.button",
        ButtonEntity=_ButtonEntity,
        ButtonEntityDescription=_ButtonEntityDescription,
    )
    _stub("homeassistant.helpers")
    _stub(
        "homeassistant.helpers.update_coordinator",
        CoordinatorEntity=_CoordinatorEntity,
        DataUpdateCoordinator=_DataUpdateCoordinator,
        Debouncer=_Debouncer,
        REQUEST_REFRESH_DEFAULT_COOLDOWN=10,
    )
    _stub(
        "homeassistant.helpers.device_registry",
        CONNECTION_NETWORK_MAC="mac",
        DeviceInfo=dict,
    )
    _stub(
        "homeassistant.util",
    )
    _stub(
        "homeassistant.util.color",
        value_to_brightness=lambda scale, v: v,
        brightness_to_value=lambda scale, v: v,
    )


# Modules imported by ha_blueair's package __init__.py that are not part
# of the new code under test. We stub them just enough to let the import
# resolve so submodules can be loaded.
try:  # pragma: no cover
    import voluptuous  # noqa: F401
except ModuleNotFoundError:
    class _Schema:
        def __init__(self, *args, **kwargs): ...

    def _required(name, *args, **kwargs):
        return name

    _stub(
        "voluptuous",
        Schema=_Schema,
        Required=_required,
        Optional=_required,
        ALLOW_EXTRA=object(),
        All=lambda *a, **kw: None,
        Range=lambda *a, **kw: None,
    )

# Late: pull in `homeassistant.config_entries`, `helpers.aiohttp_client`,
# `helpers.config_validation`, `helpers.typing` — needed by ha_blueair's
# package __init__ but not by the code we test.
if "homeassistant.config_entries" not in sys.modules:
    _stub(
        "homeassistant.config_entries",
        ConfigEntry=type("ConfigEntry", (), {}),
    )
if "homeassistant.helpers.aiohttp_client" not in sys.modules:
    _stub(
        "homeassistant.helpers.aiohttp_client",
        async_get_clientsession=lambda *a, **kw: None,
    )
if "homeassistant.helpers.config_validation" not in sys.modules:
    _stub(
        "homeassistant.helpers.config_validation",
        string=str,
        positive_int=int,
    )
if "homeassistant.helpers.typing" not in sys.modules:
    _stub("homeassistant.helpers.typing", ConfigType=dict)
# CONF_SCAN_INTERVAL is referenced by the package __init__.
_const_mod = sys.modules.get("homeassistant.const")
if _const_mod is not None and not hasattr(_const_mod, "CONF_SCAN_INTERVAL"):
    _const_mod.CONF_SCAN_INTERVAL = "scan_interval"
