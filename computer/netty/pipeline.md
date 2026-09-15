# Pipeline 与 ChannelHandler 责任链

## 一、什么是 Pipeline

```
                    ChannelPipeline

        入站 Inbound（网络 → 应用）：数据从左向右流
        ==========================================>
                         │
  ┌────────┐  ┌────────┐  ┌────────┐  ┌────────┐
  │  HEAD  │──│HandlerA│──│HandlerB│──│  TAIL  │
  │(Inbound│  │        │  │        │  │(Outbound│
  │ 入口)  │  │        │  │        │  │ 入口)  │
  └────────┘  └────────┘  └────────┘  └────────┘
                         │
        出站 Outbound（应用 → 网络）：数据从右向左流
        <==========================================
```

> **双向链表**：每个 Handler 节点都有 `prev` 和 `next` 指针，可以从 HEAD 顺链到 TAIL，也可以从 TAIL 逆链回 HEAD。
> 入站和出站的区别是**遍历方向不同**，不是箭头类型不同。

```
入站（数据从网络流入）：

  HEAD  ──fireChannelRead──►  HandlerA  ──fireChannelRead──►  HandlerB  ──fireChannelRead──►  TAIL

出站（数据从业务流出）：

  TAIL  ──fireWrite──►  HandlerB  ──fireWrite──►  HandlerA  ──fireWrite──►  HEAD
```

> 注意：这里所有箭头都是 `→`（向右），区别只在于**起点和顺序不同**。
> "双向链表"指的是每个节点的 `prev`/`next` 指针双向可遍历，不是指箭头方向。

## 二、两种 Handler

| 类型 | 方向 | 接口 | 说明 |
|------|------|------|------|
| **InboundHandler** | 入站（网络 → 你） | `ChannelInboundHandler` | 处理读到的数据 |
| **OutboundHandler** | 出站（你 → 网络） | `ChannelOutboundHandler` | 处理写出的数据 |

```
Inbound（读方向）：
  网络 ──► read() ──► HEAD ──► HandlerA ──► HandlerB ──► TAIL ──► 你的业务

Outbound（写方向）：
  你的业务 ──► write() ──► TAIL ──► HandlerB ──► HandlerA ──► HEAD ──► 网络
```

### 常见入站事件

| 事件 | 触发时机 |
|------|----------|
| `channelRegistered()` | Channel 注册到 EventLoop |
| `channelActive()` | 连接建立成功 |
| `channelRead()` | 有数据可读 |
| `channelReadComplete()` | 本次读操作完成 |
| `exceptionCaught()` | 发生异常 |
| `channelInactive()` | 连接关闭 |
| `channelUnregistered()` | Channel 从 EventLoop 注销 |

### 常见出站事件

| 事件 | 触发时机 | 本质 |
|------|----------|------|
| `bind()` | 绑定地址 | 命令 |
| `connect()` | 发起连接 | 命令 |
| `write()` | 写出数据 | 命令 |
| `flush()` | 刷新缓冲区 | 命令 |
| `read()` | 触发一次读取操作 | 命令（不是入站，详见下文） |
| `close()` | 关闭连接 | 命令 |

> **⚠️ 为什么 `read()` 是出站事件？**
>
> `read()` 是**"发起读取"的命令**，不是"收到数据"的结果。
> 它从 TAIL→HEAD 传播，最终到达 Transport 层执行真正的网络读取。
> 读取完成后，数据再通过入站的 `channelRead()` 从 HEAD→TAIL 传回。
>
> Netty 默认每次循环自动 read，不需要手动调用。
> 只有需要**手动控制读取时机**（如限流、背压、协议协商）时才用 `ctx.read()`。

## 三、责任链的传递

```java
// 定义一个入站 Handler
public class MyInboundHandler extends ChannelInboundHandlerAdapter {
    @Override
    public void channelRead(ChannelHandlerContext ctx, Object msg) {
        System.out.println("HandlerA 收到: " + msg);

        // 🔑 关键：手动调用 fireChannelRead 传递给下一个 Handler
        // 不调用 = 责任链中断，后续 Handler 收不到数据
        ctx.fireChannelRead(msg);
    }

    @Override
    public void exceptionCaught(ChannelHandlerContext ctx, Throwable cause) {
        System.err.println("异常: " + cause.getMessage());
        ctx.close();  // 发生异常时关闭连接
    }
}
```

### 入站传播

```java
// Inbound 方向：Head → HandlerA → HandlerB → Tail
// 每个 Handler 决定是否继续传播

ctx.fireChannelRead(msg);      // 继续传播到下一个 InboundHandler
// 不调用 = 拦截，数据不再向下传递
```

### 出站传播

```java
// Outbound 方向：Tail → HandlerB → HandlerA → Head
// 每个 Handler 决定是否继续传播

ctx.write(msg);                // 直接写出（跳过中间 Handler）
ctx.fireWrite(msg);            // 传播到上一个 OutboundHandler
```

## 四、配置 Pipeline

```java
// 在 ServerBootstrap 中配置
.childHandler(new ChannelInitializer<SocketChannel>() {
    @Override
    protected void initChannel(SocketChannel ch) {
        ChannelPipeline pipeline = ch.pipeline();

        // 入站：编解码
        pipeline.addLast("frameDecoder", new LengthFieldBasedFrameDecoder(1024));
        pipeline.addLast("stringDecoder", new StringDecoder());
        pipeline.addLast("stringEncoder", new StringEncoder());

        // 入站：业务逻辑
        pipeline.addLast("logHandler", new LoggingHandler(LogLevel.INFO));
        pipeline.addLast("heartbeatHandler", new HeartbeatHandler());
        pipeline.addLast("businessHandler", new MyBusinessHandler());
    }
})
```

### Pipeline 执行顺序

```
数据流入:
  网络 ──► frameDecoder（拆包）──► stringDecoder（字节→字符串）
       ──► logHandler（打印日志）──► heartbeatHandler（心跳检测）
       ──► businessHandler（业务逻辑）

数据流出:
  businessHandler ──► heartbeatHandler ──► logHandler
       ──► stringEncoder（字符串→字节）──► 网络
```

## 五、责任链的关键设计

### 1. 每个 Handler 都是链中的一环

```
┌─────────┐     ┌─────────┐     ┌─────────┐
│Handler A│────►│Handler B│────►│Handler C│
└─────────┘     └─────────┘     └─────────┘
      │               │               │
      │  ctx.write()  │  ctx.write()  │  ctx.write()
      ▼               ▼               ▼
  调用下一个   调用下一个        调用下一个
  OutboundHandler  OutboundHandler  网络
```

### 2. 拦截 vs 转发

```java
public class AuthHandler extends ChannelInboundHandlerAdapter {
    @Override
    public void channelRead(ChannelHandlerContext ctx, Object msg) {
        if (isAuthenticated(msg)) {
            // ✅ 验证通过，继续传播
            ctx.fireChannelRead(msg);
        } else {
            // ❌ 验证失败，拦截 + 关闭连接
            ctx.writeAndFlush("403 Forbidden");
            ctx.close();
            // 不调用 fireChannelRead，后续 Handler 收不到
        }
    }
}
```

### 3. 入站转出站

```java
public class EchoHandler extends ChannelInboundHandlerAdapter {
    @Override
    public void channelRead(ChannelHandlerContext ctx, Object msg) {
        // 收到入站数据后，直接写出
        ctx.writeAndFlush(msg);  // 触发出站方向
        ReferenceCountUtil.release(msg);
    }
}
```

## 六、Pipeline 的完整生命周期

```
1. Channel 创建
   └─ DefaultChannelPipeline 创建
      ├─ HEAD（HeadContext，既是 Inbound 又是 Outbound）
      └─ TAIL（TailContext，既是 Inbound 又是 Outbound）

2. initChannel() 被调用
   └─ 你在 ChannelInitializer 中 addLast 各种 Handler

3. Channel 注册到 EventLoop
   └─ fireChannelRegistered() → HEAD → ... → TAIL

4. Channel 连接建立
   └─ fireChannelActive() → HEAD → ... → TAIL

5. 有数据可读
   └─ fireChannelRead(msg) → HEAD → HandlerA → HandlerB → TAIL

6. 写出数据
   └─ write(msg) → TAIL → HandlerB → HandlerA → HEAD → 网络

7. Channel 关闭
   └─ fireChannelInactive() → HEAD → ... → TAIL
   └─ fireChannelUnregistered() → HEAD → ... → TAIL
```

## 七、Pipeline 设计模式

```
Pipeline = 责任链模式 + 双向链表

优点：
├── 高内聚低耦合：每个 Handler 只关心自己的逻辑
├── 灵活组合：想加日志？addLast 一个 LoggingHandler
├── 可插拔：想改编码方式？替换 Decoder 即可
├── 可复用：同一个 Handler 可以用于多个 Pipeline
└── 责任清晰：解码、编码、业务逻辑、日志各司其职

类比 HTTP 中间件：
├── Express.js 的 middleware 链
├── Spring MVC 的 Filter / Interceptor
├── Tomcat 的 Valve 链
└── Netty 的 Pipeline 是同样的思想
```