# 更新日志

> 本项目不分发 eNSP / VRP / 任何设备镜像。所有条目基于真实提交与实测。

## 未发布（main 最新）

### 设备可操作性梳理
- 用一份真实 35 台设备拓扑验证：27 台可经 Console 操作，8 台不可。
  - **可操作**：Router / AR / NE / CE / S 系列交换机 / AC / AP / USG 防火墙——均暴露 `com_port` 且跑 VRP / WLAN / FW CLI。
  - **不可操作**：`com_port=0` 的模拟设备：PC / Server / Client / STA / Cellphone / Cloud / FRSW / HUB / MCS，配置只在 eNSP GUI 对话框，无对外控制台端口。
  - **已知缺口**：CX 系列虽分配了 `com_port`，但型号未被 `topo.MODEL_RULES` 识别，暂按不可操作；补一条规则即可纳入可操作。
- README 新增「支持哪些设备」矩阵，明确可 / 不可操作边界，以及「Cloud 桥接真实虚拟机」这一出路。
- 明确 **SSH 操作模式仍在规划中**：当前仅支持 Console over TCP，终端 / 服务器类设备尚无法被 Agent 直接操作。

### 拓扑方案可删除
- GUI 拓扑卡片新增删除按钮（悬停显示，点击需二次确认），调用 `DELETE /api/topologies/<name>`。
- 后端按名称白名单校验并删除对应 `.topo` 文件与内存缓存，防止上传文件堆积；路径穿越等非白名单名直接拒绝。
- 删除当前选中拓扑后自动清空概览 / 设备清单视图。

### 移除 Plan 执行功能
- 删除「Plan 执行」标签页及其全部 UI（计划下拉、逐条执行、停止、进度条、实时回显）。
- 后端移除 `GET/POST /api/plan(s)` 与 `_apply_plan`，删除 `plans/` 目录。
- 命令校验仍由 `safety.validate_plan` 对单条命令把关，单步执行能力不受影响。

### Console 输出捕获加固
- `session.collect` 原静默窗口固定 0.35s，导致输出呈突发、间隔 >0.35s 的命令（如默认 `ping` 包间隔 ~2s、`save` 等待 [Y/N]）回显被截断——只拿到首包 / 首行。
- 改为随 `wait` 自适应：`grace = max(0.4, min(wait*0.35, 2.5))`。短等待仍灵敏，长等待（ping / tracert / save）放宽到 2.5s 足以捕获每轮突发，又不会在死设备上挂死。
- 实测：`ping -a 10.0.0.1 10.0.0.7` 现可完整显示 5 包回复与统计行（`0.00% packet loss`）。

### 不再预存用户项目
- 不再把用户上传的 `.topo` 作为预置项在 GUI 启动时展示；现在打开 GUI 默认无拓扑，需自行拖入 `.topo` 才会出现。
- 概览页精简：去掉设备统计卡、指纹提示与操作引导条，仅保留 SVG 拓扑预览与可操作台数徽标。

## 里程碑
- P3a GUI 升级：拖拽上传 `.topo` 自动识别设备 / 型号 / Console 端口、主题自定义、Agent 操作自动跟随设备、Plan 逐条执行 / 失败即停（`9980c71`）
- 修复上传无响应 + UTF-16 编码兼容（`5396c0e` → `4fd2c65`）
- 移除误导示例拓扑 + `parse_topo` UTF-16 加固（→ `ce9789f`）
- 真实 CLI 握手 + 指纹自检（`861631b`）
- `fixtures` / `preview.svg` 脱敏，移除站点专属信息（`f7fdabc`）
- 初始版本：核心库拆分 + 真实实验 `fixtures` 单测（`0dc3054`）
