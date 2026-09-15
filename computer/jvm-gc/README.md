# Java GC 源码剖析

## 主题大纲

| # | 知识点 | 状态 |
|---|--------|------|
| 1 | 对象何时可回收：可达性分析 | ✅ |
| 2 | 四种引用类型与回收时机 | ✅ |
| 3 | Finalizer 与"复活"机制 | ✅ |
| 4 | Young GC 触发条件 | ✅ |
| 5 | Full GC 触发条件 | ✅ |
| 6 | GC Cause 机制 | ✅ |
| 7 | 复制算法源码（Young GC） | ✅ |
| 8 | 标记-整理算法源码（Full GC） | ✅ |
| 9 | GC 完整调用链路 | ✅ |

## 前置知识

- [Java IO](../io/nio.md) — 理解 JVM 与操作系统的交互
- [Java 线程池](../thread-pool/source-analysis.md) — 理解线程与内存管理的关系

## 文件

| 文件 | 说明 |
|------|------|
| [`source-analysis.md`](source-analysis.md) | GC 底层源码剖析 |