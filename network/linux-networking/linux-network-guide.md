# Linux 网络实战指南 & Windows 对比

> 从 Docker 网络（veth/docker0/iptables）引申出的 Linux 网络知识。先理解原理，再动手实战。

---

## 一、Linux 网络的设计哲学

### 1.1 和文件系统一样：一切皆文件

回想之前学的 [文件系统核心概念](../../computer/file-system/file-system-basics.md)——Linux 的设计哲学是"一切皆文件"。

**网络也不例外。**

```bash
# 普通文件：open() → read() → close()
cat /home/user/notes.txt

# 网络连接：socket() → send()/recv() → close()
# 对于程序员来说，网络读写和文件读写是同一套接口！
```

```
open("/etc/nginx/nginx.conf")  →  返回 fd=3  →  read(3, buf, 4096)
socket(AF_INET, SOCK_STREAM)   →  返回 fd=4  →  read(4, buf, 4096)
                                        ↑
                            两者用同一套系统调用！这就是"一切皆文件"的力量
```

这个设计意味着：**网络连接、文件、管道、设备、socket，对程序来说都是"一个 fd（文件描述符）"**。你可以用 `select/poll/epoll` 同时监听网络事件和文件事件。

### 1.2 三个核心抽象层次

理解 Linux 网络，关键是理解内核中的三层抽象。**这三个层次分别回答不同的问题**：

| 层次 | 抽象 | 回答的问题 | 类比 |
|------|------|-----------|------|
| **协议层** | socket + TCP/IP 栈 | 数据按什么格式收发？丢了怎么办？ | 邮政系统（信封格式、挂号信/平信） |
| **路由层** | 路由表 | 数据走哪条路？下一站是谁？ | 邮件分拣中心（看邮编决定发往哪个城市） |
| **设备层** | 网卡 + 网桥 | 数据怎么从本机出去？物理上怎么传？ | 邮车和公路（把信实际搬过去） |

```
这三个层次在数据包的生命周期中依次起作用：

应用程序 send("hello")
        │
        ▼
┌── 协议层 ──────────────────────────────────────┐
│  1. socket：找到连接对应的 fd                   │
│  2. TCP 栈：加 TCP 头（序号、端口、校验和）       │
│  3. IP 栈：加 IP 头（源IP、目标IP、TTL）         │
└────────────────────────────────────────────────┘
        │ 完整的 IP 数据包
        ▼
┌── 路由层 ──────────────────────────────────────┐
│  4. 查路由表："目标 IP 属于哪个网段？"           │
│  5. 确定出口网卡（eth0）和下一跳网关              │
└────────────────────────────────────────────────┘
        │ 知道从哪个网卡出去
        ▼
┌── 设备层 ──────────────────────────────────────┐
│  6. 经过 netfilter 钩子（iptables 在此拦截）     │
│  7. 网卡驱动将数据转为电信号/光信号               │
│  8. 物理发送                                    │
└────────────────────────────────────────────────┘
```

### 1.3 netfilter —— 贯穿三层的"拦截器框架"

netfilter 是 Linux 内核中的**包过滤框架**，它在协议栈的五个关键位置插入了"钩子"：

| 钩子点 | 触发时机 | iptables 链 |
|--------|---------|------------|
| NF_IP_PRE_ROUTING | 数据包刚到达，路由之前 | PREROUTING |
| NF_IP_LOCAL_IN | 路由判断目标是本机 | INPUT |
| NF_IP_FORWARD | 路由判断目标是其他机器 | FORWARD |
| NF_IP_LOCAL_OUT | 本机进程发出的包 | OUTPUT |
| NF_IP_POST_ROUTING | 包即将离开，路由之后 | POSTROUTING |

**每个钩子点都可以注册回调函数**——iptables 就是挂在这些钩子上的规则集。Docker 的所有网络魔术（端口映射、跨主机通信、网络隔离）本质上都是**往这些钩子上加 iptables 规则**。

### 1.4 一张图总结：数据包的完整旅程

这是一张需要仔细看的图——理解它就理解了 Linux 网络的全部：

```
                         ┌─→ 本机进程（nginx, sshd）
                         │       ↑
                    INPUT│       │OUTPUT
                         │       │
外部网络 ──→ 网卡 ──→ PREROUTING ──→ (路由判断) ──→ FORWARD ──→ POSTROUTING ──→ 网卡 ──→ 外部网络
                                        │
                                        ↓
                                   转发到其他机器
                                   （路由器/网关场景）
```

```
数据包的"身份"在旅途中会变化：

阶段1: 刚到达                   阶段2: 路由判断后             阶段3: 离开前
  [原始IP头]                    [查路由表]                  [NAT改过的IP头]
  src: 8.8.8.8                 "目标是本机? → INPUT"        src: 172.17.0.2
  dst: 192.168.1.10            "目标是容器? → FORWARD"     dst: 192.168.1.10
```

### 1.5 Linux 网络子系统的完整架构图

```
                        ┌─────────────────┐
                        │   应用程序       │  Nginx, SSH, curl, Docker
                        │  (用户空间)      │
                        └────────┬────────┘
                                 │ socket API (socket/bind/listen/send/recv)
                        ┌────────┴────────┐
                        │   socket 层      │  struct sock (每个连接一个)
                        │   (内核空间)     │  文件描述符 → socket 的映射
                        └────────┬────────┘
                                 │
          ┌──────────────────────┼──────────────────────┐
          │                      │                      │
    ┌─────┴─────┐         ┌─────┴─────┐         ┌─────┴─────┐
    │ TCP 协议  │         │ UDP 协议  │         │ RAW 协议  │
    │ 可靠/流   │         │ 不可靠/报文│         │ 原始套接字 │
    │ 三次握手   │         │ 无连接    │         │ (ping等)  │
    │ 拥塞控制   │         │           │         │           │
    └─────┬─────┘         └─────┬─────┘         └─────┬─────┘
          │                      │                      │
          └──────────────────────┼──────────────────────┘
                                 │
                        ┌────────┴────────┐
                        │    IP 层         │  路由表 查下一跳
                        │   路由判断        │  转发开关 ip_forward
                        └────────┬────────┘
                                 │
          ┌──────────────────────┼──────────────────────┐
          │   netfilter 五钩子   │                      │
          │   PRE/FWD/IN/OUT/POST│                      │
          └──────────────────────┼──────────────────────┘
                                 │
                        ┌────────┴────────┐
                        │  网络设备抽象层  │  eth0, lo, docker0, veth, bond0
                        │  设备无关的操作   │  (一切设备统一接口)
                        └────────┬────────┘
                                 │
          ┌──────────────────────┼──────────────────────┐
          │                      │                      │
    ┌─────┴─────┐         ┌─────┴─────┐         ┌─────┴─────┐
    │ 以太网驱动 │         │ Wi-Fi 驱动 │        │ 虚拟设备    │
    │ (e1000等) │         │ (iwlwifi) │        │ veth/tun等 │
    └─────┬─────┘         └─────┬─────┘         └─────┬─────┘
          │                      │                      │
          └──────────────────────┼──────────────────────┘
                                 │
                        ┌────────┴────────┐
                        │    物理硬件       │  网卡芯片, DMA, 中断
                        └─────────────────┘
```

---

## 二、三层抽象详解

### 2.1 协议层：socket 到底是什么

socket 的本质是**内核中一个 struct，记录了一个网络连接的所有状态**：

```
struct sock (简化):
  ├── 本地 IP + 端口 (192.168.1.10:54321)
  ├── 远端 IP + 端口 (8.8.8.8:80)
  ├── 协议状态 (ESTABLISHED / LISTEN / CLOSE_WAIT ...)
  ├── 发送缓冲区 (还没发出去的数据)
  ├── 接收缓冲区 (收到了还没被 read() 取走的数据)
  └── 拥塞控制状态 (cwnd, ssthresh ...)
```

**同一个端口可以被多个 socket 使用**（只要远端 IP/端口不同），这就是 nginx 能同时处理几万个连接的原因——它只有 1 个 LISTEN socket (port 80)，但有几万个 ESTABLISHED socket，每个对应一个不同的客户端。

### 2.2 路由层：不是简单的"对号入座"

路由选择遵循 **最长前缀匹配** 原则——不是找"第一个匹配的"，而是找"最精确匹配的"：

```bash
ip route show
# default via 192.168.1.1 dev eth0         ← 0.0.0.0/0 (匹配所有，但优先级最低)
# 10.0.0.0/8 via 10.0.0.1 dev tun0        ← 匹配 10.x.x.x
# 172.17.0.0/16 dev docker0 proto kernel   ← 匹配 172.17.x.x
# 192.168.1.0/24 dev eth0 proto kernel     ← 匹配 192.168.1.x
```

```
数据包目标 172.17.0.3 查路由：

default       → 0.0.0.0/0   匹配 ✓ (32-0=32 位匹配)
10.0.0.0/8    → 不匹配 ✗
172.17.0.0/16 → 匹配 ✓ (32-16=16 位匹配)  ← 更精确！选这个
192.168.1.0/24→ 不匹配 ✗

最终选择 172.17.0.0/16 → 走 docker0 网桥
```

### 2.3 设备层：一切网络设备统一接口

Linux 内核把所有"能收发数据包的东西"都抽象为 **net_device**，有统一的 `ndo_start_xmit()`（发送）和收包回调：

| 设备 | 是真实的吗 | 用途 |
|------|-----------|------|
| eth0 | ✅ 物理网卡 | 连接外部网络 |
| lo | ❌ 虚拟 | 本机回环（127.0.0.1） |
| docker0 | ❌ 虚拟网桥 | Docker 容器间通信，类似软件交换机 |
| veth | ❌ 虚拟网线 | 成对出现，一头在容器一头在宿主机，像管道 |
| tun/tap | ❌ 虚拟隧道 | VPN (OpenVPN, WireGuard 依赖它) |
| bond0 | ✅ 多物理网卡聚合 | 提高带宽和可靠性 |

**为什么 Docker 能用 veth pair 实现隔离？** 因为内核不关心 net_device 是物理的还是虚拟的——只要它实现了收发包的接口，上层协议栈就可以在上面运行。Docker 利用了这一点：给每个容器创建一个虚拟的"网线"，protocol stack 完全不知道自己在虚拟设备上跑。

---

## 三、实战：`ip` 命令取代 `ifconfig`

> **原理回顾**：`ip` 命令操作的是 2.3 中讲的 **net_device 抽象层**——不管是物理网卡还是虚拟 veth，都用同一套命令管理。

**`ifconfig` 已废弃，一切用 `ip` 命令。**

### 3.1 查看网络接口

```bash
ip link show
# ip      → iproute2 工具集的主命令，取代 net-tools(ifconfig/route/arp)
# link    → 操作"链路层"(OSI 第2层)设备——跟 IP 无关，只看网卡本身
# show    → 列出所有网络接口(包括 DOWN 状态的)
#
# 字段含义：
#   1:              ← 接口索引号(内核内部编号)
#   lo:             ← 接口名称
#   <LOOPBACK,UP>   ← 接口标志: LOOPBACK=回环, UP=已启用, BROADCAST=支持广播
#   mtu 65536       ← 最大传输单元, 回环接口的 MTU 很大(不经过物理网络)
#   state UNKNOWN   ← 操作状态: UP=在运行, DOWN=已停用, UNKNOWN=无法判断(lo 特有)

# 查看 IP 地址（比 ip link 多了 IP 层信息）
ip addr show
# 输出示例中关键字段：
#   inet 192.168.1.10/24 brd 192.168.1.255 scope global eth0
#     inet → IPv4 地址
#     /24  → 子网掩码(等价于 255.255.255.0, 见 ip-subnetting 笔记)
#     brd  → 广播地址
#     scope global → 可被外部网络访问; host 则只有本机可用(如 127.0.0.1)

# 简写形式（最常用）
ip a
# 等同于 ip addr show，-4 只看 IPv4，-6 只看 IPv6

# 只看特定接口
ip addr show eth0
# 可以替换 eth0 为 docker0, lo, 或任何存在的接口名
```

### 3.2 启用/禁用网卡

```bash
# 禁用网卡 —— 网卡停止收发所有数据包，路由表中相关条目也会被删除
ip link set eth0 down
# ip link set → 修改链路层设备的属性
# eth0        → 目标接口名
# down        → 将接口状态设为"停用"

# 启用网卡 —— 恢复收发，会触发 DHCP 重新获取 IP（如果配置了 DHCP）
ip link set eth0 up
# 注意：如果是 SSH 连接的远程机器，不要 down 掉正在用的网卡——会断连！
```

### 3.3 配置 IP 地址

```bash
# 添加 IP —— 一个网卡可以同时拥有多个 IP 地址
ip addr add 192.168.1.100/24 dev eth0
# addr add       → 给接口添加一个 IP 地址(SIOCSIFADDR)
# 192.168.1.100  → 新分配的 IP
# /24            → 子网掩码, 和之前学的"子网掩码"笔记对应
# dev eth0       → 指定绑定到哪个接口
# 这种设置重启后丢失, 永久配置需要写 /etc/netplan/*.yaml

# 删除 IP
ip addr del 192.168.1.100/24 dev eth0
# 必须和 add 时的参数完全一致(IP + 前缀长度 + 设备名)

# 清空接口上所有 IP(慎用! 会断网)
ip addr flush dev eth0
# flush = 一次性删除该接口上的所有地址, 不区分主/次地址
```

### 3.4 实战：手动创建一对 veth，模拟 Docker 网络

Docker 创建的网络我们也能手动搭一个，理解本质：

```bash
# ═══════════════════════════════════════════════════════════
# 第1步：创建一对 veth（虚拟网线）
# ═══════════════════════════════════════════════════════════
ip link add veth0 type veth peer name veth1
#    link add          → 创建一个新的链路层设备
#    veth0             → 这一端的接口名
#    type veth         → 设备类型 = Virtual Ethernet(虚拟以太网)
#    peer name veth1   → 另一端的接口名
#
# 效果：veth0 和 veth1 像一根网线的两个头，
#       从 veth0 发出的包自动出现在 veth1 的接收队列里，反之亦然
#       类比：管道(pipe)——这头塞进去，那头掉出来

# ═══════════════════════════════════════════════════════════
# 第2步：创建两个 net namespace（模拟两个"容器"）
# ═══════════════════════════════════════════════════════════
ip netns add ns0
ip netns add ns1
#    netns add → 创建一个新的网络命名空间
#    每个 netns 拥有独立的：网卡列表、路由表、iptables 规则、
#                          网络连接(socket)列表
#    默认所有进程属于"根 netns"（宿主机），
#    新创建的 netns 只有 lo 网卡，而且 lo 是 DOWN 的

# ═══════════════════════════════════════════════════════════
# 第3步：把 veth 两头分别放进两个 namespace
# ═══════════════════════════════════════════════════════════
ip link set veth0 netns ns0
ip link set veth1 netns ns1
#    ip link set ... netns <ns> → 把接口从一个 netns 移到另一个
#    执行后，在宿主机上就看不到 veth0/veth1 了
#    它们在各自的 ns0/ns1 里变成了"本地网卡"

# ═══════════════════════════════════════════════════════════
# 第4步：给两个 veth 配 IP 并启用
# ═══════════════════════════════════════════════════════════
# 在 ns0 中操作
ip netns exec ns0 ip addr add 10.0.0.1/24 dev veth0
#    ip netns exec <ns> <cmd> → 在指定 namespace 中执行命令
#    注意：不加 ip netns exec 的命令都在"根 netns"中执行

ip netns exec ns0 ip link set veth0 up
#    必须手动启用！刚创建的 veth 默认是 DOWN

ip netns exec ns0 ip link set lo up
#    lo 必须启用！很多程序依赖 localhost 通信（比如 X11, DBus）

# 在 ns1 中操作（对称的）
ip netns exec ns1 ip addr add 10.0.0.2/24 dev veth1
ip netns exec ns1 ip link set veth1 up
ip netns exec ns1 ip link set lo up
#    10.0.0.1/24 和 10.0.0.2/24 在同一网段(10.0.0.0/24)，
#    这就是之前子网掩码笔记中的概念——同一网段可以直接通信，不需要路由

# ═══════════════════════════════════════════════════════════
# 第5步：测试连通性
# ═══════════════════════════════════════════════════════════
ip netns exec ns0 ping 10.0.0.2
# 输出：
# PING 10.0.0.2 (10.0.0.2) 56(84) bytes of data.
# 64 bytes from 10.0.0.2: icmp_seq=1 ttl=64 time=0.038 ms
#    ↑ 64 bytes      → 回包大小
#    ↑ icmp_seq=1    → 第1个 ICMP 包
#    ↑ ttl=64        → Time To Live, 每经过一个路由器减1, 64是初始值
#    ↑ time=0.038ms  → 往返时间(极快, 不经过物理网络)
# ✅ 通了！

# ═══════════════════════════════════════════════════════════
# 第6步：清理
# ═══════════════════════════════════════════════════════════
ip netns del ns0
ip netns del ns1
#    删除 netns 会自动删除其中的所有接口（veth 也会被回收）
```

---

## 四、路由表实战

> **原理回顾**：路由层是 Linux 网络栈三层抽象的第二层——"数据走哪条路"。路由选择遵循最长前缀匹配，和目标 IP 匹配得越精确的路由条目优先级越高。

### 4.1 查看路由表

```bash
ip route show
# ip route show → 查看主路由表(main table, id=254)
# 每个 net namespace 有独立的路由表

# 等价命令（旧式，net-tools 包）
route -n
# -n → 不解析域名(显示 IP 而不是主机名)，快很多

# 典型输出逐行解读：
# default via 192.168.1.1 dev eth0
#   default  → 0.0.0.0/0, 匹配所有目标(兜底规则, 优先级最低)
#   via 192.168.1.1 → 下一跳网关(家里的路由器)
#   dev eth0  → 从 eth0 网卡出去

# 172.17.0.0/16 dev docker0 proto kernel scope link src 172.17.0.1
#   proto kernel → 内核自动添加的路由(Docker 守护进程触发)
#   scope link   → 只在直连链路上有效(不需要下一跳)
#   src 172.17.0.1 → 从 docker0 发出时绑定的源 IP

# 192.168.1.0/24 dev eth0 proto kernel scope link src 192.168.1.10
#   本地直连网段: 目标在 192.168.1.x → 直接发, 不需要走网关
```

### 4.2 添加/删除路由

```bash
# 添加到某个网段的路由
ip route add 10.0.0.0/24 via 192.168.1.100 dev eth0
# ip route add → 添加一条路由条目
# 10.0.0.0/24  → 目标网络(去往这个网段的包匹配这条规则)
# via 192.168.1.100 → 下一跳地址(包交给谁)
# dev eth0     → 从哪个网卡出去

# 添加默认网关(等价于 default via)
ip route add default via 192.168.1.1
# default = 0.0.0.0/0, 所有其他规则都不匹配时走这条

# 删除某条路由
ip route del 10.0.0.0/24
# 只需要指定前缀, 不需要重复 via/dev

# 删除默认网关 —— 删了之后就访问不了外网, 只能访问直连网段
ip route del default
```

### 4.3 实战：让 namespace 能访问外网（一步步搭出 Docker 的网络）

Docker 就是自动做了这些步骤——我们现在手工重现：

```bash
# 接 3.4 的例子：ns0 现在只能和 ns1 通信, ping 8.8.8.8 不通
# 为什么不通？ns0 的路由表里:
#   ip netns exec ns0 ip route show
#   → 只有 10.0.0.0/24 dev veth0  ← 直连网段
#   → 没有 default 路由 → 不知道怎么去 8.8.8.8

# ═══════════════════════════════════════════════════════
# 第1步：创建网桥（模拟 Docker 的 docker0）
# ═══════════════════════════════════════════════════════
ip link add br0 type bridge
# type bridge → 虚拟网桥, 类似物理交换机: 多个端口, 学习MAC, 转发帧
ip link set br0 up
# 网桥自身也要启用才能工作

ip addr add 10.0.0.254/24 dev br0
# 给网桥分配 IP, 作为 ns0 的默认网关
# .254 是常见的网关后缀(.1 留给主路由, .254 留给桥)

# ═══════════════════════════════════════════════════════
# 第2步：创建 veth，一头插网桥，一头插 ns0
# ═══════════════════════════════════════════════════════
ip link add veth-br type veth peer name veth-ns
# veth-br → 插到网桥的那一头
# veth-ns → 送进 ns0 的那一头

ip link set veth-br master br0
# master br0 → 把这个接口"插"到 br0 网桥(像一个交换机端口)
# 以后 br0 收到的包会转发到 veth-br → veth-ns → ns0

ip link set veth-br up
# 网桥端口也要启用

ip link set veth-ns netns ns0
# 把 veth-ns 移到 ns0, ns0 现在多了一张网卡

ip netns exec ns0 ip addr add 10.0.0.10/24 dev veth-ns
ip netns exec ns0 ip link set veth-ns up
# ns0 用另一张网卡接入网桥, IP 是 10.0.0.10

# ═══════════════════════════════════════════════════════
# 第3步：在 ns0 添加默认路由
# ═══════════════════════════════════════════════════════
ip netns exec ns0 ip route add default via 10.0.0.254
# ns0: "去任何地方都经过 br0 (10.0.0.254)"
# 类比: 你家里的电脑默认网关是路由器的 192.168.1.1

# ═══════════════════════════════════════════════════════
# 第4步：宿主机开启 IP 转发 + NAT
# ═══════════════════════════════════════════════════════
echo 1 > /proc/sys/net/ipv4/ip_forward
# /proc/sys/net/ipv4/ip_forward:
#   0 → "我不是路由器, 不转发不是发给我的包"
#   1 → "我是路由器, 把不是发给我的包转发到目的地"
#   永久生效: sysctl -w net.ipv4.ip_forward=1

iptables -t nat -A POSTROUTING -s 10.0.0.0/24 -j MASQUERADE
# -t nat           → 操作 nat 表
# -A POSTROUTING   → 追加到 POSTROUTING 链(包即将离开网卡前)
# -s 10.0.0.0/24   → 源地址属于这个网段的包
# -j MASQUERADE    → 做 SNAT(源地址转换), 把私有IP替换成宿主机的IP
# MASQUERADE vs SNAT: MASQUERADE 自动检测出口IP(动态), SNAT 需要手动指定

# ═══════════════════════════════════════════════════════
# 第5步：测试
# ═══════════════════════════════════════════════════════
ip netns exec ns0 ping 8.8.8.8
# ns0 发出的包 → veth-ns → veth-br → br0 → 宿主机路由 → SNAT → eth0 → 外网
# ✅ 通了！
```

---

## 五、iptables / nftables 防火墙实战

> **原理回顾**：iptables 是 netfilter 框架的用户空间管理工具。netfilter 在协议栈的 5 个位置设置了钩子，iptables 在每个钩子上挂载规则链。Docker 的端口映射、网络隔离、容器出外网全都是靠往这些钩子上加 iptables 规则实现的。

### 5.1 iptables 五链四表

```
数据包在 netfilter 中的旅程：
  (网卡) → PREROUTING → (路由判断) ──┬──→ INPUT → 本地进程
                                     │
                                     └──→ FORWARD → POSTROUTING → (网卡)
                                              ↑
                                    本地进程 → OUTPUT ─┘

三个流向:
  入站:  PREROUTING → INPUT          (外网访问本机 nginx)
  转发:  PREROUTING → FORWARD → POSTROUTING  (路由器/NAT 网关)
  出站:  OUTPUT → POSTROUTING         (本机 curl 外网)
```

**四张表按优先级排列（越靠前越早执行）：**

| 优先级 | 表 | 用途 | Docker 如何使用 |
|--------|----|------|----------------|
| 1 | **raw** | 标记"不需要连接跟踪"的包 | 高性能场景跳过 conntrack |
| 2 | **mangle** | 修改包头（TTL/TOS/Mark） | 给容器的包打标记(不好管理) |
| 3 | **nat** | 修改源/目标地址 | **端口映射**(DNAT) + **出外网**(MASQUERADE/SNAT) |
| 4 | **filter** | 允许/拒绝/丢弃 | **容器间网络隔离**(FORWARD链 DROP) |

### 5.2 常用命令（每条指令逐行详解）

```bash
# ═══════════════════ 查看规则 ═══════════════════

iptables -L -n -v
# -L  → List, 列出所有链中的规则(默认 filter 表)
# -n  → Numeric, 显示 IP 而不是尝试反向 DNS 解析(否则会很慢)
# -v  → Verbose, 显示每个规则匹配到的包数(pkts)和字节数(bytes)
#
# 输出列含义:
#   pkts  → 有多少个包被这条规则匹配了(计数器)
#   bytes → 被匹配的数据总大小
#   target → 匹配后的动作(ACCEPT/DROP/REJECT/RETURN)
#   prot  → 协议(tcp/udp/icmp/all)
#   in/out → 进出网卡
#   source/destination → 源/目标 IP

iptables -t nat -L -n -v
# -t nat → Table= nat表, 查看地址转换规则
# Docker 创建的典型条目:
#   Chain POSTROUTING:
#     MASQUERADE  all -- 172.17.0.0/16  0.0.0.0/0
#     ↑ 源IP在172.17网段的包 → 自动SNAT为宿主机外网IP → 容器出外网的秘诀!
#   Chain DOCKER:
#     DNAT  tcp -- 0.0.0.0/0  0.0.0.0/0  tcp dpt:8080 to:172.17.0.2:80
#     ↑ 目标端口8080的包 → 改目标IP为172.17.0.2, 改端口为80 → 端口映射的秘诀!

iptables -L FORWARD -n -v
# 只查看 filter 表的 FORWARD 链(控制过路包, 容器间通信在此控制)

# ═══════════════════ 添加规则 ═══════════════════

iptables -A INPUT -s 192.168.1.100 -p tcp --dport 80 -j DROP
# -A INPUT    → Append, 追加到 INPUT 链末尾
# -s 192.168.1.100 → Source, 源 IP(封杀这个IP)
# -p tcp      → Protocol, 只匹配 TCP 协议
# --dport 80  → Destination Port, 目标端口 = 80(HTTP)
# -j DROP     → Jump, 匹配后执行的动作: 直接丢弃(不回复, 对方会超时)

iptables -A INPUT -s 10.0.0.0/24 -j ACCEPT
# -j ACCEPT   → 接受放行
# /24 网段 → 匹配 10.0.0.0~10.0.0.255 的所有 IP

iptables -t nat -A PREROUTING -p tcp --dport 8080 -j DNAT --to-destination 127.0.0.1:80
# -t nat            → 操作 nat 表
# -A PREROUTING     → 追加到 PREROUTING 链(包刚到达, 路由判断之前)
# -j DNAT           → Destination NAT, 修改目标地址
# --to-destination  → 把包的目标改为 127.0.0.1:80
# 效果: curl 宿主机:8080 → 实际访问 127.0.0.1:80 → 这就是"端口转发"的本质!

# ═══════════════════ 删除规则 ═══════════════════

iptables -L INPUT --line-numbers
# --line-numbers → 给每条规则显示编号
# 输出: num  target     prot opt source               destination
#        1   ACCEPT     all  --  10.0.0.0/24          anywhere

iptables -D INPUT 3
# -D INPUT 3 → Delete INPUT 链的第3条规则

# ═══════════════════ 保存规则(重启后保留) ═══════════════════

iptables-save > /etc/iptables/rules.v4    # Debian/Ubuntu
iptables-save > /etc/sysconfig/iptables   # CentOS/RHEL
# 直接 iptables 命令修改的规则只在内存中, 重启丢失!

# ═══════════════════ 清空规则(危险!) ═══════════════════

iptables -F          # Flush, 清空 filter 表所有规则! Docker 端口映射会失效!
iptables -t nat -F   # 清空 nat 表! 容器将不能访问外网!
# 恢复: systemctl restart docker → Docker 会自动重建所需的 iptables 规则
```

### 5.3 实战：不用 Docker 也能暴露内网服务

```bash
# 场景: nginx 只监听 127.0.0.1:80 (安全), 但办公室同事想通过 192.168.1.10:8080 访问

iptables -t nat -A PREROUTING -i eth0 -p tcp --dport 8080 \
  -j DNAT --to-destination 127.0.0.1:80
# -i eth0     → 只匹配从 eth0 进来的包(外网方向)
# -j DNAT     → 改目标地址为 127.0.0.1:80
# 问题: 内核默认拒绝对 127.0.0.0/8 的转发(安全机制)

echo 1 > /proc/sys/net/ipv4/conf/eth0/route_localnet
# route_localnet → 允许路由到 127.0.0.0/8(默认是禁止的)
```

### 5.4 故障排查：追踪包被哪条规则拦截

```bash
# 核心问题: "包到哪了? 被谁拦了?"

# 方法1: 看计数器, 定位命中的规则
iptables -L -n -v
# 关注 pkts 列, 找到 pkts 突然不增长的那条规则 → 就被它拦了

iptables -Z
# Zero, 所有规则计数器归零
# 然后重现问题, 再查 → 精准定位
# 用法: iptables -Z → 触发请求 → iptables -L -n -v → 看哪条 pkts>0

# 方法2: 在链的嫌疑位置插入 LOG 规则(类似代码里加 printf)
iptables -I INPUT -p tcp --dport 80 -j LOG --log-prefix "HTTP-IN: "
# -I INPUT     → Insert, 插入到 INPUT 链的最前面(不是追加!)
# -j LOG       → 不是丢弃! 只是记录, 然后继续匹配下一条规则
# --log-prefix "HTTP-IN: " → 在 /var/log/kern.log 里便于 grep
# 查看: tail -f /var/log/kern.log | grep "HTTP-IN"
```

---

## 六、抓包分析：tcpdump 实战

> **原理回顾**：tcpdump 利用 libpcap 库将网卡设为"混杂模式"，截获所有经过该网卡的数据包。当 iptables 计数器不足以定位问题时，抓包是最后的"照妖镜"。

### 6.1 基本用法

```bash
tcpdump -i eth0
# -i eth0 → 监听 eth0 网卡
# 不加任何过滤会输出巨量数据! 必须在生产环境慎用

tcpdump -i eth0 host 192.168.1.100
# host → 过滤某个 IP 的收发包(无论方向)
# 等价: src host ... (只看发), dst host ... (只看收)

tcpdump -i eth0 port 80
# port → 只要源端口或目标端口是 80 就抓
# port 80 → 同时匹配 src port 和 dst port

tcpdump -i eth0 net 172.17.0.0/16
# net + CIDR → 匹配某个网段的所有通信

tcpdump -i eth0 host 192.168.1.100 and port 80
# and → 逻辑与, or → 逻辑或, not → 逻辑非
# 支持括号分组: '(host A or host B) and port 80'

tcpdump -n -i eth0
# -n → 不把 IP 反向解析为域名(不用等 DNS, 快很多)

tcpdump -nn -vv -i eth0
# -nn → 不解析域名 AND 不解析端口名(显示 80 而不是 http)
# -vv → 非常详细(显示 TTL, checksum, TCP flags, window size 等)

tcpdump -i eth0 -w capture.pcap
# -w → 写入文件(二进制格式, 用 Wireshark 打开分析)
# .pcap 是通用格式, Wireshark/tcpdump 都能读
# -r capture.pcap → 从文件读回显示

tcpdump -c 100 -i eth0
# -c 100 → 抓够 100 个包就自动停止(防止失控)
```

### 6.2 输出格式逐字段解读

```bash
tcpdump -nn -i any port 8080
# 示例输出:
# 10:30:01.123456 IP 127.0.0.1.54321 > 127.0.0.1.8080: Flags [S], seq 123456789, win 65535, length 0
#
# 字段解读(从左到右):
# 10:30:01.123456 → 时间戳(时:分:秒.微秒)
# IP              → 网络层协议(IPv4)
# 127.0.0.1.54321 → 源 IP + 源端口
# >               → 方向
# 127.0.0.1.8080  → 目标 IP + 目标端口
# Flags [S]       → TCP 标志(见 6.3)
# seq 123456789   → TCP 序列号(初始随机值, 防止攻击)
# win 65535       → TCP 窗口大小(接收缓冲区剩余, 65535=64KB)
# length 0        → 载荷长度(SYN 包不带数据, 所以是 0)
```

### 6.3 TCP 标志位速查

```bash
# 只看握手和挥手包
tcpdump -nn -i eth0 'tcp[tcpflags] & (tcp-syn|tcp-fin) != 0'
# tcp[tcpflags] → 访问 TCP 头的第 13 个字节(标志位)
# & → 位运算(bitmask)
# tcp-syn → 第 1 位(SYN)
# tcp-fin → 第 0 位(FIN)

# 常见标志组合:
# Flags [S]      → SYN          "我要建连接"(第一次握手)
# Flags [S.]     → SYN+ACK      "收到, 我准备好了"(第二次握手)
# Flags [.]      → ACK          "已确认"(纯确认, 无数据)
# Flags [P.]     → PSH+ACK      "有数据, 请立即处理不要缓存"
# Flags [F.]     → FIN+ACK      "我没数据了, 准备关连接"
# Flags [R]      → RST          "拒绝! 端口没开/连接已关闭"
# Flags [R.]     → RST+ACK      "确认拒绝"
```

### 6.4 实战：排查"为什么容器端口不通"

```bash
# 场景: docker run -p 8080:80 后 curl localhost:8080 没反应

# 第1步: 在宿主机抓 8080 端口的包
tcpdump -nn -i any port 8080
# 另一终端 curl localhost:8080
# 预期看到:
#   IP 127.0.0.1.xxxxx > 127.0.0.1.8080: Flags [S] ...  ← curl 发 SYN
#   IP 127.0.0.1.8080 > 127.0.0.1.xxxxx: Flags [S.] ... ← 收到 SYN-ACK ✅
#   如果只看到 SYN 没有 SYN-ACK → 端口没被监听, 或 iptables DROP 了

# 第2步: 断点排除——在 docker0 抓包
tcpdump -nn -i docker0 port 80
# 如果 docker0 上有 SYN 进来 → iptables DNAT 规则正确
# 如果 docker0 上没有 → 问题在宿主机的 iptables PREROUTING

# 第3步: 在容器内部抓包(终极手段)
docker exec web tcpdump -nn -i eth0 port 80
# 如果容器内能看到 SYN → 容器收到了请求, 问题在应用层
# 如果容器内看不到 → 问题在宿主机的 nat 转发
```

---

## 七、网络问题排查手册

### 7.1 标准排查流程——自底向上，按 OSI 七层

排查网络问题要**自底向上**，先排除物理和链路层，再查 IP 层、传输层、应用层：

```
第1层(物理): 网线插了吗? 灯亮了吗?       → ip link show(看 <UP> 标志)
第2层(链路): 同网段通吗? ARP 能学到MAC?  → ping 同网段IP
第3层(IP):   IP 配了吗? 路由对吗?        → ip a; ip r
第4层(TCP):  端口监听了吗? 防火墙拦了吗?  → ss -tlnp; iptables -L -n -v
第5-7(应用): 程序在跑吗? DNS 能解析吗?    → systemctl status; dig
```

```bash
# 严格按这个顺序排查——每步都是预判"上一步可能没问题"
1. ping 127.0.0.1
   # 测试本机 TCP/IP 协议栈: lo 接口 + TCP/IP 驱动 + socket 层是否正常
   # 不通 → 网卡驱动坏了或内核模块没加载，极少见
   # 通   → 继续

2. ip link show
   # 看接口是否存在 + 状态是否为 UP
   # <BROADCAST,MULTICAST,UP> ← UP 表示已启用
   # state DOWN → sudo ip link set eth0 up

3. ip addr show
   # 确认 IP 地址已分配，前缀长度正确
   # inet 192.168.1.10/24 ← 有这个才配了 IP
   # 没有 → DHCP 没拿到, 检查 dhclient 或 NetworkManager

4. ping <同网段其他设备IP>
   # 测试 ARP + 二层连通
   # 通 → 二层正常; 不通 → 检查 ARP: ip neigh show

5. ip route show
   # 确认 default 路由指向正确的网关
   # default via 192.168.1.1 ← 必须存在
   # 没有 → ip route add default via 192.168.1.1

6. ping <网关IP>
   # ping 192.168.1.1(路由器)
   # 通 → IP 层和网关都正常
   # 不通 → 网关可能不响应 ping, 但试着 curl 外网

7. ping 8.8.8.8
   # 测试能否出公网(纯 IP, 不涉及 DNS)
   # 通 → 网络完全正常, 如果浏览器打不开网站是 DNS 的问题

8. dig google.com
   # 测试 DNS 解析
   # ;; status: NOERROR → DNS 正常
   # connection timed out; no servers could be reached → DNS 服务器不可达

9. iptables -L -n -v
   # 看防火墙是否拦截, pkts 列 >0 说明规则被命中

10. ss -tlnp | grep <端口>
    # 确认服务在监听: LISTEN 0.0.0.0:端口 → 正确; LISTEN 127.0.0.1:端口 → 仅本地

11. tcpdump -nn -i any port <端口>
    # 抓包看数据流到哪了, 精确到每个 TCP 标志位
```

### 7.2 常用诊断命令速查表

| 目的 | 命令 |
|------|------|
| 看IP | `ip a` |
| 看路由 | `ip r` 或 `route -n` |
| 看监听端口 | `ss -tlnp`（TCP 监听）/ `ss -ulnp`（UDP） |
| 看所有连接 | `ss -tanp`（包含已建立的） |
| 看网卡统计 | `ip -s link show eth0` |
| 看ARP表 | `ip neigh show` 或 `arp -n` |
| 看防火墙规则 | `iptables -L -n -v` |
| 看DNS | `cat /etc/resolv.conf` |
| DNS查询 | `dig google.com` 或 `nslookup google.com` |
| 延迟测试 | `ping -c 4 目标IP` |
| 路由追踪 | `traceroute 目标IP` 或 `mtr 目标IP`（实时） |
| 端口测试 | `nc -zv 目标IP 端口` 或 `telnet 目标IP 端口` |
| 带宽测试 | `iperf3 -c 目标IP`（需要服务端） |

### 7.3 四种经典故障场景（逐命令详解）

**场景一："端口起不来（Address already in use）"**

```bash
# 错误: bind: Address already in use → 端口被另一个进程占着

# 1. 谁占了我的端口？
ss -tlnp | grep :8080
# -t=TCP, -l=LISTEN, -n=数字端口, -p=显示进程名
# 输出字段逐列解读:
# LISTEN  0      128    0.0.0.0:8080  0.0.0.0:*   users:(("nginx",pid=1234,fd=6))
# ↑状态   ↑Recv-Q ↑Send-Q ↑本地地址:端口  ↑远端地址   ↑进程名=PID=文件描述符
# Recv-Q=0 → 没有积压的连接等待 accept()
# Send-Q=128 → 内核允许的最大等待队列长度(backlog)

# 2. 找所有占用该端口的进程
lsof -i :8080
# -i :8080 → 列出所有使用端口 8080 的进程
# 输出: nginx  1234  root  6u  IPv4  ... TCP *:8080 (LISTEN)

fuser 8080/tcp
# 更简洁: 只输出 PID, 适合脚本 `kill $(fuser 8080/tcp)`

# 3. 先优雅停止(SIGTERM), 再强制杀(SIGKILL)
kill 1234       # SIGTERM(15): 进程可以清理资源后退出
sleep 2
kill -9 1234    # SIGKILL(9): 内核直接杀, 进程无法拒绝, 但也无法清理资源
```

**场景二："能 ping 通但连不上端口"**

```bash
# 核心诊断: ping 通说明 IP 层正常, 问题一定在 TCP 层或以上

# 1. 服务真的在监听吗?
ss -tlnp | grep <端口号>
# 没有输出 → 进程没启动, 或监听了别的端口

# 2. 监听在哪个地址? 这是最容易被忽略的!
ss -tlnp
# LISTEN 127.0.0.1:3000   → 只绑定了 localhost! 外网永远连不上
# LISTEN 0.0.0.0:3000     → 绑定了所有网卡, 外网可以连 ✨
# LISTEN ::1:3000         → 只绑定 IPv6 localhost
# LISTEN *:3000           → IPv4+IPv6 双栈
# 修复: 改应用配置, 把 bind 地址从 127.0.0.1 改为 0.0.0.0

# 3. 防火墙拦了吗?(看计数器)
iptables -L INPUT -n -v | grep <端口号>
# 如果 DROP 规则的 pkts > 0 → 确认被拦截!
# 如果 pkts = 0 → 包没经过这条规则, 可能是链的顺序问题

# 4. nc 精准测试 TCP 层连通性(比 telnet 更纯粹)
nc -zv <目标IP> <端口>
# -z → Zero-I/O mode: 只建TCP连接然后立即关闭, 不传输数据
# -v → Verbose: 打印连接结果
# 返回结果解读:
#   Connection to X.X.X.X port [tcp/http] succeeded! → TCP能建连 ✅
#   Connection refused → 对方收到了SYN, 但回复了RST(端口没开或被REJECT)
#   Connection timed out → 对方没回任何东西(网络不通或被DROP)
# 关键区别: refused=对方明确拒绝, timeout=不知道是死是活
```

**场景三："DNS 解析不出来"**

```bash
# 症状: ping www.baidu.com → "Temporary failure in name resolution"
# 关键判断: 是 DNS 服务器不可达? 还是 DNS 配置错了?

# 1. 先确认网络通不通(排除 DNS 问题)
ping 8.8.8.8
# 通 → 网络正常, 是 DNS 的问题
# 不通 → 先解决网络连通性问题(回到 7.1 排查流程)

# 2. 看 DNS 配置
cat /etc/resolv.conf
# nameserver 8.8.8.8  → 指向 Google DNS
# nameserver 127.0.0.53 → 指向 systemd-resolved 的本地存根
# 如果指向 127.0.0.53, 需要检查 systemd-resolved 是否在运行

# 3. 绕过所有缓存, 直接查公共 DNS
dig @8.8.8.8 google.com
# dig 输出关键字段解析:
#   ;; ->>HEADER<<- opcode: QUERY, status: NOERROR
#     ↑ status: NOERROR=成功 SERVFAIL=DNS服务端出错 NXDOMAIN=域名不存在
#   ;; ANSWER SECTION:
#     google.com. 300 IN A 142.250.80.46
#     ↑ TTL=300秒  ↑A记录(IPv4地址)
#   ;; Query time: 50 msec
#     ↑ 超过100ms说明DNS慢; 超过1000ms用户体验很差
# 如果 dig @8.8.8.8 能解析但 ping 域名不行:
#   → 问题在本地 DNS 缓存(/etc/resolv.conf)或 nsswitch.conf

# 4. 排查 systemd-resolved(大量 Linux 发行版默认启用)
systemctl status systemd-resolved
# 如果 inactive/dead → 启动它: systemctl start systemd-resolved
resolvectl status
# 显示每个网卡的 DNS 配置(比 /etc/resolv.conf 更精确)
# systemd-resolved 在 127.0.0.53 监听, 做本地 DNS 缓存+转发
# 它如果挂了 → 所有 DNS 查询失败, 但 ping 8.8.8.8 正常!
```

**场景四："Docker 容器网络突然全挂了"**

```bash
# 症状: docker run -p 8080:80 正常启动, 但 curl localhost:8080 没反应
# 最可能的原因: iptables 规则被清掉了(防火墙脚本/其他工具干的)

# 1. 容器真的在跑? 端口映射正常?
docker ps
# STATUS 列必须是 Up, PORTS 列必须显示 0.0.0.0:8080->80/tcp
docker port <容器名>
# 80/tcp -> 0.0.0.0:8080  ← 如果为空, -p 没生效

# 2. iptables NAT 规则还在吗? (90% 的 Docker 网络故障出在这里!)
iptables -t nat -L DOCKER -n
# 预期应该看到 DNAT 规则(端口映射) 和 MASQUERADE 规则(SNAT)
# 如果 DOCKER 链完全为空 → 规则被清掉了!
# 解决方法: systemctl restart docker (Docker 会自动重建所有规则)

# 3. 内核 IP 转发开了吗?(容器出外网的必要条件)
cat /proc/sys/net/ipv4/ip_forward
# 输出:
#   0 → 内核不转发, 容器出不去外网 ← 这就是原因!
#   1 → 正常
# 临时修复: echo 1 > /proc/sys/net/ipv4/ip_forward
# 永久修复: sysctl net.ipv4.ip_forward=1 (写 /etc/sysctl.conf)

# 4. docker0 网桥还在吗?
ip link show docker0
# 应该看到: docker0: <BROADCAST,MULTICAST,UP> ...
# 如果不存在 → Docker daemon 没正常启动, systemctl status docker

# 5. docker-proxy 进程在吗?(处理 localhost 端口映射的用户态代理)
ps aux | grep docker-proxy
# docker-proxy 是 Docker 用来处理 127.0.0.1 端口映射的用户态代理
# 它如果 crash 了:
#   curl localhost:8080 → 可能不通
#   curl <宿主机LAN IP>:8080 → 可能正常(走 iptables 而不是 docker-proxy)
```

---

## 八、Linux vs Windows 网络对比

### 7.1 架构对比

| | Linux | Windows |
|--|-------|---------|
| **网络栈** | 内核内置，一切通过 netfilter | 内核 + Winsock + WFP（Windows Filtering Platform） |
| **防火墙** | iptables / nftables（命令行） | Windows Defender Firewall（GUI + netsh） |
| **配置方式** | `ip` + `ethtool` + 配置文件 | GUI + `netsh` + `PowerShell` |
| **抓包** | tcpdump / Wireshark | Wireshark / pktmon（自带） |
| **虚拟网络** | veth / bridge / macvlan / ipvlan | vSwitch（Hyper-V 虚拟交换机） |
| **命名空间** | NET namespace | 无直接等价物，Hyper-V 隔离近似 |
| **包过滤钩子** | netfilter 五链 | WFP 分层模型（更复杂） |
| **网卡配置文件** | `/etc/network/interfaces` 或 `/etc/netplan/*.yaml` | 注册表 + 网络连接面板 |
| **路由表** | `ip route` | `route print` 或 `Get-NetRoute` |

### 7.2 命令等价对照表

| 操作 | Linux | Windows |
|------|-------|---------|
| 看 IP | `ip a` | `ipconfig` / `Get-NetIPAddress` |
| 看路由表 | `ip r` / `route -n` | `route print` / `Get-NetRoute` |
| Ping | `ping -c 4` | `ping -n 4` |
| 路由追踪 | `traceroute` / `mtr` | `tracert` / `pathping` |
| DNS查询 | `dig` / `nslookup` | `nslookup` / `Resolve-DnsName` |
| 看监听端口 | `ss -tlnp` | `netstat -ano \| findstr LISTENING` |
| 看所有连接 | `ss -tanp` | `netstat -ano` / `Get-NetTCPConnection` |
| 抓包 | `tcpdump` | `pktmon` / Wireshark |
| 端口测试 | `nc -zv` | `Test-NetConnection -Port` |
| ARP 表 | `ip neigh` / `arp -n` | `arp -a` |
| 防火墙规则 | `iptables -L` | `netsh advfirewall firewall show rule name=all` |
| 网卡详情 | `ethtool eth0` | `Get-NetAdapterAdvancedProperties` |
| 网络重置 | `systemctl restart networking` | `netsh winsock reset` + 重启 |
| 刷新DNS | `systemd-resolve --flush-caches` | `ipconfig /flushdns` |

### 7.3 Windows 特有概念

| 概念 | 说明 |
|------|------|
| **WFP**（Windows Filtering Platform） | Windows 的包过滤框架，比 iptables 粒度更细，但更复杂 |
| **vSwitch** | Hyper-V 虚拟交换机，相当于 Linux bridge 的增强版（支持 VLAN、QoS、SDN） |
| **netsh** | 传统网络配置命令（逐步被 PowerShell 取代） |
| **WinNAT** | Windows 的 NAT 实现，Docker Desktop 在 Windows 上用这个 |
| **WSL2 网络** | WSL2 运行在轻量 VM 里，网络经过 NAT 转换，localhost 转发是自动的 |

### 7.4 为什么 Docker 在 Windows 上的网络更复杂

```
Linux 上的 Docker：                       Windows 上的 Docker：
┌──────────────┐                        ┌──────────────────────┐
│ 宿主机 Linux  │                        │ Windows 宿主机         │
│  ├── docker0 │                        │  ├── WinNAT           │
│  ├── iptables│                        │  ├── WFP 规则          │
│  └── 容器直连 │                        │  ├── Hyper-V VM (WSL2)│
└──────────────┘                        │  │   ├── Linux 内核     │
                                        │  │   ├── docker0      │
    内核原生支持，                         │  │   └── 容器         │
    零额外开销                             │  └──────────────────┘
                                        │
                                            多了一层 VM + NAT
                                            性能有损耗
```

---

## 九、TCP 连接状态速查

排查网络问题经常要看连接状态：

```bash
ss -tan state established
```

| 状态 | 含义 | 常见于 |
|------|------|--------|
| **LISTEN** | 等别人连我 | 服务端 nginx 在 80 端口 |
| **ESTABLISHED** | 正常通信中 | 客户端连上了服务端 |
| **SYN_SENT** | 我发出了 SYN，等对方回 | 客户端正在发起连接 |
| **SYN_RECV** | 收到了 SYN，回 SYN-ACK 了，等 ACK | 服务端半连接（SYN flood 攻击） |
| **TIME_WAIT** | 我主动关了，等一会确保对方收完 | 主动关闭连接的服务端 |
| **CLOSE_WAIT** | 对方关了，我还没关 | 代码里没 close()——连接泄漏！ |

```bash
# 统计各状态的数量
ss -tan | awk '{print $1}' | sort | uniq -c

# 只看 TIME_WAIT（太多说明短连接太多）
ss -tan state time-wait | wc -l
```

---

## 十、关键配置文件

```bash
# DNS 配置
/etc/resolv.conf
# nameserver 8.8.8.8

# 主机名
/etc/hostname
# myserver

# 静态 DNS（本地 hosts）
/etc/hosts
# 127.0.0.1 localhost
# 192.168.1.100 db-server

# 网络接口配置（不同发行版不同）
/etc/netplan/*.yaml              # Ubuntu 18.04+
/etc/network/interfaces          # Debian 老旧方式
/etc/sysconfig/network-scripts/  # CentOS/RHEL

# 内核网络参数
/etc/sysctl.conf
# net.ipv4.ip_forward=1          # 开启 IP 转发
# net.core.somaxconn=1024        # 最大监听队列
```

---

## 本章与之前的 Docker 网络的关联

| Docker 概念 | 底层 Linux 机制 | 对应本文章节 |
|------------|----------------|-------------|
| 容器有独立 IP | NET namespace | [二.4 实战：手动创建 veth](#24-实战手动创建一对-veth模拟-docker-网络) |
| `-p 8080:80` | iptables DNAT | [四.2 常用命令](#42-常用命令) |
| 容器访问外网 | iptables MASQUERADE（SNAT） | [四.1 五链四表](#41-iptables-五链四表) |
| 容器间通信 | docker0 网桥 + veth pair | [三.3 实战：让 namespace 访问外网](#33-实战让两个-namespace-能访问外网) |
| 网络不通 | iptables 规则排查 | [六.3 经典故障场景](#63-经典故障场景) |

---

## 练习题

1. 用 `ip netns` 创建两个 namespace，手动搭建一个它们之间能互相 ping 通的网络环境。
2. `ss -tan state time-wait | wc -l` 返回 5000+，可能是什么问题？怎么排查？
3. 在 Linux 上用 `iptables` 把访问本机 8080 端口的流量转发到另一台机器的 80 端口。
4. `ping www.baidu.com` 返回 `ping: www.baidu.com: Temporary failure in name resolution`，排查步骤是什么？
5. Windows 上 `ipconfig /flushdns` 和 Linux 上 `systemd-resolve --flush-caches` 做的事情一样吗？为什么？