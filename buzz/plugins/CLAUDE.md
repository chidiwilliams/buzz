# Plugins

Before adding or modifying any plugin in this directory, read [AGENTS.md](AGENTS.md)
in full. It is the authoritative guide for the Buzz plugin system and covers:

- The plugin contract (`BuzzPlugin`, `PluginMetadata`, hooks and their threads).
- Configuration fields, dependencies, and `PluginContext`.
- Localization (`plugin_gettext`, `locale/*.json`, the supported locale set).
- Packaging, bundling, and the checklist for creating a plugin.

Follow the conventions there — including localizing user-facing strings and
keeping the `locale/` file set in sync across bundled plugins.
