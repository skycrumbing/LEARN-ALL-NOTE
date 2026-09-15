# Bootstrap 启动流程

## 一、Bootstrap vs ServerBootstrap

```
Bootstrap          ServerBootstrap
（客户端启动器）     （服务端启动器）

┌──────────┐       ┌──────────────────┐
│  client   │       │  bossGroup       │── 接受新连接
│ .group()  │       │  workerGroup     │── 处理读写
│ .channel()│       │  .group(boss,    │
│ .handler()│       │   worker)        │
│ .connect()│       │  .childHandler() │── 为每个连接配置
└──────────┘       └──────────────────┘
```

| 组件 | Bootstrap | ServerBootstrap |
|------|-----------|-----------------|
| 用途 | 客户端 | 服务端 |
| EventLoopGroup | 1 个 | 2 个（boss + worker） |
| 启动方法 | `connect()` | `bind()` |
| Handler | `handler()` | `childHandler()`（每个连接的 Handler） |

## 二、服务端启动代码

```java
public class NettyServer {
    public static void main(String[] args) throws Exception {
        // 1. 创建 boss 线程组（接受连接）
        EventLoopGroup bossGroup = new NioEventLoopGroup(1);

        // 2. 创建 worker 线程组（处理 IO）
        EventLoopGroup workerGroup = new NioEventLoopGroup();  // 默认 CPU * 2

        try {
            // 3. 创建 ServerBootstrap
            ServerBootstrap bootstrap = new ServerBootstrap();

            // 4. 配置
            bootstrap.group(bossGroup, workerGroup)                   // 线程组
                .channel(NioServerSocketChannel.class)                // 传输层（NIO）
                .option(ChannelOption.SO_BACKLOG, 128)               // 服务器参数
                .childOption(ChannelOption.SO_KEEPALIVE, true)       // 连接参数
                .childOption(ChannelOption.TCP_NODELAY, true)        // 禁用 Nagle 算法
                .childHandler(new ChannelInitializer<SocketChannel>() {
                    @Override
                    protected void initChannel(SocketChannel ch) {
                        // 5. 为每个新连接配置 Pipeline
                        ch.pipeline().addLast(new MyServerHandler());
                    }
                });

            // 6. 绑定端口并启动
            ChannelFuture future = bootstrap.bind(8080).sync();
            System.out.println("Netty Server started on 8080");

            // 7. 等待服务器关闭
            future.channel().closeFuture().sync();
        } finally {
            bossGroup.shutdownGracefully();
            workerGroup.shutdownGracefully();
        }
    }
}
```

## 三、启动流程拆解

```
bootstrap.bind(8080).sync()
        │
        ▼
┌─────────────────────────────────────┐
│  1. 创建 NioServerSocketChannel      │
│     - 打开 ServerSocketChannel       │
│     - 设置非阻塞模式                  │
│     - 绑定到 8080 端口               │
└──────────────────┬──────────────────┘
                   │
                   ▼
┌─────────────────────────────────────┐
│  2. 注册到 boss EventLoop 的         │
│     Selector，关注 OP_ACCEPT          │
└──────────────────┬──────────────────┘
                   │
                   ▼
┌─────────────────────────────────────┐
│  3. boss EventLoop 开始循环          │
│     while (true) {                   │
│       selector.select()              │── 等待连接事件
│       处理 OP_ACCEPT                  │
│     }                                │
└─────────────────────────────────────┘
```

### 详细流程

```java
// bind() 内部做了什么？

// Step 1: 通过 ChannelFactory 创建 Channel
//   → NioServerSocketChannel 实现了 ServerSocketChannel
//   → 内部调用了 java.nio.channels.ServerSocketChannel.open()
//   → 设置为非阻塞：channel.configureBlocking(false)

// Step 2: 初始化 Channel
//   → 设置 ChannelPipeline（包含一个空 DefaultChannelPipeline）
//   → 设置 ChannelConfig（SO_BACKLOG 等）
//   → 设置 ChannelId

// Step 3: 注册到 EventLoop
//   → bossGroup.next() 选择一个 EventLoop
//   → EventLoop 创建自己的 Selector
//   → Channel 注册到 Selector，关注 OP_ACCEPT

// Step 4: 绑定端口
//   → javaChannel().bind(localAddress)
//   → ServerSocketChannel 绑定到 8080

// Step 5: sync() 阻塞等待
//   → 等待 Channel 注册完成
//   → 返回 ChannelFuture（异步结果）
```

## 四、关键选项说明

```java
// 服务器级别（boss）
.option(ChannelOption.SO_BACKLOG, 128)        // 连接队列长度

// 连接级别（worker，加 child 前缀）
.childOption(ChannelOption.SO_KEEPALIVE, true)  // 心跳检测死连接
.childOption(ChannelOption.TCP_NODELAY, true)   // 禁用 Nagle 算法（低延迟）
.childOption(ChannelOption.SO_SNDBUF, 65536)    // 发送缓冲区大小
.childOption(ChannelOption.SO_RCVBUF, 65536)    // 接收缓冲区大小
```

| 选项 | 说明 | 推荐值 |
|------|------|--------|
| `SO_BACKLOG` | 等待 accept 的连接队列长度 | 128 ~ 1024 |
| `SO_KEEPALIVE` | TCP 心跳，检测死连接 | `true` |
| `TCP_NODELAY` | 禁用 Nagle 算法，立即发送小包 | `true`（低延迟场景） |
| `SO_SNDBUF` | TCP 发送缓冲区 | 根据业务调整 |
| `SO_RCVBUF` | TCP 接收缓冲区 | 根据业务调整 |

## 五、Nagle 算法 vs TCP_NODELAY

```
Nagle 算法（默认开启）：
  "有未确认的小包时，合并后续小包再发"
  → 减少小包数量，提高带宽利用率
  → 但增加延迟（等确认才能发）

TCP_NODELAY = true：
  "不管有没有未确认的小包，立即发送"
  → 降低延迟
  → 但可能产生更多小包

适用场景：
  需要低延迟（聊天、游戏）→ TCP_NODELAY = true
  需要高吞吐（文件传输）→ 保持 Nagle 算法
```

## 六、客户端 Bootstrap

```java
public class NettyClient {
    public static void main(String[] args) throws Exception {
        EventLoopGroup group = new NioEventLoopGroup();

        try {
            Bootstrap bootstrap = new Bootstrap();
            bootstrap.group(group)
                .channel(NioSocketChannel.class)
                .handler(new ChannelInitializer<SocketChannel>() {
                    @Override
                    protected void initChannel(SocketChannel ch) {
                        ch.pipeline().addLast(new MyClientHandler());
                    }
                });

            ChannelFuture future = bootstrap.connect("localhost", 8080).sync();
            future.channel().closeFuture().sync();
        } finally {
            group.shutdownGracefully();
        }
    }
}
```

> 客户端只有一个 EventLoopGroup，因为没有"接受连接"的需求。