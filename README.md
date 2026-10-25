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

4) 如果你修改了 `settings.ui` 界面文件，需要重新生成 Python 代码：
   ```bash
   pyside6-uic settings.ui -o settings.py
   ```

5) 运行程序：
   ```bash
   python main.py
   ```

---

### 无 Python 环境用户的使用方法：
（如果你后续用 PyInstaller 打包了 exe）
1) 前往 Releases 页面下载最新的 `main.exe`。
2) 双击运行即可。
*(注意：部分杀毒软件可能会误报 PyInstaller 打包的程序，请添加信任或自行从源码运行。)*

---

### 功能特性

*   **在线版本获取**：直接从 Mojang 或 BMCLAPI 拉取最新的版本清单，支持正式版和快照版，也可手动输入版本号。
*   **BMCLAPI 镜像加速**：针对国内网络环境优化，默认开启 BMCLAPI 镜像源，下载速度大幅提升。
*   **断点续传与校验**：下载前自动校验 SHA1，已存在的文件自动跳过，支持单文件失败重试。
*   **异步多线程下载**：基于 `QThread` 实现，下载过程不卡顿 UI；根据源自动限制并发数（官方源高并发，镜像源限流防封禁）。
*   **全局代理穿透**：强行禁用系统代理，防止国内部分代理软件将 BMCLAPI 请求劫持到失效节点（如 USTC 镜像）。
*   **配置持久化**：自动保存 `.minecraft` 路径、下载线程数、镜像源等设置到 `config.ini`。

---

### 项目结构说明

```text
MC_downloader/
├── main.py            # 主入口，负责主界面和逻辑组装
├── downloader.py      # 核心下载模块，包含多线程下载、版本解析、进度回调
├── config.py          # 全局配置读写（config.ini）
├── settings_code.py   # 设置窗口业务逻辑（含注意事项弹窗联动）
├── settings.ui        # Qt Designer 设计文件
├── settings.py        # pyside6-uic 生成的 UI 代码（无需手动修改）
└── config.ini         # 自动生成的配置文件
```

---

### 常见问题 (FAQ)

**1. 运行后提示缺少 `settings` 模块？**
请确保你执行了 `pyside6-uic settings.ui -o settings.py`，或者直接使用仓库里提供的生成好的 `settings.py`。

**2. 下载时大量报错 403 Forbidden 或连接拒绝？**
*   确保你的下载线程数不要设置过高。BMCLAPI 有 WAF 限制（单 IP 60 秒内最多 10 次短请求），程序已自动在镜像模式下限制最大 16 线程并加了请求延迟。
*   如果报错域名是 `mirrors.ustc.edu.cn` 等不属于 BMCLAPI 的域名，请检查你的系统代理/VPN 设置。程序已经默认穿透代理，但部分全局 TUN 模式的代理可能仍会劫持。

**3. 下载完之后怎么启动游戏？**
目前这个下载器只负责**下载原版游戏文件**（核心 Jar、依赖库、Assets 资源）。启动游戏需要 Java 环境和启动参数配置，本工具暂未实现启动功能。你可以下载完成后，将 `.minecraft` 路径指向给 PCL/HMCL 等其他启动器来启动。

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
