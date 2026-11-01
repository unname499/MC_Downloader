# mc_downloader/downloader/mod_loaders/forge.py
"""
Forge mod loader installer.

通过 BMCLAPI 提供的中转清单获取版本信息，并从安装器 JAR 中直接解析
版本 JSON，全程不需要本地 Java。

版本列表来源（按顺序尝试）:
    1. BMCLAPI:  /maven/net/minecraftforge/forge/{mc_version}-{forge}/install_profile.json
    2. 镜像归档: /maven/net/minecraftforge/forge/maven-metadata.xml (过滤 MC 前缀)
    3. 官方:     https://files.minecraftforge.net/net/minecraftforge/forge/promotions_slim.json
"""
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List, Dict, Any, Optional

from mc_downloader.downloader.mod_loaders.base import ModLoaderInstaller
from mc_downloader.downloader.mod_loaders._json_utils import (
    extract_version_json, extract_install_profile, iter_processor_artifacts,
)
from mc_downloader.core.utils import fetch_json, fetch_text, download_file
from mc_downloader.core.constants import HEADERS, PROXIES, CONNECT_TIMEOUT, READ_TIMEOUT
import requests


class ForgeInstaller(ModLoaderInstaller):
    """Forge mod loader installer."""

    loader_name = "forge"
    loader_display_name = "Forge"

    FORGE_MAVEN_URL = "https://maven.minecraftforge.net"
    FORGE_MIRROR_URL = "https://bmclapi2.bangbang93.com/maven"
    PROMOTIONS_URL = "https://files.minecraftforge.net/net/minecraftforge/forge/promotions_slim.json"

    FORGE_PATH = "net/minecraftforge/forge"
    METADATA_PATH = "net/minecraftforge/forge/maven-metadata.xml"

    # ------------------------------------------------------------------ 工具

    @property
    def _maven_base(self) -> str:
        return self.FORGE_MIRROR_URL if self.use_mirror else self.FORGE_MAVEN_URL

    @staticmethod
    def _sort_key(version: str) -> tuple:
        parts = []
        for part in re.split(r"[.\-+]", version):
            m = re.match(r"(\d+)(.*)", part)
            if m:
                parts.append((int(m.group(1)), m.group(2).lower()))
            else:
                parts.append((0, part.lower()))
        return tuple(parts)

    @staticmethod
    def _mc_major(mc_version: str) -> str:
        """1.20.1 -> 1.20"""
        parts = mc_version.split(".")
        return ".".join(parts[:2]) if len(parts) >= 2 else mc_version

    # ------------------------------------------------------------------ 版本列表

    def fetch_loader_versions(self) -> List[Dict[str, Any]]:
        """获取指定 MC 版本可用的 Forge 版本。"""
        self._log(f"正在获取 {self.mc_version} 的 Forge 版本列表...")

        result: Optional[List[Dict[str, Any]]] = None
        errors = []

        # 1) 镜像 maven-metadata（最完整，优先）
        if self.use_mirror:
            try:
                result = self._from_maven_metadata()
            except Exception as e:  # noqa: BLE001
                errors.append(f"镜像 maven-metadata: {e}")

        # 2) promotions（官方，含推荐版/最新版）；仅在无结果时尝试，避免长时间等待
        if not result:
            try:
                promotions = self._from_promotions()
                if promotions:
                    result = promotions
            except Exception as e:  # noqa: BLE001
                errors.append(f"promotions: {e}")

        # 3) 非镜像模式下尝试镜像元数据作为兜底
        if not result and not self.use_mirror:
            try:
                saved = self.use_mirror
                self.use_mirror = True
                try:
                    result = self._from_maven_metadata()
                finally:
                    self.use_mirror = saved
            except Exception as e:  # noqa: BLE001
                errors.append(f"镜像 maven-metadata(兜底): {e}")

        if not result:
            self._log(f"[ERROR] 获取 Forge 版本列表失败: {'; '.join(errors) or '未知错误'}")
            return []

        result.sort(key=lambda x: self._sort_key(x["version"]), reverse=True)
        self._log(f"找到 {len(result)} 个可用的 Forge 版本")
        return result

    def _from_maven_metadata(self) -> List[Dict[str, Any]]:
        url = f"{self.FORGE_MIRROR_URL}/{self.METADATA_PATH}"
        text = fetch_text(url, use_mirror=False)
        root = ET.fromstring(text)

        prefix = f"{self.mc_version}-"
        major_prefix = f"{self._mc_major(self.mc_version)}-"
        found: Dict[str, str] = {}

        for elem in root.findall(".//versioning/versions/version"):
            full = (elem.text or "").strip()
            if not full:
                continue
            # 完整 MC 版本优先
            if full.startswith(prefix):
                forge_ver = full[len(prefix):]
                found.setdefault(forge_ver, self.mc_version)
            elif "." not in self.mc_version.split("-")[0] and full.startswith(major_prefix):
                forge_ver = full[len(major_prefix):]
                found.setdefault(forge_ver, self._mc_major(self.mc_version))

        # 对于 1.x（例如 1.20），maven 中的 key 是 1.20-xx 还是 1.20.x-xx？二者都需要匹配
        # 同时，如果 MC 版本带补丁号（1.20.1），而 maven 中只有 1.20-xx 的条目，也应当一并列出
        if "." in self.mc_version:
            for elem in root.findall(".//versioning/versions/version"):
                full = (elem.text or "").strip()
                if full.startswith(major_prefix) and full not in prefix:
                    forge_ver = full[len(major_prefix):]
                    found.setdefault(forge_ver, self.mc_version)

        versions = []
        for forge_ver, mc in found.items():
            versions.append({
                "version": forge_ver,
                "full_version": f"{mc}-{forge_ver}",
                "branch": "release",
                "mc_version": mc,
                "installer_url": self._build_installer_url(forge_ver, mc),
                "universal_url": self._build_universal_url(forge_ver, mc),
            })
        return versions

    def _from_promotions(self) -> List[Dict[str, Any]]:
        promotions = fetch_json(self.PROMOTIONS_URL, use_mirror=False, timeout=10)
        promos = promotions.get("promos", {})
        versions = []
        mc_major = self._mc_major(self.mc_version)

        for key, forge_ver in promos.items():
            matched_mc = None
            if key.startswith(f"{self.mc_version}-"):
                matched_mc = self.mc_version
            elif key.startswith(f"{mc_major}-"):
                matched_mc = mc_major
            if matched_mc is None:
                continue
            branch = key.rsplit("-", 1)[-1]
            versions.append({
                "version": forge_ver,
                "full_version": f"{matched_mc}-{forge_ver}",
                "branch": branch,
                "mc_version": matched_mc,
                "installer_url": self._build_installer_url(forge_ver, matched_mc),
                "universal_url": self._build_universal_url(forge_ver, matched_mc),
            })
        return versions

    # ------------------------------------------------------------------ URL

    def _coords(self, forge_version: str, mc_version: Optional[str] = None) -> str:
        mc = mc_version or self.mc_version
        return f"{mc}-{forge_version}"

    def _build_installer_url(self, forge_version: str, mc_version: Optional[str] = None) -> str:
        coords = self._coords(forge_version, mc_version)
        return f"{self._maven_base}/{self.FORGE_PATH}/{coords}/forge-{coords}-installer.jar"

    def _build_universal_url(self, forge_version: str, mc_version: Optional[str] = None) -> str:
        coords = self._coords(forge_version, mc_version)
        return f"{self._maven_base}/{self.FORGE_PATH}/{coords}/forge-{coords}-universal.jar"

    def get_installer_url(self, loader_version: str) -> str:
        return self._build_installer_url(loader_version)

    # ------------------------------------------------------------------ 安装

    def install_loader(self, loader_version: str) -> bool:
        """下载 Forge 安装器 → 解析版本 JSON → 下载依赖库。"""
        try:
            self._log(f"===== 开始安装 Forge {self.mc_version}-{loader_version} =====")
            self._log("镜像源：BMCLAPI" if self.use_mirror else "镜像源：Forge 官方 Maven")

            version_id = f"{self.mc_version}-forge-{loader_version}"
            version_dir = self.mc_dir / "versions" / version_id
            version_dir.mkdir(parents=True, exist_ok=True)

            # 1) 安装器 JAR
            jar_path = version_dir / f"forge-{loader_version}-installer.jar"
            self._log(f"下载 Forge 安装器: {jar_path.name}")
            download_file(
                self.get_installer_url(loader_version), jar_path, None,
                progress_tracker=self._progress_tracker,
                session=self._get_session(),
                use_mirror=False,
            )
            self._log(f"[OK] {jar_path.name}")

            if self.cancelled:
                return False

            # 2) 解析版本 JSON
            version_data = self._parse_version_json(jar_path, loader_version) \
                or self._fallback_version_json(loader_version)
            self._version_data = version_data

            target = version_dir / f"{version_id}.json"
            target.write_text(json.dumps(version_data, indent=2, ensure_ascii=False), encoding="utf-8")
            self._log(f"版本详情已保存: {target}")

            if self.cancelled:
                return False

            # 3) 安装器内自带的 maven 构件（universal / shim 等）
            self._extract_bundled_artifacts(jar_path)

            # 4) 安装器处理器所需的映射文件
            self._download_processor_artifacts(jar_path)

            # 5) 依赖库
            self._download_libraries(version_data.get("libraries", []), "Forge 依赖库")

            # 6) universal jar（旧版 Forge 必需）
            uni_url = self._build_universal_url(loader_version)
            uni_path = (self.mc_dir / "libraries" / self.FORGE_PATH
                        / self._coords(loader_version)
                        / f"forge-{self._coords(loader_version)}-universal.jar")
            if self._should_fetch_universal(version_data):
                self._execute_download_tasks([{
                    "url": uni_url,
                    "path": uni_path,
                    "sha1": None,
                    "size": 0,
                }], "Forge universal")

            # 6) 客户端 Jar
            client = (version_data.get("downloads") or {}).get("client")
            if client:
                self._execute_download_tasks([{
                    "url": client["url"],
                    "path": version_dir / f"{version_id}.jar",
                    "sha1": client.get("sha1"),
                    "size": client.get("size", 0),
                }], "Forge 客户端 Jar")

            # 7) 可选：运行 Java 安装器，补全数据处理器产物
            if self.run_java_installer:
                self._run_patcher(jar_path, loader_version)
            else:
                self._log("未启用「运行安装器补全」，跳过数据处理器产物生成。")
                self._log("如需可启动的 Forge，请在设置中开启该选项（需要 Java）。")

            self._log(f"===== Forge {self.mc_version}-{loader_version} 安装完成！ =====")
            return True

        except Exception as e:  # noqa: BLE001
            self._log(f"[ERROR] Forge 安装失败: {e}")
            return False

    # ---------------------------------------------------------- 数据处理器

    def _patcher_products(self, loader_version: str) -> List[Path]:
        """Forge 数据处理器应生成的关键文件。"""
        coords = self._coords(loader_version)
        libs = self.mc_dir / "libraries"
        products = [
            libs / self.FORGE_PATH / coords / f"forge-{coords}-client.jar",
        ]
        # 1.13+ 还会生成拆分后的客户端 jar
        mcp_version = self._mcp_version()
        if mcp_version:
            base = libs / "net" / "minecraft" / "client" / mcp_version
            products.extend([
                base / f"client-{mcp_version}-srg.jar",
                base / f"client-{mcp_version}-extra.jar",
            ])
        return products

    def _mcp_version(self) -> Optional[str]:
        """从版本 JSON 的 --fml.mcpVersion 参数推导 MCP 版本号（如 1.20.1-20230612.114412）。"""
        if not self._version_data:
            return None

        game_args = (self._version_data.get("arguments") or {}).get("game") or []
        for i, arg in enumerate(game_args):
            if arg == "--fml.mcpVersion" and i + 1 < len(game_args):
                return f"{self.mc_version}-{game_args[i + 1]}"
        return None

    def _run_patcher(self, installer_jar: Path, loader_version: str) -> bool:
        """运行安装器补全数据处理器产物，并校验结果。"""
        self._log("===== 运行安装器补全（生成 srg / extra / client 补丁）=====")

        before = {p: p.exists() for p in self._patcher_products(loader_version)}
        ok = self._run_installer_java(installer_jar)

        products = self._patcher_products(loader_version)
        produced = [p for p in products if p.exists() and not before.get(p, False)]

        if ok and all(p.exists() for p in products):
            self._log(f"补全完成，生成 {len(produced)} 个新文件")
            for p in products:
                self._log(f"  [OK] {p.name}")
            return True

        missing = [p for p in products if not p.exists()]
        if missing:
            self._log("[WARN] 以下文件仍未生成：")
            for p in missing:
                self._log(f"  [缺少] {p}")
            self._log("提示：可尝试换用 JDK 17/21，或手动运行安装器。")
        return False

    def _extract_bundled_artifacts(self, jar_path: Path) -> int:
        """
        解压安装器内 bundled 的 maven 构件到 libraries/。

        Forge 1.13+ 安装器会把 forge-universal / forge-shim 等构件
        直接打包在 maven/ 目录下，不需要额外下载。
        """
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

    def _download_processor_artifacts(self, jar_path: Path) -> bool:
        """
        下载安装器处理器需要读取的映射文件与工具。

        - mcp_config / installertools / jarsplitter 等：Forge maven（镜像优先）
        - net/minecraft:client:*:mappings：Mojang 官方 piston-meta

        这些文件不出现在 version.json 里，只有数据处理器需要。
        缺失时跳过并记录，不影响游戏本体运行；但 PCL/HMCL 补装 Forge
        时会用到它们。
        """
        profile = extract_install_profile(jar_path)
        if not profile:
            return True

        items = iter_processor_artifacts(profile)
        missing = [
            (rel, source) for rel, source in items
            if not (self.mc_dir / "libraries" / rel).exists()
        ]
        if not missing:
            return True

        self._log(f"下载安装器所需文件（{len(missing)} 个）…")

        # maven.creeperhost.net 是 Forge 官方安装器使用的 CDN，
        # 同一文件的可用性通常优于 BMCLAPI 的 maven 镜像节点。
        maven_bases = [
            "https://maven.creeperhost.net",
            self.FORGE_MIRROR_URL,
            "https://maven.minecraftforge.net",
        ]
        mojmap_base = "https://piston-meta.mojang.com/v1/packages"

        fetched = 0
        for rel, source in missing:
            if self.cancelled:
                return False

            if source == "mojmap":
                # piston-meta 的包路径以 MC 版本索引
                urls = [f"{mojmap_base}/{self.mc_version}/client.txt"]
            else:
                urls = [f"{base}/{rel}" for base in maven_bases]

            for url in urls:
                try:
                    resp = requests.get(url, headers=HEADERS,
                                        timeout=(CONNECT_TIMEOUT, READ_TIMEOUT), proxies=PROXIES)
                    if resp.status_code != 200 or not resp.content:
                        continue
                    target = self.mc_dir / "libraries" / rel
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(resp.content)
                    fetched += 1
                    break
                except Exception:  # noqa: BLE001
                    continue

        self._log(f"安装器所需文件已下载 {fetched}/{len(missing)} 个")
        if fetched < len(missing):
            self._log("[WARN] 部分安装器文件缺失（不影响启动，但启动器补装时可能需要）")
        return True

    def _parse_version_json(self, jar_path: Path, loader_version: str) -> Optional[dict]:
        """从安装器 JAR 解析版本 JSON。"""
        version_id = f"{self.mc_version}-forge-{loader_version}"
        data = extract_version_json(jar_path, version_id, self.mc_version)
        if data is None:
            self._log("[WARN] 安装器内未找到版本清单，回退到手工拼装")
            return None

        data.setdefault("id", version_id)
        data.setdefault("inheritsFrom", self.mc_version)
        return data

    def _fallback_version_json(self, loader_version: str) -> dict:
        """手工拼装（无法解析安装器时使用）。"""
        coords = self._coords(loader_version)
        return {
            "id": f"{self.mc_version}-forge-{loader_version}",
            "inheritsFrom": self.mc_version,
            "mainClass": "net.minecraft.launchwrapper.Launch",
            "libraries": [
                {
                    "name": f"net.minecraftforge:forge:{coords}",
                    "downloads": {"artifact": {
                        "path": f"{self.FORGE_PATH}/{coords}/forge-{coords}-universal.jar",
                        "url": self._build_universal_url(loader_version),
                    }},
                }
            ],
        }

    @staticmethod
    def _should_fetch_universal(version_data: dict) -> bool:
        """旧版 Forge（< 1.13）需要 universal jar。"""
        mc = str(version_data.get("inheritsFrom") or "")
        try:
            parts = [int(x) for x in mc.split(".")[:2]]
            return len(parts) == 2 and parts[0] == 1 and parts[1] <= 12
        except ValueError:
            return False
