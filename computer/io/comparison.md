# 三种 IO 对比总结

## 一、核心对比表

| 维度 | BIO | NIO | AIO |
|------|-----|-----|-----|
| **全称** | Blocking I/O | New I/O / Non-Blocking I/O | Asynchronous I/O |
| **JDK 版本** | 1.0 | 1.4 | 1.7 |
| **IO 方式** | 流式（Stream） | 通道（Channel）+ 缓冲区（Buffer） | 异步通道 + Future/回调 |
| **读写方向** | 单向（输入流 / 输出流） | 双向 | 双向 |
| **阻塞方式** | 同步阻塞 | 同步非阻塞（`read()` 仍可能阻塞） | 异步非阻塞 |
| **线程模型** | 一连接一线程 | 多路复用（Selector） | 回调 / 事件驱动 |
| **内核实现** | `read()` / `write()` | `select` / `poll` / `epoll` | Linux: 线程池模拟 / Windows: IOCP |
| **适用场景** | 低并发、简单服务 | 高并发、高性能 | Windows 异步服务 |
| **典型应用** | 数据库连接池 | **Netty**、Tomcat NIO | 较少 |

## 二、场景选择指南

```
你的场景是什么？

├─ 连接数 < 100，简单需求？
│    └─ BIO ✅ 最简单，直接能用
│
├─ 连接数 100 ~ 100,000+，需要高并发？
│    └─ NIO ✅（直接用 Netty，不要手写 NIO）
│
├─ Windows 平台 + 需要真正异步？
│    └─ AIO（IOCP）
│
└─ Linux 平台 + 需要异步？
     └─ NIO + Epoll ✅（Linux 上 AIO 实际不如 NIO）
```

## 三、底层系统调用对比

```
Linux 下多路复用的演变：

select (1970)
├── 最大 FD 限制 1024
├── 每次遍历所有 FD（O(n)）
└── 在内核和用户态之间拷贝 FD 集合

poll (1986)
├── 没有 FD 数量限制
├── 仍然遍历所有 FD（O(n)）
└── 比 select 稍好

epoll (2002)
├── 只遍历有事件的 FD（O(1)）
├── LT 模式（水平触发）/ ET 模式（边缘触发）
└── ✅ 现代 Linux 高性能 IO 的标准

Java NIO 对应关系：
├── Selector.open() → Linux 用 epoll，macOS 用 kqueue，Windows 用 IOCP/select
└── 跨平台透明切换
```

## 四、Netty 为什么选 NIO

```
Netty 的 IO 模型 = NIO + Epoll（Linux）/ KQueue（macOS）/ Epoll（Windows）

选择 NIO 的理由：
├── 1. 多路复用：一个线程管理 N 个连接 ✅
├── 2. 跨平台：Selector 自动适配各平台最优实现 ✅
├── 3. Linux 性能最优：epoll O(1) 事件通知 ✅
├── 4. AIO 在 Linux 上不如 NIO：底层线程池模拟 ❌
└── 5. 生态成熟：Tomcat、Dubbo、gRPC 都用 NIO ✅
```

## 五、一句话总结

| IO 类型 | 一句话 |
|---------|--------|
| **BIO** | 一个线程守一个连接，简单但扛不住高并发 |
| **NIO** | 一个线程守 N 个连接，通过 Selector 多路复用，**Netty 的基础** |
| **AIO** | 操作系统帮你 IO，完成后回调你，理想但 Linux 上不如 NIO |