# VRP / eNSP 实战踩坑清单

全部来自真实操作记录，见 `fixtures/`。这些是任何同类项目都会重踩的坑。

## 1. 等价路由的「续行」没有目的地址

`display ip routing-table protocol ospf`：

```
10.0.0.8/30  OSPF  10  2  D  10.0.0.2  GE0/0/0
             OSPF  10  2  D  10.0.0.6  GE0/0/1    ← 续行，无 IP 前缀
```

按「行首是 IP」解析会漏掉第二条，误报「无等价」。**判断等价优先看 `Destinations : X  Routes : Y`，Y > X 即存在等价**；或显式处理 continuation。

## 2. CLI 视图跨连接保留

eNSP 的 console 会话状态不会因断开而重置。上次停在 system-view，下次连上仍是 `[R1]`。此时首条 `system-view` 报 `Unrecognized command found at '^' position`。

解决：连接后 `to_user_view()` —— 读提示符，只有明确看到 `[...]` 才发 `quit`；在用户视图发 `quit` 会**断开连接**。

## 3. 长输出分页

先发 `screen-length 0 temporary`，否则 `display` 会停在 `---- More ----`。

## 4. `save` 是交互式命令

```
save → Are you sure to continue?[Y/N]: → y → 默认文件名 → successfully
```

通用 `send()` 会在每条命令前加 `\r\n`，在 `[Y/N]:` 提示时多送一个回车，触发
`Please choose 'YES' or 'NO' first before pressing 'Enter'`。必须用精确字节交互（`console.save_config()`）。

## 5. `com_port` 不按设备编号

实测 R2=2000、R3=2001、R4=2002、R5=2003、R6=2004、R7=2005、**R1=2006**。一律从 `.topo` 的 `com_port` 读，并做真实端口扫描确认。

## 6. 编码

`.topo` 声明 `encoding="UNICODE"`，实际是单字节文本 → 用 `utf-8, errors="replace"` 读。设备回显是 GBK → `gbk, errors="replace"` 解码。官方示例的 `vrpcfg.cfg` 也是 GBK 类编码。

## 7. 异步日志会插进回显

配置变更后设备可能推送 `DS/4/DATASYNC_CFGCHANGE:OID ...` 等日志，混在命令回显里。解析不能假设「每行都是表格数据」。

## 8. 配置保存位置

eNSP Router 的启动配置在设备虚拟 flash（`display startup` → `flash:/vrpcfg.zip`），宿主 `<GUID>/` 目录**不生成** `vrpcfg.zip`。官方示例拓扑自带的 `vrpcfg.zip` 是另一回事。以设备回显 + `display saved-configuration` 为准。

## 9. 单会话

双击 eNSP 的设备 CLI 窗口会占用 console，工具连接失败或互相踢掉。自检向导要明确提示。

## 10. 安全

eNSP_Client 把 console 监听在 `0.0.0.0:<port>`，无认证、无加密。同一网段任何人都可连设备。README 必须提示不要在不可信网络使用。
