# mc_downloader/downloader/__init__.py
"""
Downloader package - contains vanilla and mod loader downloaders.
"""
from mc_downloader.downloader.vanilla import VanillaDownloader
from mc_downloader.downloader.mod_loaders import (
    ModLoaderInstaller,
    ForgeInstaller,
    FabricInstaller,
    QuiltInstaller,
    NeoForgeInstaller,
    get_installer,
    list_loaders,
    MOD_LOADERS,
)

__all__ = [
    "VanillaDownloader",
    "ModLoaderInstaller",
    "ForgeInstaller",
    "FabricInstaller",
    "QuiltInstaller",
    "NeoForgeInstaller",
    "get_installer",
    "list_loaders",
    "MOD_LOADERS",
]