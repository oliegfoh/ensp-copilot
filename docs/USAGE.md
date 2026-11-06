# 从 0 到 1 使用 ensp-copilot

本文件是一份**操作手册**，面向第一次拿到这个工具的人。读完你能独立完成：
eNSP 起设备 → 启动后端 → 在浏览器里看实时回显 → 下发并验证配置 → 存档。

> 这不是沙盒。命令真实生效，配错会影响你的实验。**所有设备操作都必须经本工具下发，不要再去双击 eNSP 里的 CLI 窗口**（每台设备只允许一个 Console 连接，抢了会把工具踢掉）。

---

## 0. 它能做什么 / 不能做什么

- **能**：把你本机 eNSP 里已启动的路由器/交换机/防火墙/无线设备跑起来，Agent（或你）下发的每条命令、设备返回的每一个字节，都在浏览器里实时滚动。
- **不能**：不能操作 PC / Server / Cloud / HUB / FRSW 这类 `com_port=0` 的模拟设备（它们的配置只在 eNSP 对话框里）。不能连真机、EVE-NG、GNS3、HCL。

---

## 1. 前置条件

| 项 | 要求 |
|---|---|
| 系统 | Windows 本机已安装并运行 **eNSP**（本仓库**不分发** eNSP / VRP / 镜像，需自行合法持有） |
| 拓扑 | 在 eNSP 里用 `.topo` 打开，**全选设备 → 启动**，等 1–3 分钟，直到自检向导全绿 |
| 连接独占 | 启动后**不要双击任何设备的 CLI 窗口**（单会话，会抢占连接） |
| Python | 3.10+，且**零第三方依赖**（只用标准库） |
| 网络 | 只能本机 `127.0.0.1`，eNSP 与后端在同一台机器 |

---

## 2. 启动后端

```bash
git clone https://github.com/oliegfoh/ensp-copilot.git
cd ensp-copilot
python -m ensp_copilot.server --port 8765
# 然后浏览器打开 http://127.0.0.1:8765
```

- 可选参数：`--topo-dir <目录>` 指定识别 `.topo` 的目录（默认 `./topologies`）。
- 启动时会加载 `topologies/` 下的所有 `.topo`，打印 `loaded N topologies`，并提示需要 eNSP 在本机且设备已启动。
- 终端出现 `[upload]` / `[delete]` / `[http]` 等日志，说明服务在跑。

> 服务必须**常驻**。关掉终端 = 关掉服务 = 浏览器连不上。

---

## 3. 让工具认识你的拓扑（两种做法）

### 做法 A：只起设备，不传 .topo（最简）
工具连的是设备 Console 端口，不依赖 `.topo` 文件本身也能下发命令。但在 GUI 里**上传 .topo** 才会生成「设备清单」和「拓扑预览图」，所以推荐做法 B。

### 做法 B：在 GUI 上传 .topo（推荐）
1. 浏览器打开 `http://127.0.0.1:8765`，左侧「拓扑方案」卡片区。
2. 把 `.topo` 文件**拖进虚线框**，或点「选择文件」。
3. 前端会自动探测编码（eNSP 常导出 UTF-16，已处理），上传成功会提示：
   `已切换到 <name> · 识别 N 台设备`，左侧出现设备清单、中间出现 SVG 预览图。
4. 卡片右上角 `×` 可**删除**该拓扑（二次确认，同时删磁盘文件与内存），避免堆积。

> 上传的是文件副本，存到 `topologies/<name>.topo`。文件名会被规整为 `[A-Za-z0-9_-]`。

---

## 4. 看懂「设备清单」

清单里每台设备带一个徽标：

- **`CLI`（绿色）可操作**：Router / AR / NE / CE / S 系列、AC / AP、USG 防火墙 —— 有真实 `com_port`，可经 Console 下发命令。
- **`GUI`（灰色）不可操作**：PC / Server / Client / STA / Cellphone / MCS / Cloud / HUB / FRSW —— `com_port=0`，只能在 eNSP 图形界面里配。

设备名可直接点击改名——**仅本地显示名**，存在浏览器 `localStorage`，不上传、不影响设备。

---

## 5. 实时控制台（核心功能）

顶部只有两个标签：**「概览」**（拓扑 SVG + 可操作设备数）和**「实时控制台」**。

进入「实时控制台」：
- 上方一排标签 = 可操作的设备，点哪个就切到哪台的字节流。
- 下方大框是实时回显（等宽字体）。
- 底部输入框发命令，旁边两个勾选框决定权限：

| 命令类型 | 例子 | 需要勾选 |
|---|---|---|
| 只读 | `display ip interface brief`、`ping`、`tracert`、`return`、`?` | 都不用 |
| 写命令 | `system-view` 下的 `interface`/`ip address`/`ospf` 等 | **允许写命令** |
| 危险命令 | `save`、`undo …`、`reset`、`delete`、`reboot`、`format`、`startup saved-configuration` | **允许写命令** + **已确认危险命令** |

- 顶栏「**跟随**」勾选后，Agent 或其它客户端在操作某台设备时，页面会自动跳过去并切到实时控制台（可用 URL 参数 `?follow=0` 关闭）。
- 工具栏：清屏、自动滚动、暂停、字号。

> 若页面显示「无法连接服务」，先确认第 2 步的后端还活着。

---

## 6. 环境自检

左侧「环境自检」面板点「运行自检」：工具会做**端口扫描 + 逐台 CLI 握手 + 拓扑指纹比对**，逐项列出 ✓ / ✗。建议每次开始操作前跑一次，确认 7 台（或 N 台）都握手成功、且指纹和你想操作的是同一个方案。

---

## 7. 用命令行工具批量下发（tools/drive.py）

当你需要一次性给多台设备下发配置、或统一存档时，用脚本比手点快得多。

```bash
# 只读核查当前 IP 配置（默认查 test.topo 的 R1..R7）
python tools/drive.py verify_ip test

# 按 plan.json 下发配置
#   plan.json 格式： {"R1": ["system-view","ospf 1", ...], "R2": [...]}
#   写命令要加 --allow-write；含 undo/save 等危险命令要再加 --confirmed
python tools/drive.py run tools/plan_ospf.json --allow-write --topo test

# 把 running-config 存盘到所有设备（checkpoint，防断电丢失）
python tools/drive.py save_all test
```

**给想自己写脚本的人——后端 API 速查：**

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/topologies` | 已加载的拓扑列表 |
| GET | `/api/devices?topo=test` | 设备清单（含型号/com_port/是否可操作） |
| GET | `/api/render?topo=test` | 离线 SVG 预览（`&dark=1` 深色） |
| GET | `/api/status?topo=test` | 环境自检结果 |
| POST | `/api/command` | 下发一条命令，body：`{"topo","device","command","allow_write","confirmed","wait","source","client"}` |
| DELETE | `/api/topologies/<name>` | 删除某拓扑（名称限 `[A-Za-z0-9_-]`） |

> **重要坑（来自实战）：**
> 1. **每台设备会话的首条命令会被「吞字」**（只回显提示符，命令本身没生效）。`drive.py` 已对每个设备先发一次 `return` 暖场；你自己写脚本务必照做。
> 2. **VRP 的 `save` 是交互式 `[Y/N]`**。做法：先 `save`（`allow_write`+`confirmed`），再发一条 `Y`（仅 `allow_write`）作答。
> 3. **绝不要自己开 socket 连设备 Console** —— 后端已独占那根连接，只能经 `/api/command` 下发，否则会互相踢。
> 4. **多区域 OSPF 重配**：这个 eNSP 版本不认 `undo ospf 1`（用户视图报 Unrecognized）；正确姿势是在 `system-view` 下 `undo ospf 1` → 回答 `Y` 删掉整进程 → 再重建。直接叠 `network` 会导致新旧语句并存（脏状态）。

---

## 8. 安全与边界（必读）

- **必须本机运行**：连的是 `127.0.0.1:<com_port>`。
- **Console 无认证、无加密**：eNSP 实测监听在 `0.0.0.0:2000+`，同网段任何人都能连上你的设备。**不要在不可信网络使用，也不要把端口映射到公网**。
- **操作真实生效**：不是沙盒。改路由策略有把自己锁在设备外的风险。
- **不 `save` 就断电即丢**：工具默认不替你保存，存盘需显式确认。
- **只支持 eNSP**：真机 / EVE-NG / GNS3 / HCL 不适用。
- **GUI 依赖 eNSP 主进程存活**，无 headless 模式，设备必须已启动。

---

## 9. 一个最小上手示例（7 台物流骨干网）

我们实际跑通过的三步，可以用作你的模板。拓扑 `test.topo` 是 7 台路由器 R1–R7、9 条 `/30` 链路。

**第 1 步 · 端口 IP + Loopback0**（每台，写命令）：
```
system-view
interface GigabitEthernet0/0/0
 ip address 10.0.1.1 30
interface LoopBack0
 ip address 10.0.0.1 32
return
```
下发：把上面每台命令写成一个 `plan_ip.json`（格式见第 7 节），然后 `python tools/drive.py run plan_ip.json --allow-write --topo test`
（仓库里已有的 `tools/plan_ospf.json`、`tools/plan_ospf_multi.json` 也可直接 `run` 作为参考）

**第 2 步 · 单区域 OSPF 互通**（每台）：
```
system-view
ospf 1 router-id 10.0.0.1
 area 0.0.0.0
  network 10.0.0.1 0.0.0.0
  network 10.0.1.1 0.0.0.0
return
```
验证：`display ospf peer brief`（每台应 Full 邻接）、`display ip routing-table protocol ospf`、`ping -a 10.0.0.1 -c 1 10.0.0.7`（跨设备收到 Reply）。

**第 3 步 · 多区域改造**（area 0 省核心 R1–R3，area 1 市区域 R4–R6，area 2 远端 R7）：
用「精确主机掩码 `network <ip> 0.0.0.0`」把每个接口划入对应区域即可，VRP 会取最精确匹配。重配前务必先 `system-view` → `undo ospf 1` → `Y` 清空旧进程。

**每完成一步，记得存档**：`python tools/drive.py save_all test`

---

## 10. 主题与分享

- 顶栏可切换深浅色、选主色、自定义主色（存在浏览器 `localStorage`）。
- 主题可用 URL 参数分享：`http://127.0.0.1:8765?mode=dark&accent=%234f6bed`。
- 关闭自动跟随：`?follow=0`。

---

## 11. 测试（无需 eNSP）

```bash
python -m unittest discover -s tests -v
```
全部基于 `fixtures/`（真实设备回显），无需 eNSP、无需网络。
