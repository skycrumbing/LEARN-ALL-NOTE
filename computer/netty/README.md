# Netty

## 学习内容

- [x] Netty 架构全景
- [x] 为什么需要 Netty（手写 NIO 服务器的痛点）
- [x] 线程模型：EventLoop / EventLoopGroup
- [x] Pipeline 与 ChannelHandler 责任链
- [x] ByteBuf 内存管理
- [x] 零拷贝在 Netty 中的体现
- [x] 粘包/拆包解决方案
- [x] 空闲连接检测与心跳机制
- [x] 连接风暴防护
- [x] 百万 IoT 连接场景
- [x] Echo 示例：短连接 vs 长连接（本质区别、协议开销、心跳保活）
- [ ] 手写一个 Netty 聊天室

## 笔记文件

| 文件 | 说明 | 状态 |
|------|------|------|
| `architecture.md` | Netty 整体架构、为什么需要 Netty | ✅ 已完成 |
| `bootstrap.md` | Bootstrap / ServerBootstrap 启动流程 | ✅ 已完成 |
| `thread-model.md` | EventLoop 线程模型详解 | ✅ 已完成 |
| `pipeline.md` | Pipeline + ChannelHandler 责任链 | ✅ 已完成 |
| `bytebuf.md` | ByteBuf 内存模型、堆内/堆外 | ✅ 已完成 |
| `zero-copy.md` | Netty 的四种零拷贝方式 | ✅ 已完成 |
| `network-issues.md` | 粘包/拆包、空闲连接检测、连接风暴、IoT百万连接 | ✅ 已完成 |
| `echo-example.md` | Echo 示例：两套独立服务端+客户端对比短连接与长连接，含协议开销分析、心跳保活、重连机制 | ✅ 已完成 |

## 学习进度

| 阶段 | 内容 | 完成 |
|------|------|------|
| 1 | 理解 Netty 解决什么问题 | ✅ |
| 2 | 理解 Netty 整体架构分层 | ✅ |
| 3 | 理解 EventLoop 线程模型 | ✅ |
| 4 | 理解 Pipeline 责任链 | ✅ |
| 5 | 理解 ByteBuf 内存管理 | ✅ |
| 6 | 理解 Netty 零拷贝 | ✅ |
| 7 | TCP 粘包拆包实战 | ✅ |
| 8 | 空闲连接检测与心跳机制 | ✅ |
| 9 | 连接风暴防护 | ✅ |
| 10 | 百万 IoT 连接场景 | ✅ |
| 11 | 手写 Netty 聊天室 | 📝 待学习 |