# AIO（异步 IO）

## 一、什么是 AIO

AIO = **Asynchronous I/O**，异步非阻塞 IO，也叫 NIO.2。

- JDK 1.7 引入（`java.nio.channels.asynchronous` 包）
- 发起 IO 操作**立即返回**，不等待结果
- 操作完成时通过**回调**（`CompletionHandler`）或**Future**通知

```
BIO:  线程发起 read() → 阻塞等待 → 拿到数据 → 继续
NIO:  线程发起 read() → 立即返回（但数据可能在 Buffer 里也可能没有）→ 继续做别的
AIO:  线程发起 asyncRead() → 立即返回 → 操作系统完成 → 回调处理
```

## 二、两种 AIO 编程方式

### 方式一：CompletionHandler（回调）

```java
public class AioServer {
    public static void main(String[] args) throws Exception {
        AsynchronousServerSocketChannel server =
            AsynchronousServerSocketChannel.open();
        server.bind(new InetSocketAddress(8080));

        System.out.println("AIO Server started");

        // 异步 accept，不阻塞
        server.accept(null, new CompletionHandler<AsynchronousSocketChannel, Void>() {
            @Override
            public void completed(AsynchronousSocketChannel client, Void attachment) {
                // accept 完成，继续接受下一个连接（递归调用）
                server.accept(null, this);

                // 异步读取数据
                ByteBuffer buffer = ByteBuffer.allocate(1024);
                client.read(buffer, buffer, new CompletionHandler<Integer, ByteBuffer>() {
                    @Override
                    public void completed(Integer bytesRead, ByteBuffer buf) {
                        buf.flip();
                        String msg = StandardCharsets.UTF_8.decode(buf);
                        System.out.println("收到: " + msg);

                        // 异步写回
                        buf.clear();
                        buf.put("Echo: " + msg.getBytes());
                        buf.flip();
                        client.write(buf, buf, new CompletionHandler<Integer, ByteBuffer>() {
                            @Override
                            public void completed(Integer bytesWritten, ByteBuffer buf) {
                                client.close();
                            }
                            @Override
                            public void failed(Throwable exc, ByteBuffer buf) {
                                client.close();
                            }
                        });
                    }

                    @Override
                    public void failed(Throwable exc, ByteBuffer attachment) {
                        client.close();
                    }
                });
            }

            @Override
            public void failed(Throwable exc, Void attachment) {
                exc.printStackTrace();
            }
        });
    }
}
```

### 方式二：Future（轮询）

```java
Future<Integer> future = channel.read(buffer);
// 继续做其他事...

// 稍后获取结果
int bytesRead = future.get();  // 这里会阻塞
```

> `Future.get()` 会阻塞，如果所有操作都 `.get()`，那就和 BIO 没区别了。
> Future 适合**定时轮询**的场景。

## 三、AIO 的线程模型

```
┌──────────────────────────────────────────────┐
│              AIO Thread Pool                  │
│                                              │
│  线程1 ──► asyncRead() → 立即返回 → 做其他事  │
│  线程2 ──► asyncRead() → 立即返回 → 做其他事  │
│  线程3 ──► asyncRead() → 立即返回 → 做其他事  │
│                                              │
│  操作系统完成 IO 后，从线程池取线程执行回调     │
│                                              │
│  线程数 = 1~N（线程池大小），与连接数无关      │
└──────────────────────────────────────────────┘
```

- AIO 内部维护一个线程池（默认大小 = CPU 核数）
- IO 操作由操作系统异步完成
- 完成时从线程池分配线程执行 `completed()` 回调

## 四、AIO 在 Linux 上的真相

```
Java AIO (Java 7)     Linux 内核
    │                      │
    ▼                      ▼
  基于 eventfd          没有真正的异步 IO
  + signalfd              (没有像 IOCP 那样的机制)
    │                      │
    ▼                      ▼
  实际是多线程轮询        底层用线程池模拟异步
  而非真正的零拷贝
```

### 各平台 AIO 实现对比

| 平台 | 内核机制 | 真正的异步？ |
|------|----------|-------------|
| **Windows** | IOCP（I/O Completion Ports） | ✅ 真正的异步 |
| **macOS** | `kqueue` + `kevent` | ⚠️ 部分异步 |
| **Linux** | `eventfd` + `epoll` | ❌ 多线程模拟 |

> **结论**：在 Linux 上，AIO 的性能**不如** NIO + Epoll。
> 这就是为什么 Netty 基于 NIO 而非 AIO。

## 五、三种 IO 的线程模型对比

```
BIO 线程模型：
┌─────────────────────────────────┐
│  主线程                          │
│    └─ accept()                  │
│         ├── 线程1 ── read() 阻塞 │
│         ├── 线程2 ── read() 阻塞 │
│         ├── 线程3 ── read() 阻塞 │
│         └── ... N 个线程         │
└─────────────────────────────────┘
  线程数 = N（连接数）

NIO 线程模型：
┌─────────────────────────────────┐
│  Selector 线程                   │
│    └─ select()                   │
│         ├── 事件1 ── read()      │
│         ├── 事件2 ── read()      │
│         └── ... 全部就绪事件      │
│  + 工作线程池（处理业务逻辑）      │
└─────────────────────────────────┘
  线程数 = 1（Selector） + 少量工作线程

AIO 线程模型：
┌─────────────────────────────────┐
│  主线程                          │
│    └─ accept() 异步             │
│         └─ 回调 → 线程池处理      │
│  + 内部线程池（CPU 核数）         │
└─────────────────────────────────┘
  线程数 = 1 + CPU 核数
```

## 六、AIO 的适用场景

AIO 在 Java 生态中**使用很少**，原因：
1. Linux 上性能不如 NIO
2. Netty 基于 NIO，生态成熟
3. AIO API 设计复杂，回调嵌套地狱

实际使用 AIO 的场景：
- Windows 平台的大规模异步 IO
- 某些特定的数据库驱动内部使用
- 学术/实验性质