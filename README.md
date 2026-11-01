# MC Downloader

### 前言：
由于这几天PCL和HMCL官宣停止下载功能，遂自己通过DeepSeek写了一个MC下载器。

**洁癖警告：此项目80%使用DeepSeek免费版制作，代码质量可以总结为 脏、乱、差，如有大佬，欢迎重构！**

---

### 有 Python 环境用户的使用方法：

1) 克隆此仓库到本地：
   ```bash
   git clone https://github.com/你的用户名/MC_downloader.git
   cd MC_downloader
   ```

2) 创建并激活虚拟环境（推荐）：
   ```bash
   python -m venv .venv
   # Windows:
   .venv\Scripts\activate
   # macOS/Linux:
   source .venv/bin/activate
   ```

3) 安装依赖：
   ```bash
   pip install PySide6 requests qdarktheme
   ```

4) 运行程序：
   ```bash
   python main.py
   ```

   > 界面全部由代码构建，无需再用 `pyside6-uic` 生成 `settings.py`。

---

### 无 Python 环境用户的使用方法：
（如果你后续用 PyInstaller 打包了 exe）
1) 前往 Releases 页面下载最新的 `main.exe`。
2) 双击运行即可。
*(注意：部分杀毒软件可能会误报 PyInstaller 打包的程序，请添加信任或自行从源码运行。)*

---

### 功能特性

*   **在线版本获取**：直接从 Mojang 或 BMCLAPI 拉取最新的版本清单，支持正式版和快照版，也可手动输入版本号。
*   **模组加载器安装**：支持 **Forge / Fabric / Quilt / NeoForge**，选择 MC 版本与加载器后自动拉取可用加载器版本，无需本地 Java。
*   **原版自动补齐**：安装加载器时若检测到原版缺失，会先自动下载原版文件再继续安装。
*   **BMCLAPI 镜像加速**：针对国内网络环境优化，默认开启 BMCLAPI 镜像源；镜像不可用时自动回退官方源。
*   **断点续传与校验**：下载前自动校验 SHA1，已存在的文件自动跳过，支持单文件失败重试。
*   **异步多线程下载**：基于 `QThread` 实现，下载过程不卡顿 UI；根据源自动限制并发数（官方源高并发，镜像源限流防封禁）。
*   **实时进度显示**：进度条显示百分比与已下载/总大小，节流更新避免事件堆积。
*   **安装器补全（可选）**：用 Java 执行 Forge/NeoForge 安装器，生成 `srg`/`extra`/`client` 补丁文件，装完即可启动。
*   **全局代理穿透**：强行禁用系统代理，防止国内部分代理软件将 BMCLAPI 请求劫持到失效节点（如 USTC 镜像）。
*   **配置持久化**：自动保存 `.minecraft` 路径、下载线程数、镜像源、默认加载器、Java 路径等设置到 `config.ini`。

---

### 项目结构说明

```text
MC_downloader/
├── main.py                          # 主窗口与业务组装
├── main.spec                        # PyInstaller 打包配置
├── config.ini                       # 自动生成的配置文件
└── mc_downloader/
    ├── config.py                    # 配置读写
    ├── core/
    │   ├── constants.py             # URL、超时、线程上限等常量
    │   ├── utils.py                 # 下载工具（重试 / SHA1 / 进度 / 镜像回退）
    │   └── java_env.py              # Java 探测（JAVA_HOME / PATH / 常见目录）
    ├── downloader/
    │   ├── vanilla.py               # 原版下载（核心文件 / 依赖库 / 资源）
    │   └── mod_loaders/
    │       ├── base.py              # 加载器基类（公共下载 / JSON / Java 安装器）
    │       ├── _json_utils.py       # 安装器结构与处理器构件推导
    │       ├── forge.py             # Forge：maven-metadata + 安装器解析
    │       ├── fabric.py            # Fabric：meta JSON
    │       ├── quilt.py             # Quilt：meta JSON
    │       └── neoforge.py          # NeoForge：按 MC 版本映射构建号
    └── ui/
        ├── workers.py               # QThread 工作线程（进度节流）
        └── settings_window.py       # 设置窗口
```

---

### 模组加载器说明

| 加载器 | 版本来源 | 安装方式 |
| --- | --- | --- |
| Forge | BMCLAPI `maven-metadata.xml`（回退官方 promotions） | 下载安装器 JAR，解析版本 JSON 并下载依赖；可选调用 Java 补全 |
| NeoForge | BMCLAPI `maven-metadata.xml` | 同上；版本号按 `MC次版本.补丁号` 映射（如 1.21.1 → 21.1.x） |
| Fabric | Fabric Meta（镜像 `fabric-meta`） | 直接获取 profile JSON 并下载依赖 |
| Quilt | Quilt Meta（镜像 `quilt-meta`） | 直接获取 profile JSON 并下载依赖 |

> NeoForge 1.20.1 官方并未提供构建，选择该组合时列表为空属正常现象。

#### 关于「运行安装器补全」

Forge / NeoForge 1.13 之后依赖**数据处理器**生成 `client-srg.jar`、`client-extra.jar`、
`forge-xxx-client.jar` 等文件。缺少这些文件，游戏会在启动时直接崩溃：

```
Invalid paths argument, contained no existing paths: [...-srg.jar, ...-extra.jar, ...-client.jar]
```

勾选设置里的 **「运行安装器补全（Forge / NeoForge）」** 后，程序会：

1. 自动探测 Java（配置路径 → `JAVA_HOME` → `PATH` → Zulu/Adoptium 等常见目录）
2. 必要时创建 `launcher_profiles.json`（官方安装器强制要求该文件）
3. 执行 `java -jar <installer>.jar --installClient <mc_dir>`
4. 实时把安装器输出转发到日志，执行完毕后校验三个补丁文件是否生成

> 补全默认开启。未安装 Java 时会记录警告并跳过，此时 Forge 仍不完整。

---

### 常见问题 (FAQ)

**1. 下载时大量报错 403 Forbidden 或连接拒绝？**
*   确保你的下载线程数不要设置过高。BMCLAPI 有 WAF 限制（单 IP 60 秒内最多 10 次短请求），程序已自动在镜像模式下限制最大 16 线程并加了请求延迟。
*   如果报错域名是 `mirrors.ustc.edu.cn` 等不属于 BMCLAPI 的域名，请检查你的系统代理/VPN 设置。程序已经默认穿透代理，但部分全局 TUN 模式的代理可能仍会劫持。

**2. 加载器版本列表为空？**
*   确认所选 MC 版本有效（先在主界面刷新版本列表）。
*   部分加载器并不支持所有 MC 版本（例如 NeoForge 不支持 1.20.1）。

**3. Forge 装完启动崩溃，提示 `contained no existing paths`？**
*   说明安装器补全没有执行。到「设置 → 模组加载器」勾选「运行安装器补全」，并确认能检测到 Java。
*   补全需要 JDK 17 或 21；Forge 1.20.1 推荐 JDK 17。

**4. 下载完之后怎么启动游戏？**
本工具只负责**下载游戏文件 / 安装模组加载器**。启动游戏需要 Java 环境与启动参数配置，暂未实现启动功能。可以将 `.minecraft` 指向 PCL/HMCL 等启动器来启动。

---

### 免责声明

*   本工具仅供学习 Python 和 PySide6 开发使用。
*   请勿将本工具用于商业用途。
*   游戏文件版权归 Mojang Studios 所有。使用本工具下载的文件请遵循 Minecraft 最终用户许可协议 (EULA)。
*   使用 BMCLAPI 服务时，请遵守其开源社区的相关规定。

---
**致谢**
*   [BMCLAPI](https://bmclapidoc.bangbang93.com/) 提供的镜像加速服务。
*   [DeepSeek](https://deepseek.com/) 提供的 AI 代码辅助。
*   以及所有在开发过程中提供建议和排错思路的朋友。
