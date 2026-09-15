# BIO（阻塞 IO）

## 一、什么是 BIO

BIO = **Blocking I/O**，同步阻塞 IO。

核心特征：
- `read()` 会**阻塞**，直到有数据可读
- `write()` 会**阻塞**，直到数据写完
- `accept()` 会**阻塞**，直到有新连接
- 一个线程同一时刻只能处理一个连接

## 二、服务端示例

```java
public class BioServer {
    public static void main(String[] args) throws IOException {
        ServerSocket serverSocket = new ServerSocket(8080);
        System.out.println("BIO Server started on 8080");

        while (true) {
            // 🔴 阻塞点 1：等待新连接
            Socket client = serverSocket.accept();

            // 🔴 为每个连接创建一个线程（致命问题）
            new Thread(() -> {
                try {
                    handleClient(client);
                } catch (IOException e) {
                    e.printStackTrace();
                }
            }).start();
        }
    }

    private static void handleClient(Socket socket) throws IOException {
        // 🔴 阻塞点 2：等待读取数据
        BufferedReader reader = new BufferedReader(
            new InputStreamReader(socket.getInputStream(), StandardCharsets.UTF_8));

        String line;
        while ((line = reader.readLine()) != null) {
            System.out.println("收到: " + line);

            // 🔴 阻塞点 3：等待写出数据
            PrintWriter writer = new PrintWriter(
                new OutputStreamWriter(socket.getOutputStream(), StandardCharsets.UTF_8));
            writer.println("Echo: " + line);
            writer.flush();
        }
        socket.close();
    }
}
```

## 三、为什么一个连接一个线程

因为 `read()` 是阻塞的：

```
线程1 ── accept() ──► read() ──► [阻塞等待数据]
线程2 ── accept() ──► read() ──► [阻塞等待数据]
线程3 ── accept() ──► read() ──► [阻塞等待数据]
...
```

如果不为每个连接开线程，`thread1` 在 `read()` 阻塞时，整个程序就停在那里了，
其他已连接但暂时没发数据的客户端就会被忽略。

## 四、线程模型的两种方案

### 方案一：Thread-Per-Connection（每个连接一个线程）

```java
// 简单直接，但线程数 = 连接数
new Thread(() -> handle(client)).start();
```

| 连接数 | 线程数 | 内存消耗 | 性能 |
|--------|--------|----------|------|
| 100 | 100 | ~100MB | ✅ 正常 |
| 1,000 | 1,000 | ~1GB | ⚠️ 上下文切换严重 |
| 10,000 | 10,000 | ~10GB | ❌ OOM |

### 方案二：线程池

```java
// 用线程池限制线程数，但空闲连接仍会浪费线程
ExecutorService pool = Executors.newFixedThreadPool(200);
pool.submit(() -> handle(client));
```

| 连接数 | 线程数 | 问题 |
|--------|--------|------|
| 1,000 | 200 | 800 个连接排队等线程 |
| 10,000 | 200 | 9800 个连接排队 |

> **结论**：BIO 的根本问题是 **阻塞**，无论怎么优化线程模型都无法解决。

## 五、BIO 的适用场景

BIO 不是万恶之源，它适合 **低并发、长连接** 的场景：

- **数据库连接池**：连接数通常几十到几百，每个连接长期占用一个线程完全没问题
- **内部服务间通信**：连接数少，延迟不是主要瓶颈
- **简单的工具类/脚本**：不追求高性能

> 真正的高并发场景（Web 服务器、消息推送、IM 服务）必须用 NIO。