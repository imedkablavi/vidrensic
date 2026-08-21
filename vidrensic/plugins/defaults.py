from __future__ import annotations

from vidrensic.plugins.annexb import AnnexBPlugin
from vidrensic.plugins.dhav import DHAVPlugin
from vidrensic.plugins.hikvision import HikvisionPlugin
from vidrensic.plugins.mpegps import MPEGPSPlugin
from vidrensic.plugins.registry import PluginRegistry
from vidrensic.plugins.wfs import WFSPlugin


def default_plugin_registry() -> PluginRegistry:
    """Return a fresh registry containing product-shipped format families."""

    return PluginRegistry(
        [
            WFSPlugin(),
            DHAVPlugin(),
            HikvisionPlugin(),
            AnnexBPlugin(),
            MPEGPSPlugin(),
        ]
    )


__all__ = ["default_plugin_registry"]
