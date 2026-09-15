# 消息队列学习笔记

> 覆盖：RabbitMQ、Kafka、RocketMQ 的原理、相同点、不同点、各自优劣。

---

## 一、RabbitMQ

### 1.1 架构概览

```
┌─────────────────────────────────────────────────────────────┐
│  RabbitMQ 核心模型                                           │
│                                                             │
│  Producer                                                    │
│     │                                                       │
│     ▼                                                       │
│  ┌──────────┐    RoutingKey    ┌──────────┐                │
│  │ Exchange │ ───────────────► │  Queue   │                │
│  │(交换机)  │  Binding 规则    │(队列)    │ ──► Consumer   │
│  └──────────┘                  └──────────┘                │
│       ▲                                                       │
│       │ 声明绑定关系                                           │
└─────────────────────────────────────────────────────────────┘
```

### 1.1.1 Broker 是什么

> **Broker 就是 RabbitMQ 服务器实例本身**，是 Queue、Exchange、Binding 等所有消息基础设施的容器。

```
┌─────────────────────────────────────────────────────────────┐
│  Broker = 1 个 RabbitMQ 节点 (1 个 BEAM VM 实例)             │
│                                                             │
│  Broker 内部包含:                                            │
│                                                             │
│    ┌─────────────────────────────────────────────────────┐  │
│    │  vhost: /                                           │  │
│    │                                                      │  │
│    │  Exchange:                                           │  │
│    │    ├── exchange.order (direct)                       │  │
│    │    ├── exchange.logs  (topic)                        │  │
│    │    └── exchange.broadcast (fanout)                   │  │
│    │                                                      │  │
│    │  Queue:                                              │  │
│    │    ├── queue.order.create                            │  │
│    │    ├── queue.order.cancel                            │  │
│    │    └── queue.logs.error                              │  │
│    │                                                      │  │
│    │  Binding:                                            │  │
│    │    └── exchange.order ──[order.create]──► queue.order.create │
│    │                                                      │  │
│    └─────────────────────────────────────────────────────┘  │
│                                                             │
│  一句话: 你安装的每个 RabbitMQ 服务器就是一个 Broker，        │
│         上面存放着所有 vhost、Exchange、Queue、消息           │
└─────────────────────────────────────────────────────────────┘

集群扩展:
  1 个 Broker → 单机，所有资源在一台服务器上
  N 个 Broker → 集群，Queue 可跨 Broker 镜像或 Quorum 复制
  但 Exchange 和 vhost 等元数据在所有 Broker 上同步一致
```

### 1.2 核心概念

**Exchange（交换机）** — 路由规则的核心：

| 类型 | 路由规则 | 适用场景 |
|------|---------|---------|
| **direct** | RoutingKey 完全匹配 | 精确路由 |
| **fanout** | 忽略 RoutingKey，广播给所有绑定队列 | 广播通知 |
| **topic** | RoutingKey 模糊匹配（`*`单词，`#`多词） | 分类路由 |
| **headers** | 根据消息 headers 属性匹配 | 复杂条件路由 |

```
direct 示例:
  Exchange ──[RoutingKey: "order.create"]──► Queue_A
         ──[RoutingKey: "order.delete"]──► Queue_B

topic 示例:
  Exchange ──[Binding: "order.*"]──► Queue_A    (匹配 order.create, order.delete)
         ──[Binding: "order.#"]──► Queue_B     (匹配 order.create, order.payment.succeed)

fanout 示例:
  Exchange ──[广播]──► Queue_A
         ──[广播]──► Queue_B
         ──[广播]──► Queue_C
```

#### Exchange 创建原则

**每种类型可以有多个**，不存在"一种类型只允许一个 Exchange"的限制。

```
一个 vhost 中:

  Exchange 类型: direct
    ├── exchange.order        (订单相关)
    ├── exchange.payment      (支付相关)
    ├── exchange.inventory    (库存相关)
    └── ... 可以无限创建

  Exchange 类型: topic
    ├── exchange.logging      (日志)
    ├── exchange.alerts       (告警)
    └── ...

  Exchange 类型: fanout
    ├── exchange.broadcast    (广播通知)
    └── ...
```

**唯一限制：** 同一 vhost 内 Exchange **名称不能重复**，类型可以相同。

**创建原则：**

```
1. 按业务边界划分

   ✗ 错误: 一个 direct exchange 处理所有业务
     exchange.common ──[order.create]──► Queue_1
                 ──[payment.success]──► Queue_2
                 ──[user.login]──► Queue_3
     → 路由规则越来越多，混乱且难以维护

   ✓ 正确: 按业务模块拆分
     exchange.order    ──[create]──► Queue_1
                       ──[cancel]──► Queue_2

     exchange.payment  ──[success]──► Queue_3
                       ──[fail]──► Queue_4

2. 按路由规则类型选型

   需要精确路由 (RoutingKey 完全匹配)  →  direct
   需要分类模糊匹配                     →  topic
   需要广播给所有队列                   →  fanout

3. 一个 Exchange 只管一层路由

   topic 支持多级匹配:
   exchange.event:
     Binding: "order.#"           → Queue_A  (所有 order 相关)
     Binding: "order.pay.#"       → Queue_B  (仅支付相关)
     Binding: "order.pay.succeed" → Queue_C  (仅支付成功)

   发送: "order.pay.succeed"
   → Queue_A 收到 (匹配 order.#)
   → Queue_B 收到 (匹配 order.pay.#)
   → Queue_C 收到 (匹配 order.pay.succeed)

   好处: 一条消息可分发给多个粒度的消费者

4. 命名规范

   前缀 + 业务域 + 用途:
     exchange.order.create          (订单-创建)
     exchange.payment.callback      (支付-回调)
     exchange.inventory.deduct      (库存-扣减)

5. durable 必设

   Exchange 建议始终设置 durable = true:
   → 重启后绑定关系依然存在
   → 非 durable 的 Exchange 重启后丢失
```

**一个 Exchange 能绑定多少 Queue？**

```
理论无限制，但需要考虑性能:

  每个 Binding 是一条路由规则，Exchange 收到消息后
  需要遍历所有 Binding 做匹配。

  Exchange 有 100 个 Binding:
    → 每来一条消息，最多匹配 100 次
    → 依然很快（内存操作），但明显低效

  建议: 单个 Exchange 的 Binding 控制在几十以内，
        超过时考虑拆分为多个 Exchange
```

| 维度 | 说明 |
|------|------|
| 类型数量 | 每种类型可有多个 |
| 命名限制 | 同一 vhost 内名称唯一 |
| 划分原则 | 按业务模块 + 路由规则类型 |
| 命名规范 | `exchange.业务域.用途` |
| Binding 数量 | 建议控制在几十以内 |

**Virtual Host（虚拟主机）**：
- 每个 vhost 拥有独立的 Exchange、Queue、权限
- 实现多租户隔离，类似数据库的 namespace

**核心数据结构（基于 Erlang）**：
- Queue 底层是 **Erlang 的 process**（轻量级进程，非 OS 线程）
- 每个 queue 是一个独立的 Erlang process，消息在 process 间传递
- 消息持久化时写入 `mnesia` 数据库（内存+磁盘）

### 1.2.1 Erlang 进程的真相

> **关键区分：Erlang process ≠ OS 进程/线程**

每创建一个 Queue 确实多一个 Erlang 进程，但这与操作系统级别的进程完全不同。

```
┌─────────────────────────────────────────────────────────────────┐
│  OS 进程/线程             │  Erlang 进程 (BEAM process)          │
├───────────────────────────┼─────────────────────────────────────┤
│  由操作系统内核管理        │  由 BEAM 虚拟机管理                  │
│  创建开销: 毫秒级          │  创建开销: 微秒级                     │
│  内存占用: 数 MB (栈 1~8MB) │  内存占用: 初始栈仅 ~2.3KB           │
│  单机可运行: 几千个         │  单机可运行: 数百万个                  │
│  切换成本: 内核态，毫秒级    │  切换成本: 用户态，纳秒级              │
│                            │                                     │
│                            │  本质: 一段内存数据 + 一个消息队列    │
│                            │  由 BEAM 调度器映射到少量 OS 线程执行 │
└────────────────────────────┴─────────────────────────────────────┘
```

**一个 RabbitMQ 节点的实际构成：**

```
1 个 RabbitMQ 节点 = 1 个 BEAM VM 实例
  │
  ├── OS 线程:          2~16 个 (CPU 核心数)
  │
  └── Erlang 进程:      每个 queue 一个，可运行数百万个
       │
       ├── queue_1      (Erlang process #1)
       ├── queue_2      (Erlang process #2)
       ├── queue_3      (Erlang process #3)
       ├── ...
       └── queue_500000 (Erlang process #500000)  ← 完全没问题

BEAM 调度器将数十万个 Erlang 进程调度到那十几个 OS 线程上执行，
每个进程执行一小段时间片后被挂起，切换下一个，
整个过程在用户态完成，不需要内核介入。
```

**数量对比：**

```
创建 1 万个 OS 线程:
  → 内存: 1万 × 1MB 栈 = 10GB  (直接爆内存)
  → 创建耗时: 数秒

创建 1 万个 Erlang 进程:
  → 内存: 1万 × 2.3KB 栈 ≈ 23MB  (几乎可以忽略)
  → 创建耗时: 毫秒级

创建 100 万个 Erlang 进程:
  → 内存: 100万 × 2.3KB ≈ 2.3GB  (完全可行)
  → 生产环境实测: 单节点运行几十万 Erlang 进程是常规操作
```

> **结论：** 创建大量 Queue 不会像创建 OS 线程那样爆内存或拖垮系统，Queue 数量不是性能瓶颈。

### 1.3 可靠性保障

```
┌─────────────────────────────────────────────────────────────────┐
│  生产者确认 (publisher confirms)                                 │
│  • 消息到达 Broker 后返回确认                                     │
│  • 未确认前，生产者不认为消息投递成功                               │
├─────────────────────────────────────────────────────────────────┤
│  消息持久化                                                       │
│  • Queue 设置 durable=true                                      │
│  • 消息设置 delivery_mode=2 (persistent)                        │
│  • 消息写入磁盘后才返回确认                                      │
├─────────────────────────────────────────────────────────────────┤
│  消费者确认 (consumer ack)                                       │
│  • manual ack: 处理完业务后手动确认                              │
│  • 未 ack 的消息在消费者断开后重新投递                           │
├─────────────────────────────────────────────────────────────────┤
│  死信队列 (DLX)                                                   │
│  • 消息被拒绝 (reject/nack) 或 TTL 过期                          │
│  • 自动路由到配置的死信 Exchange                                 │
├─────────────────────────────────────────────────────────────────┤
│  延迟消息                                                         │
│  • 通过 x-message-ttl + 死信队列实现                            │
│  • 或使用 rabbitmq-delayed-message-exchange 插件                │
└─────────────────────────────────────────────────────────────────┘
```

### 1.4 高可用方案

```
经典 HA（镜像队列）:
  ┌──────┐         ┌──────┐         ┌──────┐
  │Node1 │◄───────►│Node2 │◄───────►│Node3 │
  │Master│         │Mirror│         │Mirror│
  └──────┘         └──────┘         └──────┘
  → 消息写入 Master 后同步到所有 Mirror
  → Master 故障时选举新的 Master
  → 问题: 同步开销大，写入性能下降

Quorum Queue (RabbitMQ 3.8+):
  → 基于 Raft 协议，替代经典镜像队列
  → 强一致性，自动故障转移
  → 写入性能优于镜像队列
```

**Raft 同步原理（简化）：**

```
3 个节点组成 Raft 集群，选举 1 个 Leader:

┌────────┐        ┌────────┐        ┌────────┐
│Leader  │        │Follower│        │Follower│
│ Node-1 │        │ Node-2 │        │ Node-3 │
└────┬───┘        └────┬───┘        └────┬───┘
     │                  │                  │
     │ 1. Producer 写入消息到 Leader       │
     │    Leader 追加到本地 Log            │
     │    状态: UNCOMMITTED                │
     │                  │                  │
     │ 2. Leader 并行向所有 Follower 发送 AppendEntries │
     │ ──►             ──►                │
     │                  │                  │
     │ 3. Follower 追加到本地 Log，返回 OK │
     │ ◄───             ◄───               │
     │                  │                  │
     │ 4. 收到多数派确认 (2/3)              │
     │    消息状态变为 COMMITTED            │
     │    返回成功给 Producer               │
     │                  │                  │
     │                  ▼                  │
     │                  消息对消费者可见     │
     ▼                  ▼                  ▼

故障转移:
  • Leader 宕机 → Follower 发起选举
  • 多数派节点选举新 Leader
  • 新 Leader 同步自己独有的 Log 给旧 Follower
  • 保证数据不丢失
```

### 1.5 吞吐量

```
单机:  约 1万~3万 msg/s
集群:  约 10万 msg/s
瓶颈:  Erlang process 的消息同步开销
```

---

## 二、Kafka

### 2.1 架构概览

```
┌──────────────────────────────────────────────────────────────────┐
│  Kafka 核心模型                                                  │
│                                                                    │
│  Producer ──► Topic ──► Partition(分区) ──► Log(日志)            │
│                          │                                        │
│                          ├── Partition 0 ──► Log 文件              │
│                          ├── Partition 1 ──► Log 文件              │
│                          └── Partition N ──► Log 文件              │
│                                        │                          │
│                                        ▼                          │
│                         Consumer Group (消费者组)                  │
│                          │                                        │
│                          ├── Consumer-A 消费 Partition 0           │
│                          ├── Consumer-B 消费 Partition 1           │
│                          └── Consumer-C 消费 Partition N           │
│                                                                    │
│  规则: 一个分区同一时刻只被组内一个消费者消费                       │
└──────────────────────────────────────────────────────────────────┘
```

### 2.2 核心概念

**Topic（主题）**：
- 消息的逻辑分类，类似 RabbitMQ 的 Exchange + Queue 组合
- 生产者和消费者都按 Topic 操作

**Partition（分区）**：
- 每个 Topic 可以被分成多个 Partition
- 每个 Partition 是一个**有序、不可变**的消息日志
- 分区是 Kafka 并行和扩展的基本单位

**Broker（代理）**：
- 每台 Kafka 服务器就是一个 Broker，是整个集群的节点
- 多个 Broker 组成集群，共同承担消息的存储和读写

```
Broker 的本质职责:

  ┌─────────────────────────────────────────────────────┐
  │  Broker-1 (server.1)                                  │
  │                                                        │
  │  负责管理分配给自己的 Partition:                        │
  │    Topic-orders   →  Partition 0 (Leader)             │
  │    Topic-orders   →  Partition 3 (Leader)             │
  │    Topic-logs     →  Partition 1 (Leader)             │
  │                                                        │
  │  内部存储:                                              │
  │    /kafka-logs/orders-0/*.log                           │
  │    /kafka-logs/orders-3/*.log                           │
  │    /kafka-logs/logs-1/*.log                             │
  │                                                        │
  │  对 Producer: 接收消息写入对应 Partition 的 Log         │
  │  对 Consumer: 提供对应 Partition 的 Log 读取           │
  └─────────────────────────────────────────────────────┘

  关键:
  • 每个 Partition 有 1 个 Leader + N 个 Follower
  • Leader 在某个 Broker 上，Follower 分布在其他 Broker 上
  • Producer 只写 Leader，Consumer 只读 Leader
  • Follower 从 Leader 同步数据，保证高可用
```

```
Partition 内部结构:

  Log 文件:
  ┌─────────────────────────────────────────────┐
  │ segment-000000.log  (4GB)                    │
  │   offset 0  → msg1                            │
  │   offset 1  → msg2                            │
  │   offset 2  → msg3                            │
  │   ...                                         │
  │   offset 100000 → msgN                        │
  ├─────────────────────────────────────────────┤
  │ segment-000001.log  (4GB)                    │
  │   offset 100001 → msgN+1                      │
  │   ...                                         │
  ├─────────────────────────────────────────────┤
  │ segment-000002.log  (当前)                    │
  │   offset 200001 → ...                          │
  └─────────────────────────────────────────────┘

  特点:
  • 追加写入，不修改已有数据
  • 每个 segment 4GB，可配置
  • offset 是消息的唯一标识（Kafka 不自定义消息 ID）
```

### 2.3 Producer 发送机制

```
┌─────────────────────────────────────────────────────────────────┐
│  1. 分区策略 (partitioner)                                       │
│     • 指定 partition → 直接发到该分区                             │
│     • 指定 key → hash(key) % numPartitions                      │
│     • 无 key → 轮询 (round-robin)                               │
│                                                                  │
│  2. 批量发送 (batch)                                              │
│     • 消息先放入缓冲区 (batch)                                    │
│     • 满足 batch.size 或 linger.ms 后批量发送                    │
│     • 减少网络 IO 次数，提升吞吐量                                │
│                                                                  │
│  3. 压缩 (compression)                                            │
│     • 支持 snappy / lz4 / zstd / gzip                          │
│     • 批量消息压缩后传输，节省网络带宽                            │
│                                                                  │
│  4. 确认机制 (acks)                                              │
│     • acks=0: 不等待确认，最快但可能丢消息                        │
│     • acks=1: Leader 确认即可                                    │
│     • acks=all: Leader + 所有 ISR follower 确认                  │
└─────────────────────────────────────────────────────────────────┘
```

### 2.4 高可用 — ISR 机制

```
副本结构:
  ┌─────────────────────────────────────────────────────┐
  │  Partition-0 的副本分布                                │
  │                                                      │
  │  Broker-1 (Leader) ◄── 同步 ──► Broker-2 (Follower)  │
  │  Broker-1 (Leader) ◄── 同步 ──► Broker-3 (Follower)  │
  │                                                      │
  │  ISR (In-Sync Replicas) = { Broker-1, Broker-2 }    │
  │  → 只包含与 Leader 同步进度足够近的副本                  │
  │                                                      │
  │  当 acks=all 时:                                      │
  │  → 消息写入 Leader 的 Log                             │
  │  → Leader 等待 ISR 中所有副本同步完成                  │
  │  → 全部确认后才返回成功                                │
  │                                                      │
  │  Leader 故障时:                                        │
  │  → 从 ISR 中选举新的 Leader                            │
  │  → 不选 ISR 之外的副本（防止数据丢失）                  │
└─────────────────────────────────────────────────────────────┘
```

### 2.5 Consumer 消费机制 — Offset 管理

```
┌─────────────────────────────────────────────────────────────────┐
│  消费者如何知道"从哪开始读"？                                     │
│                                                                  │
│  每个 Consumer Group 维护一份 offset 记录:                        │
│                                                                  │
│  ┌────────────────────────────────────────────────────┐         │
│  │  __consumer_offsets (内部 Topic)                     │         │
│  │                                                      │         │
│  │  group=my-group                                     │         │
│  │    topic=orders, partition=0, offset=100000         │         │
│  │    topic=orders, partition=1, offset=98500          │         │
│  │    topic=orders, partition=2, offset=102300         │         │
│  │                                                      │         │
│  └────────────────────────────────────────────────────┘         │
│                                                                  │
│  offset 提交策略:                                                │
│  • auto.commit: 自动提交 (每 5s)                                │
│  • manual: 处理完业务后手动提交                                   │
│                                                                  │
│  消费语义:                                                       │
│  • at-most-once: 自动提交，可能重复或丢失                         │
│  • at-least-once: 手动提交，可能重复但不丢                        │
│  • exactly-once: 幂等生产 + 事务 (Kafka 0.11+)                  │
└─────────────────────────────────────────────────────────────────┘
```

### 2.6 为何 Kafka 吞吐量极高

```
┌─────────────────────────────────────────────────────────────────┐
│  1. 顺序写 + OS Page Cache                                       │
│     • 消息追加写入，磁盘顺序 IO                                    │
│     • Linux 内核 Page Cache 缓存热数据                            │
│     • 实际多数读操作走内存，极少落盘                               │
│                                                                  │
│  2. 零拷贝 (zero-copy)                                            │
│     • 使用 sendfile() 系统调用                                    │
│     • 数据直接从 Page Cache 到网卡，不经用户空间                   │
│     • 相比传统 read()→write() 少一次拷贝                          │
│                                                                  │
│  3. 批量处理                                                       │
│     • Producer 批量发送，Consumer 批量拉取                       │
│     • 减少系统调用次数                                            │
│                                                                  │
│  4. 分区并行                                                       │
│     • 多个 Partition 分布在多个 Broker                            │
│     • 读写可以并行进行                                            │
│                                                                  │
│  结果: 单机百万级 msg/s，集群可达千万级                            │
└─────────────────────────────────────────────────────────────────┘
```

### 2.7 局限性

```
• 不保证全局有序，只保证分区内有序
• 不适合低延迟场景（有 batch 和 linger 延迟）
• 不支持消息优先级
• 不支持基于内容的路由/过滤（需 Consumer 自行判断）
• 没有原生"死信队列"概念
```

---

## 三、RocketMQ

### 3.1 架构概览

```
┌──────────────────────────────────────────────────────────────────┐
│  RocketMQ 核心模型                                               │
│                                                                    │
│  ┌────────┐                                                        │
│  │Namesrv │  轻量级注册中心，无状态，多实例互不通信                 │
│  └────┬───┘                                                        │
│       │ 注册/发现                                                    │
│       ├───► Broker-A ──► Broker-B ──► Broker-C                   │
│       │         │               │               │                │
│       │    ┌────┴────┐    ┌────┴────┐    ┌────┴────┐             │
│       │    │Topic-A  │    │Topic-B  │    │Topic-C  │             │
│       │    │ ├-Q0    │    │ ├-Q0    │    │ ├-Q0    │             │
│       │    │ ├-Q1    │    │ ├-Q1    │    │ ├-Q1    │             │
│       │    │ ├-Q2    │    │ └-Q2    │    │ └-Q2    │             │
│       │    │ └-Q3    │             │             │                │
│       │    └─────────┘             │             │                │
│       │                             │             │                │
│  Producer                            │             │                │
│     │                               ▼             ▼                │
│     ▼                        Consumer Group    Consumer Group      │
│  NameSrv → 查找 Broker 和 Topic 路由                                │
│                                                                    │
└──────────────────────────────────────────────────────────────────┘
```

### 3.2 核心概念

**Namesrv**：

> Namesrv 是 **独立部署的进程**，不是 Broker 的一部分。一个 RocketMQ 集群由 Broker 集群 + Namesrv 集群组成，两者分开部署。

```
实际部署架构:

  ┌──────────┐
  │ Namesrv-1 │  ← 独立进程，单独部署
  └────┬─────┘
       │
  ┌────┴─────┐
  │ Namesrv-2 │  ← 独立进程，单独部署
  └────┬─────┘
       │
  ┌────┴─────┐
  │ Namesrv-3 │  ← 独立进程，单独部署
  └──────────┘

  ┌──────────┐   ┌──────────┐   ┌──────────┐
  │ Broker-A │   │ Broker-B │   │ Broker-C │
  └────┬─────┘   └────┬─────┘   └────┬─────┘
       │              │              │
       └──────────────┴──────────────┘
                每个 Broker 向所有 Namesrv 注册

Producer / Consumer 轮询访问所有 Namesrv 获取路由信息
```

**三个关键点：**

```
1. 谁部署 Namesrv？
   • Namesrv 是独立进程，跟 Broker 分开部署
   • 通常部署 2~3 台，不需要很多
   • 一个 Broker 上不会同时运行 Namesrv

2. Namesrv 之间是否通信？
   • 不通信，没有主从、没有一致性协议
   • 每个 Namesrv 都保存完整的 Broker 注册信息
   • 为什么？Broker 会向所有 Namesrv 注册，所以每个 Namesrv 数据一致

3. 注册和发现的完整流程：

   Broker 启动时:
     → 向 Namesrv-1 注册: "我是 Broker-A，Topic-X 在我这里"
     → 向 Namesrv-2 注册: "我是 Broker-A，Topic-X 在我这里"
     → 向 Namesrv-3 注册: "我是 Broker-A，Topic-X 在我这里"

   Producer 发送消息时:
     → 轮询 Namesrv-1 → 获取 Topic-X 的 Broker 路由信息 → 找到 Broker-A
     → 如果 Namesrv-1 挂了，下次轮询 Namesrv-2，数据一样

   这就是 Namesrv "去中心化 + 无状态"的设计:
     → 单点故障不影响整体
     → 任意一个 Namesrv 都能提供完整路由信息
     → 不需要一致性协议，简单可靠
```

**Broker**：
- 消息的实际存储和处理节点，是整个集群的核心
- 每个 Broker 可以有 1 个 Master + 多个 Slave，组成主从副本

```
Broker 集群架构:

  ┌─────────────────────────────────────────────────────────────┐
  │                                                              │
  │  Topic-orders                                                │
  │                                                              │
  │    Queue-0:                                                   │
  │      Master (Broker-A1) ◄── 同步 ──► Slave (Broker-A2)      │
  │                                                              │
  │    Queue-1:                                                   │
  │      Master (Broker-B1) ◄── 同步 ──► Slave (Broker-B2)      │
  │                                                              │
  │  规则:                                                        │
  │  • Producer 只写 Master                                       │
  │  • Master 同步到 Slave 后返回确认                             │
  │  • Consumer 默认读 Master，可配置读 Slave (读写分离)          │
  │  • Master 故障后，Slave 可提升为新的 Master                   │
  │                                                              │
  └─────────────────────────────────────────────────────────────┘
```

#### Broker 主从同步机制

```
┌─────────────────────────────────────────────────────────────────┐
│  两种同步模式:                                                   │
│                                                                  │
│  1. ASYNC (异步复制) ★ 默认                                     │
│     ┌─────────┐         ┌─────────┐                             │
│     │ Master  │ ───────►│ Slave   │                             │
│     └────┬────┘         └─────────┘                             │
│          │                                                      │
│          │ 1. Producer 写入 Master                               │
│          │ 2. Master 立即返回成功                                │
│          │ 3. Master 异步转发给 Slave                            │
│          │                                                      │
│          ✓ 写入延迟低，吞吐量大                                   │
│          ✗ Master 宕机可能丢失少量未同步消息                      │
│                                                                  │
│  2. SYNC (同步复制)                                              │
│     ┌─────────┐         ┌─────────┐                             │
│     │ Master  │◄───────►│ Slave   │                             │
│     └────┬────┘         └─────────┘                             │
│          │                                                      │
│          │ 1. Producer 写入 Master                               │
│          │ 2. Master 同步到 Slave                                │
│          │ 3. Slave 返回确认后，Master 才返回成功                 │
│          │                                                      │
│          ✓ 数据不丢失（除非 Master+Slave 同时宕机）              │
│          ✗ 写入延迟增加，吞吐量下降                               │
│                                                                  │
├─────────────────────────────────────────────────────────────────┤
│  双写 (SYNC + ASYNC 结合):                                      │
│                                                                  │
│  Producer → 同时发往 Master 和 Slave                            │
│  → 两边都收到后返回成功                                          │
│  → 但 Master 和 Slave 各自独立存储，不做一致性校验               │
│  → 本质上是"写两遍"，不是主从同步                                │
└─────────────────────────────────────────────────────────────────┘
```

#### 与 Kafka 同步机制的区别

```
RocketMQ:
  • Master-Slave 主从架构
  • 同步方式是"文件复制"：Slave 从 Master 拉取 CommitLog 文件
  • 无 Leader 选举协议，不是随机切换
  • Master 故障时，其 Slave 自动晋升为新 Master（无仲裁/无选举）
  • 标准部署: 一个 Master 只配 1 个 Slave，一对一晋升，无歧义
  • RocketMQ 支持一个 Master 配多个 Slave (brokerId=1,2,3...)
    但这是不推荐的生产配置

  多 Slave 时 Master 故障的晋升逻辑:

  ┌─────────────────────────────────────────────────────────────┐
  │  Master (brokerId=0)                                        │
  │     ├── Slave-A (brokerId=1)                                │
  │     ├── Slave-B (brokerId=2)                                │
  │     └── Slave-C (brokerId=3)                                │
  │                                                              │
  │  Master 故障时:                                              │
  │  → RocketMQ 没有仲裁/投票机制                                │
  │  → 所有 Slave 都会独立判断 Master 是否宕机                   │
  │  → 所有 Slave 都可能同时尝试晋升为 Master                     │
  │  → 结果: 可能出现多个 Master（脑裂）                         │
  │                                                              │
  │  晋升顺序: 不是按 brokerId 排序，而是谁先检测到故障谁先晋升   │
  │                                                              │
  │  解决方案:                                                   │
  │  → 生产环境只用 1 个 Slave，避免竞争                         │
  │  → 如果必须多 Slave，需要外部监控 + 人工介入                 │
└─────────────────────────────────────────────────────────────┘

  与 Kafka 的对比:
  Kafka 的 ISR 机制中，Leader 故障时由 ZooKeeper/KRaft 协调选举，
  从 ISR 列表中选出最新的一个 Follower 成为新 Leader，只有一个当选。
  RocketMQ 没有这套机制，所以多 Slave 场景有脑裂风险。
  • 同步是 Broker 对 Broker 的直接通信

Kafka:
  • Leader-Follower + ISR 机制
  • 同步方式是"逐条消息同步"：Follower 从 Leader 拉取消息
  • 有 ZooKeeper/KRaft 协调 Leader 选举
  • ISR 动态维护，掉队 Follower 自动踢出
```

```
Broker 的本质职责:

  ┌─────────────────────────────────────────────────────┐
  │  Broker-A                                             │
  │                                                        │
  │  负责管理分配给自己的 Topic + Queue:                   │
  │    Topic-orders → Queue-0, Queue-1 (4 个 queue)       │
  │    Topic-logs   → Queue-0, Queue-1 (2 个 queue)       │
  │                                                        │
  │  内部存储:                                              │
  │    CommitLog:    所有 Topic 的消息统一追加写入          │
  │    ConsumeQueue: 每个 Queue 的索引，指向 CommitLog 位置 │
  │                                                        │
  │  对 Producer: 接收消息 → 追加写入 CommitLog            │
  │  对 Consumer:  根据 ConsumeQueue 索引读取消息          │
  └─────────────────────────────────────────────────────┘

  存储架构特点:
  • CommitLog 是所有消息的共享存储，不分 Topic
  • ConsumeQueue 是每个 Queue 的索引，记录消息大小和偏移量
  • 这种设计让磁盘顺序写和随机读都有优化
  • 支持主从同步复制（异步/同步双写）
```

**Topic**：
- 消息逻辑分类，类似 Kafka
- 每个 Topic 下有多个 Message Queue（队列）
- 一个 Message Queue 只在一个 Broker 上

**Tag**：
- 消息的二级过滤维度
- Producer 发送时指定 Tag，Consumer 订阅时过滤

```
Producer:  send("Topic-A", "Tag-create", body)
Consumer:  subscribe("Topic-A", "Tag-create || Tag-delete")
           → 只接收 Tag 为 create 或 delete 的消息
```

### 3.3 核心特性 — RocketMQ 的独门武器

**① 事务消息**

```
┌─────────────────────────────────────────────────────────────────┐
│  场景: 订单创建 + 发送消息 需要原子性                              │
│                                                                  │
│  步骤:                                                           │
│  1. Producer 发送 Half Message (半消息) 到 Broker                │
│     → 消息对消费者不可见                                          │
│  2. Broker 确认收到，Producer 执行本地事务                       │
│  3. 本地事务成功 → Producer 回复 Broker: COMMIT                   │
│     本地事务失败 → Producer 回复 Broker: ROLLBACK                │
│  4. Broker 未收到确认 → 主动回查 Producer                        │
│  5. Producer 根据事务结果回复 COMMIT 或 ROLLBACK                 │
│                                                                  │
│  ┌──────────┐         ┌──────────────┐       ┌──────────┐     │
│  │ Producer │ 1.发送  │    Broker    │ 4.回查 │ Producer │     │
│  │          │────────►│              │◄────────│          │     │
│  │          │    2.执行本地事务       │ 3/5.确认│          │     │
│  └──────────┘         └──────────────┘       └──────────┘     │
└─────────────────────────────────────────────────────────────────┘
```

这是 RocketMQ 最大的差异化优势，Kafka 没有原生支持。

**半消息的决策链路 — 谁来决定删除？**

```
┌─────────────────────────────────────────────────────────────────┐
│  Producer 发送 Half Message → 执行本地事务 → 三种结果:           │
│                                                                  │
│  情况 A: Producer 捕获异常，知道事务失败                          │
│    → Producer 主动发送 ROLLBACK 给 Broker                        │
│    → Broker 删除 Half Message                                    │
│    ★ 是 Producer 做决策，Broker 执行                             │
│                                                                  │
│  情况 B: Producer 执行完事务，但网络断掉，未发送确认               │
│    → Broker 等待超时                                             │
│    → Broker 回查 Producer: "你的事务成功了吗？"                   │
│    → Producer 执行 checkLocalTransaction，回复结果                │
│    → Broker 执行对应的操作                                        │
│    ★ Broker 只是"问"，决策权还在 Producer 手中                    │
│                                                                  │
│  情况 C: Producer 宕机，完全不可达                               │
│    → Broker 回查 → 连不上 → 重试 → 连不上 → ...                  │
│    → 重试次数用尽，Broker 默认 ROLLBACK (删除消息)                │
│    ★ 最接近"RocketMQ 主动删除"的情况                             │
│    ★ 本质是兜底：Producer 不可达，Broker 默认删除                 │
└─────────────────────────────────────────────────────────────────┘
```

**核心结论：**
- RocketMQ 不是真正的分布式事务协议（2PC/XA）
- Broker 不决定消息去留，决策权始终在 Producer 手中
- Broker 的角色：暂存消息 + 等不到确认时回查 + 兜底删除
- 这更像是"延迟确认 + 超时兜底"，而非"分布式事务协调"

**② 定时/延迟消息**

```
原生支持 18 个延迟等级 (可配置):
  1s, 5s, 10s, 30s, 1m, 2m, 3m, 5m,
  10m, 20m, 30m, 1h, 2h, 4h, 8h, 12h, 1d, 2d

内部实现:
  → 延迟消息暂存在 SCHEDULE_TOPIC_XXXX
  → 定时任务扫描，到期后重新投递到目标 Topic

对比:
  • RabbitMQ: 需要插件或死信队列变通
  • Kafka: 不支持延迟消息
  • RocketMQ: 原生支持
```

**③ 顺序消息**

```
全局有序: 单 Topic 单 Queue
  → 所有 Producer 只发送到同一个 Queue
  → 吞吐量受限

局部有序: 同一业务维度有序
  → 比如同一订单的创建/支付/发货必须有序
  → Producer 通过 hash(orderId) 选 Queue
  → Consumer 单线程消费该 Queue

Kafka: 同样通过分区实现分区内有序
RabbitMQ: 不支持顺序消息
```

**④ 消息追踪**

```
原生支持消息全链路追踪:
  Producer 发送 → Broker 接收 → Consumer 消费 → ACK 确认
  每个环节记录时间戳和状态，可在控制台查看
```

**⑤ 死信队列**

```
Consumer 消费失败达到 maxReconsumeTimes (默认 16 次)
  → 消息进入死信队列 (%DLQ%TopicName)
  → 可在控制台查看、重新投递
```

### 3.4 消费模型

```
┌─────────────────────────────────────────────────────────────────┐
│  广播模式 (BROADCASTING)                                         │
│  • 每个消费者独立消费全部消息                                     │
│  • 每个消费者维护独立 offset                                      │
│                                                                  │
│  集群模式 (CLUSTERING) ★ 默认                                     │
│  • 同一 Consumer Group 中每个消费者只消费部分队列                  │
│  • 平均分配，负载均衡                                             │
│  • 类似 Kafka 的 Consumer Group                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 3.5 吞吐量

```
单机:  约 10万~50万 msg/s
集群:  可达百万级
对比 Kafka 略低，但比 RabbitMQ 高一个数量级
```

---

## 四、三者相同点

```
┌──────────────────────────────────────────────────────────────────┐
│  1. 都是消息中间件，解耦生产者和消费者                              │
│  2. 都支持 Topic 概念（消息分类）                                  │
│  3. 都支持消息持久化（写入磁盘）                                    │
│  4. 都支持消费者确认机制 (ack)                                     │
│  5. 都支持集群部署和高可用                                          │
│  6. 都支持消息重试机制                                             │
│  7. 都支持消息回溯/重放                                            │
└──────────────────────────────────────────────────────────────────┘
```

---

## 五、三者不同点

| 维度 | RabbitMQ | Kafka | RocketMQ |
|------|----------|-------|----------|
| **开发语言** | Erlang | Java/Scala | Java |
| **协议** | AMQP / STOMP / MQTT | 自定义协议 | 自定义协议 |
| **核心模型** | Exchange → Queue → Consumer | Topic → Partition → Consumer Group | Topic → Queue → Consumer Group |
| **路由能力** | ★★★★★ (四种 Exchange) | ★★ (只有 Topic) | ★★★ (Topic + Tag) |
| **消息存储** | 内存为主，持久化到 Mnesia | 顺序追加到磁盘文件 (Page Cache) | 顺序追加到 CommitLog + ConsumeQueue |
| **吞吐量** | 1万~3万/s | 百万级/s | 10万~50万/s |
| **延迟** | 微秒级 | 毫秒级 (有 batch 延迟) | 毫秒级 |
| **顺序消息** | ❌ | 分区内有序 | 全局/局部有序 |
| **事务消息** | ❌ | 有限支持 (幂等+事务) | ★★★★★ 原生完整支持 |
| **延迟消息** | 插件变通 | ❌ | 原生支持 |
| **消息过滤** | 路由规则 | Consumer 自行过滤 | Tag 过滤 + SQL 过滤 |
| **死信队列** | ★★★★★ | ❌ (需自行实现) | ✅ 原生 |
| **消息回溯** | 有限 (死信重投递) | ★★★★★ (offset 任意跳转) | ✅ (按时间戳重放) |
| **运维复杂度** | 中等 (Erlang 生态小) | 高 (需 ZooKeeper/KRaft) | 中等 (依赖 Namesrv) |
| **中文社区** | 一般 | 强 | ★★★★★ (阿里生态) |
| **适用场景** | 复杂路由、低延迟 | 大数据流处理、日志 | 电商交易、事务、金融 |

---

## 六、各自优劣总结

### 6.1 RabbitMQ

```
优势:
  ✓ 路由最灵活 (四种 Exchange，复杂路由规则)
  ✓ 延迟最低 (微秒级)
  ✓ 协议标准 (AMQP 跨语言)
  ✓ 功能丰富 (死信、延迟、优先级、二次确认)
  ✓ 社区成熟，插件丰富

劣势:
  ✗ 吞吐量最低
  ✗ Erlang 生态小，运维门槛高
  ✗ 不支持消息回溯到任意位置
  ✗ 不支持事务消息
  ✗ 集群扩展性有限
```

### 6.2 Kafka

```
优势:
  ✓ 吞吐量最高 (百万级/s)
  ✓ 生态极强 (Flink/Spark 原生集成，数据流处理)
  ✓ 消息持久化设计优秀 (顺序写 + Page Cache + 零拷贝)
  ✓ 消费回溯能力最强 (任意 offset 跳转)
  ✓ 水平扩展性好 (分区机制天然并行)

劣势:
  ✗ 路由能力弱 (只有 Topic 维度)
  ✗ 延迟相对高 (batch 机制引入延迟)
  ✗ 运维复杂 (依赖 ZooKeeper/KRaft)
  ✗ 不支持事务消息/延迟消息/死信队列
  ✗ 单条消息查找困难 (顺序扫描)
```

### 6.3 RocketMQ

```
优势:
  ✓ 事务消息 (最强差异化优势，电商交易场景刚需)
  ✓ 延迟消息 (原生支持，开箱即用)
  ✓ 顺序消息 (全局/局部，实现清晰)
  ✓ 中文社区和文档最好 (阿里出品，国内案例多)
  ✓ 功能均衡 (死信、追踪、过滤、消息查询)
  ✓ 吞吐量和延迟在三个中间件中最均衡

劣势:
  ✗ 知名度/国际社区不如 Kafka
  ✗ 生态集成不如 Kafka (大数据领域)
  ✗ 路由能力不如 RabbitMQ
  ✗ 早期版本有历史包袱，新版本 (5.x) 架构有所变化
```

---

## 七、选型建议

```
┌──────────────────────────────────────────────────────────────────┐
│  场景                        │  推荐                              │
├──────────────────────────────────────────────────────────────────┤
│  电商订单/支付/交易          │  RocketMQ (事务消息刚需)            │
│  大数据流处理/日志采集        │  Kafka (吞吐+生态)                 │
│  复杂路由/即时通讯            │  RabbitMQ (路由灵活+低延迟)        │
│  金融交易/账务               │  RocketMQ (事务+顺序+追踪)         │
│  IoT 设备消息                │  RabbitMQ (支持 MQTT 协议)         │
│  大规模日志/埋点             │  Kafka (高吞吐+持久化)              │
│  普通异步解耦                │  三者均可，按团队技术栈选            │
│  需要延迟/定时任务           │  RocketMQ (原生延迟消息)            │
└──────────────────────────────────────────────────────────────────┘
```

---

## 总结速查

```
┌──────────────────────────────────────────────────────────────┐
│  维度         │  核心要点                                    │
├──────────────────────────────────────────────────────────────┤
│  RabbitMQ     │  Exchange路由灵活 + 低延迟 + Erlang生态       │
│  Kafka        │  高吞吐 + 顺序写+零拷贝 + 大数据生态          │
│  RocketMQ     │  事务消息 + 延迟消息 + 顺序消息 + 中文友好    │
│  选型原则     │  交易选RocketMQ / 大数据选Kafka / 路由选Rabbit │
└──────────────────────────────────────────────────────────────┘
```