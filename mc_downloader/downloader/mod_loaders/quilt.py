# mc_downloader/downloader/mod_loaders/quilt.py
"""
Quilt mod loader installer.
"""
import json
from pathlib import Path
from typing import List, Dict, Any

from mc_downloader.downloader.mod_loaders.base import ModLoaderInstaller
from mc_downloader.core.utils import fetch_json


class QuiltInstaller(ModLoaderInstaller):
    """Quilt mod loader installer."""
    
    loader_name = "quilt"
    loader_display_name = "Quilt"
    
    QUILT_META_URL = "https://meta.quiltmc.org/v3"
    QUILT_MIRROR_META_URL = "https://bmclapi2.bangbang93.com/quilt-meta/v3"
    
    def fetch_loader_versions(self) -> List[Dict[str, Any]]:
        """Fetch available Quilt versions for the Minecraft version."""
        self._log(f"正在获取 {self.mc_version} 的 Quilt 版本列表...")
        
        try:
            # Get Quilt loader versions
            loader_url = f"{self._get_meta_base()}/versions/loader"
            loaders = fetch_json(loader_url, self.use_mirror)
            
            # Get Minecraft versions
            mc_url = f"{self._get_meta_base()}/versions/game"
            mc_versions = fetch_json(mc_url, self.use_mirror)
            
            # 该 MC 版本若不在支持列表中，直接返回空列表
            mc_version_ids = {v["version"] for v in mc_versions}
            if self.mc_version not in mc_version_ids:
                self._log(f"[ERROR] Quilt 不支持 Minecraft {self.mc_version}。")
                self._log("       Quilt 从 1.14.4 起才提供支持。")
                return []
            
            # 过滤加载器版本
            versions = []
            for loader in loaders:
                if loader.get("version"):
                    versions.append({
                        "version": loader["version"],
                        "full_version": f"{self.mc_version}-quilt-{loader['version']}",
                        "branch": "stable" if loader.get("stable") else "snapshot",
                        "mc_version": self.mc_version,
                        "build": loader.get("build", 0),
                    })

            # 排序：稳定版在前，再按构建号降序
            versions.sort(key=lambda x: (x["branch"] != "stable", -x["build"]))
            
            self._log(f"找到 {len(versions)} 个可用的 Quilt 版本")
            return versions
            
        except Exception as e:
            self._log(f"[ERROR] 获取 Quilt 版本列表失败: {e}")
            return []
    
    def _get_meta_base(self) -> str:
        return self.QUILT_MIRROR_META_URL if self.use_mirror else self.QUILT_META_URL
    
    def get_installer_url(self, loader_version: str) -> str:
        """Get installer URL for specific Quilt version."""
        return f"{self._get_meta_base()}/versions/loader/{self.mc_version}/{loader_version}/profile/json"
    
    def install_loader(self, loader_version: str) -> bool:
        """Install Quilt for the specified version."""
        try:
            self._log(f"===== 开始安装 Quilt {self.mc_version}-{loader_version} =====")
            
            if self.use_mirror:
                self._log("镜像源：BMCLAPI (Quilt Meta)")
            else:
                self._log("镜像源：Quilt 官方 Meta")
            
            # Fetch Quilt profile (version.json)
            profile_url = self.get_installer_url(loader_version)
            self._log("获取 Quilt 安装配置...")
            
            profile = fetch_json(profile_url, self.use_mirror)
            profile.setdefault("id", f"{self.mc_version}-quilt-{loader_version}")
            profile.setdefault("inheritsFrom", self.mc_version)
            
            # Create version directory
            version_id = f"{self.mc_version}-quilt-{loader_version}"
            version_dir = self.mc_dir / "versions" / version_id
            version_dir.mkdir(parents=True, exist_ok=True)
            
            # Save version.json
            version_json_path = version_dir / f"{version_id}.json"
            version_json_path.write_text(
                json.dumps(profile, indent=2, ensure_ascii=False),
                encoding="utf-8"
            )
            self._log(f"版本详情已保存: {version_json_path}")
            
            if self.cancelled:
                return False
            
            # Download libraries
            libraries = profile.get("libraries", [])
            if libraries:
                self._download_libraries(libraries, "Quilt 依赖库")
            
            self._log(f"===== Quilt {self.mc_version}-{loader_version} 安装完成！ =====")
            return True
            
        except Exception as e:
            self._log(f"[ERROR] Quilt 安装失败: {e}")
            return False