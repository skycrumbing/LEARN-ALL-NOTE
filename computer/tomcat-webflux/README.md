# Tomcat NIO 与 Spring WebFlux 源码对比

## 主题大纲

| # | 知识点 | 状态 |
|---|--------|------|
| 1 | 架构全景对比 | ✅ |
| 2 | Tomcat NIO 源码（Acceptor → Poller → SocketProcessor → Adapter → Servlet） | ✅ |
| 3 | Spring WebFlux 源码（Netty EventLoop → RouterFunction → Mono/Flux → 响应写出） | ✅ |
| 4 | 线程模型深度对比（多线程 vs 事件驱动） | ✅ |
| 5 | 内存模型对比（线程栈 vs 回调链） | ✅ |
| 6 | 背压机制 | ✅ |
| 7 | 阻塞操作处理方式 | ✅ |
| 8 | 选型指南 | ✅ |

## 前置知识

- [Java IO（NIO）](../io/nio.md)
- [Netty 线程模型](../netty/thread-model.md)
- [Java 线程池](../thread-pool/source-analysis.md)

## 文件

| 文件 | 说明 |
|------|------|
| [`source-analysis.md`](source-analysis.md) | 底层关键源码剖析与总结 |

## 学习路径建议

```
1. 先复习 NIO 的 Selector 原理 → 理解 Tomcat NIO 的 Poller
2. 再看 Tomcat 启动源码 → 理解 Acceptor/Poller/线程池 三层架构
3. 再看 WebFlux 的 Netty 启动 → 理解 EventLoop 模型
4. 最后对比：线程模型 / 内存模型 / 背压 / 异步机制
```