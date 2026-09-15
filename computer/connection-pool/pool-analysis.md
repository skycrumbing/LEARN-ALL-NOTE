# 连接池专题：从数据库到 HTTP 的源码剖析

> 连接池是一个"跨领域"的抽象——数据库、Redis、HTTP、Kafka 都在用。
> 本文从**统一抽象 → 具体实现 → 源码差异**三个层次，剖析 JDK 生态中最主要的三种连接池。

---

## 目录

1. [为什么需要连接池：代价分析](#一为什么需要连接池代价分析)
2. [Apache Commons Pool：通用连接池的抽象](#二apache-commons-pool通用连接池的抽象)
3. [HikariCP：JDBC 最快的连接池](#三hikaricpjdbc-最快的连接池)
4. [HTTP 连接池：OkHttp 与 Apache HttpClient](#四http-连接池okhttp-与-apache-httpclient)
5. [RabbitMQ 连接池与保活机制](#五rabbitmq-连接池与保活机制)
6. [连接池源码差异与保活原理总览](#六连接池源码差异与保活原理总览)
7. [参数调优与常见坑](#七参数调优与常见坑)
8. [知识串联](#八知识串联)

---

## 一、为什么需要连接池：代价分析

### 1.1 建立一条连接的代价

```
TCP 连接建立：

  三次握手（1~3 RTT，取决于网络延迟）
    TCP SYN  ──→  Server
       ←──  TCP SYN-ACK
    TCP ACK  ──→

  若启用 TLS（如 JDBC 连 RDS、Redis 启用 SSL）:
    + TLS 握手（1~2 RTT 额外）

  总耗时（本地）:  约 50~200 μs
  总耗时（跨地域）: 约 20~100 ms

对比一次查询的耗时（微服务内 Redis）:
  一次 get 操作 ≈ 50~200 μs（含网络）

结论：建一次连接的开销 ≈ 一次业务查询的开销
  每次操作都建新连接 = 业务性能减半
```

### 1.2 连接池解决什么，不解决什么

```
解决：
  ✅ 连接复用（避免反复握手）
  ✅ 连接数量控制（防止打爆服务端）
  ✅ 空闲连接管理（Evictor 剔除死连接）
  ✅ 借出/归还时的连接有效性验证

不解决：
  ❌ 网络抖动导致连接半路断开（仍需业务层重试）
  ❌ 并发限制本身（池满时等待或拒绝，不提高吞吐量上限）
  ❌ 慢查询（连接池只管"连接"，不管"SQL"）
```

### 1.3 连接池 vs 线程池：两个不同维度的东西

```
┌─────────────────────┬────────────────────────────────────┐
│ 连接池              │ 线程池                              │
├─────────────────────┼────────────────────────────────────┤
│ 管理"网络资源"        │ 管理"CPU 执行资源"                    │
│ 池里存的是 socket 连接 │ 池里存的是 Thread 对象               │
├─────────────────────┼────────────────────────────────────┤
│ 连接是"被借用"的      │ 线程是"执行任务"的                    │
│ 用完要归还            │ 任务做完线程回到池里                  │
├─────────────────────┼────────────────────────────────────┤
│ 池满时等待/拒绝       │ 池满时排队/拒绝                       │
│ 连接断开需要感知       │ 线程挂了需要检测                     │
└─────────────────────┴────────────────────────────────────┘

一个完整的请求可能同时经过两层池：

  Thread（线程池借出）
    │
    ▼
  Connection（连接池借出）
    │
    ▼
  执行 SQL / Redis 命令
    │
    ▼
  Connection 归还连接池
  Thread 归还线程池
```

---

## 二、Apache Commons Pool：通用连接池的抽象

Jedis、HikariCP（早期版本）、Redisson 等都直接或间接基于 Commons Pool。
它定义了连接池的**"骨架模式"**，不同实现只需填 `ObjectFactory`。

### 2.1 核心抽象接口

```java
// 通用对象池的唯一核心接口
public interface ObjectPool<T> {
    // 借出一个对象
    T borrowObject() throws Exception;
    // 归还一个对象
    void returnObject(T obj) throws Exception;
    // 销毁一个对象（不可归还时）
    void invalidateObject(T obj) throws Exception;
}

// 工厂接口：池要造什么样的对象，全靠这个
public interface PooledObjectFactory<T> {
    // 1. 创建一个对象
    PooledObject<T> makeObject() throws Exception;
    // 2. 销毁一个对象
    void destroyObject(PooledObject<T> obj) throws Exception;
    // 3. 判断一个对象是否有效
    boolean validateObject(PooledObject<T> obj);
    // 4. 激活对象（从空闲态唤醒）
    void activateObject(PooledObject<T> obj) throws Exception;
    // 5. 钝化对象（归还池中前的处理）
    void passivateObject(PooledObject<T> obj) throws Exception;
}
```

Jedis 的工厂实现：

```java
// Jedis 的 ObjectFactory —— 池里造的就是 Jedis 对象
public class JedisFactory extends BasePooledObjectFactory<Jedis> {

    private final HostAndPort hostAndPort;
    private final int timeout;

    @Override
    public Jedis create() {
        // makeObject() 核心：新建一条 TCP 连接
        return new Jedis(hostAndPort.getHost(),
                         hostAndPort.getPort(),
                         timeout);  // ← 建连接的代价在这里
    }

    @Override
    public void destroyObject(PooledObject<Jedis> pooledJedis) {
        // destroyObject() 核心：关闭连接
        pooledJedis.getObject().close();  // socket.close()
    }

    @Override
    public boolean validateObject(PooledObject<Jedis> pooledJedis) {
        // validateObject() 核心：发 PING
        // 借出前检查（testOnBorrow）和空闲检查（testWhileIdle）都会调
        try {
            pooledJedis.getObject().ping();
            return true;
        } catch (JedisConnectionException e) {
            return false;  // 返回 false → 池销毁该连接，不借给用户
        }
    }
}
```

### 2.2 借出对象：GenericObjectPool.borrowObject()

```java
// 借出连接的核心逻辑（简化）
public T borrowObject() throws Exception {
    // Step 1: 尝试从空闲队列取一个
    IdleObject<T> idleObj = idleObjects.pollFirst();  // 取出最近最空闲的

    if (idleObj != null) {
        // 命中空闲连接
        if (testOnBorrow) {
            // 借出前体检：调 PooledObjectFactory.validateObject()
            if (factory.validateObject(idleObj)) {
                return activate(idleObj);
            } else {
                // 体检失败 → 销毁 → 继续找下一个
                destroy(idleObj);
                return borrowObject();  // 递归重试
            }
        }
        return activate(idleObj);
    }

    // Step 2: 无空闲连接 → 尝试新建
    if (getNumActive() < maxTotal) {
        PooledObject<T> newObj = factory.makeObject();
        return newObj;
    }

    // Step 3: 池满 → 阻塞等待或抛异常
    if (blockWhenExhausted) {
        return borrowObjectBlocking();  // 等 maxWaitMillis，超时抛异常
    } else {
        throw new NoSuchElementException("Pool exhausted");
    }
}
```

### 2.3 归还对象：GenericObjectPool.returnObject()

```java
public void returnObject(T obj) {
    PooledObject<T> p = allObjects.get(id);
    if (p == null) return;

    // Step 1: 判断归还时是否验证
    if (testOnReturn) {
        if (!factory.validateObject(p)) {
            destroy(p);
            return;
        }
    }

    // Step 2: 钝化（passivate）
    factory.passivateObject(p);

    // Step 3: 判断是否允许空闲
    if (getNumIdle() < maxIdle) {
        p.markReturned();
        idleObjects.addLast(p);  // 放回空闲队列
        // 注意：先放回，Evictor 后续可能会移除
    } else {
        destroy(p);  // 超过 maxIdle → 直接销毁，不留
    }
}
```

### 2.4 Evictor：后台巡检线程

```java
// Evictor 由 ScheduledExecutor 驱动
// 周期 = timeBetweenEvictionRunsMillis（默认 30s）

public void evict() {
    if (testWhileIdle) {
        int idleCount = idleObjects.size();
        int testCount = Math.min(idleCount, numTestsPerEvictionRun);

        // 随机挑 testCount 个空闲连接体检
        for (int i = 0; i < testCount; i++) {
            PooledObject<T> p = idleObjects.pollLast();
            if (p != null) {
                if (!factory.validateObject(p)) {
                    destroy(p);          // 死连接 → 销毁
                    continue;
                }

                // 活连接：判断是否超过 idleTimeout
                if (isAbandoned(p)) {
                    destroy(p);          // 超过空闲时限 → 销毁
                } else {
                    idleObjects.addLast(p);  // 合格 → 放回去
                }
            }
        }
    }

    // 判断 minIdle：池里空闲不足时主动补充
    if (getNumIdle() < minIdle) {
        int fill = minIdle - getNumIdle();
        for (int i = 0; i < fill; i++) {
            idleObjects.add(factory.makeObject());
        }
    }
}
```

---

## 三、HikariCP：JDBC 最快的连接池

HikariCP 是目前 Java 生态中**最快的 JDBC 连接池**（比 Tomcat JDBC Pool 快 4~5 倍）。
它没有继承 Commons Pool，而是**完全自研了一套内部结构**。

### 3.1 为什么 HikariCP 快：三个关键设计

```
设计 1：用 Bag 代替 LinkedBlockingQueue
═══════════════════════════════════════

Commons Pool 用 LinkedBlockingQueue 存空闲连接：
  → 每次 borrow/return 都要加锁 + 创建数组节点
  → 高并发下锁竞争激烈

HikariCP 用自研的 Bag（基于 ConcurrentLinkedQueue + ConcurrentHashMap）：
  → borrow 用 CAS 操作，无锁
  → 内部用 FastList（见下文）存连接，零对象分配
  → 高并发下吞吐量提升 3~5 倍


设计 2：FastList 代替 ArrayList
═══════════════════════════════════════

Commons Pool 的 ObjectPool 内部用 List：
  → 增删元素需要 arraycopy 或创建新数组
  → GC 压力大

HikariCP 的 FastList 是一个"非泛型"链表：
  → 用 int[] 存储对象索引，直接映射到 Object[] 数组
  → 插入/删除只改指针，不移动数据
  → 完全避免了自动装箱/拆箱
  → 零额外对象分配（borrow/return 不产生垃圾）


设计 3：激进预初始化 + 快速失败
═══════════════════════════════════════

Commons Pool 默认懒加载：
  → minIdle 个连接先建好
  → 不够时按需建
  → 高并发启动时大量线程同时建新连接 → 抖动

HikariCP 默认激进初始化：
  → 启动时立即建好 maxPoolSize 个连接
  → 后续 borrow 直接从池中取，零延迟
  → 启动时虽然慢一点，但运行时稳定

  快速失败策略：
  → 池满时最多等 connectionTimeout（默认 30s），绝不无限等
  → 超时直接抛 SQLException，不排队
  → 让业务尽早感知"数据库可能挂了"
```

### 3.2 为什么 testOnBorrow 默认是 false？

```
Commons Pool（Jedis 默认）:
  testOnBorrow = true    ✅ 每次 borrow 都 PING 一次

HikariCP:
  leakDetectionThreshold = 0（不开启）
  connectionTestQuery = null  ← testOnBorrow 等价功能默认关闭！
```

**HikariCP 敢关 testOnBorrow 的底气：**

```
原因 1：连接健康由 housekeeping 线程保证

  HikariCP 有专门的 housekeeping 线程，定期扫描池中连接：
    ├── 超过 maxLifetime 的连接 → 销毁
    ├── 超过 idleTimeout 的连接 → 销毁
    └── 空闲连接发 PING 探活（默认 1s 间隔）

  这相当于 testWhileIdle 的升级版，且频率更高。

原因 2：依赖 JDBC 驱动自身的错误处理

  大部分 JDBC 驱动（MySQL Connector/J、PostgreSQL JDBC）在
  socket 断开时会在下一次 IO 操作时立即抛 SQLException。

  HikariCP 的设计哲学：
    借出的连接如果真断了，让业务层感知这个异常
    → 业务层重试（Spring 的 RetryTemplate）
    → 比"池默默替换死连接"更可观测

原因 3：性能考量

  testOnBorrow 每次 borrow 多一次 PING 往返（1 RTT）
  高 QPS 场景下，这 1 RTT 是显著的额外延迟。
  HikariCP 选择"信任连接，出错即报"的策略。
```

### 3.3 HikariCP 的三队列模型

```
HikariCP 内部实际上有三个"队列"：

┌─────────────────────────────────────────────────────┐
│                                                      │
│  pendingQueue   (Lock-Free)                          │
│  ─────────────                            等待借出的线程 │
│  当池满时，来的请求在这里排队                           │
│  实现：SynchronousQueue                             │
│                                                      │
├─────────────────────────────────────────────────────┤
│                                                      │
│  availableConnections  (Bag)                         │
│  ───────────────────                     空闲连接     │
│  刚归还的连接在这里                                      │
│  实现：ConcurrentLinkedQueue                         │
│                                                      │
├─────────────────────────────────────────────────────┤
│                                                      │
│  activeConnections  (FastList)                       │
│  ────────────────                      正在使用的连接  │
│  借出后在这里注册                                       │
│  实现：int[] + Object[]                             │
│                                                      │
└─────────────────────────────────────────────────────┘

 borrow() 流程：
   从 availableConnections 取
     └─ 没有 → pendingQueue 阻塞等
     └─ 还完 → 从 activeConnections 摘除，放 availableConnections

 return() 流程：
   从 activeConnections 摘除
   → 放 availableConnections
     └─ 如果空闲数超 maxIdle → 销毁
```

### 3.4 HikariCP 关键源码片段

```java
// HikariPool 借出连接的核心逻辑（简化）
public Connection getConnection(long timeout) throws SQLException {
    long startTime = currentTimeMillis();

    // Step 1: 从 Bag 中尝试获取
    poolEntry = connectionBag.borrow(timeout, MILLISECONDS);
    if (poolEntry != null) {
        // 命中空闲连接 → 直接返回
        return poolEntry.getConnection();
    }

    // Step 2: Bag 空 → 尝试新建（若未达到 maxPoolSize）
    int totalCount = connectionBag.getPoolTotalSize();
    if (totalCount < maxPoolSize) {
        poolEntry = addConnection();
        return poolEntry.getConnection();
    }

    // Step 3: 池满 → 抛异常（不等待！）
    throw new SQLException("Connection is not available, request timed out after "
                           + (currentTimeMillis() - startTime) + "ms");
}

// 归还连接的核心逻辑
public void close() throws SQLException {
    // Step 1: 从 activeConnections 摘除
    poolEntry.removeFromPool();

    // Step 2: 放回 availableConnections（或 housekeeping 判断是否回收）
    connectionBag.add(poolEntry);
}
```

---

## 四、HTTP 连接池：OkHttp 与 Apache HttpClient

HTTP 连接池的本质是**TCP 连接复用**——一条 TCP 连接可以承载多次 HTTP 请求（HTTP/1.1 keep-alive / HTTP/2 multiplexing）。

### 4.1 OkHttp 的 ConnectionPool

```java
// OkHttp 的连接池（源码在 okio3/OkHttp3 ConnectionPool.java）

public final class ConnectionPool {
    // 内部用一个双向链表存空闲连接
    private final Deque<RealConnection> connections = new ArrayDeque<>();

    // 默认参数：
    private final int maxIdleConnections = 5;   // 最多保留 5 条空闲
    private final long keepAliveDurationMs = 5 * 60 * 1000;  // 5 分钟保活

    private final Runnable cleanupRunnable = () -> {
        // 定期清理过期空闲连接
        while (true) {
            long waitNanos = pruneAndGetNextDelayNanos();
            if (waitNanos <= 0) return;
            Thread.sleep(waitNanos);
        }
    };
}
```

**OkHttp 的连接复用逻辑：**

```
第一次请求 www.example.com:
  1. 连接池没有连接 → 新建 TCP 连接
  2. 发 HTTP 请求
  3. 收到响应
  4. 连接归还池（标记为空闲）

第二次请求 www.example.com（同主机）:
  1. 连接池找到空闲连接 → 直接复用（省去 TCP 握手）
  2. 发 HTTP 请求
  3. 收到响应
  4. 归还连接

第三次请求 www.example.com（但连接已被服务端主动断开）:
  1. 连接池找到"空闲"连接
  2. 尝试写请求 → TCP 报错（Connection reset）
  3. 丢弃该连接 → 新建 TCP 连接
  4. 重新发请求
  → 此时用户已感知到延迟（多了一次握手）

关键：OkHttp 不像数据库连接池那样有"借出前 PING"，
     它依赖服务端 HTTP 响应的 Connection: close 头。
```

### 4.2 Apache HttpClient 的 PoolingHttpClientConnectionManager

```java
// Apache HttpClient 的连接池（HttpClient 4.x）

PoolingHttpClientConnectionManager cm = new PoolingHttpClientConnectionManager();
cm.setMaxTotal(200);            // 总连接数上限
cm.setDefaultMaxPerRoute(20);   // 每个目标地址最多 20 个并发连接
```

**HttpClient 的连接复用：**

```
HttpClient 的连接池按 (host, port, scheme) 分组：
  ┌── www.example.com:443:https  → 最多 20 条
  ├── www.api.com:443:https      → 最多 20 条
  └── localhost:6379:redis       → 最多 20 条

每条 HTTP 连接上可以连续发多次请求（HTTP keep-alive）：

  连接 C1:
    请求1 → 响应1 → 请求2 → 响应2 → 请求3 → 响应3
       ↑ 一条 TCP 连接上复用多次请求

服务端主动断连的识别：
  如果服务端在响应头里写了 Connection: close，
  HttpClient 用完这条连接会主动关掉，不归还池

如果服务端"忘记"关（半路断了）：
  → 下次复用这条连接时发现 TCP 已断 → 报错
  → HttpClient 会重新建连接，不影响下一次
```

### 4.3 HTTP 连接池的特殊性

```
HTTP 连接池 vs 数据库/Redis 连接池的三点不同：

不同 1：HTTP 连接没有"验证"概念
  ───────────────────────────────
  DB/Redis 连接：可以发 PING 验证
  HTTP 连接：  没有独立的 PING 机制
    → 只能"用一下才知道是否断了"
    → 所以 HTTP 连接池默认不 testOnBorrow

不同 2：HTTP 连接是"请求-响应"配对，用完必须归还
  ───────────────────────────────
  DB 连接：  可以长时间持有，执行多次 SQL
  HTTP 连接： 每次请求用一条连接，收到响应必须归还
    → 高频场景下归还/借出极其频繁
    → 需要零锁的高并发设计

不同 3：HTTP 连接池按"路由"分组
  ───────────────────────────────
  DB/Redis：通常只连一个地址
  HTTP：     可能同时连几十上百个不同的域名
    → 需要 maxPerRoute 控制每个目标的并发数
    → 否则打爆某个目标的连接限制
```

---

## 五、RabbitMQ 连接池与保活机制

RabbitMQ 客户端（Java 的 `amqp-client` / Spring AMQP 的 `CachingConnectionFactory`）的连接池设计**和前面所有都不一样**——因为它底层用的是 **AMQP 协议**，协议本身就有心跳机制。

### 5.1 AMQP 协议的心跳协商

```
RabbitMQ 客户端建立连接时，心跳是在握手阶段协商出来的：

  客户端发 START-OK:
    heartbeat: 60          ← 客户端提议 60 秒

  服务端回 Connection-Tune:
    heartbeat: 60          ← 服务端同意 60 秒（或返回不同值）

  客户端回 Connection-Tune-OK:
    heartbeat: 60          ← 确认

  └─ 此后双方每 60s 互相发一次心跳包
     → 客户端 60s 无流量 → 发心跳
     → 服务端 60s 无流量 → 发心跳
     → 任一方向收不到心跳 → 对方已断 → 主动关闭
```

**心跳值是协商出来的，不是客户端单方面指定的：**

```java
// Spring AMQP 配置心跳：
spring.rabbitmq.publisher-heartbeat=60

// 实际含义：
//   客户端提议 60，服务端可以回应 0（禁用）或其他值
//   最终心跳间隔 = 客户端提议 ∩ 服务端允许

// 注意：heartbeat=0 意味着禁用协议心跳
//   → 此时完全依赖 TCP 层检测，可靠性大降
```

### 5.2 连接池的特殊性：Channel 复用

```
AMQP 的连接模型和 HTTP/DB 都不同：

  一条 TCP 连接（Connection）
    │
    ├── Channel 1  →  发/收消息（通道 1）
    ├── Channel 2  →  发/收消息（通道 2）
    ├── Channel 3  →  发/收消息（通道 3）
    └── ...

  一条 Connection 上可以开多条 Channel
  每条 Channel 独立发送/接收消息，互不干扰
```

**为什么设计成"一条连接 + 多条 Channel"？**

```
原因 1：TCP 连接开销大（三次握手 + TLS）
  → 复用一条 TCP，开多条 Channel，比开多条 TCP 划算

原因 2：AMQP 协议要求
  → AMQP 规定 Channel 1 必须是"management channel"（预留）
  → 业务 Channel 从 Channel 2 开始
  → 每条 Channel 最多 65535 个（0xFFFF，16 位）

原因 3：Connection 断开时所有 Channel 一起挂
  → 但比"多条 TCP 同时断"更容易恢复
```

### 5.3 CachingConnectionFactory 的连接池设计

```java
// Spring AMQP 的默认连接工厂
CachingConnectionFactory factory = new CachingConnectionFactory("localhost");
factory.setChannelCacheSize(25);           // 默认缓存 25 个 Channel
factory.setConnectionCacheSize(10);        // 默认缓存 10 个 Connection
```

**连接池的"双缓存"结构：**

```
┌─────────────────────────────────────────────────────────┐
│                                                          │
│  ConnectionCache（默认 10 条 Connection）                │
│  ─────────────                                  长链接  │
│                                                          │
│  Connection 1                                            │
│    └── ChannelCache（默认 25 个 Channel）               │
│         ┌─── Channel 1（management，不缓存）            │
│         ├─── Channel 2（缓存中，空闲待用）                │
│         ├─── Channel 3（缓存中，空闲待用）                │
│         ├─── Channel 25（缓存中，空闲待用）               │
│         └─── Channel 26（新建中）                         │
│                                                          │
│  Connection 2                                            │
│    └── ChannelCache（缓存中）                            │
│                                                          │
│  ...                                                     │
│                                                          │
│  默认总连接数 = 1（CachingConnectionFactory 默认）       │
│  默认每连接最多缓存 Channel 数 = 25                       │
│                                                          │
└─────────────────────────────────────────────────────────┘
```

**借出行为：**

```
publish() 被调用时：
  1. 尝试从 ChannelCache 取空闲 Channel
     └─ 有 → 复用（省去 Channel 创建开销）
     └─ 无 → 在当前 Connection 上开新 Channel（Channel 编号 +1）
     └─ 当前 Connection 通道数达上限 → 新建 Connection

  2. 用完 returnChannel(channel)
     └─ 放回 ChannelCache（不超过 cacheSize）
     └─ 超出的 Channel 直接关闭
```

### 5.4 RabbitMQ 断连后的恢复

```
RabbitMQ 客户端没有"连接池重连"概念（不同于 Jedis）

它依赖的是 AMQP 协议的"心跳 + 自动重连"：

  AMQP 心跳机制（协议层）:
    客户端/服务端每 60s 交换一次心跳
    → 任一方超过 2 倍心跳间隔无响应 → 认定对方断开
    → 主动 close() TCP 连接

  Auto-recovery（客户端层）:
    Spring AMQP 默认开启 publisher-confirm + auto-recovery

  断连后恢复流程：
    1. AMQP 心跳检测到对方断开
    2. 客户端自动重建 TCP 连接
    3. 重新握手（START → TUNE → OPEN）
    4. 重开 Channel
    5. 如果启用了 publisher-confirm + mandatory，
       消息发送会收到"确认失败"→ 业务层可重试
```

**与 Jedis 的关键区别：**

```
Jedis（Commons Pool 模式）:
  ┌── 依赖 Common Pool 的 testOnBorrow 换血
  └── 连接断了 → 池里还有假活的 → 借出后才发现

RabbitMQ（CachingConnectionFactory 模式）:
  ┌── 依赖 AMQP 协议心跳主动感知断连
  └── 心跳超时 → 立即关闭连接 → 自动重连
     不会把死连接留在池里等下次借出时才发现
```

### 5.5 Kafka 的类似设计

```
Kafka 客户端（Producer/Consumer）也有类似保活机制：

  配置参数:
    session.timeout.ms = 10000    ← 会话超时（默认 10s）
    heartbeat.interval.ms = 3000  ← 心跳间隔（默认 3s）

  心跳逻辑：
    Producer/Consumer 每 3s 向 Coordinator 发心跳
    连续 10s（session.timeout）未收到心跳 → Coordinator 认为客户端挂了
    → 触发 Rebalance（消费者组重平衡）

  与 RabbitMQ 的差异：
    ├── RabbitMQ：AMQP 协议层心跳（Connection 级别）
    ├── Kafka：   应用层心跳（Consumer Group 级别）
    └── 目的不同：
         RabbitMQ 心跳保"连接不挂"
         Kafka 心跳保"消费位置不丢"（触发 Rebalance 恢复）
```

---

## 六、连接池源码差异与保活原理总览

### 6.1 整体架构对比

```
┌─────────────────────────────────────────────────────────────────┐
│                                                                  │
│  Commons Pool（Jedis）                                           │
│  ──────────────────────────                                     │
│  LinkedBlockingQueue + Evictor                                   │
│  默认 testOnBorrow=true                                          │
│  慢启动：懒加载 minIdle 个连接                                    │
│  借出需加锁                                                     │
│                                                                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  HikariCP（MySQL 默认）                                         │
│  ──────────────────────                                         │
│  FastList + Bag + SynchronousQueue                              │
│  默认 testOnBorrow=false                                        │
│  快启动：立即初始化 maxPoolSize 个连接                            │
│  借出无锁（CAS）                                                │
│                                                                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  OkHttp ConnectionPool（HTTP 默认）                              │
│  ─────────────────────────────                                  │
│  ArrayDeque                                                     │
│  无 testOnBorrow 概念                                          │
│  默认只保留 5 条空闲连接                                         │
│  按 (host, port, scheme) 路由                                   │
│                                                                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  CachingConnectionFactory（RabbitMQ）                           │
│  ──────────────────────────────                                 │
│  ConnectionCache + ChannelCache（双缓存）                        │
│  依赖 AMQP 协议心跳                                            │
│  连接数默认 1，Channel 缓存默认 25                              │
│  Channel 复用代替 TCP 复用                                     │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 6.2 借出行为对比

```
Commons Pool 借出（Jedis）:
  1. 从空闲队列取
  2. testOnBorrow PING 验证   ← 1 RTT 额外开销
  3. 验证通过 → 返回
  4. 验证失败 → 销毁 → 新建连接
  ⚠️ 每次 borrow 都有一次 PING


HikariCP 借出（MySQL）:
  1. 从 availableConnections 取
  2. 直接返回                    ← 0 额外开销
  3. 如果断了 → 业务层下次 IO 时抛异常
  ⚠️ 没有主动验证，全凭"信任"


OkHttp 借出（HTTP）:
  1. 从 connections 双端队列取
  2. 直接尝试写请求
  3. 如果 TCP 断了 → 重试建连接
  4. 重试后正常发送
  ⚠️ 没有验证，依赖 TCP 层错误检测
```

### 6.3 为什么 OkHttp 不用 HikariCP 的设计

```
场景差异：

  HTTP 请求：
    借 → 发请求 → 收响应 → 归还
    整个过程通常 50~500ms
    同一时刻同一客户端对同一域名的并发请求不多

  DB 查询：
    借 → 执行 SQL（可能 1ms~数秒）→ 归还
    同一时刻可能有数百线程同时持有连接

  → HTTP 连接池主要瓶颈在"频繁借还时的竞争"
    → 所以用了简单高效的 ArrayDeque

  → DB 连接池主要瓶颈在"高并发借还 + 连接健康"
    → 所以 HikariCP 用了 Bag + 零锁设计
```

### 6.4 保活机制总览：五种协议，五种策略

> 这是本节最核心的问题——你问的"长链接怎么保证服务端不断开"，本质上是问五类客户端各自用了什么策略。
> 答案是：**每一层都有不同的保活手段，从 TCP 层到应用层，层层叠加。**

```
┌─────────────────────────────────────────────────────────────────┐
│                                                                  │
│  层次    机制              触发方    检测什么                        │
│  ─────  ──────────────   ──────   ───────────────────────       │
│                                                                  │
│  L1  TCP keepalive    内核层     对端是否还活着（TCP 层）        │
│       双方都发           默认关    不关心协议内容                 │
│                                                                  │
│  L2  PING/PONG         应用层   对端是否还活着 + 协议栈是否正常   │
│       主动探活           或被动   关心整个协议栈                 │
│                                                                  │
│  L3  Session 超时      服务端   客户端多久没发心跳                │
│       踢人              强制     超时就认为客户端挂了             │
│                                                                  │
│  L4  Idle 连接驱逐     客户端   连接在池里多久没用               │
│       Evictor          或服务端 超过 idleTimeout 就关闭          │
│                                                                  │
│  L5  Heartbeat 协议    AMQP    双方互相主动发心跳                 │
│       双向心跳          Kafka    超过 2×心跳间隔无响应→断开       │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 6.4.1 各协议具体保活策略

```
┌─────────────────────────────────────────────────────────────────┐
│                                                                  │
│  Jedis（Redis，Commons Pool）                                    │
│  ──────────────────────────────                                 │
│                                                                  │
│  L1 TCP keepalive:   ❌ 关闭（Netty 默认关）                      │
│  L2 PING 心跳:       ✅ testOnBorrow / testWhileIdle 的 PING   │
│                       客户端主动 → 服务端被动回 PONG             │
│  L3 Session 超时:    Redis server 端 `timeout` 配置               │
│                       默认 0 = 永不超时                           │
│  L4 Idle 驱逐:       ✅ Evictor 线程按 testWhileIdlePeriod 扫     │
│                                                                  │
│  一句话：靠应用层 PING + Evictor 巡检，
│         TCP 层靠不住（7200s 默认）                               │
│                                                                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Lettuce（Redis，Netty）                                          │
│  ──────────────────────────────                                 │
│                                                                  │
│  L1 TCP keepalive:  ✅ Netty SocketOptions.keepAlive(true)      │
│  L2 PING 心跳:      ✅ 可选配置 commandTimeout + idleCheck      │
│  L3 Session 超时:   Redis server 端 `timeout`                    │
│  L4 Idle 驱逐:      ✅ 同 HikariCP 思路，由 housekeeping 处理   │
│                                                                  │
│  一句话：Netty 底层 TCP keepalive + 应用层心跳双重保障          │
│                                                                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  CachingConnectionFactory（RabbitMQ）                            │
│  ──────────────────────────────────                              │
│                                                                  │
│  L1 TCP keepalive:  ✅ AMQP 客户端可开启                           │
│  L2 AMQP 心跳:      ✅ 握手阶段协商（如 60s）                   │
│                       双方互相主动发，不是"客户端查服务端"        │
│  L3 Session 超时:   AMQP 的 heartbeat 本身充当了超时机制         │
│  L4 Idle 驱逐:      ✅ 超心跳 2 倍即认为断连，自动关闭           │
│                                                                  │
│  一句话：AMQP 协议内建双向心跳，是"最聪明"的保活设计            │
│                                                                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Kafka Producer/Consumer                                        │
│  ──────────────────────────────                                 │
│                                                                  │
│  L1 TCP keepalive:  ✅ Java Socket keepalive（Netty 层）        │
│  L2 应用层心跳:      ✅ heartbeat.interval.ms（默认 3s）        │
│                       每 3s 向 Group Coordinator 发一次心跳     │
│  L3 Session 超时:    session.timeout.ms（默认 10s）              │
│                       10s 未收心跳 → Coordinator 认为客户端挂了   │
│                       → 触发 Rebalance                          │
│  L4 Idle 驱逐:       ✅ 超 session.timeout 直接踢出消费组        │
│                                                                  │
│  一句话：心跳不只保"连接不挂"，还保"消费位点不丢"               │
│                                                                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  OkHttp（HTTP）                                                   │
│  ──────────────────────                                         │
│                                                                  │
│  L1 TCP keepalive:  ⚠️ 默认关（Netty 层，可手动开）              │
│  L2 应用层心跳:     ❌ HTTP 协议没有心跳概念                    │
│  L3 服务端超时:     HTTP 服务器 `keepalive_timeout`              │
│                       Nginx 默认 75s                             │
│  L4 Idle 驱逐:      ✅ 连接池按 maxIdle 和 keepAliveDuration 关 │
│                                                                  │
│  一句话：HTTP 没有应用层心跳，全凭"快速用完 + 超时关闭"          │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 6.4.2 关键洞察：为什么 RabbitMQ/Kafka 有心跳而 HTTP 没有？

```
HTTP 的设计理念:
  请求-响应 模型，用完了就走
  连接保不保活不重要，重要的是"下次来能快速复用"
  → 所以 HTTP 用 Connection: keep-alive 头 + 服务端 timeout
  → 没有主动心跳，全靠"快速用完 + 超时关闭"

RabbitMQ 的设计理念:
  长连接 + 持久化 + 订阅
  一条连接可能挂 24 小时不发消息（消费端等待）
  → 必须有心跳，否则中间件断掉也不知道
  → 所以 AMQP 协议层内置双向心跳

Kafka 的设计理念:
  消费组 + 位点管理
  客户端挂了要立刻触发 Rebalance（让别的客户端接管）
  → 心跳不只保连接，还保"我在正常工作"
  → 所以 Kafka 心跳间隔 < session.timeout < 业务处理耗时
     三者是精心设计的三角关系
```

---

## 七、参数调优与常见坑

### 7.1 通用参数对照

```
┌───────────────────┬─────────────────┬──────────────────────────┐
│ 参数              │ 建议值           │ 错误设法的后果            │
├───────────────────┼─────────────────┼──────────────────────────┤
│ maxTotal          │ 与业务 QPS ×     │ 设太大 → 打爆 DB max_clients│
│                   │ 平均查询耗时     │                          │
│                   │ ≈ 20~50（一般）   │                          │
├───────────────────┼─────────────────┼──────────────────────────┤
│ minIdle           │ ≈ maxTotal / 4   │ 设太大 → 浪费连接占用内存   │
│                   │ HikariCP 可设 = 0│                          │
│                   │ （延迟创建）       │                          │
├───────────────────┼─────────────────┼──────────────────────────┤
│ maxWaitMillis     │ 1000~3000ms      │ 设太长 → 业务卡死感知不到  │
│                   │                   │ 设太短 → 正常抖动也报错    │
├───────────────────┼─────────────────┼──────────────────────────┤
│ testOnBorrow      │ HikariCP: false  │ HikariCP 强制 false       │
│                   │ Commons Pool: true│                          │
├───────────────────┼─────────────────┼──────────────────────────┤
│ testWhileIdle     │ true             │ 不开 → 死连接可能混到池中   │
├───────────────────┼─────────────────┼──────────────────────────┤
│ idleTimeout       │ 10min            │ 设太长 → 死连接清理不及时   │
│                   │ HikariCP 默认 10m│                          │
├───────────────────┼─────────────────┼──────────────────────────┤
│ maxLifetime       │ 30min~2h         │ 设太长 → 老连接遇到 DNS 变化 │
│                   │                   │ 会找不到数据库              │
└───────────────────┴─────────────────┴──────────────────────────┘
```

### 7.2 四大常见坑

```
坑 1 · HikariCP 默认 30s 超时，业务代码没 catch
═══════════════════════════════════════

  HikariCP 池满时最多等 30s → SQLException
  如果业务代码没 catch：
    → Tomcat 线程全部卡在 getConnection() 上
    → 整个服务变 503

  正确做法：
    - 业务层设置合理的数据库超时（queryTimeout）
    - 全局异常处理器捕获 SQLException
    - 配合熔断器（Hystrix/Resilience4j）降级

坑 2 · 连接泄漏检测没开，数据库连接池"慢慢死"
═══════════════════════════════════════

  代码中忘了 returnObject / close()：
    try {
        Connection conn = dataSource.getConnection();
        stmt.executeQuery(...);
        // 忘记 conn.close() 了！
    }

  HikariCP 默认漏检不开：
    → 连接一直被"借"着，无法归还
    → 池慢慢耗尽 → 服务假死

  正确做法：
    dataSource.setLeakDetectionThreshold(60000);  // 60s 未归还告警
    → HikariCP 会打印堆栈，定位漏掉的代码


坑 3 · maxLifetime 与 DB 端 timeout 冲突
═══════════════════════════════════════

  DB 端配置了 wait_timeout = 8h（MySQL 默认）
  HikariCP 配置了 maxLifetime = 30min

  正常情况：HikariCP 先关，DB 端不会断
  异常情况：网络抖动时 DB 端可能先断了

  原则：
    客户端 maxLifetime 应该 < 服务端 wait_timeout
    且服务端 timeout 应该 > 客户端 maxLifetime × 1.2（留余量）


坑 4 · OkHttp 连接池默认 5 条，打高并发时全部重建
═══════════════════════════════════════

  OkHttp 默认 maxIdleConnections = 5
  高并发时：
    → 5 条连接全部"借用中"
    → 第 6 条请求 → 池空 → 新建连接
    → 第 100 条 → 池还是 5 条空闲 → 又新建

  正确做法：
    OkHttpClient client = new OkHttpClient.Builder()
        .connectionPool(new ConnectionPool(200, 10, TimeUnit.MINUTES))
        .build();
    // maxIdle = 200，keepAlive = 10min
    // 配合服务端 HTTP keep-alive timeout 配置
```

---

## 八、知识串联

```
connection-pool 与已学笔记的关联：

┌──────────────────────────────────────────────────────────┐
│                                                          │
│  computer/thread-pool/source-analysis.md                 │
│    线程池管理"执行资源"                                    │
│    execute() 方法的状态机、Worker 保活                    │
│                                                          │
│  本次专题: 连接池管理"网络资源"                             │
│    borrowObject() 方法的状态机、Evictor 保活              │
│                                                          │
│  共同点：                                                 │
│    ├── 都是"池化"思想：先建好，借出用，用完归还               │
│    ├── 都有"最大数"限制 + "等待/拒绝"策略                   │
│    ├── 都有"健康检查"机制                                 │
│    └── 高并发下都需要"无锁"设计                             │
│                                                          │
│  不同点：                                                 │
│    ├── 线程池归还时不需要"校验"（线程不会死）                │
│    │    连接池归还时必须"校验"（连接会断）                  │
│    │                                                          │
│    └── 连接池有"生命周期"概念（建连接 vs 销毁连接）          │
│         线程池没有（线程创建后不会变）                      │
│                                                          │
├──────────────────────────────────────────────────────────┤
│                                                          │
│  computer/redis/redis-analysis.md                         │
│    7.4 节讲了连接池通用参数                                 │
│    本次专题深入 HikariCP vs Commons Pool 源码差异           │
│    以及 HTTP 连接池的特殊性                                │
│                                                          │
├──────────────────────────────────────────────────────────┤
│                                                          │
│  computer/netty/pipeline.md                              │
│    OkHttp 底层用 Netty                                    │
│    HTTP 连接池复用 TCP = Netty 的 Channel 复用             │
│    见 pipeline.md 关于 Channel 生命周期的部分               │
│                                                          │
└──────────────────────────────────────────────────────────┘
```

### 各场景连接池选型速查

```
┌─────────────────────┬──────────────────────┬────────────────────┐
│ 场景               │ 推荐连接池            │ 理由               │
├─────────────────────┼──────────────────────┼────────────────────┤
│ MySQL / PostgreSQL   │ HikariCP             │ 最快、Spring Boot 默认 │
├─────────────────────┼──────────────────────┼────────────────────┤
│ Redis（Jedis）       │ Common Pool          │ Jedis 内置，简单成熟  │
├─────────────────────┼──────────────────────┼────────────────────┤
│ Redis（Lettuce）     │ 无需连接池            │ 单连接多线程共享      │
├─────────────────────┼──────────────────────┼────────────────────┤
│ RabbitMQ            │ CachingConnectionFactory │ 双缓存+AMQP心跳协议内建保活 │
├─────────────────────┼──────────────────────┼────────────────────┤
│ HTTP 客户端          │ OkHttp ConnectionPool │ 自动管理、按路由分组  │
│                     │ HttpClient Pool      │                     │
├─────────────────────┼──────────────────────┼────────────────────┤
│ Kafka Producer       │ Kafka 内置缓冲池       │ 内部用 RecordAccumulator │
└─────────────────────┴──────────────────────┴────────────────────┘
```
