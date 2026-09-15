# 连接池专题

## 主题大纲

| # | 知识点 | 状态 |
|---|--------|------|
| 1 | 连接池通用抽象与代价分析 | ✅ |
| 2 | Apache Commons Pool 源码（GenericObjectPool） | ✅ |
| 3 | HikariCP 的三处提速设计（Bag/FastList/激进初始化） | ✅ |
| 4 | HTTP 连接池（OkHttp / Apache HttpClient） | ✅ |
| 5 | RabbitMQ 连接池与保活机制（AMQP 心跳 / Channel 复用） | ✅ |
| 6 | 五种协议的保活策略总览（TCP / Redis / RabbitMQ / Kafka / HTTP） | ✅ |
| 7 | 参数调优与四大常见坑 | ✅ |
| 8 | 与线程池/Redis/Netty 的知识串联 | ✅ |

## 前置知识

- [Java 线程池](../thread-pool/source-analysis.md) — 与连接池对比
- [Redis 原理](../redis/redis-analysis.md) — Jedis 连接池背景
- [消息队列](../mq/mq-analysis.md) — RabbitMQ 客户端使用
- [Netty Pipeline](../netty/pipeline.md) — HTTP 连接池的 Netty 基础

## 文件

| 文件 | 说明 |
|------|------|
| [`pool-analysis.md`](pool-analysis.md) | 连接池完整剖析：通用抽象 → HikariCP/OkHttp/RabbitMQ 源码 → 五种保活机制对比 → 调优 |
