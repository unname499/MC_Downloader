# mc_downloader/downloader/mod_loaders/fabric.py
"""
Fabric mod loader installer.
"""
import json
from pathlib import Path
from typing import List, Dict, Any

from mc_downloader.downloader.mod_loaders.base import ModLoaderInstaller
from mc_downloader.core.utils import fetch_json


def _version_key(version: str) -> tuple:
    """把 MC 版本串转成可比较的元组。"""
    import re
    parts = []
    for part in re.split(r"[.\-]", version):
        m = re.match(r"(\d+)(.*)", part)
        if m:
            parts.append((int(m.group(1)), m.group(2)))
        else:
            parts.append((0, part))
    return tuple(parts)


def _oldest_supported(version_ids) -> str:
    """从支持的版本集合中找出最老的正式版。"""
    stable = [v for v in version_ids if v.startswith("1.") and "-" not in v
              and "pre" not in v and "rc" not in v]
    if not stable:
        return ""
    return min(stable, key=_version_key)


class FabricInstaller(ModLoaderInstaller):
    """Fabric mod loader installer."""
    
    loader_name = "fabric"
    loader_display_name = "Fabric"
    
    FABRIC_META_URL = "https://meta.fabricmc.net/v2"
    FABRIC_MIRROR_META_URL = "https://bmclapi2.bangbang93.com/fabric-meta/v2"
    
    def fetch_loader_versions(self) -> List[Dict[str, Any]]:
        """获取指定 Minecraft 版本可用的 Fabric 加载器版本。"""
        self._log(f"正在获取 {self.mc_version} 的 Fabric 版本列表...")

        try:
            # Fabric 的 loader 列表是全游戏通用的，并非每个 MC 版本都支持
            loader_url = f"{self._get_meta_base()}/versions/loader"
            loaders = fetch_json(loader_url, self.use_mirror)

            # 先确认该 MC 版本是否在官方支持列表中
            mc_url = f"{self._get_meta_base()}/versions/game"
            mc_versions = fetch_json(mc_url, self.use_mirror)
            mc_version_ids = {v["version"] for v in mc_versions}

            if self.mc_version not in mc_version_ids:
                self._log(
                    f"[ERROR] Fabric 不支持 Minecraft {self.mc_version}。"
                )
                supported = _oldest_supported(mc_version_ids)
                if supported:
                    self._log(f"       目前可用的最老版本为 {supported}（Fabric 需要 1.14 及以上）")
                return []

            # 稳定版优先，其后为快照版
            versions = []
            for loader in loaders:
                if not loader.get("version"):
                    continue
                stable = bool(loader.get("stable"))
                versions.append({
                    "version": loader["version"],
                    "full_version": f"{self.mc_version}-fabric-{loader['version']}",
                    "branch": "stable" if stable else "snapshot",
                    "mc_version": self.mc_version,
                    "build": loader.get("build", 0),
                })

            # 排序：稳定版在前，再按构建号降序
            versions.sort(key=lambda x: (x["branch"] != "stable", -x["build"]))

            self._log(f"找到 {len(versions)} 个可用的 Fabric 版本")
            return versions

        except Exception as e:  # noqa: BLE001
            self._log(f"[ERROR] 获取 Fabric 版本列表失败: {e}")
            return []
    
    def _get_meta_base(self) -> str:
        return self.FABRIC_MIRROR_META_URL if self.use_mirror else self.FABRIC_META_URL
    
    def get_installer_url(self, loader_version: str) -> str:
        """Get installer URL for specific Fabric version."""
        # Fabric doesn't use an installer JAR, it uses a version JSON directly
        return f"{self._get_meta_base()}/versions/loader/{self.mc_version}/{loader_version}/profile/json"
    
    def _fetch_profile(self, profile_url: str, loader_version: str):
        """
        获取 Fabric 版本 JSON。失败时给出可读原因而不是裸 HTTP 异常。

        Fabric 对不支持的 MC 版本返回 400：
            no mappings version found for 1.12.2
        """
        import requests

        try:
            return fetch_json(profile_url, self.use_mirror)
        except requests.HTTPError as e:
            status = e.response.status_code if e.response is not None else 0
            detail = ""
            try:
                detail = (e.response.text or "").strip()
            except Exception:  # noqa: BLE001
                pass

            if status == 400:
                self._log(f"[ERROR] Fabric 不支持 Minecraft {self.mc_version}。")
                if detail:
                    self._log(f"       Fabric 返回：{detail}")
                self._log("       Fabric 从 1.14 起才提供 intermediary 映射，"
                          "1.12.2 等旧版本请改用 Forge。")
            elif status == 404:
                self._log(f"[ERROR] 找不到 Fabric {self.mc_version} + loader {loader_version} 的组合。")
            else:
                self._log(f"[ERROR] 获取 Fabric 配置失败（HTTP {status}）：{detail or e}")
            return None
        except Exception as e:  # noqa: BLE001
            # 镜像失败时尝试官方源
            if self.use_mirror:
                self._log(f"[WARN] 镜像获取失败，回退官方源：{e}")
                try:
                    return fetch_json(profile_url.replace(
                        self.FABRIC_MIRROR_META_URL, self.FABRIC_META_URL), use_mirror=False)
                except Exception as e2:  # noqa: BLE001
                    self._log(f"[ERROR] Fabric 安装配置获取失败：{e2}")
                    return None
            self._log(f"[ERROR] Fabric 安装配置获取失败：{e}")
            return None

    def install_loader(self, loader_version: str) -> bool:
        """Install Fabric for the specified version."""
        try:
            self._log(f"===== 开始安装 Fabric {self.mc_version}-{loader_version} =====")

            if self.use_mirror:
                self._log("镜像源：BMCLAPI (Fabric Meta)")
            else:
                self._log("镜像源：Fabric 官方 Meta")

            # 1) 获取 Fabric 版本 JSON（含 loader + intermediary）
            profile_url = self.get_installer_url(loader_version)
            self._log("获取 Fabric 安装配置...")
            profile = self._fetch_profile(profile_url, loader_version)
            if profile is None:
                return False

            profile.setdefault("id", f"{self.mc_version}-fabric-{loader_version}")
            profile.setdefault("inheritsFrom", self.mc_version)

            version_id = f"{self.mc_version}-fabric-{loader_version}"
            version_dir = self.mc_dir / "versions" / version_id
            version_dir.mkdir(parents=True, exist_ok=True)

            version_json_path = version_dir / f"{version_id}.json"
            version_json_path.write_text(
                json.dumps(profile, indent=2, ensure_ascii=False),
                encoding="utf-8"
            )
            self._log(f"版本详情已保存: {version_json_path}")

            if self.cancelled:
                return False

            # 2) 依赖库（fabric-loader / intermediary 等）
            libraries = profile.get("libraries", [])
            if libraries:
                self._download_libraries(libraries, "Fabric 依赖库")

            self._log(f"===== Fabric {self.mc_version}-{loader_version} 安装完成！ =====")
            return True

        except Exception as e:  # noqa: BLE001
            self._log(f"[ERROR] Fabric 安装失败: {e}")
            return False