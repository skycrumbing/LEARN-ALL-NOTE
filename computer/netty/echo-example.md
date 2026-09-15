# Echo 示例：短连接 vs 长连接

> 用同一个 Echo（回声）业务，写**两套完全独立**的 Netty 服务端和客户端。
> 唯一的区别就是"连接是关还是留"——所有本质差异都从代码里自然浮现。

---

## 目录

1. [短连接：服务端 A + 客户端 A](#一短连接服务端-a--客户端-a)
2. [长连接：服务端 B + 客户端 B](#二长连接服务端-b--客户端-b)
3. [本质区别：从代码到原理](#三本质区别从代码到原理)
4. [长连接如何保证"不断开"](#四长连接如何保证不断开)

---

## 协议约定

两套示例都用最简单的**行分隔协议**：每条消息以 `\n` 结尾。
Netty 用 `LineBasedFrameDecoder` + `StringDecoder` + `StringEncoder` 三件套处理粘包/拆包。

```java
// 通用的 Pipeline 初始化（两套示例都用）
ch.pipeline()
  .addLast(new LineBasedFrameDecoder(1024))   // 按行切分
  .addLast(new StringDecoder(CharsetUtil.UTF_8))   // ByteBuf → String
  .addLast(new StringEncoder(CharsetUtil.UTF_8));  // String → ByteBuf
```

> 后面的代码中，`ch.pipeline()` 都会先加上这三件套，再接业务 handler。

---

## 一、短连接：服务端 A + 客户端 A

> **核心特征**：服务端应答完立即 `close()`；客户端每次请求都新建连接，收完响应也关。

### 1.1 服务端 A：收到 → 回显 → 关闭

```java
public class ShortServer {

    public static void main(String[] args) throws Exception {
        EventLoopGroup bossGroup = new NioEventLoopGroup(1);
        EventLoopGroup workerGroup = new NioEventLoopGroup();

        try {
            ServerBootstrap bootstrap = new ServerBootstrap();
            bootstrap.group(bossGroup, workerGroup)
                     .channel(NioServerSocketChannel.class)
                     .childHandler(new ChannelInitializer<SocketChannel>() {
                         @Override
                         protected void initChannel(SocketChannel ch) {
                             ch.pipeline()
                               .addLast(new LineBasedFrameDecoder(1024))
                               .addLast(new StringDecoder(CharsetUtil.UTF_8))
                               .addLast(new StringEncoder(CharsetUtil.UTF_8))
                               .addLast(new ShortServerHandler());  // 业务 handler
                         }
                     });

            ChannelFuture future = bootstrap.bind(8888).sync();
            System.out.println("短连接服务端启动，端口 8888");
            future.channel().closeFuture().sync();
        } finally {
            bossGroup.shutdownGracefully();
            workerGroup.shutdownGracefully();
        }
    }
}

// 业务 handler：核心就两行
class ShortServerHandler extends SimpleChannelInboundHandler<String> {

    @Override
    protected void channelRead0(ChannelHandlerContext ctx, String msg) {
        System.out.println("Server A 收到: " + msg);

        // 回显
        ctx.writeAndFlush("Echo: " + msg + "\n");

        // ★★★ 短连接的核心：应答完立即关闭 ★★★
        ctx.close();
    }

    @Override
    public void exceptionCaught(ChannelHandlerContext ctx, Throwable cause) {
        cause.printStackTrace();
        ctx.close();
    }
}
```

### 1.2 客户端 A：每次请求都新建连接 → 发 → 收 → 关

Netty 是**事件驱动**的，客户端接收响应要靠 pipeline 里的 handler 回调，而不是同步调用 `channel.read()`。
下面用 `BlockingQueue` 把异步响应"桥接"回同步代码：

```java
public class ShortClient {

    public static void main(String[] args) throws Exception {
        // 模拟 3 次独立请求，每次都走完整的"建连-发-收-断连"
        for (int i = 1; i <= 3; i++) {

            // ★★★ 短连接的核心：每次请求都新建 EventLoopGroup + Bootstrap ★★★
            EventLoopGroup group = new NioEventLoopGroup(1);
            BlockingQueue<String> responses = new LinkedBlockingQueue<>();

            Bootstrap bootstrap = new Bootstrap();
            bootstrap.group(group)
                     .channel(NioSocketChannel.class)
                     .handler(new ChannelInitializer<SocketChannel>() {
                         @Override
                         protected void initChannel(SocketChannel ch) {
                             ch.pipeline()
                               .addLast(new LineBasedFrameDecoder(1024))
                               .addLast(new StringDecoder(CharsetUtil.UTF_8))
                               .addLast(new StringEncoder(CharsetUtil.UTF_8))
                               .addLast(new ChannelInboundHandlerAdapter() {
                                   @Override
                                   public void channelRead(ChannelHandlerContext ctx, Object msg) {
                                       // 收到响应 → 放进队列 → 关闭连接
                                       responses.offer((String) msg);
                                       ctx.close();   // ★★★ 短连接：收到就关 ★★★
                                   }
                               });
                         }
                     });

            // 建连
            Channel channel = bootstrap.connect("localhost", 8888).sync().channel();

            // 发
            channel.writeAndFlush("Hello " + i + "\n").sync();

            // 收（阻塞等待 handler 把响应放进队列）
            String response = responses.take();
            System.out.println("Client A 第 " + i + " 次响应: " + response);

            // 等连接真正关闭后，再进入下一次循环
            channel.closeFuture().sync();
            group.shutdownGracefully();

            Thread.sleep(500);  // 模拟请求间隔
        }
    }
}
```

### 1.3 短连接交互时序

```
Client A                          Server A
   │                                │
   │────── TCP 三次握手 ──────────►  │  ← 第 1 次建连
   │                                │
   │────── "Hello 1\n" ──────────► │
   │                                │
   │                                │── 应用层: ctx.close()
   │                                │   close 内部两步:
   │                                │   ① flush 出站缓冲 ↓
   │◄───── "Echo: Hello 1\n" ──── │     ← ① 的产物：数据先到
   │                                │   ② 内核发 FIN ↓
   │◄────── FIN ① ───────────────  │  ┐  ← ② 的产物：FIN 后到
   │────── ACK ─────────────────► │  │ 四次挥手
   │                                │   客户端应用层也 ctx.close()
   │────── FIN ② ─────────────────► │  │ (close 的第 ② 步)
   │◄────── ACK ─────────────────  │  ┘  ← 第 1 次断连
   │                                │
   │────── TCP 三次握手 ──────────►  │  ← 第 2 次建连（重新握手）
   │                                │
   │────── "Hello 2\n" ──────────► │
   │                                │── 应用层: ctx.close()
   │◄───── "Echo: Hello 2\n" ──── │     (①flush)
   │  ... 同上四次挥手 (②FIN/ACK) ..│  ← 第 2 次断连
   │                                │
   │  ... 第 3 次重复 ...            │
```

> **关键：close() ≠ FIN，close() = flush + 发 FIN**
>
> 时序图里"回显数据"和"FIN ①"不是重复，而是 close() 两步的分别产物：
> - 回显数据 = close 第 ① 步（flush）的结果
> - FIN ① = close 第 ② 步（发 FIN）的结果
>
> 四次挥手是**双向**的：服务端先 `close()` 发 FIN ①，客户端收到响应后又 `close()` 发 FIN ②。两次 close() 各发一个 FIN，凑成完整的四次挥手。

#### 1.3.1 close() 的真实语义：主动关闭，不是"告知对端"

> `ctx.close()` 不是"告知对端可以关"，而是**我方主动关闭**——它是 TCP 四次挥手的发起动作。

`ctx.close()` 内部做的事：

```
1. 触发出站 close 事件，沿 pipeline 向 HEAD 传播
2. 先 flush 出站缓冲区（确保回显数据真的发出去）
3. 调用底层 socket.close()
4. 内核发送 TCP FIN 包   ← 四次挥手的"第一枪"
5. 我方进入 FIN_WAIT_1 状态
```

> 关键：close() 发的是 **FIN**（我方主动关闭），不是许可。对端收到 FIN 后**被动**感知"对方要关了"。
>
> 另一点：close() 会先 flush 待发数据再发 FIN，所以"回显 → close()"的顺序是安全的——对端一定先收到回显数据，再收到 FIN。如果反过来先 close() 再 writeAndFlush()，数据就发不出去了（连接都在关了）。

#### 1.3.2 为什么客户端也要 ctx.close()：CLOSE_WAIT 陷阱

```
服务端先 ctx.close() → 发 FIN ①
  → 客户端内核收到 FIN，回 ACK，进入 CLOSE_WAIT 状态

CLOSE_WAIT = "我方已知对端要关，但我方应用层还没关"的中间态

如果客户端应用层一直不调 ctx.close()：
  ┌ 连接永远卡在 CLOSE_WAIT
  └ 占用 fd 和内存，长期积累导致 fd 耗尽

所以客户端 handler 收到响应后也要 ctx.close() → 发 FIN ②
  → 完成四次挥手，连接真正关闭
```

> 示例里两次 `ctx.close()` 各发一个 FIN：
> - 服务端的 close() 发 FIN ①（服务端先关，因为 handler 里先调）
> - 客户端的 close() 发 FIN ②（收到响应后也关）
>
> 这就是"短连接"的完整关闭流程。

### 1.4 短连接的代价

```
每次请求都要经历：
  TCP 三次握手（1~3 RTT）
  收发数据  （1 RTT）
  TCP 四次挥手（2 RTT）
  ─────────────────────
  合计 4~6 RTT / 每次请求

假设 RTT = 50ms：
  3 次请求 ≈ 3 × 200ms = 600ms
  其中真正用于业务的数据传输只占 1 RTT（50ms）
  其余 150ms 全是协议开销
```

---

## 二、长连接：服务端 B + 客户端 B

> **核心特征**：连接建立后不关闭；客户端在同一连接上连续发多次请求；服务端回显但不关连接。

### 2.1 服务端 B：收到 → 回显 → 不关闭

```java
public class LongServer {

    public static void main(String[] args) throws Exception {
        EventLoopGroup bossGroup = new NioEventLoopGroup(1);
        EventLoopGroup workerGroup = new NioEventLoopGroup();

        try {
            ServerBootstrap bootstrap = new ServerBootstrap();
            bootstrap.group(bossGroup, workerGroup)
                     .channel(NioServerSocketChannel.class)
                     // ★ 长连接必备：开启 TCP keepalive ★
                     .childOption(ChannelOption.SO_KEEPALIVE, true)
                     .childHandler(new ChannelInitializer<SocketChannel>() {
                         @Override
                         protected void initChannel(SocketChannel ch) {
                             ch.pipeline()
                               .addLast(new LineBasedFrameDecoder(1024))
                               .addLast(new StringDecoder(CharsetUtil.UTF_8))
                               .addLast(new StringEncoder(CharsetUtil.UTF_8))
                               // 空闲检测：60s 没收到数据就关（防止假死连接）
                               .addLast(new IdleStateHandler(60, 0, 0, TimeUnit.SECONDS))
                               .addLast(new LongServerHandler());
                         }
                     });

            ChannelFuture future = bootstrap.bind(9999).sync();
            System.out.println("长连接服务端启动，端口 9999");
            future.channel().closeFuture().sync();
        } finally {
            bossGroup.shutdownGracefully();
            workerGroup.shutdownGracefully();
        }
    }
}

// 业务 handler：和短连接的唯一区别就是没有 ctx.close()
class LongServerHandler extends SimpleChannelInboundHandler<String> {

    @Override
    protected void channelRead0(ChannelHandlerContext ctx, String msg) {
        System.out.println("Server B 收到: " + msg);

        // 回显
        ctx.writeAndFlush("Echo: " + msg + "\n");

        // ★★★ 长连接的核心：不关闭，连接继续留着 ★★★
        // 没有 ctx.close()
    }

    @Override
    public void userEventTriggered(ChannelHandlerContext ctx, Object evt) {
        if (evt instanceof IdleStateEvent) {
            IdleStateEvent event = (IdleStateEvent) evt;
            if (event.state() == IdleState.READER_IDLE) {
                // 60s 没收到数据 → 判定客户端已走 → 主动关
                System.out.println("检测到空闲连接，主动关闭: " + ctx.channel().remoteAddress());
                ctx.close();
            }
        }
    }

    @Override
    public void exceptionCaught(ChannelHandlerContext ctx, Throwable cause) {
        cause.printStackTrace();
        ctx.close();
    }
}
```

### 2.2 客户端 B：一次连接，连续发多条

```java
public class LongClient {

    public static void main(String[] args) throws Exception {
        // ★★★ 长连接的核心：只建一次连接 ★★★
        EventLoopGroup group = new NioEventLoopGroup(1);
        BlockingQueue<String> responses = new LinkedBlockingQueue<>();

        Bootstrap bootstrap = new Bootstrap();
        bootstrap.group(group)
                 .channel(NioSocketChannel.class)
                 .handler(new ChannelInitializer<SocketChannel>() {
                     @Override
                     protected void initChannel(SocketChannel ch) {
                         ch.pipeline()
                           .addLast(new LineBasedFrameDecoder(1024))
                           .addLast(new StringDecoder(CharsetUtil.UTF_8))
                           .addLast(new StringEncoder(CharsetUtil.UTF_8))
                           .addLast(new ChannelInboundHandlerAdapter() {
                               @Override
                               public void channelRead(ChannelHandlerContext ctx, Object msg) {
                                   // 收到响应 → 放进队列
                                   // ★★★ 不 close！连接继续留着 ★★★
                                   responses.offer((String) msg);
                               }
                           });
                     }
                 });

        // 只连一次
        Channel channel = bootstrap.connect("localhost", 9999).sync().channel();

        // 在同一连接上连续发 3 次请求
        for (int i = 1; i <= 3; i++) {
            channel.writeAndFlush("Hello " + i + "\n");

            // 阻塞等待响应
            String response = responses.take();
            System.out.println("Client B 第 " + i + " 次响应: " + response);

            Thread.sleep(500);  // 模拟间隔，连接保持
        }

        // ★★★ 长连接：所有请求都发完了才关 ★★★
        channel.closeFuture().sync();
        group.shutdownGracefully();
        System.out.println("所有请求完成，连接关闭");
    }
}
```

### 2.3 长连接交互时序

```
Client B                          Server B
   │                                │
   │────── TCP 三次握手 ──────────►  │  ← 建连 1 次
   │                                │
   │────── "Hello 1\n" ──────────► │
   │                                │── 回显（不关！）
   │◄───── "Echo: Hello 1\n" ──── │
   │                                │
   │────── "Hello 2\n" ──────────► │  ← 同一连接继续发
   │                                │── 回显（不关！）
   │◄───── "Echo: Hello 2\n" ──── │
   │                                │
   │────── "Hello 3\n" ──────────► │  ← 同一连接继续发
   │                                │── 回显（不关！）
   │◄───── "Echo: Hello 3\n" ──── │
   │                                │
   │── 应用层: channel.close() ──► │  ← 用完才断连（客户端先关）
   │   close 内部两步:                │
   │   ① flush 出站缓冲（此时无待发数据，空操作）
   │   ② 内核发 FIN ↓
   │────── FIN ① ─────────────────► │  ┐  ← close 第 ② 步的产物
   │◄────── ACK ─────────────────  │  │ 四次挥手
   │                                │   服务端应用层也 close()
   │◄────── FIN ② ─────────────────  │  │ (close 的第 ② 步)
   │────── ACK ─────────────────► │  ┘
```

> 和短连接一样的机制：close() = flush + 发 FIN。
> 长连接里客户端先关，所以 **FIN ① 来自客户端**（和短连接服务端先关相反）。
> 但无论谁先关，close 的两步和四次挥手的双向过程都相同。

> 长连接的四次挥手里，**第一个 FIN 来自客户端**（因为是客户端先调 `channel.close()`），这和短连接相反（短连接服务端先关）。但无论谁先关，四次挥手的双向过程是一样的。

### 2.4 长连接的代价

```
3 次请求总共经历：
  TCP 三次握手  1 次（1~3 RTT）
  收发数据      3 次（3 RTT）
  TCP 四次挥手  1 次（2 RTT）
  ─────────────────────
  合计 6~8 RTT

对比短连接的 12~18 RTT
省了一半，而且请求越多节省越明显
```

---

## 三、本质区别：从代码到原理

### 3.1 一行代码的区别

```
短连接服务端：
    ctx.writeAndFlush("Echo: " + msg + "\n");
    ctx.close();   ← 就这一行

长连接服务端：
    ctx.writeAndFlush("Echo: " + msg + "\n");
    // 没有 ctx.close()

  └ 一行代码，两种模式，性能差一个数量级
```

### 3.2 客户端行为对比

| 行为 | 短连接客户端 A | 长连接客户端 B |
|------|---------------|---------------|
| 建连次数 | 3 次（每次请求都建） | 1 次 |
| EventLoopGroup | 每次请求新建+关闭 | 全程共用一个 |
| Bootstrap | 每次请求新建 | 全程共用一个 |
| 收到响应后 | `ctx.close()` 立即关 | 不关，等下一次 |
| 连接关闭时机 | 每个请求之后 | 所有请求完成之后 |

### 3.3 n 次请求的 RTT 开销公式

```
短连接：n × (握手 + 数据 + 挥手) = n × (4~6 RTT)
长连接：握手 + n × 数据 + 挥手   = (3~5) + n × 1 RTT
```

代入不同 n 值：

| n 次请求 | 短连接开销 | 长连接开销 | 长连接节省 |
|---------|-----------|-----------|-----------|
| 1 | 4~6 RTT | 4~6 RTT | 0%（一样） |
| 10 | 40~60 RTT | 13~15 RTT | ~75% |
| 100 | 400~600 RTT | 103~105 RTT | ~80% |
| 1000 | 4000~6000 RTT | 1003~1005 RTT | ~80% |

> n 越大，长连接的协议开销占比越趋近于 0；短连接则线性增长。

### 3.4 资源层面的区别

假设 1000 个客户端，每个客户端每分钟发 60 条请求（持续 10 分钟 = 600 条）：

```
短连接场景：
  - 同一时刻的并发连接数 = 当前并发请求数（可能上千）
  - 每个连接存活 ~200ms，然后进入 TIME_WAIT（默认 2 分钟）
  - TIME_WAIT 会占端口号（默认约 32768 个可用）
  - 高频请求时端口可能耗尽 → 无法建新连接
  - TCP 建连抖动严重（每分钟上万次握手）

长连接场景：
  - 1000 个客户端 = 1000 条固定连接
  - 0 次 TIME_WAIT（连接不断）
  - 端口数稳定
  - 无建连抖动
  - 代价：服务端要持续维持 1000 条连接的内存和心跳开销
```

### 3.5 选型指南

**用短连接的场景：**

- 请求离散，间隔很长（超过连接空闲超时）
  - 例：定时任务每 24 小时调用一次远程 API
- 设备本身无法维持长连接（极低功耗、需即时休眠）
  - 例：NB-IoT 电池传感器，上报完立即深度休眠，无法长期保活
  - 例：DNS 查询、CoAP（UDP 协议，本质无连接）
- 安全/审计敏感，每次请求后必须立即断连
  - 例：银行转账、政务系统的强审计要求
- 一次性数据上报，发完即弃
  - 例：埋点日志批量上传后立即释放资源

> ⚠️ 常见误区："客户端数量极多就该用短连接"——错。
> 千万级 IoT 设备恰恰用长连接（MQTT），因为短连接每分钟千万次握手会让 Broker 被 TIME_WAIT 拖垮。详见第四章 4.4 节。

**用长连接的场景：**

- 高频请求，持续交互
  - 例：微服务间 RPC、游戏服务器
- 服务端需要主动推送
  - 例：WebSocket 聊天、推送通知、实时数据流
- IoT 设备大规模接入与消息推送
  - 例：MQTT（千万设备长连接 + 遗嘱消息 + QoS 持久会话）
- 流式传输，消息大小不确定
  - 例：文件传输、视频流
- 请求-响应需要低延迟
  - 例：高频交易、实时风控
- 客户端数量可控（几百~几万），每个客户端活跃度高
  - 例：Redis、RabbitMQ 客户端连接

---

## 四、长连接如何保证"不断开"

这是长连接最常被问到的问题——TCP 建立后，双方都不主动发消息，怎么知道这条连接还活着？

### 4.1 三层保障机制

```
第一层 · TCP keepalive（内核层）—— 检测"对端主机是否还活着"
  SO_KEEPALIVE 开启后，Linux 默认 7200s 空闲才发探测包
  默认值太长（2 小时），但开启后可调参（见 4.1.1）
  定位：兜底机制，防对端整机崩溃/网络物理中断

第二层 · IdleStateHandler（Netty 应用层）—— 检测"应用是否还响应"
  服务端定期检测连接是否空闲，空闲超时主动关
  客户端定期发心跳，防止被对方判定为"已走"
  定位：主检测，能感知应用层假死，可携带业务信息

第三层 · 重连机制（业务层）—— 检测"连接是否已断"
  连接终究会断（网络波动、服务端重启）
  客户端必须能检测断连并自动重连
  定位：恢复机制，让长连接"看起来"始终可用
```

#### 4.1.1 TCP keepalive 不是"没用"，是"默认参数不合适"

```
应用层心跳管：应用层是否活着
TCP keepalive 管：对端主机是否活着

两者是不同层面，互补关系，不是二选一：

  应用层心跳能检测：
    服务端应用挂了，但 socket 还在 → 心跳发不出，对方感知到

  TCP keepalive 才能检测（应用层无能为力）：
    对端整机崩溃（断电、kernel panic）
    网络物理中断（网线拔了、路由器挂了）
    → 此时应用层根本没机会发心跳（进程都死了，谁来调 write？）
    → 只能靠内核层的 TCP 探测包去试
```

Linux 开启 `SO_KEEPALIVE` 后有三个可调参数（默认值太长，但可调短）：

| 参数 | 含义 | 默认值 |
|------|------|--------|
| `TCP_KEEPIDLE` | 空闲多久后开始发探测 | 7200s（2 小时） |
| `TCP_KEEPINTVL` | 探测包间隔 | 75s |
| `TCP_KEEPCNT` | 探测失败几次判定死亡 | 9 次 |

```java
// Netty 在 Linux 上用 EpollChannelOption 调这三个参数
Bootstrap b = new Bootstrap();
b.group(group)
 .channel(EpollSocketChannel.class)   // 用 Epoll 才能设这些参数
 .option(ChannelOption.SO_KEEPALIVE, true)
 .option(EpollChannelOption.TCP_KEEPIDLE, 60)   // 60s 空闲开始探测
 .option(EpollChannelOption.TCP_KEEPINTVL, 10)  // 每 10s 探一次
 .option(EpollChannelOption.TCP_KEEPCNT, 3);     // 探 3 次失败判定死亡
// （JDK 9+ 也可用 ExtendedSocketOptions.TCP_KEEPIDLE）
```

#### 4.1.2 为什么 TCP keepalive 和应用层心跳要都开

```
TCP keepalive 的局限                    应用层心跳的补充
─────────────────────────────────────────────────────────
默认参数太长（2h）                      间隔可配（10s/30s）
只探测 TCP 层                          能探测应用层是否响应
NAT/防火墙可能伪造探测结果              业务数据交互更可靠
无法携带业务信息                        可带版本号、负载、状态
内核实现，改不了业务逻辑                完全自定义
─────────────────────────────────────────────────────────
应用层心跳的局限                        TCP keepalive 的补充
─────────────────────────────────────────────────────────
应用挂了/线程阻塞就发不出               内核兜底，只要 socket 在就探
对端整机崩溃时无能为力                  这正是 TCP keepalive 的主场
─────────────────────────────────────────────────────────

正确姿势：两层都开
  TCP keepalive 调短参数做兜底（防整机崩溃）
  应用层心跳做主检测（防应用假死 + 携带业务信息）
```

### 4.2 完整的心跳示例

**客户端：30s 没发数据就主动发一个 PING**

```java
ch.pipeline()
  .addLast(new LineBasedFrameDecoder(1024))
  .addLast(new StringDecoder(CharsetUtil.UTF_8))
  .addLast(new StringEncoder(CharsetUtil.UTF_8))
  // writerIdleTime = 30s：30s 没写数据就触发事件
  .addLast(new IdleStateHandler(0, 30, 0, TimeUnit.SECONDS))
  .addLast(new ChannelInboundHandlerAdapter() {
      @Override
      public void userEventTriggered(ChannelHandlerContext ctx, Object evt) {
          if (evt instanceof IdleStateEvent) {
              IdleStateEvent event = (IdleStateEvent) evt;
              if (event.state() == IdleState.WRITER_IDLE) {
                  // 30s 没发数据 → 主动发心跳
                  ctx.writeAndFlush("PING\n");
              }
          }
      }

      @Override
      public void channelRead(ChannelHandlerContext ctx, Object msg) {
          String s = (String) msg;
          if ("PONG".equals(s)) {
              // 收到服务端心跳响应 → 连接正常
          }
      }

      @Override
      public void channelInactive(ChannelHandlerContext ctx) {
          // ★ 连接断开 → 触发重连 ★
          System.out.println("连接断开，5s 后重连");
          ctx.executor().schedule(() -> {
              // 重新建连逻辑
          }, 5, TimeUnit.SECONDS);
      }
  });
```

**服务端：60s 没收到数据就主动关**

```java
ch.pipeline()
  .addLast(new LineBasedFrameDecoder(1024))
  .addLast(new StringDecoder(CharsetUtil.UTF_8))
  .addLast(new StringEncoder(CharsetUtil.UTF_8))
  // readerIdleTime = 60s：60s 没收到数据就触发事件
  .addLast(new IdleStateHandler(60, 0, 0, TimeUnit.SECONDS))
  .addLast(new ChannelInboundHandlerAdapter() {
      @Override
      public void channelRead(ChannelHandlerContext ctx, Object msg) {
          String s = (String) msg;
          if ("PING".equals(s)) {
              ctx.writeAndFlush("PONG\n");  // 回心跳
          } else {
              // 正常业务消息
          }
      }

      @Override
      public void userEventTriggered(ChannelHandlerContext ctx, Object evt) {
          if (evt instanceof IdleStateEvent) {
              IdleStateEvent event = (IdleStateEvent) evt;
              if (event.state() == IdleState.READER_IDLE) {
                  // 60s 没收到数据 → 判定客户端已走 → 主动关
                  System.out.println("客户端长时间无心跳，关闭连接");
                  ctx.close();
              }
          }
      }
  });
```

### 4.3 userEventTriggered 的本质

> 上面心跳示例里，`IdleStateHandler` 检测到空闲后，是通过 `userEventTriggered` 把信号传给业务 handler 的。
> 这个回调的本质是什么？为什么不用 `channelRead` 传？

#### 一句话本质

> `userEventTriggered` 是 Netty Pipeline 里**和"数据读写"并列的另一条事件通道**——专门走"非网络数据"的控制信号。

#### Pipeline 里有两条独立的事件通道

```
Pipeline 是一条双向链表，挂着所有 handler。
事件在上面传播有两条通道：

┌─────────────────────────────────────────────────────────────┐
│  通道一：数据事件（由 socket IO 触发）                          │
│  ──────────────────────────────────                          │
│  socket 有数据 → channelRead      → handler A → B → C        │
│  socket 可写   → channelWritabilityChanged → A → B → C       │
│  连接建立      → channelActive    → A → B → C                 │
│  连接断开      → channelInactive  → A → B → C                 │
│                                                              │
│  特点：触发源是底层网络事件，和"字节"强相关                     │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  通道二：自定义事件（由代码触发）                               │
│  ──────────────────────────────────                          │
│  IdleStateHandler 定时器到点 → fireUserEventTriggered        │
│                                 → 下游 handler B → C        │
│  业务代码主动调用 → ctx.fireUserEventTriggered(myEvent)     │
│                                 → 下游 handler B → C        │
│                                                              │
│  特点：触发源是"定时器"或"业务代码"，和字节无关                │
└─────────────────────────────────────────────────────────────┘

两条通道共用同一条 pipeline，但事件类型不同，
handler 用不同的回调方法接收。
```

#### 接口层面的平级关系

看 `ChannelInboundHandler` 接口，`userEventTriggered` 和 `channelRead` 是**平级的入站回调**：

```java
public interface ChannelInboundHandler {
    void channelRegistered(ChannelHandlerContext ctx, ...);
    void channelActive(ChannelHandlerContext ctx);
    void channelRead(ChannelHandlerContext ctx, Object msg);        // ← 数据通道
    void channelReadComplete(ChannelHandlerContext ctx);
    void userEventTriggered(ChannelHandlerContext ctx, Object evt); // ← 自定义通道
    void channelInactive(ChannelHandlerContext ctx);
    // ...
}
```

唯一区别是**触发源**：`channelRead` 由 socket 数据到达触发，`userEventTriggered` 由代码主动 `fire` 触发。

#### "user" 不是"用户"，是"user-defined"

> 名字里的 "user" 容易被误解为"用户登录的用户"。
> 实际是 **user-defined（用户自定义）** 的意思——即"除标准 IO 事件外，开发者或框架扩展自定义的事件"。
> IdleStateHandler 就是 Netty 框架自己定义的一种 user event。

#### IdleStateHandler 是怎么用这条通道的

```java
// IdleStateHandler 内部（简化）
class IdleStateHandler extends ChannelInboundHandlerAdapter {

    @Override
    public void handlerAdded(ChannelHandlerContext ctx) {
        // 1. 注册时启动一个定时任务
        ctx.executor().scheduleAtFixedRate(() -> {
            if (now - lastReadTime > readerIdleTime) {
                // 2. 空闲超时 → 构造一个事件
                IdleStateEvent event = new IdleStateEvent(IdleState.READER_IDLE);
                // 3. 通过"自定义事件通道"往下游传
                ctx.fireUserEventTriggered(event);
            }
        }, readerIdleTime, readerIdleTime, TimeUnit.SECONDS);
    }

    @Override
    public void channelRead(ChannelHandlerContext ctx, Object msg) {
        lastReadTime = System.nanoTime();  // 数据通道的回调，顺便刷新时间
        ctx.fireChannelRead(msg);          // 数据继续往下游传
    }
}
```

下游业务 handler 用"自定义事件通道"接收：

```java
class MyHandler extends ChannelInboundHandlerAdapter {
    @Override
    public void userEventTriggered(ChannelHandlerContext ctx, Object evt) {
        if (evt instanceof IdleStateEvent) {
            // 收到空闲事件 → 处理
        }
    }
}
```

#### 为什么不直接用 channelRead 传空闲信号？

```
如果硬要用数据通道传：
  ┌ 要么发一条特殊"数据"（如 "IDLE\n"），污染业务协议
  └ 要么在 channelRead 里判断，但空闲事件根本不是 socket 来的数据

userEventTriggered 的设计价值：
  ┌ 把"控制信号"和"业务数据"彻底解耦
  └ 同一条 pipeline 上，两套信号互不干扰
  └ 框架级 handler（如 IdleStateHandler）只产生控制信号，
     不碰业务数据，业务 handler 也不会被它的信号干扰
```

#### 还能用 fireUserEventTriggered 传任意自定义事件

```java
// 业务代码主动发一个自定义事件
public class HandshakeCompleteEvent { ... }

ctx.fireUserEventTriggered(new HandshakeCompleteEvent());

// 下游 handler 接收
@Override
public void userEventTriggered(ChannelHandlerContext ctx, Object evt) {
    if (evt instanceof HandshakeCompleteEvent) {
        // 握手完成 → 启动业务逻辑
    } else if (evt instanceof IdleStateEvent) {
        // 空闲 → 关连接
    }
}
```

> TLS 握手完成、登录鉴权通过、连接迁移……这些"非数据"的状态变更，都用这条通道。

---

### 4.4 为什么要用应用层心跳，而不是只靠 TCP keepalive？

```
TCP keepalive 的三个致命缺陷：

1. 默认 7200s（2 小时）才发第一次探测
   服务端进程挂了，客户端要等 2 小时才知道

2. TCP keepalive 只探测 TCP 层
   服务端应用挂了，TCP 层可能还"活着"（半开连接）
   → TCP 探测能过，应用探测才暴露问题

3. 防火墙 / NAT 会主动关闭长期空闲连接
   但不会通知客户端 → 客户端下次发数据才发现

应用层心跳解决这些问题：
- 心跳间隔可配（10s / 30s / 60s），不依赖操作系统默认值
- 应用挂了，心跳自然发不出 → 对方立即感知
- 心跳还可以携带业务数据（版本号、状态、负载等）
```

### 4.5 工业级范例：MQTT 的长连接设计

MQTT 是为长连接而生的协议，它的设计印证了前面讲的所有保活原理——协议层 KeepAlive、遗嘱兜底、持久会话补发，全部做进了协议本身。

**MQTT 的连接生命周期**

```
MQTT 设备                          Broker
   │                                  │
   │──── TCP 三次握手 ──────────────►  │  ← 建连 1 次
   │──── TLS 握手（MQTTS, 8883）────►  │  ← 可选
   │──── CONNECT ────────────────────►│  ← 应用层握手
   │     (ClientID, KeepAlive=60,     │     含保活承诺 + 遗嘱
   │      Will, 用户名/Token)          │
   │◄──── CONNACK ───────────────────│
   │                                  │
   │──── SUBSCRIBE topic ───────────►│  ← 订阅
   │◄──── SUBACK ────────────────────│
   │                                  │
   │──── PUBLISH ────────────────────►│  ← 上报
   │◄──── PUBLISH（推送）─────────────│  ← 服务端主动推
   │  ... 同一连接持续数小时/数天 ...   │
   │                                  │
   │── PINGREQ（心跳，仅 2 字节）──────►│  ← 空闲时保活
   │◄── PINGRESP ────────────────────│
   │                                  │
   │── DISCONNECT ───────────────────►│  ← 正常断开
   │──── TCP 四次挥手 ──────────────►  │
```

**MQTT 为长连接做的三件事**

```
① Keep Alive：协议层保活承诺
   CONNECT 包里带 KeepAlive 字段（秒）
   → 客户端承诺"我至少每 60s 发一次报文"
   → Broker 在 1.5 × KeepAlive 内没收到任何报文 → 判定掉线
   → 空闲时发 PINGREQ（2 字节）兑现承诺

② Last Will and Testament：遗嘱消息（断连兜底）
   CONNECT 时带一条遗嘱："如果我掉线，请帮我发布 X 到 topic Y"
   触发条件：
     ├── KeepAlive 超时
     ├── TCP 异常断开
     └── 设备崩溃没来得及 DISCONNECT
   → Broker 自动发布遗嘱 → 其他订阅者立即感知设备掉线
   → 这正是前面 4.2 节"心跳检测断连"的协议级实现

③ QoS + 持久会话：弥补断连期间的消息
   QoS 1/2 + Clean Session = false
   → 设备掉线期间，Broker 持续为它缓存消息
   → 设备重连后，Broker 补发掉线期间的消息
   → 即使长连接断了一段时间，消息也不丢
```

**为什么千万级 IoT 反而必须用长连接**

```
假设千万设备，每分钟上报 1 次：

短连接方案（每条消息建一次连接）:
  千万次/分钟 × TCP 握手
  → Broker 每分钟处理 1000 万次握手
  → TIME_WAIT 状态爆炸（每个断连占一个端口/内存）
  → 端口和 fd 耗尽 → 实际撑不住

MQTT 长连接方案:
  千万设备 × 1 条持久连接
  → Broker 单机百万连接（EMQX/VerneMQ 就为此设计）
  → 集群化后千万连接可承载
  → 空闲时心跳流量极小（PINGREQ 2 字节）
  → 这才是真实 IoT 大规模场景的解法
```

> 结论：MQTT 把"长连接 + 心跳保活 + 断连兜底 + 消息补发"四件套做进了协议本身。
> 它印证了第三章的选型结论——大规模 IoT 是长连接的典型主场，不是短连接。

### 4.6 一句话总结

```
短连接：每次请求 = 完整 TCP 生命周期
        协议开销随请求数线性增长
        适合"低频 + 安全敏感"的场景

长连接：N 次请求 = 1 次 TCP 生命周期 + N 次数据收发
        协议开销被 N 摊薄到趋近于 0
        适合"高频 + 推送 + 低延迟"的场景
        但必须配套心跳检测 + 重连机制
```
