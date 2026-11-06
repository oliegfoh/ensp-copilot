# 项目故事与对外文案

> README 是给访客看的产品页；这份是**讲述**：项目怎么来的、为什么长这样、以及可以直接复制出去用的介绍文案。
> 后续所有对外介绍、仓库描述、演示讲稿，以本文为准。

## 一、起点：一次真实的 7 台设备实验

2026-11-05，一台装了 eNSP V1.3.00.100 的 Windows 机器，一个 7 台路由器的综合实验：双 AS、OSPF 双域、IS-IS 办事处、A/B 双业务流、两条 EBGP 出口。

最初的诉求很朴素：「你能不能直接帮我操作 eNSP？」调研后发现 eNSP 没有开放 API，GUI 自动化靠坐标和焦点，脆弱且要求用户全程不动鼠标。于是转向两条更可靠的路：SSH（要先给每台设备配管理 IP、Cloud、路由，鸡生蛋）和 **Console over TCP**（`.topo` 里直接写着 `com_port`，实测 `127.0.0.1:2000+` 是裸 TCP 字符流，7/7 直连成功，零依赖、零 IP 规划）。

后者成了整个项目的地基。这一步的意义是：**设备接入其实不难，难的是接入之后怎么让人放心。**

实验一共做了五轮：接口与 LoopBack 编址 → OSPF 分域 → 链路 cost → IS-IS → IBGP/EBGP 全连接，最后 7 台 `save`。`plans/` 里那 5 份 JSON、`fixtures/` 里那些回显，都是当时的真实产物，不是编出来的示例。

## 二、五个翻车现场，变成五条设计原则

| 现场 | 当时发生了什么 | 固化成什么 |
|---|---|---|
| `com_port` 不按设备编号 | R2=2000 但 R1=2006，靠猜必然连错台 | 一律从 `.topo` 解析；且**自检以真实端口扫描为准**，不盲信文件 |
| 视图跨连接保留 | 上轮连接停在 system-view，下轮首条 `system-view` 报 `Unrecognized command` | 每次连接后 `to_user_view()` 规整视图 |
| `save` 的 `[Y/N]` | 通用 `send()` 多发一个回车，设备报「Please choose 'YES' or 'NO' first」，7 台全没保存成 | 交互式 `save` 单独写字节级交互处理器，不走通用下发 |
| **等价路由续行误判** | VRP 把第二条等价路由印成不重复目的地址的续行；正则要求行首是 IP，全部漏掉，误报「无等价」，还据此给出了「属预防性设计」的错误结论 | 判定等价优先用官方计数 `Routes > Destinations`；**关键结论必须两种独立方法交叉验证**；解析器显式处理 continuation |
| Console 单会话被抢占 | 用户只要双击开一个 CLI 窗口，Agent 就进不去 | `SessionManager` 唯一持有 socket，实时窗口只能订阅、绝不能自己 `connect()` |

第四个最值钱。它不是「工具报错」，而是**工具给了一个看起来很像对的错误结论**。用户拿截图质疑后复查，才发现问题，还顺带发现第一次 cost 只改了两台、另外两台仍留着等价路由。

这件事直接决定了项目定位：**验证层比下发层值钱**。能把命令敲进设备不稀奇，能可靠地判断「配完到底对不对」才是难点。所以架构里 `safety.py`、`env.py`、fixtures golden test 的权重，高于 `console.py` 本身。

## 三、为什么坚持 plan → dry-run → 确认

实验过程中用户改过三次主意：设备名要改回实验原始命名、`save` 留到自己来、R7 的 LoopBack0 先别配；后来又改主意要全部保存。

如果 Agent 是「收到一句话就直接敲」，这些变更会变成一串难以追溯的叠加操作。改成 plan JSON 之后：

- 每轮配置是**一份可 review、可 diff、可回放的文件**
- 用户中途改主意，改 plan 重放即可，不用猜「现在设备上到底是什么状态」
- 出问题能拿基线 `display current-configuration` 做 diff，而不是靠记忆

LLM 在这个架构里**只负责产出 plan JSON，绝不直连设备**。甚至 MVP 完全不接 LLM——外部 Agent（Claude / Cursor / WorkBuddy）写好 plan，工具负责安全地执行它。这不是技术保守，是把「可能出错的推理」和「一定生效的动作」隔开。

## 四、为什么零依赖

clone 下来 `python -m ensp_copilot.server` 就能跑，是刻意选的：

- Console 是裸 TCP 字符流，标准库 `socket` 足够，不需要 paramiko / telnetlib（Python 3.13 已移除后者）
- 实时推送只需要「后端 → 前端」单向流，SSE 用 stdlib `http.server` 就能做，不必上 WebSocket 库
- MVP 用 `<pre>` 而不是 `xterm.js`，因为要展示的是回显滚动，不是完整终端仿真

结果：33 个单测在没有 eNSP、没有网络、没有第三方包的机器上就能跑完。对一个教学向开源项目，「别人能一键跑起来」比「技术栈看起来先进」重要得多。

## 五、为什么 MCP 只做 adapter

调研发现 GitHub 上已有多个 eNSP MCP Server，`.topo` 解析、Console 批量下发、ping/display、看板都做过了。再做「又一个 MCP Server」没有意义。

而且 MCP 是 request/response 模型，**做实时字节流窗口反而更绕**——必须靠 tee 广播 + 推流，在 MCP 里转一圈没有好处。

所以核心是独立库 `ensp_copilot/`，MCP adapter 约 100 行挂在外面，随时可加、不进核心。别人现成的 Agent 想驱动，接上 adapter 就行；不接也能用网页。

## 六、对外文案速查（可直接复制）

### 一句话 · 中文

> 把 `.topo` 交给 Agent，在本地浏览器里实时看着它把 eNSP 设备配完——每条命令可预览、可审计、可回滚。

### One-liner · EN

> An auditable, local-first runner for Huawei eNSP labs: drop a `.topo`, start the devices, then watch every CLI command and device reply stream live in your browser.

### GitHub 仓库描述（≤350 字符，建议用这条）

```
Auditable, local-first runner for Huawei eNSP labs. Drop a .topo, start devices in eNSP, then watch every CLI command and device reply stream live in the browser (real console bytes, not a replay). Plan JSON -> dry-run -> confirm -> step-by-step display verification. Zero runtime dependencies, pure Python stdlib. Unofficial; eNSP/VRP not included.
```

### Topics 标签

```
ensp, huawei, vrp, network-simulation, network-automation, ospf, bgp, isis,
cli, console, python, local-first, sse, education, netlab
```

### 30 秒介绍

> eNSP 没有 API，让 AI 代配设备很容易做成黑盒：敲了什么、错在哪一步，用户都不知道。
> 这个项目反过来做——先用 JSON 把配置写成可审阅的计划，确认之后再逐条下发；后端唯一持有设备 Console 的那根 TCP 连接，把真实字节流同时广播给浏览器窗口和命令执行器，所以你看到的就是设备真实回显，不是日志回放。
> 每步用 `display` 回读验证，零第三方依赖，clone 下来一条命令就能跑。仓库里 5 份 plan 和全部回显，都来自一次真实的 7 台路由器、16 个 BGP 邻居的实验。

### 一分钟项目讲述（适合 README 首屏 / 分享开场）

> 起点是一次很具体的需求：「你能不能直接帮我操作 eNSP？」
> 查下来 eNSP 的 Console 其实是本地裸 TCP 端口，端口就写在 `.topo` 文件里——7 台设备全部直连成功，不用 SSH、不用配管理 IP、不用加 Cloud。接入这一层一下就通了。
> 但接着的一次翻车改变了整个项目方向：VRP 把等价路由的第二条印成不重复目的地址的续行，我的解析脚本全漏了，于是给出一个「当前没有等价路由、这步配置属于预防性设计」的错误结论。用户拿截图质疑，复查才发现不但判断错了，第一次改 cost 还漏了两台设备。
> 那一刻很清楚：**能把命令敲进设备不值钱，能可靠判断配完到底对不对才值钱。**
> 所以最终做出来的不是「AI 自动配网」，而是一个可审计的本地实验执行器：需求变成 plan，plan 先给人看，确认后才下发，下发时全程实时可见，每步回读验证。LLM 只写计划，永远不直接碰设备。
> 定位也据此调整：GitHub 上接入层的 MCP Server 已经不少了，我们做的是体验层——真实字节流窗口、按需求给拓扑候选、以及把踩过的坑固化成护栏和 golden test。

### 首屏演示脚本（录 GIF 用）

1. 打开 `http://127.0.0.1:8765`，展示候选卡片与 SVG 拓扑预览（形状=设备类型，实线=可 CLI 操作）
2. 点「自检」→ 端口扫描、逐台握手、指纹比对全绿
3. 选一份 plan → 逐条预览命令 → 点「执行」
4. 窗口里命令与设备回显同步滚动
5. 切到 eNSP 设备（同一台机器）`display current-configuration`，证明配置真实生效

## 七、诚实清单

对外介绍时不要越过这些线：

- 「按需求自动生成多个 `.topo` 候选」目前**只有渲染器和 1 份示例拓扑**，生成器未实现
- 「逐条执行 / 失败即停」已由 GUI 的 Plan 视图实现；**基线自动回滚**仍只有辅助函数，未接端到端流程
- 实时窗口当前是 `<pre>` + SSE，`xterm.js` 未接
- MCP adapter 未写
- 只支持 eNSP，不支持真机 / EVE-NG / GNS3 / HCL
- 不做云端服务，工具必须与 eNSP 同一台机器
