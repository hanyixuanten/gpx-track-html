# GPX Track HTML — GPS 轨迹可视化工具

将 GPX 格式的 GPS 轨迹文件转换为交互式 HTML 地图，支持在高德卫星图和街道图之间切换，鼠标悬停查看实时路程、速度和时间信息。

## 功能特性

- 📍 **GPX 解析** — 支持解析标准 GPX 格式的 GPS 轨迹文件
- 🗺️ **双地图源** — 内置**高德卫星图**和**高德街道图**，右下角可自由切换
- 🧭 **坐标纠偏** — WGS-84 自动转换为 GCJ-02（火星坐标系），适配高德地图
- 🖱️ **悬停详情** — 鼠标悬停轨迹任意位置，实时显示路程、速度、时间和持续时间
- 🚩 **起止标记** — 绿色起点与红色终点标记
- 📊 **统计信息** — 左上角信息面板展示总距离、海拔、速度、时长等数据
- ⚡ **速度平滑** — 自动剔除 GPS 漂移数据，平滑速度曲线
- ⏱️ **暂停剔除** — 自动识别并剔除停留时间，准确计算运动时间
- 📦 **批量处理** — 自动扫描并处理目录下所有 GPX 文件

## 环境要求

- Python 3.7+
- 依赖库：`gpxpy`、`folium`

## 安装

```bash
git clone https://github.com/hanyixuanten/gpx-track-html.git
cd gpx-track-html
pip install gpxpy folium
```

## 使用方法

将 GPX 文件放在与脚本相同的目录下，然后运行：

特点：简单实现，使用 folium 原生 Tooltip 悬停。

### 输出

每个 GPX 文件生成对应的 `{文件名}_map.html`，用浏览器打开即可查看。

## 坐标说明

GPS 设备记录的是 **WGS-84** 坐标，高德地图使用 **GCJ-02**（火星坐标系）。脚本自动完成坐标转换，确保轨迹准确显示。

## 依赖

- [gpxpy](https://github.com/tkrajina/gpxpy) — GPX 文件解析
- [folium](https://python-visualization.github.io/folium/) — Leaflet.js 地图生成