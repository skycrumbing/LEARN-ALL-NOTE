# Java IO

## 学习内容

- [x] Java IO 体系全景
- [x] BIO（阻塞 IO）
- [x] NIO（非阻塞 IO / 新 IO）
- [x] AIO（异步 IO）
- [x] 三种 IO 对比
- [ ] 零拷贝（mmap / sendfile / DirectBuffer）
- [ ] Netty 的 IO 模型

## 笔记文件

| 文件 | 说明 | 状态 |
|------|------|------|
| `overview.md` | Java IO 全景图、为什么有 NIO/AIO | ✅ 已完成 |
| `bio.md` | 阻塞 IO：InputStream/OutputStream/Socket | ✅ 已完成 |
| `nio.md` | 非阻塞 IO：Channel/Buffer/Selector | ✅ 已完成 |
| `aio.md` | 异步 IO：AsynchronousChannel/CompletionHandler | ✅ 已完成 |
| `comparison.md` | 三种 IO 的对比总结 | ✅ 已完成 |

## 学习进度

| 阶段 | 内容 | 完成 |
|------|------|------|
| 1 | 理解 Java IO 分类与历史背景 | ✅ |
| 2 | 理解 BIO 阻塞模型与线程瓶颈 | ✅ |
| 3 | 理解 NIO 三大核心组件 | ✅ |
| 4 | 理解 Selector 多路复用机制 | ✅ |
| 5 | 理解 AIO 异步事件驱动模型 | ✅ |
| 6 | 对比三种模型，理解适用场景 | ✅ |
| 7 | 理解零拷贝原理 | 📝 待学习 |
| 8 | 深入 Netty 的 IO 实现 | 📝 待学习 |