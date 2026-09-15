# EventLoop 线程模型

## 一、Netty 的线程模型

```
┌─────────────────────────────────────────────────────────────────┐
│                    Netty 线程模型                                  │
│                                                                  │
│  ┌──────────────┐          ┌──────────────────────────────┐    │
│  │  BossGroup   │          │  WorkerGroup                  │    │
│  │              │          │                              │    │
│  │  EventLoop   │─accept──►│  EventLoop 1                 │    │
│  │  (1 个线程)  │          │    ├── Channel A             │    │
│  │              │          │    ├── Channel B             │    │
│  │  职责：       │          │    └── ...                   │    │
│  │  接受新连接    │          │  EventLoop 2                 │    │
│  │              │          │    ├── Channel C             │    │
│  │              │          │    ├── Channel D             │    │
│  │              │          │    └── ...                   │    │
│  │              │          │                              │    │
│  │              │          │  EventLoop N                 │    │
│  │              │          │    └── ...                   │    │
│  └──────────────┘          └──────────────────────────────┘    │
│                                                                  │
│  boss: 1 个线程，只负责 accept                                   │
│  worker: N 个线程（CPU * 2），负责 IO 读写 + 业务处理            │
└─────────────────────────────────────────────────────────────────┘
```

## 二、EventLoop 的核心特性

### 特性一：一个 Channel 绑定一个 EventLoop

```
Channel A ──► EventLoop 1 ──► Selector 1
Channel B ──► EventLoop 1 ──► Selector 1  (同一个 EventLoop 管理多个 Channel)
Channel C ──► EventLoop 2 ──► Selector 2
Channel D ──► EventLoop 2 ──► Selector 2
```

- 一个 `EventLoop` 在**整个生命周期**内只被**一个线程**执行
- 一个 `Channel` 从创建到销毁，始终由**同一个 EventLoop** 处理
- 一个 `EventLoop` 可以同时管理**多个 Channel**

### 特性二：线程安全保证

```
因为 Channel 的所有 IO 操作都由同一个 EventLoop 的同一个线程执行，
所以 ChannelHandler 不需要加锁！

Channel A 的读写 → 永远是 EventLoop-1 的 thread-1 执行
→ 无需 synchronized
→ 无需 volatile
→ 无需 AtomicXXX
```

> 这是 Netty 线程模型最优雅的设计：**用单线程替代锁**。

### 特性三：EventLoop 既处理 IO 又处理任务

```
EventLoop 的主循环：

while (true) {
    int events = selector.select(1000);  // 1. 等待 IO 事件

    for (SelectionKey key : selectedKeys) {
        if (key.isAcceptable()) {
            // 2. 处理 accept
        } else if (key.isReadable()) {
            // 3. 处理 read → 触发 Pipeline
        } else if (key.isWritable()) {
            // 4. 处理 write
        }
    }

    // 5. 处理任务队列（用户提交的异步任务）
    runAllTasks();
}
```

`EventLoop` 不仅处理网络 IO，还处理：
- **定时任务**：`eventLoop.schedule()`
- **普通任务**：`eventLoop.execute()`
- **定时心跳**
- **超时检测**

## 三、EventLoopGroup 的分配策略

```java
// bossGroup：1 个 EventLoop（1 个线程）
EventLoopGroup bossGroup = new NioEventLoopGroup(1);

// workerGroup：不传参数 = 默认 CPU 核数 * 2
EventLoopGroup workerGroup = new NioEventLoopGroup();
// 如 8 核 CPU → 16 个 EventLoop → 16 个线程
```

### 新连接如何分配到 EventLoop？

```
新连接到来:
  boss EventLoop accept()
       │
       ▼
  创建 NioSocketChannel
       │
       ▼
  workerGroup.next() ──► 选择一个 EventLoop
       │                  │
       │                  ▼
       │          ┌──────────────┐
       │          │ 轮询分配       │
       │          │ EventLoop 1   │
       │          │ EventLoop 2   │
       │          │ EventLoop 3   │
       │          │ ...           │
       │          └──────────────┘
       │
       ▼
  Channel 注册到选中的 EventLoop 的 Selector
```

> Netty 使用**轮询（Round-Robin）**策略分配 EventLoop，保证负载均衡。

## 四、一个 Channel 绑定一个 EventLoop 的好处

```java
// 例子：在 handler 里发起一个写操作

public class MyHandler extends ChannelInboundHandlerAdapter {
    @Override
    public void channelRead(ChannelHandlerContext ctx, Object msg) {
        // 这段代码由 Channel 绑定的 EventLoop 线程执行
        // 无需担心线程安全问题

        // 可以直接操作共享状态
        someSharedState.add(msg);  // 不需要 synchronized！

        // 可以安全地写入 Channel
        ctx.writeAndFlush(response);  // 不会被其他线程干扰
    }
}
```

如果 Channel 的读写由不同线程执行：
```java
// ❌ 需要加锁
synchronized (channel) {
    channel.writeAndFlush(msg);
}

// ❌ 或者用队列
blockingQueue.offer(msg);
```

> Netty 的设计让开发者**完全不需要关心并发问题**。

## 五、EventLoop 的执行线程

```
EventLoop
├── 在 EventLoop 自己的线程中执行的任务
│   ├── IO 事件（read/write/accept）
│   ├── Pipeline 中的 handler 调用
│   └── 定时任务
│
└── 在其他线程中提交的任务
    └── 会通过任务队列，等 EventLoop 空闲时在自己的线程中执行

例如：
    其他线程 → eventLoop.execute(runnable)
               → runnable 被加入任务队列
               → EventLoop 在自己的线程中执行 runnable
               → 保证了 runnable 与 Channel 的 IO 在同一线程
```

### 为什么要提交到 EventLoop？

```java
// ChannelHandler 中：
ctx.writeAndFlush(msg);
// 如果当前线程就是 EventLoop 线程 → 直接执行
// 如果当前线程不是 EventLoop 线程 → 直接提交到该 Channel 绑定的 EventLoop 的任务队列
```

#### 完整流程举例

假设服务器有 3 个 EventLoop，**Channel-A** 绑定到 **EventLoop-2**（线程 2），
某个**业务线程（线程 99）**想要给 Channel-A 发消息：

```
  线程 2（EventLoop-2）        线程 3（EventLoop-3）        线程 99（业务线程）
 ┌──────────────────┐    ┌──────────────────┐    ┌──────────────────────┐
 │ Channel-A 的     │    │ Channel-D 的     │    │ ctx.writeAndFlush()  │
 │ Selector         │    │ Selector         │    │ 操作 Channel-A       │
 │                  │    │                  │    │                      │
 │ 任务队列: []     │    │ 任务队列: []     │    │ 1. inEventLoop()?    │
 │                  │    │                  │    │  → 是线程2吗？不是！  │
 │                  │    │                  │    │                      │
 └──────────────────┘    └──────────────────┘    │ 2. eventLoop.execute │
                                                  │    ()               │
                                                  └─────────┬──────────┘
                                                            │
                                                            ▼
                                                  ┌──────────────────┐
                                                  │ 线程2 的任务队列:  │
                                                  │ [写操作任务]       │
                                                  └────────┬─────────┘
                                                           │
                                                           ▼
                                                  ┌──────────────────┐
                                                  │ 线程2 在主循环中   │
                                                  │ runAllTasks()    │
                                                  │ → Channel-A.write│
                                                  └──────────────────┘
```

#### 为什么能一步到位？

`ctx` 在 Channel 创建时就**已经知道自己的 EventLoop 是谁**，永远不变：

```
Channel-A 创建时：
  ┌─────────────────────────────┐
  │ Channel-A                   │
  │  .eventLoop = EventLoop-2   │ ← 创建时就确定，终身不变
  │  .pipeline                  │
  │    .ctxA.eventLoop = EL-2   │
  │    .ctxB.eventLoop = EL-2   │
  │    ...                      │
  └─────────────────────────────┘
```

所以 `ctx.writeAndFlush(msg)` 内部做了两件事：

```java
// Step 1: 判断当前线程
EventLoop el = ctx.executor();  // → 直接拿到 EventLoop-2

// Step 2: 如果是 EventLoop-2 自己 → 直接执行
//         如果是其他线程 → 把任务直接 offer 到 EventLoop-2 的任务队列
```

#### ❌ vs ✅

```
❌ 你以为的（转发）：
  线程99 → 扔到线程池 → 线程3 捡到 → 发现是别人的 → 再转发 → 线程2 捡到 → 执行

✅ 实际（直投）：
  线程99 → 直接告诉 EventLoop-2 → 放到它的任务队列 → EventLoop-2 执行
```

> **核心保证**：无论从哪里调用，Channel 的操作最终都在 EventLoop 线程中执行。
> EventLoop 的 Selector 只注册属于自己的 Channel，永远不会"读到别人的 Channel"。
> 跨线程场景只发生在 Handler 代码中显式调用 `ctx.writeAndFlush()` 等操作时。

## 六、总结

```
Netty 线程模型的核心原则：

1. 一个 EventLoop = 一个线程（终身不变）
2. 一个 Channel  = 一个 EventLoop（终身不变）
3. 一个 EventLoop = 多个 Channel（通过 Selector 多路复用）
4. Channel 的所有 IO 操作 = 同一个线程执行（无需加锁）
5. 异步任务 = 提交到 EventLoop 的任务队列（保证线程安全）
```