# mc_downloader/downloader/mod_loaders/neoforge.py
"""
NeoForge mod loader installer.

版本号方案（NeoForge 1.20.5+）：
    主版本 = MC 次版本，次版本 = MC 补丁号，之后为构建号。
        1.21       -> 21.1.x
        1.21.1     -> 21.1.x
        1.21.4     -> 21.4.x
        1.21.11    -> 21.11.x
    例外：1.20.4 及其更早的版本使用旧式 "1.20.1-47.1.106" 命名。
"""
import re
import xml.etree.ElementTree as ET
from typing import List, Dict, Any, Optional

from mc_downloader.downloader.mod_loaders.base import ModLoaderInstaller
from mc_downloader.downloader.mod_loaders._json_utils import extract_version_json
from mc_downloader.core.utils import fetch_text
from mc_downloader.core.constants import HEADERS, PROXIES
import requests


class NeoForgeInstaller(ModLoaderInstaller):
    """NeoForge mod loader installer."""

    loader_name = "neoforge"
    loader_display_name = "NeoForge"

    NEOFORGE_MAVEN_URL = "https://maven.neoforged.net"
    NEOFORGE_MIRROR_URL = "https://bmclapi2.bangbang93.com/maven"

    METADATA_PATH = "net/neoforged/neoforge/maven-metadata.xml"
    INSTALLER_PATH = "net/neoforged/neoforge/{ver}/neoforge-{ver}-installer.jar"

    # ------------------------------------------------------------------ 工具

    @property
    def _maven_base(self) -> str:
        return self.NEOFORGE_MIRROR_URL if self.use_mirror else self.NEOFORGE_MAVEN_URL

    @staticmethod
    def _parse_mc_version(mc_version: str) -> Optional[tuple]:
        """把 "1.21.1" 解析成 (21, 1)。解析失败返回 None。"""
        m = re.match(r"^1\.(\d+)(?:\.(\d+))?$", mc_version.strip())
        if not m:
            return None
        minor = int(m.group(1))
        patch = int(m.group(2)) if m.group(2) else 0
        return minor, patch

    @classmethod
    def _matches_mc(cls, neoforge_version: str, mc_version: str) -> bool:
        """判断某个 NeoForge 版本是否对应指定的 MC 版本。"""
        parsed = cls._parse_mc_version(mc_version)
        if parsed is None:
            # 快照版本等，只能做前缀匹配
            return neoforge_version.startswith(f"{mc_version}-")
        minor, patch = parsed

        # 旧式命名："1.20.1-47.1.106"
        if neoforge_version.startswith("1."):
            return neoforge_version.startswith(f"{mc_version}-")

        m = re.match(r"^(\d+)\.(\d+)\.", neoforge_version)
        if not m:
            return False
        major, sub = int(m.group(1)), int(m.group(2))
        return major == minor and sub == patch

    @staticmethod
    def _sort_key(version: str) -> tuple:
        parts = []
        for part in re.split(r"[.\-+]", version):
            m = re.match(r"(\d+)(.*)", part)
            if m:
                # 正式版排在预发布版之前
                suffix = m.group(2).lower()
                rank = 1 if suffix.startswith("beta") else (0 if suffix.startswith("alpha") else 2)
                parts.append((int(m.group(1)), rank, suffix))
            else:
                parts.append((0, 0, part))
        return tuple(parts)

    # ------------------------------------------------------------------ 版本列表

    def fetch_loader_versions(self) -> List[Dict[str, Any]]:
        """获取指定 Minecraft 版本可用的 NeoForge 版本。"""
        self._log(f"正在获取 {self.mc_version} 的 NeoForge 版本列表...")

        urls = [f"{self._maven_base}/{self.METADATA_PATH}"]
        if self.use_mirror:
            # 镜像失败时回退官方
            urls.append(f"{self.NEOFORGE_MAVEN_URL}/{self.METADATA_PATH}")

        all_versions: List[str] = []
        last_err: Optional[Exception] = None
        for url in urls:
            try:
                text = fetch_text(url, use_mirror=False)
                root = ET.fromstring(text)
                all_versions = [v.text.strip() for v in root.findall(".//versioning/versions/version") if v.text]
                if all_versions:
                    break
            except Exception as e:  # noqa: BLE001
                last_err = e
                self._log(f"[WARN] 读取 {url} 失败: {e}")

        if not all_versions:
            self._log(f"[ERROR] 无法获取 NeoForge 版本元数据: {last_err}")
            return []

        matched = [v for v in all_versions if self._matches_mc(v, self.mc_version)]
        matched.sort(key=self._sort_key, reverse=True)

        versions = []
        for ver in matched:
            branch = "beta" if ("beta" in ver or "alpha" in ver or "snapshot" in ver) else "release"
            versions.append({
                "version": ver,
                "full_version": ver,
                "branch": branch,
                "mc_version": self.mc_version,
                "installer_url": self._build_installer_url(ver),
            })

        self._log(f"找到 {len(versions)} 个可用的 NeoForge 版本")
        return versions

    # ------------------------------------------------------------------ 安装

    def _build_installer_url(self, neoforge_version: str) -> str:
        path = self.INSTALLER_PATH.format(ver=neoforge_version)
        return f"{self._maven_base}/{path}"

    def get_installer_url(self, loader_version: str) -> str:
        return self._build_installer_url(loader_version)

    def install_loader(self, loader_version: str) -> bool:
        """下载 NeoForge，并直接生成版本 JSON（无需 Java）。"""
        try:
            self._log(f"===== 开始安装 NeoForge {loader_version} =====")
            self._log("镜像源：BMCLAPI" if self.use_mirror else "镜像源：NeoForge 官方 Maven")

            version_id = f"{self.mc_version}-neoforge-{loader_version}"
            version_dir = self.mc_dir / "versions" / version_id
            version_dir.mkdir(parents=True, exist_ok=True)

            # 1) 安装器 JAR（含版本清单）
            jar_path = version_dir / f"neoforge-{loader_version}-installer.jar"
            self._log(f"下载 NeoForge 安装器: {jar_path.name}")
            self._download_installer(self.get_installer_url(loader_version), jar_path)
            self._log(f"[OK] {jar_path.name}")

            if self.cancelled:
                return False

            # 2) 版本 JSON
            version_data = self._build_version_json(loader_version, jar_path)
            target = version_dir / f"{version_id}.json"
            target.write_text(
                __import__("json").dumps(version_data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            self._log(f"版本详情已保存: {target}")

            if self.cancelled:
                return False

            # 3) 安装器内自带的 maven 构件
            self._extract_bundled_artifacts(jar_path)

            # 4) 依赖库
            self._download_libraries(version_data.get("libraries", []), "NeoForge 依赖库")

            # 5) 客户端 Jar
            client = (version_data.get("downloads") or {}).get("client")
            if client:
                client_path = version_dir / f"{version_id}.jar"
                self._execute_download_tasks([{
                    "url": client["url"],
                    "path": client_path,
                    "sha1": client.get("sha1"),
                    "size": client.get("size", 0),
                }], "NeoForge 客户端 Jar")

            # 6) 可选：运行 Java 安装器，补全数据处理器产物
            if self.run_java_installer:
                self._run_patcher(jar_path, loader_version)
            else:
                self._log("未启用「运行安装器补全」，跳过数据处理器产物生成。")

            self._log(f"===== NeoForge {loader_version} 安装完成！ =====")
            return True

        except Exception as e:  # noqa: BLE001
            self._log(f"[ERROR] NeoForge 安装失败: {e}")
            return False

    def _run_patcher(self, installer_jar, loader_version: str) -> bool:
        """运行 NeoForge 安装器补全数据处理器产物。"""
        self._log("===== 运行安装器补全（生成客户端补丁文件）=====")
        ok = self._run_installer_java(installer_jar)
        if ok:
            self._log("注入器执行完成")
        else:
            self._log("[WARN] 安装器未能成功执行，NeoForge 可能无法启动")
        return ok

    def _extract_bundled_artifacts(self, jar_path) -> int:
        """解压安装器内 bundled 的 maven 构件（universal / client 等）到 libraries/。"""
        import zipfile

        count = 0
        try:
            with zipfile.ZipFile(jar_path) as zf:
                for name in zf.namelist():
                    if not name.startswith("maven/") or name.endswith("/"):
                        continue
                    rel = name[len("maven/"):]
                    target = self.mc_dir / "libraries" / rel
                    if target.exists() and target.stat().st_size > 0:
                        continue
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(name) as src, open(target, "wb") as dst:
                        dst.write(src.read())
                    count += 1
        except Exception as e:  # noqa: BLE001
            self._log(f"[WARN] 解压安装器内置构件失败: {e}")
            return count

        if count:
            self._log(f"已从安装器解压 {count} 个内置构件")
        return count

    def _download_installer(self, url: str, path) -> None:
        from mc_downloader.core.utils import download_file
        download_file(
            url, path, None,
            progress_tracker=self._progress_tracker,
            session=self._get_session(),
            use_mirror=False,
        )

    def _build_version_json(self, loader_version: str, installer_jar) -> dict:
        """
        生成 NeoForge 版本 JSON。

        安装器 JAR 中包含版本清单；若解析失败则按 Maven 坐标手工拼装。
        """
        version_id = f"{self.mc_version}-neoforge-{loader_version}"
        parsed = extract_version_json(installer_jar, version_id, self.mc_version)
        if parsed is not None:
            return parsed
        self._log("[WARN] 安装器内未找到版本清单，回退到手工拼装")

        # 回退：手工拼装
        base = self._maven_base
        version_id = f"{self.mc_version}-neoforge-{loader_version}"
        maven_path = f"net/neoforged/neoforge/{loader_version}"
        libraries = [
            {
                "name": f"net.neoforged:neoforge:{loader_version}",
                "downloads": {
                    "artifact": {
                        "path": f"{maven_path}/neoforge-{loader_version}-universal.jar",
                        "url": f"{base}/{maven_path}/neoforge-{loader_version}-universal.jar",
                    }
                },
            }
        ]
        return {
            "id": version_id,
            "inheritsFrom": self.mc_version,
            "mainClass": "cpw.mods.bootstraplauncher.BootstrapLauncher",
            "libraries": libraries,
        }
