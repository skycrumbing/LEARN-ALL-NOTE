# Tomcat NIO 与 Spring WebFlux 底层源码剖析

> 本文从**线程模型**、**连接处理链路**、**内存模型**、**异步机制**四个维度，
> 逐层剖析 Tomcat NIO 与 Spring WebFlux（底层 Netty）的源码实现差异。

---

## 目录

1. [架构全景对比](#一架构全景对比)
2. [Tomcat NIO 源码剖析](#二tomcat-nio-源码剖析)
3. [Spring WebFlux 源码剖析](#三spring-webflux-源码剖析)
4. [核心差异深度总结](#四核心差异深度总结)
5. [选型指南](#五选型指南)

---

## 一、架构全景对比

```
┌─────────────────────────────────────┐         ┌─────────────────────────────────────┐
│         Tomcat NIO (Servlet)         │         │   Spring WebFlux (Reactive)         │
├─────────────────────────────────────┤         ├─────────────────────────────────────┤
│                                     │         │                                     │
│  Acceptor ──►  Poller ──► 线程池    │         │  EventLoop ──► EventLoop ──► ...    │
│    (accept)     (read/poll)   (执行业务) │      (accept+IO)   (IO+业务)              │
│                                     │         │                                     │
│  3 种线程角色，串行流水线式           │         │  1 种线程角色，自包含闭环             │
│  业务执行在线程池中（阻塞式）          │         │  业务执行在 EventLoop 中（非阻塞式）    │
│                                     │         │                                     │
│  请求生命周期：阻塞 / Servlet 3.1 异步  │         │  请求生命周期：响应式（Mono/Flux）      │
│                                     │         │                                     │
│  Servlet API: HttpServletRequest   │         │  Reactive API: ServerHttpRequest    │
│                                     │         │                                     │
└─────────────────────────────────────┘         └─────────────────────────────────────┘
```

### 线程模型一览

```
Tomcat NIO:
  Acceptor 线程 ──► Poller 线程 ──► 工作线程池（N 个）
      1 个              1 个（或多个）       通常 200 个
   只负责 accept       负责 selector.select()  负责 Servlet 业务处理

Spring WebFlux (Netty):
  EventLoop 线程 ──► 同一个 EventLoop
   accept + IO + 业务处理，全在一个线程里完成
   无工作线程池
```

> **核心差异一句话**：Tomcat NIO 把 IO 和业务分开（IO 用少量线程，业务用大量线程池），
> WebFlux 把 IO 和业务合在一起（一个 EventLoop 线程搞定全部，但必须是异步非阻塞）。

---

## 二、Tomcat NIO 源码剖析

### 2.1 启动：NioEndpoint 初始化

Tomcat 的连接器（Connector）在初始化时创建 **Endpoint**，Tomcat NIO 的实现是 `NioEndpoint`。

```java
// org.apache.tomcat.util.net.NioEndpoint
public class NioEndpoint extends AbstractJsseEndpoint<NioChannel> {

    // ===== 1. Acceptor 线程数量（默认 2 个）=====
    protected int acceptorThreadCount = 2;

    // ===== 2. Poller 线程数量（默认 1 个）=====
    // 实际上是通过 selectorToPoll 参数控制 Selector 数量

    // ===== 3. 工作线程池（实际处理 Servlet 业务）=====
    // 继承自 AbstractEndpoint，默认是 TaskExecutor 包装的 ThreadPoolExecutor
    // maxThreads 默认 200，minSpareThreads 默认 10
    protected int maxThreads = 200;

    // ===== 4. Selector 实现（Linux 用 epoll）=====
    protected Selector selector;
    // 内部通过 NioSelectorPool 管理多个 Selector 实例
    protected NioSelectorPool selectorPool;
}
```

**关键源码：启动入口 `startInternal()`**

```java
// NioEndpoint.startInternal()
@Override
protected void startInternal() throws Exception {
    // 1. 创建工作线程池
    if (getExecutor() == null) {
        createExecutor();
        // 内部：TaskExecutor，底层是 ThreadPoolExecutor
        // corePoolSize = minSpareThreads (10)
        // maxPoolSize = maxThreads (200)
        // workQueue = LinkedBlockingQueue(maxQueueSize, default 10000)
    }

    // 2. 初始化 Selector 池
    if (getSelectorPool() == null) {
        selectorPool = new NioSelectorPool(getSelectorPoolSize(), this);
        // 默认 selectorPoolSize = 1
        // 即一个 Poller 对应一个 Selector
    }

    // 3. 启动 Acceptor 线程
    // 创建 acceptorThreadCount（默认 2）个 Acceptor 线程
    int count = getAcceptorThreadCount();
    for (int i = 0; i < count; i++) {
        Thread acceptorThread = new Thread(new Acceptor(this), getThreadNamePrefix() + "-Acceptor-" + i);
        acceptorThread.setPriority(getAcceptorThreadPriority());
        acceptorThread.setDaemon(getDaemon());
        acceptorThread.start();
    }

    // 4. 启动 Poller 线程
    Poller poller = new Poller();
    Thread pollerThread = new Thread(poller, getName() + "-Poller");
    pollerThread.setPriority(getPollerThreadPriority());
    pollerThread.setDaemon(true);
    pollerThread.start();
}
```

**源码要点**：
- `Acceptor` 数量默认为 2（应对 accept 风暴，避免单一 Acceptor 成为瓶颈）
- `Poller` 数量默认为 1（负责从 Selector 取 IO 事件，然后分发给工作线程池）
- 工作线程池 = **真正的业务处理线程池**，默认 200 个线程

---

### 2.2 第一层：Acceptor 线程

```java
// org.apache.tomcat.util.net.NioEndpoint.Acceptor
protected static final class Acceptor extends AbstractEndpoint.Acceptor {

    @Override
    public void run() {
        // 标准 accept 循环
        while (running) {
            try {
                setState(State.ACCCEPTING);

                // 1. 从 ServerSocket 上 accept 新连接
                NioChannel socket = null;
                socket = serverSocketFactory.acceptSocket(socket);
                // socket = new NioChannel()
                //   NioChannel 内部封装了 Java NIO 的 SocketChannel

                // 2. 设置 Socket 选项
                socket.setProperties();
                // 如 TCP_NODELAY、SO_RCVBUF、keepAlive 等

                // 3. 设置 SO_LINGER 以正确处理 shutdown
                socket.getIOChannel().configureBlocking(false);

                // 4. 关键：把新连接"扔给"Poller，自己继续 accept 下一个
                if (!poller.events.offer(socket)) {
                    // 如果 Poller 的队列满（默认 128），则等待
                    countDownConnection();
                    closeSocket(socket);
                }
            } catch (Exception ioe) {
                // ...
            }
        }
        setState(State.NEW);
    }
}
```

**源码要点**：
- Acceptor **不做任何业务处理**，只做 `accept()`
- 接受到连接后立即 `offer()` 到 Poller 的 `events` 队列
- `events` 是一个**有界队列**（默认容量 128），防止连接风暴时内存耗尽
- 如果队列满，直接关闭新连接（`countDownConnection()`）

```
连接到来
  │
  ▼
Acceptor: ServerSocket.accept()
  │
  ▼
NioChannel socket = new NioChannel(SocketChannel)
  │
  ▼
Poller.events.offer(socket)  ← 有界队列，容量 128
  │
  ▼
Acceptor 回到 while 循环，继续 accept
```

---

### 2.3 第二层：Poller 线程（Selector 多路复用）

```java
// org.apache.tomcat.util.net.NioEndpoint.Poller 实现 Runnable
protected class Poller implements Runnable, Executor {

    // Poller 的 events 队列：Acceptor 把新连接放到这里
    protected final ArrayBlockingQueue<NioChannel> events =
        new ArrayBlockingQueue<>(128);

    // Poller 内部维护一个 Selector
    protected Selector selector;

    @Override
    public void run() {
        while (true) {
            try {
                boolean hasEvents = false;

                // ===== Step 1: 处理 events 队列中的新连接 =====
                // 把队列里的事件"塞"到 Selector 中注册
                Iterator<NioChannel> iter = events.iterator();
                while (iter.hasNext()) {
                    NioChannel socket = iter.next();
                    iter.remove();

                    // 把新连接注册到 Selector，关注 OP_READ
                    // 附带一个 NioSocketWrapper 作为 attachment
                    final NioSocketWrapper socketWrapper =
                        NioChannelWrapper.get().wrap(socket, NioEndpoint.this);

                    if (socket != null) {
                        // 关键：SocketProcessor 任务，封装了读操作
                        SocketProcessor<D> sc =
                            new SocketProcessor<>(socketWrapper, SendfileD=null);
                        // 注册到 Selector：key.interestOps(OP_READ)
                        socket.register(sc, selector);
                        hasEvents = true;
                    } else {
                        // socket == null 时，直接注册 SocketProcessor
                        getExecutor().execute(sc);
                        hasEvents = true;
                    }
                }

                if (!hasEvents) {
                    // 没有新连接事件，selector.select() 等待 IO 就绪
                    selector.select(1000);
                }

                // ===== Step 2: 遍历 Selector 上的就绪事件 =====
                Set<SelectionKey> keys = selector.selectedKeys();
                Iterator<SelectionKey> it = keys.iterator();

                while (it.hasNext()) {
                    SelectionKey sk = it.next();
                    it.remove();

                    NioSocketWrapper socketWrapper =
                        (NioSocketWrapper) sk.attachment();
                    if (socketWrapper == null) {
                        // ... 清理
                        continue;
                    }

                    // ===== 关键分发逻辑 =====
                    if (!socketWrapper.isValid()) {
                        // 连接已失效，清理
                    } else if (sk.isReadable()) {
                        // 有数据可读 → 创建 SocketProcessor 任务，提交到工作线程池
                        SocketProcessor<SocketWrapper> sc =
                            recycledProcessors.poll();
                        if (sc == null) {
                            sc = new SocketProcessor<>(socketWrapper, Event.RECEIVED);
                        } else {
                            sc.reset(socketWrapper);
                        }
                        // 🔑 核心：SocketProcessor 提交到工作线程池执行
                        getExecutor().execute(sc);
                    } else if (sk.isWritable()) {
                        // 有数据可写 → 同样提交到工作线程池
                        getExecutor().execute(sc);
                    }
                }

                // ===== Step 3: 处理超时事件 =====
                if (timeout > 0) {
                    socketWrapper.timeout();
                }

            } catch (Exception x) {
                // ...
            }
        }
    }
}
```

**源码要点**：
- Poller 是**真正在做 selector.select() 的线程**
- 它做两件事：
  1. **注册新连接**：从 events 队列取出 NioChannel，注册到 Selector
  2. **分发就绪事件**：遍历 Selector 上就绪的 key，把读/写任务打包成 `SocketProcessor`，**提交到工作线程池**
- **Poller 本身不做业务处理**，它只负责 IO 事件的分发

```
Poller 主循环:
  1. 从 events 队列取出新连接 → register(selector, OP_READ)
  2. selector.select(1000) 等待 IO 就绪
  3. 遍历 selectedKeys:
     - 可读 → getExecutor().execute(new SocketProcessor(socketWrapper))
     - 可写 → getExecutor().execute(new SocketProcessor(socketWrapper))
  4. 处理超时事件
```

---

### 2.4 第三层：SocketProcessor（业务处理入口）

```java
// org.apache.tomcat.util.net.SocketProcessorBase
protected class SocketProcessor implements Runnable {

    private final SocketWrapperBase<S> socketWrapper;
    private final Event event;

    public SocketProcessor(SocketWrapperBase<S> socketWrapper, Event event) {
        this.socketWrapper = socketWrapper;
        this.event = event;
    }

    @Override
    public void run() {
        // 这个 run() 在工作线程池中执行！
        booleanepProcessSocket = (event == Event.OPEN);
        boolean closeSocket = false;

        while (!closed && events != null &&
               (event == null || events.pop(event))) {
            try {
                if (event == Event.RECEIVED) {
                    // 处理读事件 → 交给 Processor
                    pollerEvent = processor.process(socketWrapper, event);
                } else if (event == Event.SENDFILE) {
                    // 处理零拷贝发送
                    pollerEvent = processor.process(socketWrapper, event);
                } else if (event == Event.DISCONNECT) {
                    // 处理断开
                    pollerEvent = processor.process(socketWrapper, event);
                }

                // 如果 Processor 返回一个 PollerEvent，
                // 说明需要再次通知 Poller 做某事（如注册 OP_WRITE）
                if (pollerEvent != null) {
                    // 把这个事件放回 Poller 的事件队列
                    pollerEvent.submit(false);
                }
            } catch (Exception e) {
                // ...
            }
        }
    }
}
```

**源码要点**：
- `SocketProcessor` 就是工作线程池拿到的"任务"
- 它的工作是**调用 Processor 来处理具体的 HTTP 协议解析**
- 如果处理结果需要再次 IO（如写回响应），会通过 `pollerEvent` 通知 Poller

---

### 2.5 第四层：Processor → Adapter → Container

这是 Tomcat 的"协议处理"层，从原始字节流到 Servlet 请求的完整链路。

```java
// org.apache.tomcat.util.net.NioEndpoint.NioProcessor
public class NioProcessor extends ProcessorBase<NioChannel> {

    @Override
    protected boolean parseRequests(SocketWrapperBase<?> socketWrapper,
                                     RequestInfo rp, boolean comet) throws Exception {

        // 1. 从 NioChannel 读取数据到 buffer
        NioChannel channel = (NioChannel) socketWrapper.getSocket();
        NioBufferHandler bufHandler = channel.getReadBufHandler();

        while (true) {
            ByteBuffer readBuf = bufHandler.getReadBuf();
            int read = channel.read(readBuf);

            if (read >= 0) {
                // 读到了数据，进行 HTTP 协议解析
                if (readBuf.remaining() > 0) {
                    // 数据不足一个完整 HTTP 请求，继续读
                    continue;
                }
            }

            // 2. 解析 HTTP 请求行和头
            return rp.getReq().parseRequestLine() && rp.getReq().parseHeaders();
        }
    }

    // 解析完成后，调用 Adapter
    @Override
    protected boolean processSocket(SocketWrapperBase<?> socketWrapper,
                                     SocketEvent event, boolean dispatch) {
        if (event == SocketEvent.OPEN_READ) {
            // 交给 Adapter 处理
            adapter.service(socketWrapper, event);
        }
        return true;
    }
}
```

```java
// org.apache.coyote.AbstractProtocol$AbstractConnectionHandler
// 解析完 HTTP 请求后，最终调用到 CoyoteAdapter

// org.apache.catalina.connector.CoyoteAdapter
public class CoyoteAdapter implements Adapter {

    @Override
    public void service(org.apache.coyote.Request req,
                        org.apache.coyote.Response res) throws Exception {

        // 1. 把 Coyote 的 Request 转为 Servlet 的 HttpServletRequest
        Request request = (Request) req.getNote(ADAPTER_NOTES);
        Response response = (Response) res.getNote(ADAPTER_NOTES);
        request.setCoyoteRequest(req);
        response.setCoyoteResponse(res);

        // 2. 调用 Servlet 容器（LifecycleBase → Pipeline → Valve → Servlet）
        connector.getService().getContainer().getPipeline().getFirst().
            invoke(request, response);
        // 这里进入 StandardEngine → StandardHost → StandardContext → StandardWrapper
        // 最终调用到 doFilter() → service() → 你的 Controller
    }
}
```

**完整链路总结**：

```
Acceptor  accept()
  │
  ▼
Poller  register() + selector.select()
  │
  ▼
  getExecutor().execute(SocketProcessor)
  │
  ▼
SocketProcessor.run()          ← 工作线程池中的线程执行
  │
  ▼
NioProcessor.processSocket()
  │
  ▼
CoyoteAdapter.service()        ← HTTP 请求 → Servlet 请求
  │
  ▼
StandardEngine → StandardHost → StandardContext → StandardWrapper
  │
  ▼
FilterChain.doFilter()          ← 过滤器链
  │
  ▼
HttpServlet.service()           ← 你的 Controller/Servlet
```

---

### 2.6 工作线程池详解

Tomcat NIO 的工作线程池由 `TaskExecutor` 提供，底层是 `ThreadPoolExecutor`：

```
核心参数（默认值）:
┌──────────────────┬──────────┐
│ 参数              │ 默认值    │
├──────────────────┼──────────┤
│ corePoolSize      │ 10       │  (minSpareThreads)
│ maxPoolSize       │ 200      │  (maxThreads)
│ workQueue         │ LinkedBlockingQueue │
│                   │ 容量 10000      │
│ keepAliveTime     │ 60s      │
│ ThreadFactory     │ TomcatThreadFactory │
│ RejectionPolicy   │ 自定义（会等待队列有空位） │
└──────────────────┴──────────┘
```

**拒绝策略源码**：

```java
// 当线程池满时，Tomcat 不会直接拒绝，而是等待队列有空位
// 源码在 TaskExecutor 中：
@Override
public void execute(Runnable command) {
    if (executor == null) {
        throw new RejectedExecutionException("No executor available");
    }
    try {
        executor.execute(command);
    } catch (RejectedExecutionException rx) {
        // 尝试直接把任务给当前线程执行（不是线程池的线程时）
        if (executor instanceof ThreadPoolExecutor) {
            try {
                // 阻塞等待工作队列有空位
                ((ThreadPoolExecutor) executor).getQueue().put(command);
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
            }
        }
    }
}
```

> Tomcat 的线程池拒绝策略比较特殊：不是直接丢任务，而是**让调用方等待**，
> 直到队列有空位。这意味着**极端情况下 Acceptor 会被阻塞**。

---

### 2.7 Tomcat NIO 的 Servlet 3.1 异步支持

Tomcat 虽然本质是阻塞式线程池模型，但通过 **Servlet 3.1 Asynchronous API** 部分缓解了线程饥饿：

```java
// 异步 Servlet 示例
@WebServlet(urlPatterns = "/async", asyncSupported = true)
public class AsyncServlet extends HttpServlet {
    @Override
    protected void doGet(HttpServletRequest req, HttpServletResponse resp)
            throws IOException {
        // 1. 启动异步上下文 → 当前工作线程立即释放回线程池
        AsyncContext asyncContext = req.startAsync();

        // 2. 在异步上下文里执行耗时操作
        asyncContext.start(() -> {
            try {
                Thread.sleep(5000); // 模拟耗时
                // 3. 处理完后，再次从线程池拿一个线程来写响应
                asyncContext.getResponse().getWriter().write("done");
                asyncContext.complete();
            } catch (Exception e) {
                asyncContext.complete();
            }
        });
        // 4. 到这里 doGet() 返回，工作线程回到线程池
    }
}
```

**源码原理**：

```java
// org.apache.catalina.core.AsyncContextImpl
public class AsyncContextImpl implements AsyncContext {

    @Override
    public void start(Runnable task) {
        // 关键：任务提交到哪里？
        if (asyncThreads) {
            // 如果配置了 asyncThreads=true，提交到独立线程
            ExecutorService asyncExecutor = context.getAsyncExecutor();
            asyncExecutor.execute(task);
        } else {
            // 默认：提交到 Tomcat 工作线程池
            ((CoyoteAsyncContext) asyncContext).getEndpoint().execute(task);
        }
    }
}
```

> **关键理解**：Servlet 3.1 异步并不是真正释放线程，而是：
> 1. `doGet()` 返回时释放当前线程
> 2. 耗时操作（如 DB 查询）仍然需要**再占用一个线程**
> 3. 最终效果：**减少了同时占用的线程数**，但没有消除线程的使用

---

## 三、Spring WebFlux 源码剖析

### 3.1 架构总览

```
Spring WebFlux
  │
  ├── Spring MVC 的 Reactive 替代
  ├── 底层默认使用 Netty（也可用 Tomcat/Jetty，但 Netty 是官方推荐）
  └── 核心抽象：Mono / Flux（响应式流）

数据流：
  客户端请求
    │
    ▼
  Netty EventLoop 接收连接 + 读取数据
    │
    ▼
  HTTP 协议解析（Netty 的 HttpServerCodec）
    │
    ▼
  Spring WebFlux 路由（RouterFunction）
    │
    ▼
  调用 Handler（HandlerFunction / @Controller）
    │
    ▼
  返回 Mono/Flux（不阻塞 EventLoop！）
    │
    ▼
  Mono/Flux 订阅 → Netty EventLoop 写出响应
```

---

### 3.2 启动：Netty WebServer 初始化

```java
// org.springframework.boot.web.reactive.netty.NettyWebServer
public class NettyWebServer implements WebServer {

    public NettyWebServer(Factory<HttpServer> factory, int port) {
        this.httpServer = factory.get().host("0.0.0.0").port(port);
        this.port = port;
    }

    @Override
    public void start() throws WebServerException {
        this.channel = this.httpServer.bind().block().channel();
        // bind() 返回 Mono，block() 阻塞等待绑定完成
        // 底层就是 Netty 的 ServerBootstrap.bind().sync()
    }
}
```

**底层 Netty 启动（简化）**：

```java
// 等价于 Netty 的 Bootstrap 流程
EventLoopGroup bossGroup = new NioEventLoopGroup(1);     // 1 个线程做 accept
EventLoopGroup workerGroup = new NioEventLoopGroup();    // CPU * 2 个线程做 IO + 业务

ServerBootstrap bootstrap = new ServerBootstrap();
bootstrap.group(bossGroup, workerGroup)
    .channel(NioServerSocketChannel.class)
    .childOption(ChannelOption.TCP_NODELAY, true)
    .childHandler(new ChannelInitializer<SocketChannel>() {
        @Override
        protected void initChannel(SocketChannel ch) {
            // ===== Netty Pipeline 初始化 =====
            ChannelPipeline pipeline = ch.pipeline();

            // 1. HTTP 解码器：把字节流解码成 HttpRequest
            pipeline.addLast("httpCodec",
                new HttpServerCodec());

            // 2. 聚合器：把 HTTP 请求合并（处理 chunked 等）
            pipeline.addLast("httpAggregator",
                new HttpObjectAggregator(1048576));

            // 3. WebFlux 的核心 Handler
            pipeline.addLast("httpRequestHandler",
                new ReactorHttpServerHandler(handler));
            // handler 是 Spring WebFlux 提供的 RequestHandler
        }
    });

ChannelFuture future = bootstrap.bind(port).sync();
```

**与 Tomcat 对比**：
| Tomcat NIO | WebFlux (Netty) |
|-----------|-----------------|
| Acceptor 线程 | Boss EventLoop（1 个线程） |
| Poller 线程 | Worker EventLoop（CPU*2 个线程） |
| 工作线程池（200 个） | **无** — 业务在 EventLoop 中执行 |

---

### 3.3 连接处理：ReactorHttpServerHandler

这是 WebFlux 的核心"入口 Handler"，负责把 Netty 的 HTTP 请求路由到 Spring 的控制器。

```java
// org.springframework.http.server.reactive.netty.NettyAdapter
// 以及 ReactorHttpServerHandler

public class ReactorHttpServerHandler implements ChannelInboundHandlerAdapter {

    private final ConnectionProvider connectionProvider;
    private final HttpRequestHandler handler; // Spring WebFlux 的请求处理器

    @Override
    public void channelRead(ChannelHandlerContext ctx, Object msg) {
        if (msg instanceof HttpContent) {
            // 1. 读取 HTTP 请求数据（Netty 已经把字节流解码成 HttpRequest）
            //    注意：这段代码在 EventLoop 线程中执行，非阻塞！

            // 2. 包装成 Reactor Netty 的 HttpServerRequest
            // 3. 最终调用 Spring WebFlux 的路由逻辑
            //    → RouterFunction.match()
            //    → HandlerFunction.handle()
            //    → 返回 Mono<ServerResponse>

            // 🔑 关键：整个过程没有创建新线程，没有阻塞 EventLoop
            //    所有耗时操作（DB、HTTP 调用）都通过 Mono/Flux 异步编排
        }
    }
}
```

---

### 3.4 路由与处理：RouterFunction → HandlerFunction

```java
// WebFlux 路由定义（函数式风格）
RouterFunction<ServerResponse> route = RouterFunctions.route()
    .GET("/users/{id}", handler::getUser)    // 路由 → HandlerFunction
    .POST("/users", handler::createUser)
    .build();

// HandlerFunction 返回 Mono<ServerResponse>
public Mono<ServerResponse> getUser(ServerRequest request) {
    String id = request.pathVariable("id");

    // 🔑 关键：返回 Mono，不阻塞 EventLoop
    return userRepository.findById(id)  // 返回 Mono<User>
        .flatMap(user -> ServerResponse.ok()
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(user));            // 返回 Mono<ServerResponse>
}
```

### Mono 的本质与订阅回调流程

#### Mono 是什么？

`Mono<T>` 是一个**最多产生 0 或 1 个 T 元素的"数据流描述"**。

```java
// ❌ 同步方式（Tomcat Servlet）：立即返回值，线程一直等到拿到结果
User user = userRepository.findById(id);  // 线程阻塞在这里，等 DB 返回

// ✅ 异步方式（WebFlux）：返回一个"承诺"，不等结果
Mono<User> mono = userRepository.findById(id);  // 立即返回一个 Mono 对象
```

Mono 不是值，而是一个**延迟执行的承诺**。它描述了一段处理链路，但**不会执行，直到有人订阅它**。

```
Mono<User> 不是 User，而是一个"等会儿会给你一个 User"的合约

类比：
  Mono<User>    ← 像餐厅的"点菜单"，写上了你要什么，但菜还没做
  User          ← 像端上桌的菜
  subscribe()   ← 像把菜单交给厨房，厨房开始做菜
  onNext()      ← 像菜做好了端上来
```

#### 完整的订阅与回调流程（从请求到响应）

以 `getUser` 方法为例，看 Mono 链**如何被"回调回去"写出响应**：

```java
// Handler 中的代码：
return userRepository.findById(id)          // ① 上游：产生 User
    .flatMap(user -> ServerResponse.ok()    // ② 下游：User → ServerResponse
        .bodyValue(user));
```

从 Netty 收到请求到最终写出响应的完整链路：

```
Step 1: Netty EventLoop 线程执行到 Handler
        │  Handler 返回 Mono<ServerResponse>
        │
        ▼
Step 2: Handler 方法返回！
        │  EventLoop 线程立即释放，去处理下一个请求
        │  ⚠️ Mono 此时只是"承诺"，尚未执行
        │
        ▼
Step 3: Reactor Netty 的 HTTP 层订阅这个 Mono
        │
        │  mono.subscribe(new Subscriber<ServerResponse>() {
        │      @Override
        │      public void onSubscribe(Subscription s) {
        │          s.request(1);  // 背压：请求 1 个数据
        │      }
        │      @Override
        │      public void onNext(ServerResponse response) {
        │          // 数据到了 → 写出 HTTP 响应
        │          ctx.channel().writeAndFlush(response);
        │      }
        │  });
        │
        ▼

> **⚠️ 常见误区：谁订阅了谁？**
>
> 容易误以为"ServerResponse 订阅了 Mono"，这是不对的。
> `ServerResponse` 是流经 Mono 链的一个**数据值**，不是订阅者。
> 真正的订阅关系是：

> ```
> Reactor Netty 的 HTTP 层（订阅者 / Subscriber）
>     ← 调用 subscribe() ←
>     Mono<ServerResponse>（被订阅者 / Publisher）
>
> ServerResponse 只是上游产生、经过 flatMap 转换后流向下游的数据值
> ```

> **正确理解**：
> - 订阅者：Reactor Netty 的 HTTP 层（最终负责写出响应的代码）
> - 被订阅者：Handler 返回的 `Mono<ServerResponse>`
> - 数据值：`ServerResponse` 对象，流经 Mono 链最终到达订阅者

        ▼
Step 4: subscribe() 从最下游向最上游传播订阅信号
        │
        │  传播方向（下游 → 上游）:
        │    Netty Subscriber → flatMap → findById()
        │
        │  每个节点收到订阅后，向自己的上游发出 request(1)
        │
        ▼
Step 5: findById() 收到订阅 → 开始执行数据库查询
        │  DB 返回结果 → 触发 onNext(user)
        │
        ▼
Step 6: 数据流（上游 → 下游，与订阅方向相反）:
        │
        │  findById() → onNext(user)
        │      │
        │      ▼
        │  flatMap 的 lambda 被调用: user -> ServerResponse.ok().bodyValue(user)
        │      │
        │      ▼
        │  Mono<ServerResponse> → onNext(ServerResponse)
        │      │
        │      ▼
        │  Reactor Netty Subscriber → onNext(ServerResponse)
        │
        ▼
Step 7: Subscriber 收到数据 → Netty EventLoop 写出 HTTP 响应到客户端
```

**两个方向的流动（必须理解的关键）**：

```
订阅信号传播方向（下游 → 上游）:
═══════════════════════════════════════

Netty Subscriber 调用 subscribe()
    │  request(1) — "我要 1 个数据"
    ▼
flatMap 节点收到订阅 → 转发 request(1) 给上游
    │  request(1)
    ▼
findById() 收到订阅 → 开始执行查询

─────────────────────────────────────────

数据流动方向（上游 → 下游，和订阅方向相反）:
═══════════════════════════════════════

findById() 完成 → onNext(user)
    │
    ▼
flatMap 节点收到 user → 执行 lambda → onNext(ServerResponse)
    │
    ▼
Netty Subscriber 收到 ServerResponse → 写出 HTTP 响应
```

> **核心理解**：`flatMap` 不是"等数据到了再做"，而是**把两个 Mono 串成一条链**。
> 当上游数据到达时，链自动向下传递，最终到达 Netty 的 Subscriber，由它写出响应。
> 这个过程对 EventLoop 来说是"非阻塞的"——它不需要等待，数据到了自然会被触发。

---

**源码层面 Mono 的调度**：

```java
// 当返回的 Mono 需要执行 DB 查询时，
// 通过 Scheduler 将任务从 EventLoop 调度到另一个线程池：

userRepository.findById(id)
  .subscribeOn(Schedulers.boundedElastic())  // ← 关键：切换到独立线程池
  .flatMap(user -> ServerResponse.ok()
      .bodyValue(user))
  .subscribeOn(eventLoop)                    // ← 写响应时切回 EventLoop
```

```java
// Mono.subscribeOn() 源码核心
public final Mono<T> subscribeOn(Scheduler scheduler) {
    return onAssembly(new MonoSubscribeOn<>(this, scheduler));
}

// MonoSubscribeOn.subscribe()
@Override
public void subscribe(CoreSubscriber<? super T> actual) {
    // 1. 用 Scheduler 创建 Worker
    Worker worker = scheduler.createWorker();

    // 2. 将订阅操作提交到 Worker（即提交到调度器的线程池）
    worker.schedule(() -> {
        // 3. 在目标线程池中执行真正的订阅
        MonoSubscribeOn.this.source.subscribe(
            new SubscribeOnSubscriber<>(actual, worker));
    });
}
```

**这是 WebFlux 处理阻塞操作的标准模式**：

```
EventLoop (线程 1)
  │  收到请求
  │  调用 Handler
  │  Handler 返回 Mono
  │
  ▼
Mono.subscribeOn(Schedulers.boundedElastic())
  │
  ▼
boundedElastic 线程池 (线程 101)
  │  执行 DB 查询（阻塞操作在这里）
  │  查询完成，返回数据
  │
  ▼
EventLoop (线程 1)  ← flatMap 后切回
  │  写响应
  │
  ▼
EventLoop (线程 1)
  继续处理下一个请求
```

---

### 两种情况对比：有 subscribeOn vs 无 subscribeOn

这是理解 WebFlux 线程模型最关键的分界线：

#### 情况 A：有 `subscribeOn(boundedElastic)` — 查询在独立线程中

```java
return userRepository.findById(id)
    .subscribeOn(Schedulers.boundedElastic());  // ← 有这句
```

```
Reactor Netty 订阅 Mono
    │
    ▼
subscribeOn 把订阅任务提交到 boundedElastic 线程池
    │  worker.schedule(() -> { ... })  ← 异步提交
    │  schedule() 立即返回，当前线程（EventLoop）不受阻
    │
    ▼
boundedElastic 线程（线程 101）执行 findById()
    │  DB 查询（阻塞操作发生在这里）
    │
    ▼
✅ EventLoop 线程在这段时间自由处理其他请求
    │
    ▼
DB 返回 → 数据流回 EventLoop → 写出响应
```

#### 情况 B：没有 `subscribeOn` — 查询直接在 EventLoop 线程中

```java
return userRepository.findById(id);  // ← 没有 subscribeOn
```

```
Reactor Netty 订阅 Mono
    │
    ▼
没有 subscribeOn，整条链在 EventLoop 线程中执行
    │
    ▼
❌ EventLoop 线程直接执行 findById()
    │  DB 查询（阻塞操作发生在 EventLoop 线程！）
    │  如果底层是 JDBC，EventLoop 被占住
    │
    ▼
EventLoop 在此期间无法处理其他请求
    │
    ▼
DB 返回 → 写出响应 → EventLoop 恢复
```

#### 两种情况的本质区别

```
┌──────────────────────────────────────────────────────────────────────┐
│  EventLoop 线程的时间线对比                                            │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  情况 A（有 subscribeOn）:                                           │
│                                                                      │
│  T0: 收到请求                                                        │
│  T1: Handler 返回 Mono                                               │
│  T2: subscribe() → worker.schedule() → 立即返回  ← EventLoop 释放   │
│  T3: EventLoop 去处理请求 B、C、D...（同时 boundedElastic 在执行查询） │
│  T4: DB 返回 → EventLoop 写响应                                       │
│                                                                      │
│  ✅ T2 ~ T4 期间 EventLoop 处理了其他 N 个请求                         │
│                                                                      │
│  ─────────────────────────────────────────────────────────────────  │
│                                                                      │
│  情况 B（无 subscribeOn）:                                           │
│                                                                      │
│  T0: 收到请求                                                        │
│  T1: Handler 返回 Mono                                               │
│  T2: subscribe() → 直接在 EventLoop 执行 findById()                  │
│  T3: EventLoop 阻塞在 DB 查询上...（其他请求排队等待）                  │
│  T4: DB 返回 → 写响应 → EventLoop 恢复                               │
│                                                                      │
│  ❌ T2 ~ T4 期间 EventLoop 被占住，无法处理其他请求                    │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

#### 重要细节：subscribeOn 内部是怎么"不阻塞"的

```java
// subscribeOn 的源码:
worker.schedule(() -> {  // schedule() 是异步提交！
    this.source.subscribe(subscriber);  // findById() 在这里执行
});
// ↑ schedule() 返回后，当前线程（EventLoop）立即继续执行
```

所以 EventLoop 在 `subscribe()` 调用中的执行过程：

```
EventLoop 执行:
  1. Handler()        → 返回 Mono
  2. subscribe()      → subscribeOn 内部调用 worker.schedule() → 立即返回
  3. subscribe() 结束  → EventLoop 继续执行

这三个步骤对 EventLoop 来说都是"非阻塞的"，耗时极短。
真正的 DB 查询发生在 boundedElastic 线程中，EventLoop 在这期间去处理其他请求了。
```

#### 补充：即使无 subscribeOn，也不是整个服务器瘫痪

```
WebFlux 通常有 CPU * 2 个 EventLoop 线程（如 8 核 = 16 个）

情况 B 中"无 subscribeOn"：
  - 阻塞的是"处理这个请求的那个 EventLoop 线程"
  - 其他 EventLoop 线程仍在正常工作
  - 但如果大量请求都没有 subscribeOn，所有 EventLoop 线程都会被占住

情况 A 中"有 subscribeOn"：
  - 没有任何 EventLoop 线程被阻塞
  - 所有 EventLoop 线程持续工作
  - 阻塞操作分散在 boundedElastic 线程池中
```

---

### 核心总结：Spring MVC vs WebFlux 的订阅模式差异

#### 一句话总结

> 在 Spring MVC 中，业务线程如果要拿到结果，**必须阻塞等待**，期间不能执行其他事情。
> 在 WebFlux 中，EventLoop 可以把阻塞操作交给独立线程执行，**自己释放去处理其他请求**，
> 结果完成时沿订阅链自动传递回 Netty 写出响应。

#### 详细对比

```
Spring MVC（无论 BIO 还是 NIO）:
═══════════════════════════════════════

  请求进来 → 工作线程 A 处理
      │
      ▼
  工作线程 A 开子线程查 DB
      │
      ▼
  ⚠️ 工作线程 A 必须阻塞等待子线程返回结果
     （join / await / get()）
      │
      ▼
  子线程返回 → 工作线程 A 继续执行 → 写出响应

  ❌ 核心问题：工作线程 A 从请求开始到结束都被占用
     即使开了子线程，主线程还是要等结果
     结果到了也是"同一个线程 A"继续处理

  Servlet 3.1 异步尝试解决：
     doGet() 返回释放线程 A → 异步回调再拿线程 B 写响应
     → 但本质上还是"线程"在流转，没有消除线程的使用


WebFlux:
═══════════════════════════════════════

  请求进来 → EventLoop 处理
      │
      ▼
  Handler 返回 Mono → 订阅链构建完毕
     链：DB线程 → flatMap → Netty Subscriber → 写出响应
      │
      ▼
  ✅ EventLoop 立即释放，去处理其他请求
     不需要等待，不需要 join，不需要 await
      │
      ▼
  DB 线程查询完成 → 触发 onNext(user)
      │
      ▼
  数据沿着已构建好的订阅链自动传递:
     DB线程 → flatMap → Netty Subscriber → 写出响应
      │
      ⚠️ 不需要"找到"对应的请求
         订阅链在构建时已经确定了数据流向
```

#### "找到"的修正

```
❌ 不准确的理解：
   "DB 线程完成后，EventLoop 找到对应的 HTTP 请求返回结果"
   → 暗示了某种"主动查找"行为


✅ 准确的理解：
   "DB 线程完成后，结果沿着订阅时已构建好的链路
    自动传递到 Netty Subscriber，由它写出响应"
   → 链路在订阅时就串好了，数据顺着链流过去


类比：
   ❌ "菜做好了，服务员去柜台找到点了这道菜的人"
   ✅ "点菜单上已经写好了桌子号，菜做好了直接端过去"
```

#### 两者的本质差异

```
┌──────────────────────────────────────────────────────────────────┐
│                                                                  │
│  Spring MVC:                                                     │
│    一个请求 = 一个线程从始至终                                     │
│    线程之间通过"等待-唤醒"传递结果                                 │
│    线程是"被占用的"                                                │
│                                                                  │
│  WebFlux:                                                        │
│    一个请求 = 一条订阅链，横跨多个线程                              │
│    线程之间通过 onNext() 传递数据                                  │
│    EventLoop 永远是"空闲的"（不被阻塞）                            │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

---

### `subscribeOn()` 与背压的关系

##### subscribeOn() 在做什么？

`subscribeOn()` 做的事情很简单：**把整条订阅链的执行切换到另一个线程池**。

```java
userRepository.findById(id)
  .subscribeOn(Schedulers.boundedElastic())  // 整条链改在 boundedElastic 线程池中执行
  .flatMap(user -> ServerResponse.ok().bodyValue(user))
```

看源码核心逻辑：

```java
public final Mono<T> subscribeOn(Scheduler scheduler) {
    // 在操作符链中插入一个 MonoSubscribeOn 节点
    return onAssembly(new MonoSubscribeOn<>(this, scheduler));
}

// 当最下游调用 subscribe() 时，MonoSubscribeOn 的 subscribe() 被调用
@Override
public void subscribe(CoreSubscriber<? super T> actual) {
    // 1. 从指定 Scheduler 创建 Worker
    Worker worker = scheduler.createWorker();

    // 2. 把"真正的订阅"提交到 Worker 的线程池执行
    worker.schedule(() -> {
        // 🔑 这段代码在 boundedElastic 的线程中执行！
        //    而不是在 EventLoop 线程中执行！
        this.source.subscribe(new SubscribeOnSubscriber<>(actual, worker));
    });
}
```

**线程切换效果**：

```
❌ 没有 subscribeOn 时（如果 findById 底层是 JDBC）:

  EventLoop 线程执行整条链:
    userRepository.findById(id)  ← 如果底层是 JDBC，这里阻塞！
      → flatMap
      → 写出响应

  EventLoop 在等 DB 返回的这段时间内完全被占住，无法处理其他请求


✅ 加上 subscribeOn(Schedulers.boundedElastic()) 后:

  EventLoop 线程:
    Handler 返回 Mono → EventLoop 线程立即释放

  boundedElastic 线程池（线程 101）:
    subscribeOn 触发 → 在这里执行 findById()
    → DB 查询（可以阻塞，不影响 EventLoop）
    → 数据返回 → flatMap 执行 → ServerResponse 产生

  EventLoop 线程:
    flatMap 结果 → 写出 HTTP 响应
    → 继续处理下一个请求

  ✅ 阻塞操作在独立线程池中，EventLoop 完全不受影响
```

> **类比**：EventLoop 就像餐厅服务员，负责接待客人（接收请求）和端菜（写出响应）。
> `subscribeOn(boundedElastic)` 就是告诉他"你不用自己下厨，把炒菜任务交给后厨厨师（boundedElastic 线程池）"。
> 厨师炒好菜后，服务员再端出去。

##### 和背压的关系

> **`subscribeOn` 和背压是两个正交的概念：`subscribeOn` 解决"在哪里执行"的问题，
> 背压解决"多快消费"的问题。但它们通过同一个机制——`Subscription.request(n)`——连接在一起。**

看完整流程中两者的分工：

```
完整的订阅 + 背压流程:

Reactor Netty Subscriber 订阅 Mono
    │
    ▼
onSubscribe(subscription) 被调用
    │
    │  subscription.request(1)
    │  ↑ 这是背压：Subscriber 告诉上游"我要 1 个数据"
    │  Mono 最多 1 个元素，所以通常 request(1)
    │
    ▼
request(1) 沿链向上传播:
    │  Netty Subscriber → flatMap → subscribeOn → findById()
    │
    ▼
subscribeOn 节点收到 request(1)
    │
    │  subscribeOn 把"执行"放到 boundedElastic 线程，
    │  但背压信号 request(1) 是在当前线程同步传播的
    │  两者互不影响
    │
    ▼
findById() 在 boundedElastic 线程中执行
    │  → DB 查询
    │  → 返回数据
    │
    ▼
onNext(user) 沿链向下传播:
    │  findById() → flatMap → Netty Subscriber
    │
    ▼
Netty Subscriber 收到数据 → 写出响应
    │
    ▼
如果需要更多数据（Mono 最多 1 个，Flux 可能多个），
再调用 request(1)，链重新从上游请求
```

**两者的区别与联系**：

```
┌────────────────────────────┬──────────────────────────────────┐
│       subscribeOn()        │         背压 (Backpressure)       │
├────────────────────────────┼──────────────────────────────────┤
│ 解决"在哪里执行"             │ 解决"多快产生/消费"               │
├────────────────────────────┼──────────────────────────────────┤
│ 线程调度：EventLoop ↔ 线程池 │ 流量控制：request(n) 控制速率      │
├────────────────────────────┼──────────────────────────────────┤
│ 阻塞操作放到独立线程池        │ 消费慢时上游减速，不撑爆内存         │
├────────────────────────────┼──────────────────────────────────┤
│ 适用于 Mono 和 Flux          │ 对 Flux 更明显（多个元素）         │
│                              │ Mono 最多 1 个元素，背压体现为     │
│                              │ 下游 request(1) 后上游才产生 1 个  │
├────────────────────────────┼──────────────────────────────────┤
│ 通过 Scheduler 实现         │ 通过 Subscription.request(n) 实现  │
│                              │ 但 request(n) 信号通过 subscribeOn │
│                              │ 节点正常传播，两者不冲突            │
└────────────────────────────┴──────────────────────────────────┘
```

**背压在 Flux 中更直观的例子**：

```java
// 背压对 Mono 的体现：
// 下游 request(1) → 上游才产生 1 个数据 → 下游用完再 request(1)
// Mono 只有 0 或 1 个元素，背压效果不太明显

// 背压在 Flux 中更明显：
Flux.interval(Duration.ofSeconds(1))   // 上游每 1s 产生 1 个
    .onBackpressureBuffer(10)          // 背压策略：最多缓存 10 个
    .subscribe(item -> {
        Thread.sleep(5000);            // 下游故意每 5s 才消费 1 个
        process(item);
    });
    // 上游速度（1s/个） > 下游速度（5s/个）
    // 背压启动：缓存到 10 个后，上游暂停产生数据
    // 下游消费掉一个 → 请求一个 → 上游继续产生
```

**在 WebFlux HTTP 请求场景中**：

```
HTTP 请求处理中的背压：

客户端发送数据 → Netty 接收 → WebFlux 处理 → 写出响应

Mono 场景（普通请求/响应）:
  下游（Netty Subscriber）request(1)
  → 上游最多产生 1 个 ServerResponse
  → 背压在此场景下几乎无感，因为就 1 个元素

Flux 场景（流式响应，如 SSE / gRPC streaming）:
  下游（Netty Subscriber）request(n)
  → 上游按请求速率产生数据
  → 如果客户端网络慢，Netty 写不快 → request(n) 变小
  → 上游自动减速，不会撑爆内存
  → 这就是背压在 WebFlux 中最有价值的场景
```

---

### 3.5 背压（Backpressure）

这是 WebFlux 相比 Tomcat NIO 最大的独特能力之一：

```java
// 生产者（数据源）
Flux<Long> numbers = Flux.interval(Duration.ofMillis(100));

// 消费者（处理器）
numbers
    .onBackpressureBuffer(128)    // 背压策略：缓冲 128 个元素
    .subscribe(
        item -> process(item),     // 处理速度跟不上时触发背压
        error -> {},
        () -> System.out.println("done")
    );
```

**WebFlux 的背压机制**：

```
消费者（通过 request(n) 给"额度"）
    │
    ▼
Subscription 订阅链（额度沿链向上传递）
    │
    ▼
生产者（每产生一个数据消耗一个额度，额度=0 时停下等待）
    │
    └── 额度=0 → 等待（减速）
    └── 额度>0 → 持续产出（加速）
```

**源码关键接口**：

```java
// org.reactivestreams 三大核心接口
public interface Publisher<T> {
    void subscribe(Subscriber<? super T> subscriber);
}

public interface Subscriber<T> {
    void onSubscribe(Subscription subscription);  // 收到订阅
    void onNext(T item);                            // 收到数据
    void onError(Throwable error);
    void onComplete();
}

public interface Subscription {
    void request(long n);  // 消费者调用：请求 n 个元素
    void cancel();
}
```

---

### 背压的本质：额度计数器

> **背压不是一种"魔法"，而是一种"约定 + 实现"。**
> `request(n)` 从消费者发出后，通过订阅链一级一级向上传递给生产者。
> 生产者收到后，**自己决定**最多产生 n 个数据，然后等待下一次 `request(n)`。
> 如果生产者不实现这个逻辑，背压就完全失效。

#### 生产者端必须实现背压

```java
// ===== 消费者端 =====
public class MySubscriber implements Subscriber<Long> {
    private Subscription subscription;

    @Override
    public void onSubscribe(Subscription s) {
        this.subscription = s;
        subscription.request(1);  // ← 先请求 1 个
    }

    @Override
    public void onNext(Long item) {
        System.out.println("处理: " + item);
        doSlowWork();                         // 模拟耗时处理
        subscription.request(1);              // ← 处理完才请求下一个
    }
}

// ===== 生产者端（必须实现背压逻辑）=====
public class BackpressureAwarePublisher implements Publisher<Long> {
    @Override
    public void subscribe(Subscriber<? super Long> subscriber) {
        subscriber.onSubscribe(new Subscription() {
            private long demanded = 0;  // ← 额度计数器

            @Override
            public void request(long n) {
                // 消费者请求了 n 个，额度增加
                demanded += n;
            }

            // 生产者持续产出
            public void produce() {
                while (true) {
                    // ===== 核心：检查额度 =====
                    if (demanded <= 0) {
                        // 消费者还没要数据，等待（减速）
                        wait();
                        continue;
                    }
                    subscriber.onNext(counter++);
                    demanded--;  // 消耗一个额度
                    // 如果消费者处理慢，request(n) 调得少，
                    // demanded 很快就变成 0，生产者就停下
                }
            }
        });
    }
}
```

#### 减速和加速的本质

```
减速：
═══════════════════════════════════════

消费者处理慢 → request(n) 调得少
    │
    ▼
生产者的 demanded 额度快速消耗到 0
    │
    ▼
生产者检查 demanded <= 0 → 等待（减速）
    │
    ▼
等到消费者再调 request(n)，demanded > 0 → 恢复生产


加速：
═══════════════════════════════════════

消费者处理快 → request(n) 调得多
    │
    ▼
生产者的 demanded 额度一直 > 0
    │
    ▼
生产者持续产出，不被限制（加速）
```

> **核心理解**：背压的本质是一个"额度计数器"。
> 消费者通过 `request(n)` 给额度，生产者每产生一个数据消耗一个额度。
> 额度为 0 时生产者停下，等待消费者补充额度。

#### 用时间线看整个过程

```
T0:  消费者 request(3)
     → 生产者额度 = 3
     → 生产者发出 3 个数据: onNext(1), onNext(2), onNext(3)
     → 生产者额度 = 0

T1:  消费者处理了第 1 个，request(1)
     → 生产者额度 = 1
     → 生产者发出 1 个数据: onNext(4)
     → 生产者额度 = 0 → 等待...

T2:  消费者处理了第 2、3 个，request(2)
     → 生产者额度 = 2
     → 生产者发出 2 个数据: onNext(5), onNext(6)
     → 生产者额度 = 0 → 等待...

T3:  消费者又处理了一个，request(1)
     → 生产者额度 = 1
     → 生产者发出 1 个数据: onNext(7)
     → ...

可以看到：
  消费者每处理完一个，额度才增加 1
  生产者只能按额度产出，不能超过
  这就是背压：消费者的消费速度反向控制了生产者的生产速度
```

#### 背压策略在实践中的应用

```java
Flux.interval(Duration.ofSeconds(1))   // 生产者：每 1s 产生 1 个
    .onBackpressureBuffer(128)         // 背压缓冲：最多缓存 128 个
    .subscribe(item -> {
        Thread.sleep(5000);            // 消费者：每 5s 处理 1 个
        process(item);
    });
```

```
=== 前 128 个元素的积累 ===

T0:    生产者产生 #1 → 缓冲器存入 #1
T1s:   生产者产生 #2 → 缓冲器存入 #2
  ...
T128s: 缓冲器存满 128 个 → 背压启动！
       生产者收到"额度=0" → 暂停产生（减速）

=== 背压启动后的稳态 ===

生产者每 1s 想产生 1 个
消费者每 5s 才消费 1 个
→ 缓冲器保持接近满
→ 生产者大部分时间在"等待额度"（减速）
→ 消费者每消费一个，生产者才能多产生一个
```

> Tomcat NIO **没有背压概念** — 线程池满了就排队或拒绝，没有这种精细的流量控制。

---

### 3.6 WebFlux 的线程池（Schedulers）

```java
// WebFlux 使用的调度器：
┌────────────────────────┬─────────────────────────────────┐
│ Scheduler              │ 用途                              │
├────────────────────────┼─────────────────────────────────┤
│ Schedulers.parallel()  │ 固定线程池（CPU * 2），用于 CPU 密集任务 │
│ Schedulers.boundedElastic() │ 弹性线程池（默认 256 上限），用于 IO 密集 │
│ Schedulers.single()    │ 单线程，用于单线程场景               │
│ Schedulers.immediate() │ 当前线程，不切换                    │
│ eventLoop              │ Netty 的 EventLoop，用于网络 IO      │
└────────────────────────┴─────────────────────────────────┘
```

```java
// boundedElastic 线程池（对应 Tomcat 工作线程池的角色）
// 默认配置：
// - maxThreads = 256
// - keepAliveTime = 60s
// - workQueue = SynchronousQueue（不排队，直接创建新线程）
```

---

## 四、核心差异深度总结

### 4.1 线程模型差异（最核心）

```
Tomcat NIO（多线程模型）:
═══════════════════════════════════════

  1 Acceptor ──► 1 Poller ──► 200 个工作线程
  少线程做 IO     少线程做分派     多线程做业务

  特点：
  ├── 业务线程可以阻塞（synchronized、sleep、DB 查询）
  ├── 线程数 = 并发连接数上限（受 maxThreads 限制）
  ├── 每个请求占一个线程直到处理完
  └── 线程上下文切换开销大（上下文切换 ≈ 1000ns）

  适合：CPU 密集型、阻塞式业务、传统 Servlet 生态


Spring WebFlix（事件驱动模型）:
═══════════════════════════════════════

  CPU * 2 个 EventLoop
  同时处理 IO + 业务（非阻塞）

  特点：
  ├── 业务线程绝对不能阻塞！
  ├── 线程数 = CPU * 2（固定，不随并发增长）
  ├── 每个请求不占线程，以"回调链"形式存在于 EventLoop 中
  └── 无线程上下文切换（一个请求从头到尾在同一线程）

  适合：高并发 IO 密集型、长连接、Websocket、流式响应
```

**代码层面对比**：

```java
// ===== Tomcat NIO：一个请求 = 一个线程 =====
// 线程生命周期：
//   从线程池取出 → doGet() → 处理完 → 回到线程池
// 线程在此期间是"独占"的

@WebServlet("/hello")
public class HelloServlet extends HttpServlet {
    @Override
    protected void doGet(HttpServletRequest req, HttpServletResponse resp)
            throws IOException {
        // 这个线程被当前请求独占，直到方法返回
        // 如果这里 sleep(1000)，这个线程就浪费 1s
        Thread.sleep(1000);  // ❌ 阻塞了工作线程！
        resp.getWriter().write("hello");
    }
}


// ===== WebFlux：一个请求 = 一段回调链 =====
// 无线程被"独占"，EventLoop 继续处理其他请求
// 耗时操作通过 Mono/Flux 切换到其他线程池

@GetMapping("/hello")
public Mono<String> hello() {
    // 这个线程（EventLoop）不会被阻塞
    // 当 Mono 的订阅需要执行耗时操作时，会切换到 boundedElastic 线程池
    return Mono.fromCallable(() -> {
        Thread.sleep(1000);  // 这个 sleep 在 boundedElastic 线程中执行
        return "hello";
    }).subscribeOn(Schedulers.boundedElastic());
    //                    ↑ subscribeOn 是关键：切换到独立线程池
}
```

---

### 4.2 请求生命周期对比

```
Tomcat NIO 请求生命周期：
══════════════════════════════════

  T0:  Acceptor  accept() 连接
  T1:  Poller 注册到 Selector
  T2:  Poller 检测到可读 → 提交 SocketProcessor 到工作线程池
  T3:  工作线程执行 SocketProcessor.run()
  T4:  Processor 解析 HTTP → Adapter.service() → Servlet.service()
  T5:  Servlet 返回 → 响应写出 → 工作线程回到线程池
  T6:  连接可能复用（keep-alive）→ Poller 继续处理

  线程占用时间 = T3 → T5（可能几毫秒到几秒）


WebFlux 请求生命周期：
══════════════════════════════════

  T0:  Boss EventLoop accept() 连接
  T1:  Worker EventLoop 注册 Channel
  T2:  Worker EventLoop 检测到可读 → 执行 Pipeline handler
  T3:  Pipeline 解码 HTTP → 调用 Spring 路由
  T4:  Handler 返回 Mono/Flux → EventLoop 继续处理其他请求（不阻塞！）
  T5:  Mono 上游产生数据 → 回调链触发
  T6:  EventLoop 写出响应 → 继续处理下一个请求

  EventLoop "占用"时间 ≈ T2 + T3（仅解析阶段，非常短）
  T4 → T5 期间 EventLoop 在处理其他请求
```

---

### 4.3 内存模型对比

```
Tomcat NIO 内存占用模型：
══════════════════════════════════

每个活跃请求占用：
  ├── 1 个工作线程栈（默认 1MB）= 1MB
  ├── Request/Response 对象
  ├── Filter 链上的局部变量
  └── 业务逻辑中的局部变量

1000 个并发请求 ≈ 1000 * 1MB = 1GB 线程栈内存

结论：Tomcat 的并发能力受内存限制（线程数 = 内存 / 线程栈大小）


WebFlux 内存占用模型：
══════════════════════════════════

每个活跃请求占用：
  ├── Mono/Flux 回调链（几个对象引用）≈ 几 KB
  ├── Netty 的 ByteBuf（堆外直接内存，可复用）
  └── 无独立线程栈

1000 个并发请求 ≈ 1000 * 几KB = 几 MB

结论：WebFlux 的并发能力受 CPU 和 IO 限制，而非内存
```

---

### 4.4 异步/非阻塞实现对比

```
Tomcat NIO 的"异步"：
══════════════════════════════════

  Servlet 3.1 Async API:
    1. doGet() 启动 AsyncContext → 当前线程释放
    2. 耗时操作在另一个线程中执行（仍然是阻塞式）
    3. 完成后从线程池拿线程写响应

    本质：还是线程池模型，只是线程利用率提高了
    缺点：没有消除线程的使用，只是"借还"而已

  CompletableFuture（JDK 8+）:
    CompletableFuture.supplyAsync(() -> slowDBQuery())
      .thenApply(result -> result.toString())
    → 本质也是在线程池中执行阻塞操作

  Reactor / WebFlux（引入后）:
    Mono.from(slowDBQuery())
      .subscribeOn(Schedulers.boundedElastic())
    → 在独立线程池中执行阻塞操作，EventLoop 不被阻塞


WebFlux 的"异步"：
══════════════════════════════════

  响应式编程（Reactive Programming）:
    1. 所有耗时操作通过 Mono/Flux 表达
    2. 操作通过 subscribeOn() 调度到合适线程
    3. 通过 .flatMap()、.concatMap() 等组合
    4. 有背压机制控制流量
    5. 整个调用链是"非阻塞的"

    本质：用"回调 + 调度器"替代"线程 + 阻塞"
    优点：线程数固定（CPU * 2），无上下文切换
```

---

### 4.5 背压对比

```
Tomcat NIO：无背压
══════════════════════════════════

  客户端发送速度 > 服务器处理速度时：
    ├── 线程池队列填满
    ├── 新请求被拒绝（HTTP 503 或连接超时）
    └── 无法"告诉客户端慢点发"

  本质：要么接受，要么拒绝，二选一


WebFlux：有背压
══════════════════════════════════

  客户端发送速度 > 服务器处理速度时：
    ├── 通过 Subscription.request(n) 控制
    ├── 可以请求 "给我 1 个"、"给我 10 个"、"暂停"
    ├── 可以 buffer() 缓存一段时间
    └── 可以 drop() 丢弃来不及处理的

  背压策略：
    ├── onBackpressureBuffer(128)    → 缓冲 128 个
    ├── onBackpressureDrop()          → 丢弃多余的
    ├── onBackpressureLatest()        → 只保留最新的
    └── onBackpressureError()         → 抛异常

  本质：精细的流量控制，不是"接受/拒绝"，而是"调速率"
```

---

### 4.6 关键源码对比总结表

| 维度 | Tomcat NIO | Spring WebFlux (Netty) |
|------|-----------|----------------------|
| **底层 IO** | Java NIO Selector | Netty NioEventLoop |
| **IO 线程** | Acceptor(2) + Poller(1) | Boss(1) + Worker(CPU*2) |
| **业务线程** | 工作线程池（默认 200） | 无（EventLoop 本身处理） |
| **阻塞模型** | 可以阻塞（线程池隔离） | 不能阻塞（必须异步非阻塞） |
| **请求表示** | HttpServletRequest（有状态） | ServerHttpRequest（无状态） |
| **响应方式** | 同步写出 | Mono/Flux 响应式写出 |
| **背压** | 无 | 有（Reactive Streams） |
| **内存占用/请求** | ≈ 1MB（线程栈） | ≈ 几 KB（回调链） |
| **并发上限** | 受内存限制（线程数） | 受 CPU/IO 限制 |
| **编程模型** | 命令式（同步） | 响应式（声明式） |
| **阻塞操作处理** | 直接在当前线程执行 | 通过 subscribeOn 切换到独立线程池 |
| **零拷贝** | sendfile (NIO Processor) | Netty CompositeByteBuf + FileRegion |
| **长连接** | 支持（但占线程） | 天然适合（不占线程） |
| **生态兼容** | Servlet 全生态 | Reactor 生态（需适配） |

---

## 五、选型指南

```
你的场景是什么？

├─ 传统 CRUD、RESTful API？
│    └─ Tomcat NIO ✅
│       理由：开发简单、生态成熟、调试方便、阻塞式代码可接受
│
├─ 高并发 WebSocket / 长连接？
│    └─ WebFlux ✅
│       理由：一个 EventLoop 管上千连接，Tomcat 线程池扛不住
│
├─ 流式响应（Server-Sent Events / gRPC streaming）？
│    └─ WebFlux ✅
│       理由：Flux 天然支持流，背压机制保证流量可控
│
├─ 需要聚合多个远程服务响应？
│    └─ WebFlux ✅（但需注意阻塞库适配）
│       理由：Mono.zip() / Mono.when() 并行编排
│
├─ 团队不熟悉响应式编程？
│    └─ Tomcat NIO ✅
│       理由：WebFlux 学习曲线陡，排错困难
│
└─ 需要兼容大量 Servlet 生态库？
     └─ Tomcat NIO ✅
        理由：Hibernate、JDBC、Tomcat 原生库等都基于 Servlet
```

### 关键提醒

```
使用 WebFlux 的三条铁律：

1. 🔴 不要在 EventLoop 线程中调用阻塞 API
   ✅ 正确：userRepository.findById(id).subscribeOn(Schedulers.boundedElastic())
   ❌ 错误：userRepository.findById(id)（如果底层是 JDBC，会阻塞 EventLoop）

2. 🔴 不要混用阻塞和非阻塞库
   ✅ 正确：用 WebFlux + R2DBC（响应式 JDBC）
   ❌ 错误：用 WebFlux + 传统 JDBC（HikariCP）— 除非配合 subscribeOn

3. 🔴 不要捕获 RuntimeException 后静默丢弃
   ✅ 正确：Mono.error(e) 或 Mono.empty() 让错误传播
   ❌ 错误：try { ... } catch (Exception e) { /* 什么都不做 */ }
```

---

## 六、一句话总结

```
Tomcat NIO = 多线程 + 阻塞 IO，简单好用，适合传统 Web 开发
WebFlux   = 事件驱动 + 异步非阻塞，极致并发，适合高吞吐场景

Tomcat NIO 用"线程"换"并发"
WebFlux 用"回调"换"并发"

当并发量不超过线程池上限时，两者性能差距不大
当并发量突破线程池上限时，WebFlux 优势巨大
```