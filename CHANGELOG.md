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

## 里程碑
- P3a GUI 升级：拖拽上传 `.topo` 自动识别设备 / 型号 / Console 端口、主题自定义、Agent 操作自动跟随设备、Plan 逐条执行 / 失败即停（`9980c71`）
- 修复上传无响应 + UTF-16 编码兼容（`5396c0e` → `4fd2c65`）
- 移除误导示例拓扑 + `parse_topo` UTF-16 加固（→ `ce9789f`）
- 真实 CLI 握手 + 指纹自检（`861631b`）
- `fixtures` / `preview.svg` 脱敏，移除站点专属信息（`f7fdabc`）
- 初始版本：核心库拆分 + 真实实验 `fixtures` 单测（`0dc3054`）
