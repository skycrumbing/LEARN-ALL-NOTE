# NIO（非阻塞 IO）

## 一、NIO 三大核心组件

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  Channel    │     │   Buffer    │     │  Selector   │
│  数据通道    │     │  数据容器    │     │  多路复用器  │
└─────────────┘     └─────────────┘     └─────────────┘
```

| 组件 | 说明 | 类比 BIO |
|------|------|----------|
| `Channel` | 双向数据通道 | `InputStream` + `OutputStream`（各是单向的） |
| `Buffer` | 数据的临时容器 | 没有直接对应，BIO 直接读写 |
| `Selector` | 多路复用器，一个线程监控多个 Channel | 没有对应，BIO 一个线程一个连接 |

---

## 二、Buffer：数据的搬运工

```
┌──────────────────────────────────────────┐
│              ByteBuffer                  │
│                                          │
│  [0, capacity)    ← 总容量，创建后不变    │
│        │                                 │
│        ▼                                 │
│  position ──► 当前读写位置               │
│                          │               │
│                          ▼               │
│                   limit ──► 读/写的边界  │
│                                          │
│  [0, position)   ← 已写入的数据          │
│  [position, limit) ← 剩余可写空间        │
└──────────────────────────────────────────┘
```

### 关键属性

| 属性 | 说明 | 写模式下 | 读模式下 |
|------|------|----------|----------|
| `capacity` | 总容量 | 不变 | 不变 |
| `position` | 当前位置 | 写入位置 | 读取位置 |
| `limit` | 边界 | = capacity（可全写） | = 写入的 position（只读已有数据） |
| `mark` | 标记位置 | 可回退读取 | 可回退读取 |

### 读写模式切换（flip）

```java
ByteBuffer buffer = ByteBuffer.allocate(1024);

// ===== 写模式 =====
buffer.put("Hello".getBytes());   // position 移到 5
// position=5, limit=1024, capacity=1024

// ===== flip：切换到读模式 =====
buffer.flip();
// position=0, limit=5, capacity=1024
// 现在 read() 会从 position=0 读到 limit=5

// ===== 读模式 =====
byte[] data = new byte[5];
buffer.get(data);  // 读取 "Hello", position 移到 5

// ===== clear：准备再次写入 =====
buffer.clear();
// position=0, limit=1024, capacity=1024
```

### Buffer 操作速查

| 操作 | 效果 |
|------|------|
| `put()` / `get()` | 写入/读取，position 后移 |
| `flip()` | 写→读切换：limit=position, position=0 |
| `clear()` | 读→写切换：position=0, limit=capacity |
| `compact()` | 将未读数据前移，position=未读数据末尾 |
| `mark()` / `reset()` | 标记/回退到标记位置 |
| `remaining()` | limit - position，剩余可操作字节数 |
| `hasRemaining()` | position < limit，是否还有数据 |

---

## 三、Channel：数据通道

```
┌──────────┐         ┌──────────────┐         ┌──────────┐
│  File    │◄───────►│  FileChannel  │◄───────►│  Buffer  │
└──────────┘         └──────────────┘         └──────────┘

┌──────────┐         ┌──────────────┐         ┌──────────┐
│  Socket  │◄───────►│SocketChannel │◄───────►│  Buffer  │
└──────────┘         └──────────────┘         └──────────┘

┌──────────┐         ┌──────────────┐         ┌──────────┐
│  Server  │◄───────►│ServerSocket  │◄───────►│  Buffer  │
│  Socket  │         │ Channel      │         └──────────┘
└──────────┘         └──────────────┘
```

| Channel 类型 | 用途 | 对应 BIO |
|-------------|------|----------|
| `FileChannel` | 文件 IO | `FileInputStream` / `FileOutputStream` |
| `SocketChannel` | TCP 客户端连接 | `Socket` |
| `ServerSocketChannel` | TCP 服务器监听 | `ServerSocket` |
| `DatagramChannel` | UDP | `DatagramSocket` |

**关键区别**：Channel 是**双向的**，既能读也能写；而 BIO 的 Stream 是单向的。

---

## 四、Selector：多路复用的灵魂

```
    注册 Channel 1 ──┐
    注册 Channel 2 ──┼──►  Selector  ──►  轮询：哪些 Channel 有事件？
    注册 Channel 3 ──┤          │
    注册 Channel N ──┘          │
                                │
                                ▼
                         ┌──────────────┐
                         │  SelectionKey │
                         │  OP_ACCEPT    │── 有新连接
                         │  OP_CONNECT   │── 连接已建立
                         │  OP_READ      │── 有数据可读
                         │  OP_WRITE    │── 可以写数据
                         └──────────────┘
```

### Selector 工作流程

```java
// 1. 创建 Selector
Selector selector = Selector.open();

// 2. 创建 ServerSocketChannel 并设置为非阻塞
ServerSocketChannel serverChannel = ServerSocketChannel.open();
serverChannel.configureBlocking(false);  // 🔑 非阻塞！
serverChannel.bind(new InetSocketAddress(8080));

// 3. 注册到 Selector，关注 OP_ACCEPT 事件
serverChannel.register(selector, SelectionKey.OP_ACCEPT);

// 4. 主循环
while (true) {
    int readyCount = selector.select(1000);  // 阻塞等待事件，超时 1s
    if (readyCount == 0) continue;

    // 5. 遍历就绪的 key
    Iterator<SelectionKey> iter = selector.selectedKeys().iterator();
    while (iter.hasNext()) {
        SelectionKey key = iter.next();

        if (key.isAcceptable()) {
            // 新连接到来
            SocketChannel client = serverChannel.accept();
            client.configureBlocking(false);
            client.register(selector, SelectionKey.OP_READ);
        } else if (key.isReadable()) {
            // 有数据可读
            SocketChannel client = (SocketChannel) key.channel();
            ByteBuffer buffer = ByteBuffer.allocate(1024);
            client.read(buffer);
            buffer.flip();
            // 处理数据...
            buffer.clear();
            // 注册可写事件
            key.interestOps(SelectionKey.OP_WRITE);
        } else if (key.isWritable()) {
            // 可以写数据
            SocketChannel client = (SocketChannel) key.channel();
            // client.write(buffer);
            key.interestOps(SelectionKey.OP_READ);  // 写完转回读
        }

        iter.remove();  // 🔑 必须手动 remove，Selector 不会自动移除
    }
}
```

### 关键设计点

| 要点 | 说明 |
|------|------|
| `configureBlocking(false)` | 必须设置为非阻塞，否则 `read()` 仍会卡住 Selector 线程 |
| `select(timeout)` | 阻塞等待事件，有事件返回，超时返回 0 |
| `selectedKeys().iterator().remove()` | 必须手动移除已处理的 key，否则下次还会处理到 |
| `interestOps()` | 动态修改关注的事件类型（读↔写切换） |
| `attachment` | SelectionKey 可以附带对象，用于存储状态 |

---

## 五、NIO 事件驱动完整示例

```java
public class NioServer {
    public static void main(String[] args) throws IOException {
        Selector selector = Selector.open();

        ServerSocketChannel server = ServerSocketChannel.open();
        server.configureBlocking(false);
        server.bind(new InetSocketAddress(8080));
        server.register(selector, SelectionKey.OP_ACCEPT);

        System.out.println("NIO Server started, 1 thread handles N connections");

        while (true) {
            selector.select();  // 阻塞等待
            Set<SelectionKey> keys = selector.selectedKeys();
            Iterator<SelectionKey> iter = keys.iterator();

            while (iter.hasNext()) {
                SelectionKey key = iter.next();
                iter.remove();

                if (!key.isValid()) continue;

                if (key.isAcceptable()) {
                    handleAccept(key, selector);
                } else if (key.isReadable()) {
                    handleRead(key);
                } else if (key.isWritable()) {
                    handleWrite(key);
                }
            }
        }
    }

    private static void handleAccept(SelectionKey key, Selector selector) throws IOException {
        ServerSocketChannel server = (ServerSocketChannel) key.channel();
        SocketChannel client = server.accept();
        client.configureBlocking(false);

        // 附带一个状态对象
        ByteBuffer readBuffer = ByteBuffer.allocate(1024);
        client.register(selector, SelectionKey.OP_READ, readBuffer);
        System.out.println("Client connected: " + client.getRemoteAddress());
    }

    private static void handleRead(SelectionKey key) throws IOException {
        SocketChannel client = (SocketChannel) key.channel();
        ByteBuffer buffer = (ByteBuffer) key.attachment();

        int bytesRead = client.read(buffer);
        if (bytesRead == -1) {
            client.close();
            key.cancel();
            return;
        }

        buffer.flip();
        String message = StandardCharsets.UTF_8.decode(buffer).toString();
        System.out.println("收到: " + message);
        buffer.clear();

        // 准备写回
        key.interestOps(SelectionKey.OP_WRITE);
    }

    private static void handleWrite(SelectionKey key) throws IOException {
        SocketChannel client = (SocketChannel) key.channel();
        client.write(ByteBuffer.wrap("Echo OK\n".getBytes(StandardCharsets.UTF_8)));
        key.interestOps(SelectionKey.OP_READ);  // 写完后回到读模式
    }
}
```

---

## 六、NIO 的核心突破

```
BIO:  线程数 = 连接数  →  每个线程阻塞等待一个连接的 IO
NIO:  线程数 = 1（或很少）→  一个线程通过 Selector 管理 N 个连接

关键转变：
  从"线程等待 IO" → 到 "IO 就绪后通知线程"
  从"每个连接占一个线程" → 到 "所有连接共享一个线程池"
```

> **注意**：NIO 的 `read()` / `write()` 仍然是同步阻塞的（会阻塞当前线程），
> 只是不会被 `accept()` 卡住。真正的异步非阻塞是 AIO。