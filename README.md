# OpenSandbox Viz

OpenSandbox 可视化管理面板 — Streamlit 单文件应用，支持 Windows exe 打包。

## 启动

**方式一：源码运行**
```bash
cd D:\projects\opensandbox-viz
uv run streamlit run app.py
```

**方式二：exe（内网离线可用）**
```bash
dist\opensandbox-viz.exe
# 首次解压 10-30s，访问 http://127.0.0.1:8501
```

## 功能

| 页面 | 入口 | 功能 |
|------|------|------|
| 📋 总览 | 侧栏 | 分页列表（←上一页/下一页→）、行内 🔍 详情、一键创建、**自动刷新（5s）** |
| 🔍 详情 | 列表按钮 | 状态/资源指标、暂停/恢复/续期/删除、代码执行、文件浏览、**进程管理（ps/kill）**、快照（创建/恢复）、原始数据、诊断日志 |
| ⚙️ 配置 | 侧栏 | API Base、API Key、useProxy 开关、恢复默认 |

创建沙箱支持：镜像、超时、CPU/内存、Entrypoint、**环境变量**（KEY=VAL 格式）、useProxy。

## 配置

通过 **⚙️ 配置页** 或环境变量设置：

- `OSB_API_BASE` — 生命周期 API 地址（默认 `http://localhost:8080/v1`）
- `OSB_API_KEY` — API Key（默认 `dev-api-key-change-in-production`）

## 打包

```bash
cd D:\projects\opensandbox-viz
uv add pyinstaller
uv run pyinstaller --onefile --name opensandbox-viz \
  --collect-all streamlit \
  --collect-all tornado \
  --collect-all watchdog \
  --hidden-import streamlit \
  --hidden-import streamlit.web.bootstrap \
  --hidden-import streamlit.runtime \
  --hidden-import streamlit.web.cli \
  --hidden-import httpx \
  --add-data "app.py:." \
  run.py
# 输出: dist\opensandbox-viz.exe
```

> macOS 需在 Mac 上运行相同命令，PyInstaller 不支持跨 OS 编译。
