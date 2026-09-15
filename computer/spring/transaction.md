# 事务管理 @Transactional

> `@Transactional` 是 AOP 最典型的应用，也是把"AOP + 连接池 + ThreadLocal + 异常传播"全串起来的注解。
> 本文聚焦：事务传播行为、@Transactional 完整调用链、Connection 绑定 ThreadLocal、7 种失效场景根因、涉及的设计模式、能学到什么。

---

## 目录

1. [事务传播行为：7 种](#一事务传播行为7-种)
2. [@Transactional 完整调用链](#二transactional-完整调用链)
3. [Connection 绑定 ThreadLocal](#三connection-绑定-threadlocal)
4. [7 种失效场景的根因](#四7-种失效场景的根因)
5. [涉及的设计模式](#五涉及的设计模式)
6. [能学到什么](#六能学到什么)

---

## 一、事务传播行为：7 种

### 什么叫"传播行为"

```
事务方法 A 调事务方法 B 时，B 的事务怎么办?

  ┌ B 复用 A 的事务?      → REQUIRED（默认）
  ┌ B 自己开新事务?       → REQUIRES_NEW
  ┌ B 不开事务?           → NOT_SUPPORTED
  ┌ B 必须在事务里?       → MANDATORY（否则抛异常）
  └ ...共 7 种
```

### 7 种传播行为详解

| 传播行为 | A 有事务时 | A 无事务时 | 典型场景 |
|---------|-----------|-----------|---------|
| **REQUIRED**（默认） | 加入 A 的事务 | 新开事务 | 90% 场景 |
| **REQUIRES_NEW** | 挂起 A，新开独立事务 | 新开事务 | 日志记录（不因业务失败而丢日志） |
| **NESTED** | 在 A 事务里开"保存点"（嵌套） | 新开事务 | 部分回滚 |
| **SUPPORTS** | 加入 A 的事务 | 不开事务 | 查询方法 |
| **NOT_SUPPORTED** | 挂起 A，不开事务 | 不开事务 | 耗时操作（不让事务拖累） |
| **MANDATORY** | 加入 A 的事务 | 抛异常 | 强制必须在事务内 |
| **NEVER** | 抛异常 | 不开事务 | 强制不能在事务内 |

### REQUIRED vs REQUIRES_NEW 的关键区别

```
场景: A 调 B

REQUIRED:
  A 开事务 T1
    B 加入 T1
    B 失败 → T1 标记 rollback-only
  A 也跟着回滚
  → A 和 B 同生共死

REQUIRES_NEW:
  A 开事务 T1
    挂起 T1，B 开新事务 T2
    B 失败 → T2 回滚
    恢复 T1
  A 提交 T1
  → A 不受 B 影响（B 失败 A 仍提交）

  应用: 日志切面用 REQUIRES_NEW
    → 即使业务方法失败，日志也要存进去
```

### NESTED 的"保存点"

```
A 开事务 T1
  在 T1 里建保存点 SP1
  B 执行（共用 T1，但能回滚到 SP1）
  B 失败 → 回滚到 SP1（不是回滚整个 T1）
  A 继续
A 提交 T1

  → B 失败只回滚自己，A 不受影响
     但 B 成功的话，结果会跟着 A 提交
  → 依赖数据库的 SAVEPOINT 机制（MySQL InnoDB 支持）
```

### REQUIRES_NEW vs NESTED 的本质区别

> 表面看两者都是"B 失败不影响 A"，容易混淆。但它们在一个关键场景下**完全相反**：
> **A 回滚时，B 的结果会不会跟着一起回滚？**

```
REQUIRES_NEW:
═══════════════════════════════════════

  A 开事务 T1
    挂起 T1，B 开【独立】事务 T2
    B 成功 → T2 立即提交 ✅（永久生效！）
    恢复 T1
  A 失败回滚 → T1 回滚

  → B 的数据【已经提交，不会回滚】
  → A 回滚了，但 B 的结果还在 → 可能数据不一致！


NESTED:
═══════════════════════════════════════

  A 开事务 T1
    在 T1 里建保存点 SP1
    B 执行（B 的成功【没有提交】，只是记录在 SP1 之后）
    B 失败 → 回滚到 SP1（B 撤销，A 继续）
  A 成功 → 提交 T1 → B 的结果【此时才真正生效】
  A 失败 → 回滚 T1 → B 的结果【一起回滚！】

  → B 的命运和 A 绑定
```

**具体场景看差别**（下单 A 调扣库存 B，A 最后失败）：

```
REQUIRES_NEW 的结果（危险）:
  扣库存 B（REQUIRES_NEW）→ 独立提交 → 库存已扣
  下单 A 失败回滚 → 订单没生成
  → 结果: 库存扣了，但订单没了 → 数据不一致 ❌


NESTED 的结果（安全）:
  扣库存 B（NESTED）→ 保存点，未提交
  下单 A 失败回滚 → 整个 T1 回滚
  → 结果: 库存恢复，订单也没生成 → 数据一致 ✅
```

**完整对比表**：

| 维度 | REQUIRES_NEW | NESTED |
|------|-------------|--------|
| 事务关系 | 两个**完全独立**的事务 | **同一个事务**里的保存点 |
| 底层机制 | 挂起 T1 + 新开 T2（独立 Connection） | SAVEPOINT 保存点 |
| B 提交时机 | B 结束就**独立提交** | 不独立提交，**随 A 一起** |
| B 失败影响 | 只回滚 B，A 继续 | 回滚到保存点，A 继续 |
| **A 回滚时** | **B 不受影响**（已提交） | **B 一起回滚** |
| B 数据可见性 | B 提交后**立即可见** | A 提交前**不可见** |
| 典型场景 | 日志（要独立记录） | 子操作（可失败但要整体一致） |

**各自适合什么场景**：

```
REQUIRES_NEW 适合: B 要"无论如何都独立生效"
  ┌ 日志记录: 业务失败了日志也要存
  │ 审计追踪: 操作本身必须留痕，不管业务成败
  └ 独立消息: 发消息通知，不受业务回滚影响

NESTED 适合: B 要"和 A 同生共死，但 B 自己失败可以救"
  ┌ 子操作可失败: 扣优惠券失败不影响下单主流程
  │  → B 失败回滚到保存点，A 继续
  └ 但整体必须一致: 下单失败，库存也要恢复
     → A 回滚，B 跟着回滚
```

> **一句话记忆**：
> - REQUIRES_NEW = **"你死我活，各不相干"**（B 永久生效）
> - NESTED = **"同生共死，但允许我自救"**（B 可单独失败，但 A 亡则 B 亡）

---

## 二、@Transactional 完整调用链

### 从方法调用到事务提交的完整流程

```
调用方: userService.transfer(from, to, amount)

  1. 调用 $Proxy0.transfer（AOP 代理对象，见 aop.md）
     │
     ▼
  2. 拦截器链: ... → TransactionInterceptor
     │
     ▼
  3. TransactionInterceptor.invoke(invocation)
     │
     ▼
  4. createTransactionIfNecessary()              ← ★ 开事务
     │   事务管理器: PlatformTransactionManager
     │   │
     ▼   ▼
  5. DataSourceTransactionManager.doBegin()
     │
     ├─ 5.1 从 DataSource（HikariCP）拿 Connection  ← 你学过的连接池
     │       Connection conn = dataSource.getConnection();
     │
     ├─ 5.2 conn.setAutoCommit(false)             ← 关闭自动提交
     │
     ├─ 5.3 把 conn 绑定到 ThreadLocal             ← ★ 关键
     │       TransactionSynchronizationManager.bindResource(
     │           dataSource, new ConnectionHolder(conn));
     │
     ├─ 5.4 创建 TransactionInfo 记录事务状态
     │
     ▼
  6. invocation.proceed()                          ← 执行业务方法
     │   │
     │   ▼
     │   业务代码: accountDao.debit(from); accountDao.credit(to);
     │     │
     │     ▼
     │   MyBatis/JDBC 执行 SQL:
     │     怎么拿 Connection?
     │     → 从 ThreadLocal 拿同一个 conn！（不是新拿）
     │     → 保证 debit 和 credit 在同一事务里
     │
     ▼
  7. commitTransactionAfterReturning()            ← ★ 提交
     │   OR
     │   completeTransactionAfterThrowing(ex)     ← ★ 回滚
     │
     ▼
  8. cleanupTransactionInfo()
     │   ├─ 从 ThreadLocal 解绑 Connection
     │   ├─ conn.commit() 或 conn.rollback()
     │   └─ conn 归还给 HikariCP（自动设回 autoCommit=true）
     │
     ▼
  9. 返回结果给调用方
```

### 关键洞察：所有 SQL 共用同一个 Connection

```
业务方法里调多个 DAO:

  transfer() {
      accountDao.debit(from);    // SQL 1
      accountDao.credit(to);     // SQL 2
      logDao.insert(log);        // SQL 3
  }

  → 三个 SQL 必须用同一个 Connection，才能一起提交/回滚

  怎么保证同一个?
    事务开始时把 conn 绑到 ThreadLocal
    MyBatis 执行 SQL 前从 ThreadLocal 拿 conn
    → 拿到的是同一个

  没有事务的话:
    每次 SQL 都从连接池新拿 conn → 不同 SQL 用不同 conn → 不能一起回滚
```

---

## 三、Connection 绑定 ThreadLocal

### TransactionSynchronizationManager 的核心结构

```java
public abstract class TransactionSynchronizationManager {

    // 线程 → 资源（DataSource → ConnectionHolder）
    private static final ThreadLocal<Map<Object, Object>> resources =
        new NamedThreadLocal<>("Transactional resources");

    // 线程 → 同步回调列表
    private static final ThreadLocal<Set<TransactionSynchronization>> synchronizations =
        new NamedThreadLocal<>("Transaction synchronizations");

    // 线程 → 当前事务名
    private static final ThreadLocal<String> currentTransactionName =
        new NamedThreadLocal<>("Current transaction name");

    // 绑定 conn 到当前线程
    public static void bindResource(Object key, Object value) {
        resources.get().put(key, value);   // key=DataSource, value=ConnectionHolder
    }

    // 业务代码取 conn
    public static Object getResource(Object key) {
        return resources.get().get(key);   // 按 DataSource 取 conn
    }
}
```

### 为什么用 ThreadLocal

```
并发场景:

  Thread-1 调 transfer() → 绑定 conn1 到 Thread-1 的 ThreadLocal
  Thread-2 调 transfer() → 绑定 conn2 到 Thread-2 的 ThreadLocal

  → 两个线程的事务互不干扰
  → 各自的 SQL 各自从自己的 ThreadLocal 拿 conn

  ┌ ThreadLocal 保证线程隔离
  │  → 这是"每个请求一个事务"的基础
  │
  ┌ 对比: 全局变量存 conn → 多线程串台，灾难
  │
  └ 这是 Spring 处理"请求级状态"的标准手法
     RequestContextHolder 也是同样套路
```

### DataSourceUtils 拿连接的调用链

```java
// 业务层 DAO 执行 SQL 时，底层这么拿连接（不是直接 dataSource.getConnection）
public static Connection getConnection(DataSource dataSource) {
    // 1. 先从 ThreadLocal 拿（有事务时命中）
    ConnectionHolder holder = (ConnectionHolder)
        TransactionSynchronizationManager.getResource(dataSource);

    if (holder != null) {
        return holder.getConnection();   ← 复用事务里的 conn
    }

    // 2. 没事务 → 从连接池新拿（HikariCP）
    return dataSource.getConnection();
}
```

> **洞察**：同一个方法，在"事务里"和"事务外"行为不同——事务里复用 conn，事务外新拿。这就是为什么 `@Transactional` 注解能"无形中"把多个 SQL 绑成一个事务。

---

## 四、7 种失效场景的根因

> 所有的失效，根因只有一个：**绕过了 AOP 代理**。理解了 aop.md，这些场景都能推出来。

### 失效 1：自调用（this 调用）

```java
@Service
public class UserService {
    @Transactional
    public void transfer() { ... }

    public void batch() {
        this.transfer();   // ❌ 事务失效
    }
}

// 调 userService.batch():
//   → 进入代理，batch() 没事务切面 → 执行原始 batch
//   → 原始对象里 this.transfer() → this 是原始对象，不是代理
//   → 不经过代理 → 事务切面不触发 → 失效

// 解法:
//   1. 把 transfer() 拆到另一个类（跨类调用走代理）
//   2. 注入自己: @Autowired UserService self; self.transfer();
//   3. 用 AopContext.currentProxy()（需 exposeProxy=true）
```

> **根因**：AOP 代理只拦截"外部调用"，内部 `this.` 调用不经过代理。

### 失效 2：方法不是 public

```java
@Transactional
void transfer() { ... }   // ❌ 包级私有，失效（CGLIB 不重写）

// 原因:
//   JDK 动态代理: 接口方法默认 public，private 方法不在接口
//   CGLIB: 生成子类，不能重写 private/final 方法
//   → 代理类没有这个方法 → 拦截不到
```

### 失效 3：方法是 final

```java
@Transactional
public final void transfer() { ... }   // ❌ CGLIB 不能重写 final

// Spring 5.x 改进: 能检测并报警告，但仍然失效
```

### 失效 4：方法被 static 修饰

```java
@Transactional
public static void transfer() { ... }   // ❌ 静态方法属于类

// 原因:
//   AOP 代理是"对象方法"的拦截
//   静态方法不经过对象 → 代理拦不住
```

### 失效 5：异常被 catch 吞掉

```java
@Transactional
public void transfer() {
    try {
        accountDao.debit(from);
        accountDao.credit(to);   // ← 抛异常
    } catch (Exception e) {
        log.error("失败", e);     // ❌ 吞了异常
        // 没再抛 → 切面以为正常返回 → 提交事务！
    }
}

// 原因:
//   事务回滚靠 TransactionInterceptor 捕获异常
//   异常被业务层 catch 了，切面收不到 → 不回滚 → 提交

// 解法:
//   1. catch 后 throw new RuntimeException(e) 重新抛
//   2. 或手动 TransactionAspectSupport.currentTransactionStatus().setRollbackOnly()
```

> **根因**：事务的回滚信号是"异常"，吞了异常 = 没信号 = 不回滚。

### 失效 6：异常类型不对（默认只回滚 RuntimeException）

```java
@Transactional
public void transfer() throws Exception {
    accountDao.debit(from);
    if (to == null) throw new Exception("收款人不存在");   // ❌ 受检异常
    accountDao.credit(to);
}

// 默认: 只回滚 RuntimeException 和 Error
//   抛 Exception（受检）→ 不回滚 → 提交

// 解法:
//   @Transactional(rollbackFor = Exception.class)
//   ← 显式指定回滚的异常类型
```

> **根因**：Spring 默认按"非受检异常 = 系统故障 = 回滚，受检异常 = 业务异常 = 提交"的假设。这个假设不符合所有业务，所以要手动 `rollbackFor`。

### 失效 7：对象不是 Spring 管理的（new 出来的）

```java
UserService userService = new UserService();   // ❌ 不是 Bean
userService.transfer();                          // 没代理 → 失效

// 原因:
//   AOP 代理是 Spring 在 Bean 生命周期第 ⑥ 步生成的
//   new 出来的对象没经过 Spring → 没代理 → 切面失效

// 解法: 必须从容器拿 Bean
//   @Autowired UserService userService;
```

### 失效场景总表

| 场景 | 根因 | 解法 |
|------|------|------|
| 自调用 | this 不是代理 | 拆类 / 注入自己 / AopContext |
| 非 public | 代理不能重写 | 改 public |
| final 方法 | CGLIB 不能重写 final | 去 final |
| static 方法 | 代理拦不住类方法 | 改实例方法 |
| 异常被吞 | 切面收不到异常 | 重新抛 / 手动 setRollbackOnly |
| 异常类型不对 | 默认只回滚 RuntimeException | rollbackFor=Exception.class |
| new 出来的对象 | 没经过 Bean 生命周期 | 从容器拿 Bean |

> **统一根因**：AOP 代理是对"对象方法的调用"的拦截。所有绕开"代理对象 + 方法调用"的操作都会失效。

---

## 五、涉及的设计模式

### 5.1 模板方法模式（事务管理器骨架）

```java
// AbstractPlatformTransactionManager 定义骨架
public abstract class AbstractPlatformTransactionManager {

    public final TransactionStatus getTransaction(TransactionDefinition definition) {
        Object transaction = doGetTransaction();          ← 子类实现
        // ... 通用逻辑
    }

    public void commit(TransactionStatus status) {
        doCommit(status);                                  ← 子类实现
    }

    public void rollback(TransactionStatus status) {
        doRollback(status);                                ← 子类实现
    }

    // 抽象方法，子类填空
    protected abstract Object doGetTransaction();
    protected abstract void doCommit(TransactionStatus status);
    protected abstract void doRollback(TransactionStatus status);
}

// DataSourceTransactionManager 填空
public class DataSourceTransactionManager extends AbstractPlatformTransactionManager {
    @Override
    protected Object doGetTransaction() {
        // 从 ThreadLocal 拿 ConnectionHolder
    }
    @Override
    protected void doCommit(TransactionStatus status) {
        conn.commit();
    }
    // ...
}

// JpaTransactionManager / JtaTransactionManager 也是子类，各自填空
```

> **模式**：模板方法模式。Spring 定事务流程的骨架，具体怎么拿连接/提交/回滚由子类实现。

### 5.2 策略模式（传播行为）

```java
// 7 种传播行为 = 7 种策略
Propagation.REQUIRED
Propagation.REQUIRES_NEW
// ...

// AbstractPlatformTransactionManager 根据 propagation 选择策略:
switch (definition.getPropagationBehavior()) {
    case REQUIRED:        // 加入或新建
    case REQUIRES_NEW:    // 挂起 + 新建
    case NESTED:          // 保存点
    case SUPPORTS:        // 有就加入，无就无
    // ...
}
```

> **模式**：策略模式。传播行为是"如何处理事务边界"的策略。

### 5.3 代理模式（AOP 的应用）

```
@Transactional 触发 AOP 代理生成（见 aop.md）

  TransactionInterceptor 就是拦截器链里的一环
  → 代理模式 + 责任链模式

  本章是 AOP 的"应用层"，AOP 是"机制层"
```

### 5.4 ThreadLocal 模式（线程局部存储）

```
TransactionSynchronizationManager 用 ThreadLocal 存事务资源

  → 不是 GoF 23 种模式，但是并发编程的经典手法
  → 解决"每请求一状态"的隔离问题

  类似的应用:
    RequestContextHolder（每请求一个 RequestContext）
    ThreadLocalRandom（每线程一个 Random）
    MDC（每线程一个日志上下文）
```

---

## 六、能学到什么

### 6.1 "横切 + 状态绑定"的组合拳

```
@Transactional 一个注解，做了三件事:

  ┌ 横切: AOP 拦截方法
  ┌ 状态: ThreadLocal 绑定 Connection
  ┌ 异常: 捕获异常决定提交/回滚

  缺一不可:
    没横切 → 注解不生效
    没 ThreadLocal → 多个 SQL 不能共用 conn
    没异常机制 → 不知道该提交还是回滚

  → 一个功能往往是多种技术的组合
     理解每个技术的职责，才能拆解复杂功能
```

### 6.2 "复用"的层次

```
@Transactional 复用了多少已有基础设施:

  ┌ HikariCP（连接池）→ 拿 Connection
  │  你学过连接池，这里直接用
  │
  ┌ AOP（动态代理）→ 拦截方法调用
  │  你学过 AOP，这里是它的应用
  │
  ┌ ThreadLocal → 绑定请求级状态
  │  并发编程基础
  │
  ┌ Bean 生命周期 → 生成代理的时机
  │  你学过 IoC，第 ⑥ 步生成代理

  → 没有任何"新发明"
     全是已有机制的组合
     → 这就是"组合优于发明"的工程思想
```

### 6.3 "默认值"的取舍

```
@Transactional 默认:
  传播 = REQUIRED
  回滚 = RuntimeException + Error
  隔离 = 数据库默认

  为什么这样默认?
    REQUIRED: 最常用、最不容易出错
    RuntimeException: 受检异常通常是业务可控的（不该回滚）
    隔离用默认: 不强制覆盖数据库配置

  → 但默认不总对:
    业务想"受检异常也回滚" → rollbackFor=Exception.class
    业务想"日志独立提交" → propagation=REQUIRES_NEW
    → 默认值是"权衡多数场景"，特殊场景要改

  → 工程教训: 用框架的默认值前，要懂它假设了什么
     不符合假设就改，别抱怨框架
```

### 6.4 "失效场景"的学习法

```
背 7 种失效场景很累，但其实有统一根因:

  所有失效 = 绕过了 AOP 代理

  理解了这点，能推出第 8、第 9 种:
    ├ 反射调用 method.invoke(target) → 绕过代理 → 失效
    ├ 序列化/反序列化后的对象 → 不是代理 → 失效
    └ 跨 ClassLoader 拿的代理 → 不被识别 → 失效

  → 学习要抓"根因"，不要背"现象"
     理解了根因，能预测未列出的场景
```

### 6.5 调试事务问题的思路

```
事务没生效 / 数据没回滚:

  1. 检查是不是从容器拿的 Bean（不是 new 的）
  2. 检查方法是不是 public、非 final、非 static
  3. 检查是不是自调用（this.method）
  4. 检查异常是不是被 catch 吞了
  5. 检查抛的异常类型（是否需要 rollbackFor）
  6. 打开 Spring 事务日志: logging.level.org.springframework.transaction=DEBUG
     → 看 "Creating new transaction" / "Participating in existing transaction"
        判断事务有没有开启

  → 这套排查流程，本质就是"验证 AOP 代理是否生效"
```

---

## 与其他笔记的串联

```
→ aop.md
    @Transactional 的 TransactionInterceptor 是 AOP 拦截器链的一环
    AOP 代理在 Bean 生命周期第 ⑥ 步生成
    → 没代理就没事务

→ ioc-container.md
    事务失效场景 7（new 出来的对象）就是没经过 Bean 生命周期
    → Bean 第 ⑥ 步没走 → 没代理

→ circular-dependency.md
    @Transactional + 循环依赖的坑:
    循环依赖时 AOP 提前代理（getEarlyBeanReference）
    → 但 @Transactional 通常无碍（循环依赖拿的是同一个代理）
    → @Async + 循环依赖才会出问题（@Async 代理延迟生成）

→ connection-pool/pool-analysis.md
    事务从 HikariCP 拿 Connection
    → 理解了连接池，事务只是上面一层"借用"
    → 事务结束归还连接给池

→ thread-pool/source-analysis.md
    ThreadLocal 保证每请求/每线程事务隔离
    → @Async 让方法跑到另一个线程 → 跨线程 → 原 ThreadLocal 拿不到
    → 这是 @Async + @Transactional 的坑之一

→ netty/pipeline.md
    TransactionInterceptor 是拦截器链的一环 = 责任链模式
    和 Netty Pipeline 同构
```
