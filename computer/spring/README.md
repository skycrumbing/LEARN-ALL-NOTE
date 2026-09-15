# Spring 核心专题

> 不讲 Spring 怎么用，讲 Spring **底层怎么运转**：每个核心机制的调用链、涉及的设计模式、能学到什么。
> 这是 Java 后端框架的基石，也是把 IoC/Netty/连接池/线程串起来的"胶水"。

---

## 主题大纲

| # | 知识点 | 文件 | 状态 |
|---|--------|------|------|
| 1 | IoC 容器与 Bean 生命周期（9 步调用链） | [`ioc-container.md`](ioc-container.md) | ✅ |
| 2 | 三级缓存破解循环依赖 | [`circular-dependency.md`](circular-dependency.md) | ✅ |
| 3 | AOP 与动态代理（JDK vs CGLIB） | [`aop.md`](aop.md) | ✅ |
| 4 | 事务管理 @Transactional（调用链 + 失效场景） | [`transaction.md`](transaction.md) | ✅ |
| 5 | Spring 设计模式总览 + 综合收获 | [`design-patterns.md`](design-patterns.md) | ✅ |

---

## 前置知识

- [Java 线程池](../thread-pool/source-analysis.md) — @Async 的基础
- [连接池专题](../connection-pool/pool-analysis.md) — @Transactional 背后拿连接
- [Tomcat NIO vs WebFlux](../tomcat-webflux/source-analysis.md) — Spring 的两种 Web 栈
- [HashMap / ConcurrentHashMap] — BeanFactory 内部就是 Map

## 学习路径建议

```
1. IoC 容器 + Bean 生命周期   ← 地基，理解 Bean 怎么被造出来
        │
        ▼
2. 三级缓存 + 循环依赖        ← Bean 造的过程中最棘手的问题
        │
        ▼
3. AOP + 动态代理             ← Bean 的后处理，@Transactional/@Async 靠它
        │
        ▼
4. 事务管理                   ← AOP 的典型应用，串联连接池/ThreadLocal
        │
        ▼
5. 设计模式总览               ← 回头看 Spring 用了多少经典模式
```
