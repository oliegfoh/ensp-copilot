# 架构

## 两层，不要混

| 层 | 协议 | 本项目 |
|---|---|---|
| 设备接入 | 裸 TCP → `127.0.0.1:<com_port>` | `console.py` + `session.py` |
| AI 集成 | MCP（可选） | P4 的薄 adapter，不进核心 |

MCP 是「AI 客户端 ↔ 工具」协议，与「程序如何连设备」无关。现有 eNSP MCP 项目底层同样是 Telnet/console 端口。

## 唯一会话 + tee

eNSP 对每台设备的 console **只允许一个 TCP 连接**。因此：

```
                ┌─ 浏览器 SSE（常驻订阅）
eNSP device ─── Session ─ Hub ─┼─ 命令执行器（临时订阅 + 写锁）
                └─ 日志/验证（常驻订阅）
```

`SessionManager` 是唯一持有 socket 的地方。`Hub.publish()` 把**同一份真实字节流**广播给所有订阅者。实时窗口绝不能自己 `connect()`，否则会把执行器踢掉。

`SessionManager(sink=...)` 另把每个会话的字节带设备名镜像到全局 `ACTIVE` Hub。`/events/active` 是单条 SSE：既发 `{"type":"bytes"}`（全部设备），也发 `{"type":"active"}`（当前操作的设备/命令/来源）。前端常驻订阅、按设备缓存，切设备只换显示不重连，因此 Agent 在任意设备上下发命令时窗口都不丢字节。

`write_lock` 保证同一设备一次只有一条命令在飞，避免回显串台。

## 请求路径

| 路径 | 作用 |
|---|---|
| `GET /api/topologies` | 列出 `topologies/*.topo` + 指纹 + 可操作设备数 |
| `GET /api/render?topo=` | 离线 SVG 缩略图 |
| `GET /api/status?topo=&fingerprint=` | 自检报告（端口扫描 + 指纹比对） |
| `GET /events?topo=&device=` | SSE 单设备字节流（兼容保留） |
| `GET /events/active` | SSE 全局流：全部设备字节 + 当前活动设备通知 |
| `GET /api/devices?topo=` | 设备清单（名称/型号/类别/端口/可操作性） |
| `POST /api/upload` | 上传 `.topo` 并自动识别设备 |
| `POST /api/command` | 单条命令（经 `safety.validate_plan`） |
| `POST /api/plan` | 应用 plan JSON |

## 为什么用 SSE 而不是 WebSocket

WebSocket 需要第三方库；SSE 是 stdlib `http.server` 就能做的单向流，而实时窗口只需要「后端 → 前端」的字节推送。写方向用普通 HTTP POST。零依赖，clone 即可运行。

## 跟随机制

`POST /api/command` 在执行前发一条 `active` 事件。GUI 发起的请求带 `client`（页面级随机 ID），外部 Agent 不带 —— 前端只对「非本页来源」强制切到实时控制台，避免 Plan 执行把自己跳走。`?follow=0` 或取消顶栏「跟随」可完全关闭。

## 设备可操作性

```
manageable = com_port > 0 AND category.has_cli
```

| 类别 | CLI | 说明 |
|---|---|---|
| router / switch / firewall / wireless | VRP | 可操作，语法略有差异 |
| pc | 简化命令 | 需单独适配命令集 |
| server / client | 无 | 服务配置是 GUI 对话框 |
| cloud / hub | 无 | 纯桥接 |

SVG 中**形状编码类别，描边编码可操作性**（实线=可 CLI，虚线灰显=GUI 专用）。

## 自检为什么不以 `.topo` 为准

`com_port` 由 eNSP 在打开/保存拓扑时分配，工具自己生成的 `.topo` 可能与实际不一致，且端口不按设备编号排序（实测 R1=2006、R2=2000）。`env.check()` 一律先做真实端口扫描，再逐台 CLI 握手；`fingerprint()`（设备名+型号集合的哈希）用于防止用户打开了另一个方案。
