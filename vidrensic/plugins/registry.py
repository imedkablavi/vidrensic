from __future__ import annotations

from collections.abc import Iterable

from vidrensic.plugins.base import FormatPlugin


class PluginRegistry:
    def __init__(self, plugins: Iterable[FormatPlugin] = ()):
        self._plugins: dict[str, FormatPlugin] = {}
        for plugin in plugins:
            self.register(plugin)

    def register(self, plugin: FormatPlugin) -> None:
        name = plugin.name.strip().lower()
        if not name:
            raise ValueError("plugin name cannot be empty")
        if name in self._plugins:
            raise ValueError(f"plugin already registered: {name}")
        self._plugins[name] = plugin

    def get(self, name: str) -> FormatPlugin:
        try:
            return self._plugins[name.lower()]
        except KeyError as exc:
            raise KeyError(f"unknown plugin: {name}") from exc

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._plugins))

    def detect_best(self, source):
        results = [(plugin.detect(source), plugin) for plugin in self._plugins.values()]
        if not results:
            raise LookupError("no format plugins are registered")
        result, plugin = max(results, key=lambda item: item[0].confidence)
        return result, plugin
