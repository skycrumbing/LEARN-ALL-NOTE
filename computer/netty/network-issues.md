# Netty 处理常见网络问题

## 一、TCP 粘包与拆包

### 1.1 什么是粘包和拆包

TCP 是**面向字节流**的协议，没有"消息"的概念。它不知道你的数据在哪里开始、在哪里结束。

```
发送方视角：               TCP 实际传输：
                          （一串连续的字节流）

┌──────┐  ┌──────┐  ┌──────┐
│ 消息1 │  │ 消息2 │  │ 消息3 │
└──────┘  └──────┘  └──────┘
     │        │        │
     ▼        ▼        ▼
     ────────────────────────────►
              TCP 字节流
     ┌───────────────────────────────┐
     │  消息1的消息2的消息3           │
     │  (中间没有任何分隔符)          │
     └───────────────────────────────┘
```

**粘包**：多条消息被合在一起收到

```
发送:  send("Hello") → send("World")
接收:  read("HelloWorld")    ← 粘在一起了
```

**拆包**：一条消息被分成多次收到

```
发送:  send("Hello World, this is a long message")
接收:  read("Hello W")
      read("orld, this is a long message")  ← 被拆了
```

### 1.2 为什么会出现

| 原因 | 说明 |
|------|------|
| **TCP 是流式协议** | 没有消息边界，只有连续的字节流 |
| **Nagle 算法** | 有未确认的小包时，合并后续小包再发 → 发送方粘包 |
| **MSS 限制** | 大包超过 1460 字节被拆成多个 TCP 段 → 接收方拆包 |
| **接收缓冲区** | 应用层一次 read 读不完缓冲区数据 → 拆包 |

```
发送: send("A") → send("B") → send("C")

可能的接收情况:
  情况1: read("ABC")               ← 全粘
  情况2: read("A") → read("BC")   ← 部分粘
  情况3: read("A") → read("B") → read("C")  ← 完美
  情况4: read("A") → read("Bc") → read("rest")  ← 部分拆
```

### 1.3 四种解决方案

| # | 方案 | 原理 | 适用场景 |
|---|------|------|----------|
| 1 | **消息定长** | 每条消息固定长度，如 100 字节 | 简单协议、日志上报 |
| 2 | **特殊分隔符** | 用 `\n` 或 `\r\n` 分隔 | HTTP、FTP 等文本协议 |
| 3 | **长度字段** | 消息头带 4 字节长度字段 | 大多数 RPC、金融协议 |
| 4 | **协议头部** | 自定义消息头含魔数、版本、长度等 | 复杂业务协议 |

---

#### 方案一：消息定长

```java
// 每条消息固定 100 字节，不足补空格
FixedLengthFrameDecoder decoder = new FixedLengthFrameDecoder(100);

// Pipeline 配置
pipeline.addLast("fixedLength", decoder);
pipeline.addLast("handler", new MyHandler());
```

```
发送:  "Hello        " (100字节)  "World        " (100字节)
      └─── frame1 ──┘              └─── frame2 ──┘

接收:  decoder 每次读 100 字节输出一个 frame
```

| 优点 | 缺点 |
|------|------|
| 实现最简单 | 短消息浪费空间，长消息放不下 |
| 性能高 | 消息长度变化时无法扩展 |

---

#### 方案二：特殊分隔符

```java
// 用换行符 \n 分隔消息（类似 HTTP）
LineBasedFrameDecoder decoder = new LineBasedFrameDecoder(1024);  // 最大行长度 1024

pipeline.addLast("lineDecoder", decoder);
pipeline.addLast("stringDecoder", new StringDecoder());
pipeline.addLast("handler", new MyHandler());
```

```
发送:  "Hello\nWorld\nFoo Bar\n"
      └───frame1──┘└───frame2───┘└─────frame3─────┘

接收:  decoder 按 \n 切割，输出三条消息
```

| 优点 | 缺点 |
|------|------|
| 简单直观 | 消息内容不能包含分隔符 |
| 适合文本协议 | 长消息容易超过缓冲区，需设 maxFrameLength |

---

#### 方案三：长度字段（最常用）

```java
// LengthFieldBasedFrameDecoder 参数详解：
//   1. maxFrameLength:   最大帧长度（防止恶意大帧）
//   2. lengthFieldOffset: 长度字段在帧中的偏移（从 0 开始）
//   3. lengthFieldLength: 长度字段本身占几个字节
//   4. lengthAdjustment:  长度字段值与实际数据长度的差值
//   5. initialBytesToStrip: 解码后跳过的字节数
LengthFieldBasedFrameDecoder decoder = new LengthFieldBasedFrameDecoder(
    1024,        // 最大帧长度 1024 字节
    0,           // 长度字段从第 0 字节开始
    4,           // 长度字段占 4 字节（int）
    0,           // 长度值就是数据长度，无额外偏移
    0            // 不移除任何字节
);

pipeline.addLast("frameDecoder", decoder);
pipeline.addLast("stringDecoder", new StringDecoder());
pipeline.addLast("handler", new MyHandler());
```

```
发送的字节流结构:
┌────────┬────────────────────────┐
│ 长度字段│       消息体          │
│(4字节) │   (长度字段值的大小)    │
└────────┴────────────────────────┘
  int: 5     "Hello" (5字节)
  int: 5     "World" (5字节)
```

```
发送:  [0x00000005][Hello][0x00000005][World]
                        │
                        ▼
LengthFieldBasedFrameDecoder 自动切割:

  1. 读 4 字节长度字段 → 得到 5
  2. 再读 5 字节数据   → "Hello"，输出 frame1
  3. 重复过程          → "World"，输出 frame2
```

| 优点 | 缺点 |
|------|------|
| 支持变长消息 | 发送方也要配合写长度字段 |
| 消息内容不受限制 | 需要理解参数含义 |
| **最通用的方案** | |

**发送方配合使用 `LengthFieldPrepender`**：

```java
// 发送方：在数据前自动写入 4 字节长度字段
pipeline.addLast("lengthPrepender", new LengthFieldPrepender(4));
```

---

#### 方案四：协议头部（高级）

```java
// 自定义消息头结构
// ┌──────┬────────┬────────┬──────────┐
// │魔数  │ 版本   │ 命令类型│  体长度  │
// │4字节 │ 1字节  │ 1字节  │  4字节   │
// └──────┴────────┴────────┴──────────┘
// 头部共 10 字节，后面跟消息体

pipeline.addLast("frameDecoder", new LengthFieldBasedFrameDecoder(
    65536,    // 最大帧长度
    10,       // 长度字段从第 10 字节开始（跳过魔数+版本+命令类型）
    4,        // 长度字段占 4 字节
    0,        // 长度值就是体长度
    10        // 解码后跳过前 10 字节头部，只留消息体
));
```

| 优点 | 缺点 |
|------|------|
| 携带版本/命令类型等元信息 | 实现最复杂 |
| 支持协议升级 | 需要维护协议规范 |

#### 方案三深入：帧解码器如何处理不完整数据

这是粘包拆包最核心的问题：**read() 可能只读到半条消息，下游处理器怎么不收到不完整数据？**

答案：帧解码器内部维护一个 **cumulation（累积缓冲区）**，不凑齐完整消息绝不下传。

##### 核心机制：累积缓冲区

```
Socket 网络数据
  │
  ▼
Selector 检测到 OP_READ
  │
  ▼
Netty read() 读取到 ByteBuf（可能 1 条 / 半条 / 1.5 条）
  │
  ▼
fireChannelRead() 传给第一个 Handler
  │
  ▼
┌──────────────────────────────────────────────┐
│  LengthFieldBasedFrameDecoder               │
│                                              │
│  内部维护一个 cumulation（累积缓冲区）        │
│                                              │
│  ┌────────────────────────────────────┐      │
│  │  cumulation:                       │      │
│  │  [完整消息1][完整消息2][半条消息3..]│      │
│  │   ← 已经攒好的数据                  │      │
│  └────────────────────────────────────┘      │
│                                              │
│  每次收到新数据：                             │
│  1. 追加到 cumulation                       │
│  2. 检查是否有完整消息                       │
│  3. 有 → 切割完整消息，fire 给下游            │
│  4. 没有 → 继续攒，什么都不做               │
└──────────────────────────────────────────────┘
  │
  ▼  只传完整消息
下一个 Handler（如 StringDecoder）
  │
  ▼  只处理完整消息
业务 Handler
```

##### 四种场景拆解

假设协议 `[4字节长度][消息体]`：

```
场景一：一次读到半条

  read() 结果:  [0x00000005]     ← 只有长度字段，没有消息体

  cumulation:   [0x00000005]
  解析:         读到长度 = 5，需要 4 + 5 = 9 字节
  实际:         只有 4 字节 < 9 字节
  → 不完整，等待下次数据到来
  → 不 fire 任何消息给下游
```

```
场景二：下次读到剩余部分

  read() 结果:  [Hello]          ← 5 字节消息体

  cumulation:   [0x00000005][Hello]
  解析:         长度 = 5，需要 9 字节，实际 9 >= 9
  → 完整！切割 [Hello]，fire 给下游
  → cumulation 清空
```

```
场景三：一次读到一条 + 半条

  read() 结果:  [0x00000005][World][0x00000006]

  cumulation:   [0x00000005][World][0x00000006]  总长 15

  第一轮循环:
    读长度 = 5，需要 9 字节，实际 15 >= 9 → 完整
    → 切割 [World]，fire 给下游
    → cumulation 剩余: [0x00000006]

  第二轮循环:
    读长度 = 6，需要 10 字节，实际只有 4 < 10 → 不完整
    → 停止循环，等待下次数据

  结果: 只 fire 了一条 [World] 给下游
```

```
场景四：一次读到多条

  read() 结果:  [0x00000003][Hi!][0x00000004][Hey!][0x00000003]

  cumulation:   总长 16

  第一轮: 读 3，需要 7 字节，实际 16 >= 7 → fire [Hi!]
  第二轮: 读 4，需要 8 字节，实际 9 >= 8 → fire [Hey!]
  第三轮: 读 3，需要 7 字节，实际只有 4 < 7 → 停止

  结果: 连续 fire 了两条消息给下游
```

##### 场景汇总

| read() 的结果 | Decoder 行为 | 下游收到 |
|--------------|-------------|---------|
| 半条消息 | 攒入缓冲区，等待 | 什么都没收到 |
| 一条完整 | 切割，fire | 一条消息 |
| 一条 + 半条 | 切完整 fire，剩半条攒着 | 一条消息 |
| 多条完整 | 逐条切割，全部 fire | 多条消息 |
| 多条 + 半条 | 切完整 fire，剩半条攒着 | 多条消息 |

##### Decoder 的核心代码逻辑

```java
// LengthFieldBasedFrameDecoder.decode() 简化逻辑：
@Override
protected Object decode(ChannelHandlerContext ctx, ByteBuf in) {
    // 1. 超出最大帧长度，丢弃（防恶意大帧）
    if (cumulation.readableBytes() > maxFrameLength) {
        cumulation.clear();
        throw new TooLongFrameException();
    }

    // 2. 循环尝试解码
    while (cumulation.readableBytes() >= lengthFieldLength) {
        // 3. 读长度字段
        int frameLength = readFrameLength(cumulation);

        // 4. 判断数据是否完整
        int needed = lengthFieldLength + frameLength;
        if (cumulation.readableBytes() < needed) {
            // 🔑 不完整 → 停止循环，等待下次数据
            return null;
        }

        // 5. 完整 → 切割帧，fire 给下游
        ByteBuf frame = cumulation.readRetainedSlice(needed);
        ctx.fireChannelRead(frame);

        // 6. 继续处理剩余数据
    }
    return null;
}
```

**关键就这一行**：

```java
if (cumulation.readableBytes() < needed) {
    return null;  // 数据不够，攒着等下次
}
```

`<` 是停止信号，`>=` 和 `>` 的情况靠 `while` 循环自然处理：

```
readableBytes > needed  →  只切 needed 那么多，剩下的留在 cumulation 继续循环
readableBytes = needed  →  切完刚好，继续循环看有没有更多
readableBytes < needed  →  不够，return null 停止
```

举例：一次读到 `[长度4][Hi!][长度4][Hey!][长度3]`（18字节）：

```
第一轮: readable=18, needed=7  → 18 >= 7, 切 7 字节 fire [Hi!], 剩 11
第二轮: readable=11, needed=8  → 11 >= 8, 切 8 字节 fire [Hey!], 剩 3
第三轮: readable=3,  连长度字段(4)都不够 → while 退出, return null
```

下游处理器**永远看不到半条消息**，不完整的数据被拦截在 Decoder 这里，存在 `cumulation` 里等着。

##### 内存保护：maxFrameLength

```
如果客户端故意不发完整消息，一直发半条，cumulation 会无限增长吗？

不会。Decoder 有 maxFrameLength 保护：

  if (cumulation.readableBytes() > maxFrameLength) {
      cumulation.clear();          // 清空缓冲区
      ctx.fireExceptionCaught(     // 触发异常事件
          new TooLongFrameException());
  }
```

配置 `maxFrameLength` 时设为你的最大合理消息长度 + 一点余量，超过就丢弃并断开连接，防止内存被撑爆。

---

## 二、空闲连接检测

### 2.1 为什么要检测空闲连接

```
问题场景：

客户端已断开，但服务端不知道：

服务端               客户端
  │                    │
  │   ← 还在处理这个连接
  │                    │  ← 进程已崩溃/网络已断
  │                    │     (服务端一无所知)
  │                    │
  ▼                    ▼
  服务端持续为该连接分配资源，
  Channel 占用 EventLoop 的 Channel 列表，
  永远不会释放
```

Netty 提供了 `IdleStateHandler` 来自动检测空闲连接：

```java
pipeline.addLast("idleStateHandler",
    new IdleStateHandler(
        60,   // readerIdleTime: 60秒没读到数据 → 读空闲
        0,    // writerIdleTime: 0 = 不检测写空闲
        0     // allIdleTime: 0 = 不检测读写空闲
    )
);
pipeline.addLast("handler", new MyHandler());
```

### 2.2 IdleStateHandler 的三种空闲类型

```
┌─────────────────────────────────────────────────────────┐
│              IdleStateHandler 三种状态                    │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  读空闲 (READER_IDLE)                                    │
│  ┌─────────────────────────────────────┐               │
│  │  最近一次 read() 到现在的时间        │               │
│  │  超过 readerIdleTime 秒             │               │
│  └─────────────────────────────────────┘               │
│                                                         │
│  写空闲 (WRITER_IDLE)                                    │
│  ┌─────────────────────────────────────┐               │
│  │  最近一次 write() 到现在的时间       │               │
│  │  超过 writerIdleTime 秒             │               │
│  └─────────────────────────────────────┘               │
│                                                         │
│  读写空闲 (ALL_IDLE)                                     │
│  ┌─────────────────────────────────────┐               │
│  │  最近一次 read/write 到现在的时间    │               │
│  │  超过 allIdleTime 秒                │               │
│  └─────────────────────────────────────┘               │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

### 2.3 IdleStateEvent 的处理

```java
public class MyHandler extends ChannelInboundHandlerAdapter {

    @Override
    public void userEventTriggered(ChannelHandlerContext ctx, Object evt) {
        if (evt instanceof IdleStateEvent) {
            IdleStateEvent event = (IdleStateEvent) evt;

            if (event.state() == IdleState.READER_IDLE) {
                // 60 秒没收到数据
                System.out.println("读空闲：客户端长时间没发数据");
                // 主动发送心跳请求
                ctx.writeAndFlush(HeartbeatRequest.PING);

            } else if (event.state() == IdleState.WRITER_IDLE) {
                // 写空闲
                System.out.println("写空闲");

            } else if (event.state() == IdleState.ALL_IDLE) {
                // 读写都空闲
                System.out.println("读写空闲，连接可能已死");
                ctx.close();  // 直接关闭
            }
        }
    }
}
```

### 2.4 心跳机制

```
心跳是检测空闲连接的标准做法：

  客户端                  服务端
    │                      │
    │─── 每 30s 发 PING ──►│
    │◄── 收到后回 PONG ───│
    │                      │
    │   （持续收发心跳）     │
    │                      │
    │─── 60s 没收到 PING ──►│
    │                      │  └─ 判定客户端已死
    │                      │     ctx.close()
```

```java
// 服务端配置：
pipeline.addLast("idleHandler",
    new IdleStateHandler(60, 0, 0));  // 60秒读空闲
pipeline.addLast("heartbeatHandler", new HeartbeatHandler());
pipeline.addLast("businessHandler", new BusinessHandler());

// 心跳 Handler（放在业务 Handler 之前）
public class HeartbeatHandler extends ChannelInboundHandlerAdapter {

    @Override
    public void userEventTriggered(ChannelHandlerContext ctx, Object evt) {
        if (evt instanceof IdleStateEvent) {
            // 读空闲 → 服务端没收到客户端心跳
            ctx.writeAndFlush(HeartbeatResponse.PONG);  // 确认还在
        }
    }

    @Override
    public void channelRead(ChannelHandlerContext ctx, Object msg) {
        if (msg instanceof HeartbeatRequest) {
            // 收到客户端心跳，回复 PONG
            ctx.writeAndFlush(HeartbeatResponse.PONG);
        } else {
            // 业务消息，继续传递
            ctx.fireChannelRead(msg);
        }
    }
}
```

---

## 三、连接风暴（瞬间大量连接）

### 3.1 什么是连接风暴

```
正常场景：
  每秒 100 个新连接 → 服务器从容处理

连接风暴：
  每秒 10,000 个新连接涌入

  ┌─────────────────────────────────────┐
  │         瞬间连接洪峰                  │
  │                                      │
  │   /‾‾‾‾‾‾‾\                         │
  │  /          \                        │
  │ /            \                       │
  │/              \                      │
  │                \                     │
  │                 \                    │
  │                  \                   │
  └────────────────────── 时间 ──────────►
```

**常见原因**：
- CDN 过期后大量客户端同时回源
- 秒杀活动，用户同时发起请求
- 攻击者发起连接洪水攻击（Slowloris 等）

### 3.2 Netty 的防护措施

Netty 提供了多层次的防护机制：

```
┌─────────────────────────────────────────────────────┐
│            连接风暴防护体系                            │
├─────────────────────────────────────────────────────┤
│                                                     │
│  第一层：操作系统层                                   │
│  ┌──────────────────────────────────┐              │
│  │ SO_BACKLOG（连接队列长度）         │              │
│  │ 超过队列长度 → 直接拒绝连接         │              │
│  └──────────────────────────────────┘              │
│                                                     │
│  第二层：Channel 配置层                               │
│  ┌──────────────────────────────────┐              │
│  │ ChannelMaxInitialMessageCount     │              │
│  │ 限制单个 Channel 最大消息数         │              │
│  └──────────────────────────────────┘              │
│                                                     │
│  第三层：应用层                                       │
│  ┌──────────────────────────────────┐              │
│  │ 限流（Rate Limiting）              │              │
│  │ 拒绝/排队/降级                     │              │
│  └──────────────────────────────────┘              │
│                                                     │
└─────────────────────────────────────────────────────┘
```

### 3.3 SO_BACKLOG（操作系统层）

```java
// 设置连接队列长度
bootstrap.option(ChannelOption.SO_BACKLOG, 1024);
```

```
OS 内核 TCP 连接队列：

  新连接 ──► [ 队列 ] ──► 服务端 accept()

  队列满时：
  ┌─────────────────────────────┐
  │  [ 排队... 排队... 排队 ]   │
  │  [ 1024 个已排队，满了！    │
  │    拒绝新的连接 ]             │
  └─────────────────────────────┘
```

### 3.4 ChannelMaxInitialMessageCount（防慢速攻击）

```java
pipeline.addLast("slowAttack",
    new SlowStreamTrafficShapingHandler(1024, 0, 1024));
```

防止单个连接发送大量数据但不处理（Slowloris 攻击）。

### 3.5 应用层限流（最实用）

#### 关于线程安全的两个关键点

```
┌────────────────────────────────────────────────────────────────┐
│  问题一：Handler 实例是共享的吗？                                │
│                                                                │
│  ❌ 不是。每个 Channel 创建时，initChannel() 中                   │
│     new RateLimiterHandler(...) 会创建独立的实例。               │
│                                                                │
│  ┌────────┐   ┌────────┐   ┌────────┐                         │
│  │Channel1│   │Channel2│   │Channel3│                         │
│  │handler1│   │handler2│   │handler3│   ← 各自独立实例          │
│  └────────┘   └────────┘   └────────┘                         │
│                                                                │
│  所以不能用 instance 变量计数（每个 handler 从 0 开始），         │
│  不能用 static int（共享了但 ++ 线程不安全），                     │
│  也不能用 instance AtomicInteger（共享了但每个从 0 开始）。       │
│                                                                │
│  ✅ 正确方案：static AtomicInteger 或构造器注入共享对象            │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  问题二：多个 EventLoop 线程并发操作计数器                        │
│                                                                │
│  Channel-A 的 channelActive() → EventLoop-1 线程               │
│  Channel-B 的 channelActive() → EventLoop-2 线程               │
│  Channel-C 的 channelActive() → EventLoop-3 线程               │
│                                                    │            │
│                                                    ▼            │
│                          currentConnections++ 被多个线程同时执行   │
│                          read → +1 → write 不是原子操作          │
│                          结果：计数器少算！                       │
│                                                                │
│  Thread1: read=5                                    │           │
│  Thread2: read=5                                    │           │
│  Thread1: write=6  ←──────────── 两个都从 5 开始     │           │
│  Thread2: write=6  ←──────────── 应该是 7，结果是 6  │           │
└────────────────────────────────────────────────────────────────┘
```

#### 正确实现：构造器注入共享计数器

```java
// 1. 创建一个共享的计数器对象（在 initChannel 外面）
AtomicInteger sharedCounter = new AtomicInteger(0);

// 2. 在 initChannel 中注入共享对象（所有 handler 共享同一个 counter）
pipeline.addLast("rateLimiter", new RateLimiterHandler(10000, sharedCounter));

// 3. Handler 使用共享的计数器
public class RateLimiterHandler extends ChannelInboundHandlerAdapter {

    // 🔑 sharedCounter 是所有 handler 实例共享的同一个对象
    // 🔑 AtomicInteger 保证 incrementAndGet 的原子性
    private final AtomicInteger counter;
    private final int maxConnections;

    public RateLimiterHandler(int maxConnections, AtomicInteger sharedCounter) {
        this.maxConnections = maxConnections;
        this.counter = sharedCounter;
    }

    @Override
    public void channelActive(ChannelHandlerContext ctx) {
        // 先增再判断，超了回退（原子操作保证多线程安全）
        if (counter.incrementAndGet() > maxConnections) {
            counter.decrementAndGet();
            ctx.close();
            return;
        }
        // 连接关闭时减回计数
        ctx.channel().closeFuture().addListener(future -> counter.decrementAndGet());
        ctx.fireChannelActive();
    }
}
```

**为什么构造器注入优于 `static AtomicInteger`？**

| 方案 | 共享？ | 线程安全？ | 可测试性 | 推荐度 |
|------|--------|-----------|---------|--------|
| `static AtomicInteger` | ✅ | ✅ | ❌ 全局状态，难以重置 | ⚠️ |
| 构造器注入 `AtomicInteger` | ✅ | ✅ | ✅ 可以传 mock、重置 | ✅ 推荐 |
| 实例 `AtomicInteger` | ❌ | ✅ | ✅ | ❌ 每个 handler 独立，计数器无用 |

**为什么用 `incrementAndGet` 而不是 `getAndIncrement`？**

```
incrementAndGet():  先 +1 再返回新值
  → 返回 10001，判断 > 10000，回退 -1，拒绝 ✅

getAndIncrement():  返回旧值再 +1
  → 返回 10000，判断 > 10000？否（等于），通过 ❌
  → 实际已有 10001 个连接
```

**为什么不用 `static int` + `volatile`？**

```java
// ❌ volatile int 仍然不行！
volatile int count = 0;
count++;  // read → +1 → write 三步，volatile 只保证可见性，不保证原子性

// ❌ synchronized 也可以，但性能不如 AtomicInteger
synchronized void increment() { count++; }  // 重量级锁，高并发下有性能损耗
```

| 方案 | 线程安全？ | 性能 |
|------|-----------|------|
| `int` 普通变量 | ❌ | 快但数据错 |
| `volatile int` + `++` | ❌（volatile 不保证原子性） | 快但数据错 |
| `synchronized` | ✅ | 有锁开销 |
| `AtomicInteger` | ✅ | ✅ 无锁，CAS 实现，最推荐 |

### 3.6 限流策略选择

| 策略 | 说明 | 适用场景 |
|------|------|----------|
| **固定窗口** | 每秒最多 N 个请求 | 简单限流 |
| **滑动窗口** | 最近 1 秒最多 N 个请求 | 更平滑的限流 |
| **令牌桶** | 以固定速率生成令牌，请求消耗令牌 | **最常用**，允许短时突发 |
| **漏桶** | 以固定速率处理请求，多余排队或丢弃 | 平滑流量 |

---

## 四、直播视频流处理

### 4.1 视频流 vs 消息流的本质区别

前面讲的粘包/拆包、帧解码都是针对**消息模式**（聊天、RPC），
但直播视频流是**流模式**，两者处理逻辑完全不同。

```
消息模式（聊天 / RPC）：
  ┌──────┐  ┌──────┐  ┌──────┐
  │ 消息1 │  │ 消息2 │  │ 消息3 │
  └──────┘  └──────┘  └──────┘
  有明确的"一条消息"边界
  → 需要帧解码器界定边界
  → 攒齐一条才往下传
  → 核心问题：消息完整性

流模式（视频 / 音频）：
  ┌──────────────────────────────────────────────┐
  │  连续的、巨大的、无边界的数据流               │
  │  ═══════════════════════════════════════      │
  │  (每秒几 MB，不是"一条一条"的)               │
  └──────────────────────────────────────────────┘
  没有"一条消息"的概念
  → 不需要帧解码器
  → 不需要攒齐再传，收到就立刻推
  → 核心问题：数据连续性 + 缓冲区管理
```

### 4.2 视频流的 Pipeline 配置

```java
// 视频流不需要帧解码器！
pipeline.addLast("handler", new VideoStreamHandler());

// 消息流才需要：
// pipeline.addLast("frameDecoder", new LengthFieldBasedFrameDecoder(1024));
// pipeline.addLast("handler", new MessageHandler());
```

### 4.3 视频流 Handler：直接透传

```java
public class VideoStreamHandler extends ChannelDuplexHandler {

    @Override
    public void channelRead(ChannelHandlerContext ctx, Object msg) {
        ByteBuf data = (ByteBuf) msg;

        // 不做粘包处理
        // 不等待"凑齐"
        // 收到多少，传多少
        ctx.fireChannelRead(data.retain());
    }
}
```

**对比消息流 Handler**：

| | 消息流 | 视频流 |
|---|--------|--------|
| 帧解码器 | ✅ 需要 `LengthFieldBasedFrameDecoder` | ❌ 不需要 |
| 粘包处理 | ✅ 攒齐完整消息才 fire | ❌ 不需要 |
| 数据传递 | 逐条 fire | 收到就传 |
| 核心关注 | 消息边界 | 缓冲区管理 + 背压 |

### 4.4 视频流最核心的问题：背压

背压 = 生产速度和消费速度不匹配时怎么办。

```
编码器（生产者）  →  内存缓冲区  →  客户端（消费者）

编码器速度快，客户端速度慢：
  缓冲区不断积压
  → 内存撑爆 → OOM
  → 延迟越来越大 → 直播卡顿

编码器速度慢，客户端速度快：
  缓冲区被读空
  → 断流 → 花屏
```

### 4.5 三种背压处理策略

#### 策略一：丢弃旧帧（保实时性）

```java
// 适用于直播场景：宁可丢旧帧，也要保留最新帧，保证延迟恒定
public class VideoStreamHandler extends ChannelDuplexHandler {

    // 🔑 用 ArrayBlockingQueue 模拟"丢旧保新"的环形缓冲区
    // 满时调用 poll() 取出最旧的帧，再 offer() 放入新帧
    private final ArrayBlockingQueue<ByteBuf> ringBuffer = new ArrayBlockingQueue<>(100);

    @Override
    public void channelRead(ChannelHandlerContext ctx, Object msg) {
        ByteBuf data = (ByteBuf) msg;

        // 🔑 先 retain，保证 Pipeline 尾节点 auto-release 后 Queue 仍持有引用
        // refCnt: 1 → 2
        data.retain();

        if (!ringBuffer.offer(data)) {
            // offer 返回 false = 缓冲区满了
            // 此时 data 仍然有效（retain 过，没 release 过），refCnt = 2

            // 取出最旧帧释放，腾出空间
            ByteBuf oldest = ringBuffer.poll();
            if (oldest != null) {
                ReferenceCountUtil.release(oldest);
            }

            // 直接再次入队，data 从未被释放过
            ringBuffer.offer(data);
        }
        // refCnt = 2, Queue 持有一个引用
        // Pipeline 尾节点自动 release → refCnt = 1, Queue 仍然有效
    }
}
```

**为什么 `retain()` 一次就够了？**

```
入口:  data.refCnt() = 1
  │
  ▼
data.retain()               → refCnt = 2（我们保留了一个引用）
  │
  ▼
offer(data) 成功            → Queue 持有引用
  │
  ▼
Pipeline 尾节点 auto-release → refCnt = 1（Queue 仍有效 ✅）
  │
  ▼
poll() + fireChannelRead()  → Pipeline 尾节点 auto-release → refCnt = 0（释放 ✅）

如果 offer 失败:
  │
  ▼
data 仍然 refCnt = 2（从未 release 过）
  │
  ▼
poll() 取出旧帧 → release() → 腾出空间
  │
  ▼
offer(data) 成功            → Queue 持有引用
  │
  ▼
Pipeline 尾节点 auto-release → refCnt = 1（Queue 仍有效 ✅）
```

**错误写法对比**：

```java
// ❌ 释放后立即重用——技术正确但危险
data.retain();              // refCnt = 2
if (!ringBuffer.offer(data)) {
    ReferenceCountUtil.release(data);  // refCnt = 1 ← 卡在 1，没到 0 所以能用
    // 但只要有人改代码（比如忘记上面的 retain），这里就变成 refCnt = 0，内存泄漏！
    ByteBuf oldest = ringBuffer.poll();
    ReferenceCountUtil.release(oldest);
    data.retain();          // refCnt = 2 ← 重新 retain
    ringBuffer.offer(data);
}

// ✅ 正确写法——retain 一次，不 release
data.retain();              // refCnt = 2
if (!ringBuffer.offer(data)) {
    ByteBuf oldest = ringBuffer.poll();
    ReferenceCountUtil.release(oldest);
    ringBuffer.offer(data); // data 从未被释放，直接入队
}
```

```
环形缓冲区（RingBuffer）：

满时：
┌───┬───┬───┬───┬───┐
│ 1 │ 2 │ 3 │ 4 │ 5 │  ← 5 号帧覆盖 1 号帧
└───┴───┴───┴───┴───┘

效果：缓冲区永远只保留最新的 N 帧，延迟恒定
代价：客户端可能看到跳帧（不连续）
```

| 优点 | 缺点 |
|------|------|
| 延迟恒定，实时性好 | 丢帧，画面可能跳变 |
| 内存有界，不会 OOM | 弱网场景体验差 |
| 实现简单 | |
| **适合：实时直播、视频会议** | |

#### 策略二：拒绝新数据（保完整性）

```java
// 适用于录播/推流场景：宁可延迟，也不能丢数据
public class VideoStreamHandler extends ChannelDuplexHandler {

    private final int maxBufferSize = 10 * 1024 * 1024;  // 10MB
    private int currentBufferSize = 0;

    @Override
    public void channelRead(ChannelHandlerContext ctx, Object msg) {
        ByteBuf data = (ByteBuf) msg;

        if (currentBufferSize + data.readableBytes() > maxBufferSize) {
            // 缓冲区快满了 → 拒绝接收新数据
            // 通知上游降低编码速度
            ReferenceCountUtil.release(data);
            return;
        }

        currentBufferSize += data.readableBytes();
        ctx.fireChannelRead(data);
    }
}
```

| 优点 | 缺点 |
|------|------|
| 数据完整，不丢帧 | 延迟会持续增长 |
| 适合弱网环境 | 极端情况下延迟不可控 |
| **适合：录播、延迟要求不高的直播** | |

#### 策略三：动态码率控制（最优雅）

```
根据缓冲区水位动态调整编码器码率：

缓冲区水位低（< 30%）：
  → 提高码率 → 提升画质

缓冲区水位高（> 70%）：
  → 降低码率 → 减少数据量

        高码率 ──────────────┐
                             │
        码率  ───────────────┤
                             │
        低码率 ──────────────┘
              低水位    高水位
                缓冲区水位
```

```java
// 伪代码：根据缓冲区水位调节码率
public class AdaptiveRateHandler extends ChannelDuplexHandler {

    private final Encoder encoder;
    private final BufferMonitor monitor;

    @Override
    public void channelRead(ChannelHandlerContext ctx, Object msg) {
        int waterLevel = monitor.getWaterLevel();  // 0~100%

        if (waterLevel > 70) {
            encoder.setBitrate(encoder.getBitrate() * 0.9);  // 降码率
        } else if (waterLevel < 30) {
            encoder.setBitrate(encoder.getBitrate() * 1.1);  // 升码率
        }

        ctx.fireChannelRead(msg);
    }
}
```

| 优点 | 缺点 |
|------|------|
| 延迟和画质自动平衡 | 实现最复杂 |
| 适应网络波动 | 需要编码器支持动态码率 |
| **适合：商业直播平台** | |

### 4.6 消息流 vs 视频流 对比总结

```
┌─────────────────────────────────────────────────────────────┐
│                    两种数据处理模型                            │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  维度              消息流              视频流                │
│  ──────────────────────────────────────────────             │
│  数据特点          有边界、小、离散     无边界、大、连续       │
│  帧解码器          ✅ 必须              ❌ 不需要             │
│  粘包/拆包         ✅ 要处理             ❌ 不适用            │
│  攒齐再传          ✅ 是                ❌ 收到就传           │
│  核心问题          消息完整性            缓冲区管理 + 背压     │
│  Pipeline 特点     层层解码             层层透传              │
│  丢数据影响        消息丢失              跳帧/花屏            │
│  典型协议          HTTP、RPC            RTMP、HLS、WebRTC    │
│  典型应用          聊天、IM、API         直播、视频会议        │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 4.7 视频流常见的传输协议

| 协议 | 延迟 | 特点 | 适用场景 |
|------|------|------|----------|
| **RTMP** | 3~5s | 成熟稳定，推流标准 | 主播推流到服务器 |
| **HLS** | 10~30s | 基于 HTTP，CDN 友好 | 大规模分发（优酷/爱奇艺） |
| **WebRTC** | < 500ms | 超低延迟，P2P | 视频会议、互动直播 |
| **FLV** | 1~3s | Flash 遗留，被 Web 广泛支持 | Web 端低延迟直播 |

---

## 五、百万 IoT 连接场景

### 5.1 线程模型是否适用？

IoT 场景下服务器需要连接百万级设备，Netty 的线程模型**完全适用**，而且本身就是为这种场景设计的。

**核心推演**：

```
100 万 IoT 设备，每台每 30 秒发一次心跳 + 偶尔上报数据
16 个 EventLoop（8 核 CPU × 2）
→ 每个 EventLoop 管理 62,500 个 Channel

每个 Channel 的数据几秒到几十秒才来一次
→ 99.9% 的时间，Channel 没有 IO 事件
→ Selector 只处理有事件的 Channel
→ 每个 EventLoop 实际每秒处理的事件很少
```

**瓶颈不在线程数，而在内存和文件描述符**：

```
BIO 模型（百万连接）：
  100 万个线程，每个 1MB 栈 = 1TB 内存 ❌ 不可能

Netty 模型（百万连接）：
  16 个线程，每个 1MB 栈 = 16MB 内存
  + 每个 Channel 约 1~2KB（Channel + Pipeline + Buffer）
  = 16MB + 100万 × 2KB ≈ 2GB 内存 ✅ 可行
```

> **核心原因**：一个线程通过 Selector 多路复用管理 N 个 Channel，线程数不随连接数增长。

### 5.2 三个需要解决的工程问题

#### 问题一：文件描述符限制

```
Linux 默认每个进程最多 1024 个 FD

需要调整：
  ulimit -n 2000000          # 用户级限制
  sysctl fs.file-max=5000000 # 系统级限制
```

#### 问题二：海量 Channel 的内存开销

```java
// 每个 Channel 的内存组成：
Channel 对象      ~500 bytes
ChannelPipeline   ~200 bytes
每个 Handler       ~100 bytes
ByteBuf 缓冲区     ~1KB（默认）
Socket 缓冲区      ~4KB（OS 内核）
─────────────────────────────
总计              ~6KB / Channel

100 万 × 6KB = 6GB 内存
```

**优化方向**：

```java
// 1. 减少 Handler 数量（每个 Handler 都占内存）
pipeline.addLast("business", new SimpleBusinessHandler());  // 一个就够了

// 2. 使用较小的 ByteBuf
bootstrap.childOption(ChannelOption.SO_RCVBUF, 2048);  // 减小接收缓冲区
bootstrap.childOption(ChannelOption.SO_SNDBUF, 2048);  // 减小发送缓冲区

// 3. 使用 Epoll（Linux 专属，性能更好）
EventLoopGroup group = new EpollEventLoopGroup();
```

#### 问题三：海量心跳的定时器压力

```
100 万连接，每 30 秒一次心跳
→ 每秒约 33,333 次心跳事件

如果每个连接都用 IdleStateHandler：
  100 万个 IdleStateHandler 对象 → 内存爆炸

解决方案：不在每个 Channel 上挂 IdleStateHandler，
而是用一个全局的心跳扫描器
```

```java
// ❌ 错误：每个 Channel 都挂一个 IdleStateHandler
pipeline.addLast(new IdleStateHandler(60, 0, 0));  // 100 万个 = 内存爆炸

// ✅ 正确：全局心跳扫描器
public class GlobalHeartbeatDetector {
    // 使用 HashedWheelTimer 或 ScheduledExecutorService
    private final ConcurrentHashMap<ChannelId, Long> lastActiveTime = new ConcurrentHashMap<>();
    private final ConcurrentHashMap<ChannelId, Channel> channelMap = new ConcurrentHashMap<>();

    public void register(Channel channel) {
        lastActiveTime.put(channel.id(), System.currentTimeMillis());
        channelMap.put(channel.id(), channel);
    }

    public void updateActivity(Channel channel) {
        lastActiveTime.put(channel.id(), System.currentTimeMillis());
    }

    public void start() {
        ScheduledExecutorService scheduler = Executors.newSingleThreadScheduledExecutor();
        scheduler.scheduleAtFixedRate(() -> {
            long now = System.currentTimeMillis();
            lastActiveTime.forEach((id, lastTime) -> {
                if (now - lastTime > 60_000) {
                    Channel channel = channelMap.remove(id);
                    lastActiveTime.remove(id);
                    if (channel != null) channel.close();
                }
            });
        }, 30, 30, TimeUnit.SECONDS);
    }
}
```

### 5.3 优化对比表

| 维度 | 默认 Netty 配置 | 百万 IoT 优化后 |
|------|---------------|---------------|
| 线程数 | 16（不变） | 16（不变） |
| 文件描述符 | 1024 | 2000000（需调 ulimit） |
| 心跳检测 | 每个 Channel 的 IdleStateHandler | 全局扫描器 |
| 内存（单 Channel） | ~6KB | ~3KB（减 Handler + 减 Buffer） |
| 内存（百万 Channel） | ~6GB | ~3GB |
| CPU | 低（IoT 数据低频） | 低（大部分 Channel 空闲） |
| **结论** | ✅ | ✅ 可行但需优化 |

### 5.4 为什么 Netty 的线程模型在 IoT 场景下是正确的

```
IoT 场景的特点：
  1. 连接数巨大（百万级）
  2. 单连接数据量极小（几十字节/次）
  3. 数据频率极低（几秒到几分钟一次）
  4. 长连接为主

Netty 的线程模型天然匹配：
  1. 一个线程管理 N 个 Channel → 连接数大无压力 ✅
  2. 数据量小 → 单次 IO 处理快 ✅
  3. 频率低 → Selector 大部分时间空转 ✅
  4. 长连接 → Channel 生命周期长，不需要频繁创建销毁 ✅
```

**瓶颈不在 Netty 的线程模型，而在内存、FD 和心跳管理。**