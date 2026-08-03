# 秒杀商城系统技术总结

> 整理日期：2026-07-29
> 涵盖主题：NIO/BIO/AIO → 高并发秒杀 → 异步通知 → 大数据Excel导出

---

## 目录

1. [NIO、BIO、AIO 的核心区别](#一niobioaio-的核心区别)
2. [Channel 与 Selector 的关系](#二channel-与-selector-的关系)
3. [configureBlocking(false) 的本质](#三configureblockingfalse-的本质)
4. [秒杀系统高并发与库存一致性](#四秒杀系统高并发与库存一致性)
5. [MQ 消费失败处理机制](#五mq-消费失败处理机制)
6. [异步场景下用户通知方案](#六异步场景下用户通知方案)
7. [数据库分批读取方案](#七数据库分批读取方案)
8. [超大 Excel 流式写入原理](#八超大-excel-流式写入原理)
9. [SXSSF 临时文件清理机制](#九sxssf-临时文件清理机制)
10. [tmp 目录的设计哲学](#十tmp-目录的设计哲学)

---

## 一、NIO、BIO、AIO 的核心区别

### 1.1 本质：谁在等，谁在读

| 模式 | 谁在等 | 谁在读 | 核心问题 |
|------|--------|--------|----------|
| **BIO** | 用户线程（自己睡觉）| 用户线程 | 1连接=1线程，内存爆炸 |
| **NIO** | select() / epoll()（内核代理）| 用户线程 | 解决了内存问题，但复杂度上升 |
| **AIO** | 操作系统内核（完全外包）| 操作系统内核 | 回调驱动，编程模型最简单 |

### 1.2 BIO 的阻塞模型

```
BIO 线程的真实状态：

  时刻1: socket.accept()  ──→ [睡死，等连接]      CPU: 0%
  时刻2: socket.read()    ──→ [睡死，等数据]      CPU: 0%
  时刻3: 数据来了，唤醒线程
  时刻4: 真正读数据（内存拷贝）                    CPU: 瞬间
  时刻5: 处理数据（业务逻辑）                      CPU: 取决于业务
  时刻6: 回到 read()      ──→ [睡死]              CPU: 0%

90% 的时间线程在"等"，只有 10% 在"干活"——最大浪费。
```

### 1.3 NIO 的非阻塞模型

```
NIO 单线程的真实状态：

  时刻1: selector.select()   ──→ [睡，等任一Channel就绪]  CPU: 0%
  时刻2: Channel-3 变得可读
  时刻3: key.isReadable() → channel.read(buffer)  ──→ 立即读到数据！CPU: 瞬间
  时刻4: 处理 buffer 里的数据（纯内存操作）               CPU: 瞬间
  时刻5: 回到 selector.select()  ──→ [睡]            CPU: 0%

"等"这件事由 OS 内核的 epoll 代理，不占你的线程。
```

### 1.4 read() 本身不快，快的是"不用等"

```
BIO 和 NIO 调用的是同一个 read() 系统调用：
→ 把数据从内核缓冲区复制到用户缓冲区，速度完全相同
→ NIO 快的原因：数据没到时，线程不被迫睡觉，可以去干别的事

类比：
  BIO = 你站在快递柜前等快递员放快递
  NIO = 你留手机号走人，快递到了手机通知你
  动作没变，省的是等待时间。
```

### 1.5 核心结论

> **NIO 相比 BIO 的最大优势：不是 read() 变快了，而是 BIO 需要线程在等网络中数据到来，而 NIO 不需要。**
>
> BIO 的线程是"等待的代价"——等待要单独分配一个线程和内存。
> NIO 的 Selector 是"等待的复用"——一个线程替所有连接等待，成本极低。

---

## 二、Channel 与 Selector 的关系

### 2.1 为什么 Stream 不行？

```
BIO 用的是 InputStream / OutputStream：
  → 每个连接需要两个流（读+写）
  → Stream 不能切换到非阻塞模式
  → Stream 不能注册到 Selector
  → Stream 天生就是阻塞的
```

### 2.2 Channel 的定义

```
Channel = 能被 Selector 监控的"连接"

① 包装了 fd（文件描述符，操作系统层面）
② 支持非阻塞模式 configureBlocking(false)
③ 可以注册到 Selector
④ 双向：既可读又可写（不需要两个流）
```

### 2.3 完整链路

```
应用代码
    │
    │ 操作
    ↓
Channel（包装 fd，切换非阻塞模式）
    │
    │ register()
    ↓
Selector（监控 Channel 里的 fd）
    │
    │ epoll / select 系统调用
    ↓
操作系统内核（监控 socket fd 状态变化）
    │
    │ 数据到达
    ↓
返回就绪事件给 Selector
    │
    │ channel.read(buffer)
    ↓
用户态（从内核复制数据到 Buffer）
```

### 2.4 Channel vs Stream 对比

| 问题 | Stream（BIO）| Channel（NIO）|
|------|------------|--------------|
| 连接是什么 | `Socket` 对象自带流 | `SocketChannel` 对象 |
| 能否非阻塞 | 不能 | `configureBlocking(false)` |
| 能否被 Selector 监控 | 不能 | `register(selector, OP_READ)` |
| 读写需要几个对象 | 两个（读流+写流）| 一个 Channel 就够了 |

---

## 三、configureBlocking(false) 的本质

### 3.1 阻塞 vs 非阻塞

```java
// 阻塞模式（默认，和 BIO 一样）
channel.configureBlocking(true);
channel.read(buffer);   // 数据没到？线程睡死 ❌

// 非阻塞模式
channel.configureBlocking(false);
channel.read(buffer);  // 数据没到？立即返回 0，不阻塞 ✅
```

### 3.2 底层原理对比

```
阻塞模式（true）：
  channel.read() 被调用
       ↓
  OS 检查：数据有没有到？
       ↓
  没到 → 线程进入睡眠状态（不占CPU）
  到了 → 唤醒线程，复制数据，返回

非阻塞模式（false）：
  channel.read() 被调用
       ↓
  OS 检查：数据有没有到？
       ↓
  没到 → 立即返回 0 或 -1（不等待）
  到了 → 立即复制数据并返回字节数
  线程永远不睡觉，永远不阻塞
```

### 3.3 为什么必须是非阻塞模式？

```
Selector 通知的是"可能可以读"，不是"保证有数据"。

阻塞模式（Channel）：Selector 通知你"可读"，你去读，发现没数据 → 线程再次睡死 ❌
非阻塞模式（Channel）：Selector 通知你"可读"，你去读，有数据就读到，没数据就返回0 → 继续 select() ✅

只有 Channel 是非阻塞的，Selector 单线程才能高效管理海量连接。
```

### 3.4 非阻塞模式 read() 的返回值

```java
int n = channel.read(buffer);

n > 0   // 读到了 n 个字节，数据在 buffer 里
n == 0  // 没有数据（对方没发），但连接没关闭，是常态
n == -1 // 连接对方关闭了，可以关闭 Channel 了
```

---

## 四、秒杀系统高并发与库存一致性

### 4.1 什么是超发和少发

```
超发：100件库存，卖出了 120 单  ← 付了钱没货，最严重
少发：100件库存，只卖出了 80 单  ← 有货卖不出去，损失收入

理想状态：卖出数 = 库存数，直到库存归零。
```

### 4.2 完整分层架构

```
┌─────────────────────────────────────────────────────────────┐
│                      用户请求 (10000+ QPS)                    │
└──────────────────────────────┬──────────────────────────────┘
                               │
                    ┌──────────▼──────────┐
                    │   1. 接入层           │
                    │   限流 + 熔断 + 鉴权  │
                    └──────────┬───────────┘
                               │
                    ┌──────────▼──────────┐
                    │   2. 缓存层 (Redis)  │
                    │   库存预扣 + Lua原子扣减│
                    └──────────┬───────────┘
                               │ 库存充足时
                    ┌──────────▼──────────┐
                    │   3. 消息队列 (MQ)    │
                    │   异步下单 + 削峰填谷  │
                    └──────────┬───────────┘
                               │
                    ┌──────────▼──────────┐
                    │   4. 数据库层 (MySQL)│
                    │   最终一致性 + 库存回滚 │
                    └─────────────────────┘
```

### 4.3 MySQL 原子扣减（防超发底线）

```sql
-- ✅ 正确做法（一步操作，原子，不会超发）
UPDATE inventory
SET stock = stock - 1
WHERE product_id = ?
  AND stock > 0;  -- stock > 0 是关键！

-- 影响行数 = 1 → 扣减成功
-- 影响行数 = 0 → 库存不足

-- ❌ 错误做法（两步操作，非原子，会超发）
SELECT stock FROM inventory WHERE product_id = ?;  -- 读到 stock = 1
UPDATE inventory SET stock = stock - 1;           -- 线程A扣成0
UPDATE inventory SET stock = stock - 1;           -- 线程B扣成-1，超发！
```

### 4.4 Redis Lua 原子扣减（扛住高并发）

```lua
-- seckill_stock.lua
-- Redis 执行 Lua 脚本是原子的，整个脚本执行期间不会执行其他命令

local stock = redis.call('GET', KEYS[1])

if not stock then
    return -1  -- 库存未初始化
end

stock = tonumber(stock)

if stock <= 0 then
    return 0   -- 库存不足
end

redis.call('DECR', KEYS[1])
return stock - 1  -- 返回扣减后的库存数
```

### 4.5 三层防超发体系

```
第一层：Redis Lua 原子扣减
  → Lua 保证 Redis 内部操作原子
  → 10万并发进来，只有100个能扣成功（库存100件）

第二层：MySQL UPDATE WHERE stock > 0
  → 即使 Redis 失效，MySQL 层原子保证

第三层：唯一索引兜底
  → 同一用户同一商品只有一条订单记录
  → 插入失败直接返回"已购买"
```

### 4.6 核心服务代码

```java
@Service
public class SeckillService {

    @Autowired
    private RedisTemplate<String, Object> redisTemplate;
    @Autowired
    private KafkaTemplate<String, SeckillMessage> kafkaTemplate;
    @Autowired
    private DefaultRedisScript<Long> seckillScript;

    /**
     * 秒杀下单（核心逻辑）
     */
    public Result seckillOrder(Long userId, Long productId) {
        // ===== 第一步：Redis Lua 原子扣库存 =====
        Long stockLeft = redisTemplate.execute(
            seckillScript,
            Collections.singletonList("seckill:stock:" + productId)
        );

        if (stockLeft == null || stockLeft < 0) {
            throw new SeckillException("库存不足，请稍后重试");
        }

        // ===== 第二步：检查是否重复购买 =====
        String userKey = "seckill:user:" + productId + ":" + userId;
        Boolean isNew = redisTemplate.opsForValue().setIfAbsent(userKey, "1");
        if (Boolean.FALSE.equals(isNew)) {
            throw new SeckillException("您已参与过秒杀，请勿重复购买");
        }

        // ===== 第三步：发送订单消息到 MQ =====
        String orderId = generateOrderId(userId, productId);
        SeckillMessage msg = new SeckillMessage(userId, productId, orderId);
        kafkaTemplate.send("seckill_orders", orderId, msg);

        // ===== 第四步：返回结果 =====
        return Result.success("下单成功，订单号：" + orderId);
    }
}
```

### 4.7 数据库表设计

```sql
CREATE TABLE inventory (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    product_id BIGINT NOT NULL,
    stock INT NOT NULL DEFAULT 0,
    version INT NOT NULL DEFAULT 0,
    create_time DATETIME,
    update_time DATETIME,
    INDEX idx_product (product_id)
);

CREATE TABLE orders (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    order_id VARCHAR(64) NOT NULL UNIQUE,
    user_id BIGINT NOT NULL,
    product_id BIGINT NOT NULL,
    status VARCHAR(20),
    create_time DATETIME,
    INDEX idx_user_product (user_id, product_id),
    -- 唯一索引防止重复下单
    UNIQUE INDEX idx_seckill (user_id, product_id)
);
```

---

## 五、MQ 消费失败处理机制

### 5.1 失败分两类

```
1. 临时性失败（可恢复）
   - MySQL 连接超时
   - 网络抖动
   → 应该重试

2. 永久性失败（不可恢复）
   - 库存不足
   - 订单已存在
   - 数据格式错误
   → 直接标记失败，不重试
```

### 5.2 指数退避重试

```java
@KafkaListener(topics = "seckill_orders", groupId = "seckill-group")
public void processOrder(SeckillMessage msg) {
    int maxRetry = 3;
    int retryCount = 0;

    while (retryCount < maxRetry) {
        try {
            doProcessOrder(msg);
            return;  // 成功，直接返回
        } catch (TemporaryException e) {
            // 临时性错误，指数退避重试：2s, 4s, 8s
            retryCount++;
            long delay = (long) Math.pow(2, retryCount) * 1000;
            Thread.sleep(delay);
            log.warn("消费失败，第{}次重试", retryCount);
        } catch (PermanentException e) {
            // 永久性错误，不重试，直接进入失败流程
            handlePermanentFailure(msg, e.getMessage());
            return;
        }
    }

    // 超过最大重试次数，进入死信队列
    sendToDeadLetterQueue(msg, "max_retry_exceeded");
}
```

### 5.3 死信队列（DLQ）兜底

```
┌──────────────┐     消费失败      ┌──────────────┐
│ seckill_orders │ ──重试3次均失败──→ │ seckill_orders_DLQ │
│   (主队列)     │                  │   (死信队列)       │
└──────────────┘                  └──────────────┘
                                            │
                              ┌─────────────┼─────────────┐
                              ↓             ↓             ↓
                        告警通知      人工处理      库存回滚
                        (管理员)     (运营介入)     (自动)
```

### 5.4 库存回滚

```java
private void handlePermanentFailure(SeckillMessage msg, String reason) {
    log.error("订单处理最终失败: orderId={}, reason={}", msg.getOrderId(), reason);

    // ===== 第一步：回滚 Redis 库存 =====
    String redisKey = "seckill:stock:" + msg.getProductId();
    redisTemplate.opsForValue().increment(redisKey);

    // ===== 第二步：记录失败订单 =====
    FailOrderRecord record = new FailOrderRecord();
    record.setOrderId(msg.getOrderId());
    record.setUserId(msg.getUserId());
    record.setProductId(msg.getProductId());
    record.setFailReason(reason);
    record.setFailTime(new Date());
    failOrderMapper.insert(record);

    // ===== 第三步：更新用户状态 =====
    String userKey = "seckill:user:" + msg.getProductId() + ":" + msg.getUserId();
    redisTemplate.delete(userKey);

    // ===== 第四步：通知用户 =====
    notifyUserFailure(msg.getUserId(), msg.getOrderId(), reason);
}
```

### 5.5 定时任务兜底

```java
/**
 * 定时任务：检查 10 分钟内未完成的订单
 * 防止消息丢失、死信处理遗漏等极端情况
 */
@Scheduled(fixedDelay = 60000)
public void checkPendingOrders() {
    List<Order> pendingOrders = orderMapper.selectPendingOrders(
        LocalDateTime.now().minusMinutes(10)
    );

    for (Order order : pendingOrders) {
        OrderStatus status = queryRealStatus(order.getOrderId());

        if (status == OrderStatus.SUCCESS) {
            // 状态一致，无需处理
        } else if (status == OrderStatus.FAILED) {
            rollbackInventory(order.getProductId());
        } else {
            // 状态未知，重新投递
            kafkaTemplate.send("seckill_orders_retry", order.getOrderId(), toMessage(order));
        }
    }
}
```

---

## 六、异步场景下用户通知方案

### 6.1 三种通知方式组合

```
用户下单
    │
    ├── 同步返回：下单请求已受理（PROCESSING）
    │
    ├── 异步处理中...
    │       │
    │       ├── 成功 → 通知用户
    │       └── 失败 → 通知用户 + 库存回滚
    │
    └── 用户侧三种通知方式（组合使用）
            ├── ① 轮询查询订单状态（最简单）
            ├── ② WebSocket 实时推送（最及时）
            └── ③ 短信/推送通知（最终兜底）
```

### 6.2 方案一：轮询查询

```java
// 接口1：提交秒杀
@PostMapping("/seckill/order")
public Result submitOrder(Long userId, Long productId) {
    return Result.success(orderId, "PROCESSING");
}

// 接口2：查询订单状态
@GetMapping("/order/status")
public Result getOrderStatus(String orderId) {
    Order order = orderMapper.selectByOrderId(orderId);
    if (order == null) {
        String tempStatus = redisTemplate.opsForValue()
            .get("order:temp:" + orderId);
        return Result.success(tempStatus != null ? tempStatus : "PROCESSING");
    }
    return Result.success(order.getStatus());
}
```

```javascript
// 前端：每 2 秒查一次，最多 60 次
async function pollOrderStatus(orderId) {
    for (let i = 0; i < 60; i++) {
        await sleep(2000);
        const { status } = await fetch(`/order/status?orderId=${orderId}`);

        if (status === 'SUCCESS') {
            showSuccess('下单成功！订单号：' + orderId);
            return;
        }
        if (status === 'FAILED') {
            showFailure('下单失败，请重新尝试');
            return;
        }
    }
    showFailure('订单处理超时，请稍后查看订单列表');
}
```

### 6.3 方案二：WebSocket 实时推送

```java
@Service
public class WebSocketService {

    // userId → WebSocket Session 映射
    private Map<Long, Session> userSessions = new ConcurrentHashMap<>();

    @OnOpen
    public void onOpen(Session session, @PathParam("userId") Long userId) {
        userSessions.put(userId, session);
    }

    @OnClose
    public void onClose(@PathParam("userId") Long userId) {
        userSessions.remove(userId);
    }

    // 推送订单结果给用户
    public void pushOrderResult(Long userId, OrderResult result) {
        Session session = userSessions.get(userId);
        if (session != null && session.isOpen()) {
            session.getAsyncRemote().sendObject(JSON.toJSONString(result));
        }
    }
}

// MQ 消费完成后推送
@KafkaListener(topics = "seckill_orders")
public void processOrder(SeckillMessage msg) {
    try {
        doProcessOrder(msg);
        webSocketService.pushOrderResult(msg.getUserId(),
            new OrderResult("SUCCESS", msg.getOrderId(), "下单成功！"));
    } catch (Exception e) {
        webSocketService.pushOrderResult(msg.getUserId(),
            new OrderResult("FAILED", msg.getOrderId(), "下单失败，库存已释放"));
        handlePermanentFailure(msg, e.getMessage());
    }
}
```

### 6.4 方案三：短信/推送通知（兜底）

```java
@KafkaListener(topics = "seckill_orders")
public void processOrder(SeckillMessage msg) {
    try {
        doProcessOrder(msg);

        // 成功通知
        notifyService.sendSms(msg.getUserId(),
            "【秒杀】您已成功秒杀商品，订单号：" + msg.getOrderId() + "，请在30分钟内支付。");
        notifyService.sendPush(msg.getUserId(), "🎉 秒杀成功！", "订单号：" + msg.getOrderId());

    } catch (Exception e) {
        // 失败通知
        notifyService.sendSms(msg.getUserId(),
            "【秒杀】您参与的秒杀活动处理失败，库存已释放，请重新尝试。");
        notifyService.sendPush(msg.getUserId(), "❌ 秒杀失败", "库存已释放，可重新参与。");
        handlePermanentFailure(msg, e.getMessage());
    }
}
```

### 6.5 完整流程图

```
用户发起秒杀请求
        │
        ├── Redis Lua 扣库存失败
        │       └── 同步返回：{"status": "SOLD_OUT", "msg": "库存已售罄"}
        │
        └── Redis Lua 扣库存成功
                │
                ├── 发 MQ 消息
                ├── 写 Redis 临时状态：PROCESSING
                └── 同步返回：{"status": "PROCESSING", "orderId": "ORD_001"}

                ┌─────────────────────────────────────┐
                │          MQ 异步消费                 │
                └──────────────┬──────────────────────┘
                               │
              ┌────────────────┼────────────────┐
              ↓                ↓                ↓
        ┌───────────┐  ┌───────────┐  ┌────────────────┐
        │ MySQL扣库存│  │ 临时失败   │  │ 永久失败        │
        │ 成功       │  │(网络抖动)  │  │(库存不足等)     │
        └─────┬─────┘  └─────┬─────┘  └───────┬────────┘
              │              │                │
              ↓              ↓                ↓
        ┌───────────┐  ┌───────────┐  ┌────────────────┐
        │创建订单    │  │指数退避    │  │ 回滚Redis库存   │
        │SUCCESS    │  │重试(2,4,8s│  │ 删除购买标记    │
        └─────┬─────┘  └─────┬─────┘  └───────┬────────┘
              │              │                │
              ↓              │                ↓
        ┌───────────┐        │         ┌──────────────┐
        │ MQ消费成功 │        │         │ 告警+记录DLQ  │
        │ 通知用户   │        │         └──────────────┘
        └─────┬─────┘        │                │
              │              ↓                ↓
              │        重试3次失败          ┌──────────────┐
              │              │              │ 通知用户失败  │
              │              └──────────────│ 短信/推送    │
              │                           └──────────────┘
              │
       ┌──────┼──────┬──────────┐
       ↓      ↓      ↓          ↓
    ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐
    │ WS  │ │轮询 │ │短信 │ │推送 │
    │推送 │ │查询 │ │通知 │ │通知 │
    └─────┘ └─────┘ └─────┘ └─────┘
       ↑      ↑      ↑      ↑
       └──────┴──────┴──────┘
            用户感知结果
```

---

## 七、数据库分批读取方案

### 7.1 三种分页方式对比

| 方式 | 原理 | 缺点 | 适用场景 |
|------|------|------|---------|
| `OFFSET LIMIT` | `OFFSET N, LIMIT M` | OFFSET越大越慢，要先跳过N行 | 百万以下 |
| **游标分页（推荐）** | 记录上次位置，下次从该位置继续 | 需要有唯一排序字段 | **千万级，必须用** |
| `WHERE id > lastId` | 主键/时间戳 > 上次值 | 适合连续递增字段 | 订单表 |

### 7.2 为什么游标分页比 OFFSET 快？

```
假设有 1000 万条数据，查第 500 万 ~ 500万+1000 条：

OFFSET 方式：
  SELECT ... LIMIT 1000 OFFSET 5000000
  → 数据库要扫描到第500万行才返回
  → 时间复杂度：O(N)

游标分页方式：
  SELECT ... WHERE id > 5000000 LIMIT 1000
  → 直接从 id=5000001 开始拿
  → 时间复杂度：O(1)，恒定
```

### 7.3 游标分页核心代码

```java
@Service
public class OrderBatchService {

    @Autowired
    private OrderMapper orderMapper;

    public <T> void batchProcess(OrderQueryParams params,
                                  int batchSize,
                                  BatchProcessor<T> processor) {
        long lastId = 0L;
        int totalProcessed = 0;
        boolean hasMore = true;

        while (hasMore) {
            // ===== 每次只查 batchSize 条 =====
            List<T> batch = orderMapper.selectOrdersByCursor(
                lastId, batchSize,
                params.getStartDate(),
                params.getEndDate(),
                params.getStatus()
            );

            if (batch.isEmpty()) {
                hasMore = false;
                break;
            }

            processor.process(batch);

            // ===== 记录游标：取这批最后一条的ID =====
            T lastRecord = batch.get(batch.size() - 1);
            lastId = extractId(lastRecord);

            totalProcessed += batch.size();
            hasMore = (batch.size() == batchSize);

            // 控制数据库 QPS
            if (hasMore) {
                Thread.sleep(10);
            }

            if (totalProcessed % 50000 == 0) {
                log.info("已处理 {} 条，当前游标 lastId={}", totalProcessed, lastId);
            }
        }

        log.info("全部处理完成，总计: {} 条", totalProcessed);
    }
}
```

### 7.4 Mapper SQL

```java
@Mapper
public interface OrderMapper {

    @Select("<script>" +
        "SELECT id, order_id, user_id, product_id, amount, " +
        "       status, create_time, update_time " +
        "FROM orders " +
        "WHERE id > #{lastId} " +
        "  AND create_time BETWEEN #{startDate} AND #{endDate} " +
        "<if test='status != null'> AND status = #{status} </if>" +
        "ORDER BY id ASC " +
        "LIMIT #{pageSize} " +
        "</script>")
    List<Order> selectOrdersByCursor(
        @Param("lastId") long lastId,
        @Param("pageSize") int pageSize,
        @Param("startDate") LocalDateTime startDate,
        @Param("endDate") LocalDateTime endDate,
        @Param("status") String status
    );
}
```

---

## 八、超大 Excel 流式写入原理

### 8.1 xlsx 文件的本质

```
.xlsx 文件 = 一个 ZIP 压缩包
              里面装的是多个 XML 文件

orders.xlsx
 ├── [Content_Types].xml       ← 文件内容类型声明
 ├── _rels/.rels              ← 包关系文件
 └── xl/
      ├── workbook.xml          ← 工作簿（Sheet列表）
      ├── styles.xml            ← 样式（字体、颜色）
      ├── sharedStrings.xml     ← 共享字符串（去重）
      └── worksheets/
           └── sheet1.xml       ← 数据内容（行+列）
```

### 8.2 普通写入 vs 流式写入的本质区别

```
普通写入（XSSF，会OOM）：
  所有数据全部加载到内存 → 生成 sheet1.xml → 压缩成 .xlsx
  内存占用 = 1000万条 × 每条大小 ≈ 几个 GB ❌

流式写入（SXSSF / EasyExcel）：
  写入时 → 先写到磁盘临时文件（temp files）
  关闭时 → 把所有临时文件合并成最终 sheet1.xml → 压缩成 .xlsx
  内存占用 = 只保留当前批次（几百行）≈ 几 MB ✅
```

### 8.3 SXSSF 三个内存区域

```
┌─────────────────────────────────────────────────────────────┐
│              SXSSFWorkbook 内存结构                          │
├─────────────────┬─────────────────┬─────────────────────────┤
│  常驻内存        │   Row Buffer    │    磁盘临时文件          │
│  (表头、样式)    │   (活跃行)      │    (已写完的行)          │
│  ~几 KB         │   ~500行(可配置) │    ~N×500行             │
│  始终保留        │ 超过阈值触发flush │  文件累积，最终合并    │
└─────────────────┴────────┬────────┴─────────────────────────┘
```

### 8.4 写入流程

```
数据进来 → listOfOrders: [Row 1, Row 2, ... Row 500]
     ↓
写入 Row Buffer

count >= 500 ?
  ↓ Yes
flush → 写入磁盘 .tmp 临时文件（SXSSF-0.tmp）
buffer 清空！

继续 write() → 再次填满 → flush → 清空 → 循环

最终效果：内存中始终只有 ≤500 行的数据
         已写完的行全部在磁盘 .tmp 文件中
```

### 8.5 关闭时合并（finish）

```
1. 把 Row Buffer 中剩余的行 flush 到最后一个 .tmp 文件

2. 按顺序合并所有 .tmp 文件：
   sheet1.xml += sxsf-0.tmp
   sheet1.xml += sxsf-1.tmp
   ...

3. 把 sheet1.xml + workbook.xml + styles.xml 等
   全部打包（ZIP）成最终的 orders.xlsx

4. 删除所有 .tmp 临时文件

内存峰值出现在第2步，但此时 Row Buffer 已清空
内存 = 表头 + 样式 + 正在合并的数据片段 ≈ 几十 MB
```

### 8.6 一句话原理

> **流式写入 = 边写边 flush 到磁盘 + 最后合并打包。**
> **内存占用 = Row Buffer 大小（固定值），与总数据量无关。**

### 8.7 EasyExcel 流式导出完整代码

```java
@Service
@Slf4j
public class OrderExportService {

    @Autowired
    private OrderMapper orderMapper;

    public void exportOrdersToExcel(OrderQueryParams params, String filePath) {
        long startTime = System.currentTimeMillis();
        long totalCount = 0;

        ExcelWriter excelWriter = EasyExcel.write(filePath, OrderExcelDTO.class)
                .registerWriteHandler(new LongestMatchColumnWidthStyleStrategy())
                .build();

        WriteSheet writeSheet = EasyExcel.writerSheet("订单对账单").build();

        try {
            long lastId = 0L;
            int batchNo = 0;
            int batchSize = 2000;

            while (true) {
                // ===== 数据库分批读取（游标分页）=====
                List<Order> batch = orderMapper.selectOrdersByCursor(
                        lastId, batchSize,
                        params.getStartDate(),
                        params.getEndDate(),
                        params.getStatus()
                );

                if (batch.isEmpty()) break;

                // ===== 实体 → DTO =====
                List<OrderExcelDTO> data = batch.stream()
                        .map(OrderExcelDTO::fromEntity)
                        .collect(Collectors.toList());

                lastId = batch.get(batch.size() - 1).getId();
                batch.clear();   // 帮助 GC
                batch = null;

                // ===== 流式写入（不堆积在内存）=====
                excelWriter.write(data, writeSheet);
                data.clear();    // 关键：写完立即清空
                data = null;

                totalCount += batchSize;
                batchNo++;

                if (batchNo % 50 == 0) {
                    log.info("处理中: {} 条, 游标 id={}", totalCount, lastId);
                }

                Thread.sleep(5);  // 控制数据库 QPS
            }

        } finally {
            excelWriter.finish();  // 必须关闭
        }

        long cost = System.currentTimeMillis() - startTime;
        log.info("导出完成: {} 条, 耗时: {}s", totalCount, cost / 1000);
    }
}
```

### 8.8 实测数据参考

| 数据量 | 批次大小 | 预估耗时 | 峰值内存 |
|--------|---------|---------|---------|
| 100 万条 | 2000/批 | 3-5 分钟 | ~100MB |
| 500 万条 | 2000/批 | 15-20 分钟 | ~100MB |
| 1000 万条 | 2000/批 | 30-40 分钟 | ~100MB |
| 5000 万条 | 2000/批 | 3-5 小时 | ~100MB |

---

## 九、SXSSF 临时文件清理机制

### 9.1 临时文件存放位置

```java
// 默认使用系统临时目录
System.getProperty("java.io.tmpdir")

// Windows：C:\Users\用户名\AppData\Local\Temp\
// Linux：/tmp/

// 可手动指定
new SXSSFWorkbook(500, "/data/tmp");
```

### 9.2 操作系统会不会自动删除？

**不会主动定期删除**。SXSSF 临时文件需要通过 `dispose()` 手动删除。

| 场景 | 会不会删除 |
|------|-----------|
| 正常调用 `dispose()` / `close()` | ✅ 会 |
| JVM 正常退出 | ✅ 会 |
| try-with-resources | ✅ 会 |
| **JVM 崩溃** | ❌ 不会 |
| **程序异常退出** | ❌ 不会 |
| **没有调用 dispose()** | ❌ 不会 |
| OS 重启（/tmp 目录）| ✅ 可能（tmpfs 或配置了 tmpfiles.d）|

### 9.3 四种清理方案

#### 方案一：try-with-resources（首选）

```java
try (SXSSFWorkbook workbook = new SXSSFWorkbook(500)) {
    // 整个写入逻辑
} // ← 自动调用 dispose()，临时文件被删除
```

#### 方案二：finally 手动清理

```java
SXSSFWorkbook workbook = null;
try {
    workbook = new SXSSFWorkbook(500);
    // 业务逻辑
} finally {
    if (workbook != null) {
        workbook.dispose();   // 删除所有 .tmp 文件
        workbook.close();
    }
}
```

#### 方案三：定时任务兜底清理

```java
@Scheduled(cron = "0 0 3 * * ?")  // 每天凌晨3点
public void cleanupTempFiles() {
    File[] tmpFiles = new File("/data/tmp").listFiles(
        (d, name) -> name.startsWith("sxsf-")
    );

    for (File file : tmpFiles) {
        // 删除超过 24 小时的临时文件
        if (System.currentTimeMillis() - file.lastModified() > 24 * 3600 * 1000) {
            file.delete();
        }
    }
}
```

#### 方案四：启动时清理

```java
@PostConstruct
public void cleanupOnStartup() {
    File[] files = new File(System.getProperty("java.io.tmpdir"))
        .listFiles((d, name) -> name.startsWith("sxsf-"));

    if (files != null && files.length > 0) {
        log.warn("发现 {} 个遗留临时文件，启动时清理...", files.length);
        for (File f : files) {
            f.delete();
        }
    }
}
```

### 9.4 磁盘空间监控 + 告警

```java
@Scheduled(fixedRate = 60000)
public void monitorDiskSpace() {
    File file = new File(System.getProperty("java.io.tmpdir"));
    double usagePercent = (double) (file.getTotalSpace() - file.getFreeSpace())
                          / file.getTotalSpace() * 100;

    if (usagePercent > 80) {
        alertService.sendAlert("磁盘空间告警",
            "临时目录使用率超过 80%：" + String.format("%.1f", usagePercent));
    }
}
```

---

## 十、tmp 目录的设计哲学

### 10.1 tmp 目录是"约定"而非"垃圾箱"

```
/tmp 目录不是操作系统自动管理的垃圾回收站。
它是一个"约定好的标准位置"，由操作系统创建并设置权限。

应用程序负责：
  ✓ 自己创建文件
  ✓ 自己删除文件（用完就删）
  ✓ 异常时兜底清理

操作系统负责：
  ✓ 创建目录
  ✓ 设置权限（1777，任何人可以读写）
  ✓ 提供访问入口

操作系统不负责：
  ✗ 定期扫描并删除文件（除非配置了 tmpfiles.d）
  ✗ 监控文件大小
  ✗ 主动管理生命周期
```

### 10.2 为什么需要 tmp 目录？

```
没有 tmp 目录：
  应用A：把临时文件放 C:\temp\
  应用B：把临时文件放 C:\windows\temp\
  应用C：把临时文件放 D:\
  → 查找困难、卸载时不知道去哪清理、权限混乱

有 tmp 目录：
  所有应用约定：临时文件 → 放 /tmp 或 C:\Users\...\Temp
  → 统一入口、方便清理、权限统一
```

### 10.3 tmp 目录的三大用途

```
用途1：进程间通信（IPC）
  /tmp/socket.lock
  /tmp/myapp.pid

用途2：临时数据存储
  vim 编辑文件 → 先写到 /tmp/vimxxx.tmp
  浏览器下载 → 先存 /tmp

用途3：锁文件和套接字
  MySQL.sock
  .X0-lock
```

### 10.4 Linux 的清理机制

```
Linux 有些发行版有 tmpfiles.d 定时清理：
  /usr/lib/tmpfiles.d/tmp.conf
  d /tmp 1777 root root 30d  ← 超过30天的文件会被删除

但这个不是所有系统都默认开启！
长期运行的服务器进程依然需要应用自己管理。

设计哲学："谁创建谁清理"
而不是"系统自动回收的垃圾模型"
```

### 10.5 一句话总结

> **tmp 目录是操作系统提供的一个"标准放置临时文件的位置"，遵循"谁创建谁清理"的责任模型。操作系统把"什么时候删除"的决定权交给应用程序，而不是自己猜。**

---

## 附录：核心原则总结

| 主题 | 核心原则 |
|------|---------|
| **NIO vs BIO** | BIO 是线程在等，NIO 是 Selector 替所有人等，快的是"省去了等待" |
| **Channel + Selector** | Channel 是能被 Selector 监控的连接，两者配合才能实现非阻塞 IO |
| **configureBlocking(false)** | 切换为非阻塞模式，read/write 立即返回，不让线程睡觉 |
| **秒杀防超发** | Redis Lua 原子扣减（第一层）+ MySQL UPDATE 原子扣减（底线）+ 唯一索引兜底 |
| **MQ 失败处理** | 临时失败重试（指数退避）+ 永久失败进 DLQ + 库存回滚 |
| **异步通知** | 同步返回"受理"→ 异步处理 → WebSocket + 轮询 + 短信/推送组合通知 |
| **分批读取** | 游标分页优于 OFFSET，性能恒定 O(1) 而非 O(N) |
| **流式写入** | 边写边 flush 到磁盘 + 最后合并，内存占用与总数据量无关 |
| **临时文件** | try-with-resources 自动清理 + 定时任务兜底 + 启动时清理 + 磁盘告警 |

---

*文档结束*
