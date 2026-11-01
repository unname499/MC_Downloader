# mc_downloader/downloader/mod_loaders/__init__.py
"""
Mod loader installation modules.
"""
from mc_downloader.downloader.mod_loaders.base import ModLoaderInstaller
from mc_downloader.downloader.mod_loaders.forge import ForgeInstaller
from mc_downloader.downloader.mod_loaders.fabric import FabricInstaller
from mc_downloader.downloader.mod_loaders.quilt import QuiltInstaller
from mc_downloader.downloader.mod_loaders.neoforge import NeoForgeInstaller

__all__ = [
    "ModLoaderInstaller",
    "ForgeInstaller",
    "FabricInstaller",
    "QuiltInstaller",
    "NeoForgeInstaller",
]

# Registry of available mod loaders
MOD_LOADERS = {
    "forge": ForgeInstaller,
    "fabric": FabricInstaller,
    "quilt": QuiltInstaller,
    "neoforge": NeoForgeInstaller,
}


def get_installer(loader_name: str) -> type:
    """Get mod loader installer class by name."""
    return MOD_LOADERS.get(loader_name.lower())


def list_loaders() -> list[str]:
    """List available mod loader names."""
    return list(MOD_LOADERS.keys())