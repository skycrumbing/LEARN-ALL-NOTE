# AOP 与动态代理

> @Transactional、@Async、@Cacheable、日志切面… 都靠 AOP。
> 本文聚焦：AOP 核心概念、JDK 动态代理 vs CGLIB 的完整调用链、代理选择策略、拦截器链执行流程、涉及的设计模式、能学到什么。

---

## 目录

1. [AOP 核心概念](#一aop-核心概念)
2. [两种代理：JDK 动态代理 vs CGLIB](#二两种代理jdk-动态代理-vs-cglib)
3. [代理选择策略与调用链](#三代理选择策略与调用链)
4. [拦截器链的执行流程](#四拦截器链的执行流程)
5. [AOP 与 Bean 生命周期的关系](#五aop-与-bean-生命周期的关系)
6. [涉及的设计模式](#六涉及的设计模式)
7. [能学到什么](#七能学到什么)

---

## 一、AOP 核心概念

### 为什么需要 AOP

```
日志、事务、权限、限流... 这些"横切关注点"散落在各业务方法里:

  ┌ 没有 AOP:
  │  public void transfer(...) {
  │      log.info("开始转账");
  │      try {
  │          conn.setAutoCommit(false);
  │          // 业务逻辑
  │          conn.commit();
  │      } catch (Exception e) {
  │          conn.rollback();
  │          log.error("失败", e);
  │      }
  │  }
  │  ← 每个方法都重复写日志、事务代码

  └ 有 AOP:
     public void transfer(...) {
         // 纯业务逻辑
     }
     ← @Transactional 自动包了事务
     ← @Slf4j 切面自动包了日志
```

### AOP 的术语（用"做饭"类比）

```
Aspect（切面）: 一个横切功能模块
  ┌ 例: LogAspect（日志切面）、TransactionAspect（事务切面）
  └ 相当于"厨房里的卫生检查员"

Pointcut（切点）: 哪些方法被拦截
  ┌ 例: execution(* com.example.service.*.*(..))
  └ 相当于"检查哪些菜"

Advice（通知）: 在什么时候做什么
  ┌ @Before   方法前
  │ @After    方法后（无论成功失败）
  │ @AfterReturning  方法成功返回后
  │ @AfterThrowing   方法抛异常后
  └ @Around  环绕（前后都能控制）
  └ 相当于"检查的时机"

JoinPoint（连接点）: 程序执行中的某个点
  ┌ 理论上: 方法调用、字段访问、构造器...
  └ Spring AOP 只支持【方法级】连接点
  └ 相当于"程序运行中可以插入检查的时机"

Weaving（织入）: 把切面应用到目标的过程
  ┌ 编译时织入: AspectJ（修改 .class）
  │ 类加载时织入: AspectJ + LTW
  └ 运行时织入: Spring AOP（动态代理）← 本章重点
  └ 相当于"什么时候把检查员安排进去"
```

---

## 二、两种代理：JDK 动态代理 vs CGLIB

Spring AOP 的核心就是"动态代理"。两种实现：

### 2.1 JDK 动态代理

```
原理: 运行时生成一个实现目标接口的代理类

  目标:
    interface UserService {
        void save(String name);
    }
    class UserServiceImpl implements UserService { ... }

  代理后:
    class $Proxy0 implements UserService {     ← JDK 生成的类
        InvocationHandler handler;             ← 持有处理器
        public void save(String name) {
            handler.invoke(this, saveMethod, new Object[]{name});
        }
    }

  调用 userService.save("a"):
    → 实际调 $Proxy0.save("a")
    → 转发给 InvocationHandler.invoke
    → invoke 里执行切面逻辑 + 真实方法
```

**InvocationHandler 调用链**：

```java
// JDK 动态代理的核心接口
public interface InvocationHandler {
    Object invoke(Object proxy, Method method, Object[] args) throws Throwable;
}

// Spring 的实现（简化）
class JdkDynamicAopProxy implements InvocationHandler {

    @Override
    public Object invoke(Object proxy, Method method, Object[] args) {
        // 1. 找出这个方法对应的拦截器链
        List<Object> chain = advised.getInterceptorsAndDynamicInterceptionAdvice(method);

        if (chain.isEmpty()) {
            // 没切面 → 直接反射调目标方法
            return method.invoke(target, args);
        }

        // 2. 有切面 → 创建 ReflectiveMethodInvocation，触发拦截器链
        MethodInvocation invocation = new ReflectiveMethodInvocation(
            proxy, target, method, args, targetClass, chain);

        // 3. 链式执行（见第四章）
        return invocation.proceed();
    }
}
```

> **限制**：JDK 动态代理要求目标**必须有接口**。没接口就用不了。

### 2.2 CGLIB 代理

```
原理: 运行时生成目标类的【子类】，重写方法

  目标:
    class OrderService {           ← 没接口
        public void create(String id) { ... }
    }

  代理后（CGLIB 用 ASM 生成字节码）:
    class OrderService$$EnhancerByCGLIB extends OrderService {
        MethodInterceptor interceptor;
        @Override
        public void create(String id) {
            interceptor.intercept(this, createMethod, args, methodProxy);
        }
    }

  调用 orderService.create("x"):
    → 实际调子类的 create
    → 转发给 MethodInterceptor.intercept
    → intercept 里执行切面逻辑 + 真实方法
```

**MethodInterceptor 调用链**：

```java
// CGLIB 的核心接口
public interface MethodInterceptor extends Callback {
    Object intercept(Object obj, Method method, Object[] args, MethodProxy proxy);
}

// Spring 的实现
class CglibAopProxy implements MethodInterceptor {

    @Override
    public Object intercept(Object obj, Method method, Object[] args, MethodProxy proxy) {
        // 1. 找拦截器链
        List<Object> chain = advised.getInterceptorsAndDynamicInterceptionAdvice(method);

        if (chain.isEmpty()) {
            // 没切面 → 调父类原方法
            return proxy.invokeSuper(obj, args);
        }

        // 2. 创建 CglibMethodInvocation，触发拦截器链
        MethodInvocation invocation = new CglibMethodInvocation(
            obj, target, method, args, targetClass, chain, proxy);

        // 3. 链式执行
        return invocation.proceed();
    }
}
```

> **限制**：CGLIB 不能代理 `final` 类/方法（不能继承），不能代理构造方法。

### 2.3 两种代理对比

| 维度 | JDK 动态代理 | CGLIB |
|------|-------------|-------|
| 原理 | 实现接口 | 继承类（生成子类） |
| 要求 | 目标必须有接口 | 目标类可继承（非 final） |
| 字节码生成 | Proxy.newProxyInstance | ASM 生成 .class |
| 性能（创建） | 快 | 慢（生成字节码） |
| 性能（调用） | 反射调用，稍慢 | 直接方法调用，快 |
| Spring 默认 | 有接口时用 | SpringBoot 2.x+ 强制用 |

---

## 三、代理选择策略与调用链

### 选择逻辑（AbstractAutoProxyCreator）

```
createProxy() 的代理选择调用链:

  AbstractAutoProxyCreator.createProxy()
    │
    ├─ ProxyFactory.getProxy(classLoader)
    │   │
    │   ├─ if (target class 有接口 且 配置 proxyTargetClass=false)
    │   │     └─ new JdkDynamicAopProxy(advised)      ← JDK 动态代理
    │   │
    │   ├─ else
    │   │     └─ new CglibAopProxy(advised)            ← CGLIB
    │   │
    │   └─ ObjenesisCglibAopProxy（用 Objenesis 绕过构造器实例化）
    │
    └─ 返回代理对象

  判断条件:
    ┌ hasInterface: 目标类是否实现接口
    │ proxyTargetClass: 是否强制用 CGLIB（@EnableAspectJAutoProxy(proxyTargetClass=true)）
    │
    │ SpringBoot 2.x+ 默认 proxyTargetClass=true
    │  → 即使有接口也用 CGLIB（统一行为，避免接口/类代理不一致）
```

### 关键源码片段

```java
// DefaultAopProxyFactory.createAopProxy（简化）
public AopProxy createAopProxy(AdvisedSupport config) {
    // 判断是否强制用 CGLIB
    if (config.isProxyTargetClass()) {
        return new CglibAopProxy(config);
    }

    // 没强制 → 看有没有接口
    Class<?>[] interfaces = config.getTargetClass().getInterfaces();
    if (interfaces.length > 0) {
        return new JdkDynamicAopProxy(config);  // 有接口 → JDK
    }
    return new CglibAopProxy(config);            // 没接口 → CGLIB
}
```

> **洞察**：Spring 2.x 之前默认 JDK（有接口就用），2.x 之后默认 CGLIB（强制类代理）。原因：类代理行为统一，避免"注入时按接口拿代理，事务失效"的经典坑。

---

## 四、拦截器链的执行流程

### 拦截器链结构

```
一个方法可能被多个切面拦截:

  @Transactional + @Async + 自定义日志切面

  → 拦截器链: [TransactionInterceptor, AsyncInterceptor, LogInterceptor]

  执行顺序（默认按 @Order 或 @Priority）:
    外层 → 内层 → 目标方法 → 内层 → 外层

  LogInterceptor.before
    TransactionInterceptor.before
      AsyncInterceptor.before
        ── 目标方法执行 ──
      AsyncInterceptor.after
    TransactionInterceptor.after
  LogInterceptor.after
```

### ReflectiveMethodInvocation.proceed() 调用链

```java
// 责任链的核心
public class ReflectiveMethodInvocation implements MethodInvocation {

    private final List<?> interceptors;     // 拦截器链
    private int currentInterceptorIndex = -1;

    @Override
    public Object proceed() throws Throwable {
        // 链走完了 → 调目标方法
        if (this.currentInterceptorIndex == this.interceptors.size() - 1) {
            return invokeJoinpoint();   // 反射调 target.method()
        }

        // 取下一个拦截器
        Object interceptor = this.interceptors.get(++this.currentInterceptorIndex);

        // 交给拦截器处理，拦截器内部会调 proceed() 继续往下
        return ((MethodInterceptor) interceptor).invoke(this);
    }
}
```

### @Around 的特殊处理

```
@Around 是最特殊的通知，因为它"包裹"整个执行:

  @Around("pointcut()")
  public Object around(ProceedingJoinPoint pjp) throws Throwable {
      log.info("before");
      Object result = pjp.proceed();   ← 调 proceed() 触发下一个拦截器/目标
      log.info("after");
      return result;
  }

  → @Around 的拦截器调用 proceed() 才会继续链
  → 忘了调 proceed() → 目标方法不执行（常见 bug）
```

### 完整执行调用链（以 transfer 方法 + 事务切面 + 日志切面为例）

```
调用方: userService.transfer(from, to, amount)

  1. 调用 $Proxy0.transfer（代理对象）
     │
     ▼
  2. JdkDynamicAopProxy.invoke
     │   拿到拦截器链: [LogInterceptor, TransactionInterceptor]
     ▼
  3. 创建 ReflectiveMethodInvocation
     │
     ▼
  4. invocation.proceed()
     │   currentInterceptorIndex = 0
     ▼
  5. LogInterceptor.invoke(invocation)
     │   执行 @Before: log.info("开始 transfer")
     │   调 invocation.proceed()  ← 继续
     │     │   currentInterceptorIndex = 1
     │     ▼
     │   TransactionInterceptor.invoke(invocation)
     │     │   开事务: conn.setAutoCommit(false)
     │     │   调 invocation.proceed()  ← 继续
     │     │     │   currentInterceptorIndex = 2（== size，走完了）
     │     │     ▼
     │     │   invokeJoinpoint()
     │     │     反射调 target.transfer(from, to, amount)
     │     │     ← 真实业务逻辑
     │     │     return 结果
     │     │
     │     │   回到 TransactionInterceptor
     │     │   正常: conn.commit()
     │     │   异常: conn.rollback()
     │     │   return 结果
     │     ▼
     │   回到 LogInterceptor
     │   执行 @AfterReturning: log.info("完成")
     │   return 结果
     ▼
  6. 返回结果给调用方
```

---

## 五、AOP 与 Bean 生命周期的关系

### AOP 在 Bean 生命周期的哪一步？

```
回顾 ioc-container.md 的 9 步生命周期:

  ① 实例化  ── 不涉及 AOP
  ② 属性填充 ── 不涉及 AOP（但循环依赖时会提前生成代理，见下文）
  ③ Aware    ── 不涉及 AOP
  ④ 前置处理 ── 不涉及 AOP
  ⑤ 初始化   ── 不涉及 AOP
  ⑥ 后置处理 ── ★★★ AOP 代理生成点
  ⑦ 注册     ── 注册的是代理对象（如果生成了）

  AOP 的入口: AbstractAutoProxyCreator.postProcessAfterInitialization
              ← 这是 BeanPostProcessor 的"后置"方法
```

### AbstractAutoProxyCreator 的核心逻辑

```java
// AbstractAutoProxyCreator（简化）
public abstract class AbstractAutoProxyCreator
        implements BeanPostProcessor {

    // ⑥ 后置处理: 这里决定是否生成代理
    @Override
    public Object postProcessAfterInitialization(Object bean, String beanName) {
        if (bean == null) return null;

        // 1. 找出所有匹配该 Bean 的切面
        Object[] specificInterceptors = getAdvicesAndAdvisorsForBean(bean.getClass(), beanName);

        // 2. 有切面 → 生成代理
        if (specificInterceptors != null) {
            Object proxy = createProxy(bean, specificInterceptors);
            return proxy;   ← 返回代理，替换原始对象
        }

        // 3. 没切面 → 返回原始对象
        return bean;
    }
}
```

### 循环依赖时的"提前代理"

```
回忆 circular-dependency.md:
  三级缓存的 ObjectFactory 调 getEarlyBeanReference
  → 这里也可能生成代理！

  AbstractAutoProxyCreator.getEarlyBeanReference:
    1. 记录 earlyProxyReferences.put(beanName, bean)
       ← 标记"这个 Bean 已经早期代理过"
    2. wrapIfNecessary(bean) → 生成代理
    3. 返回代理

  然后到第 ⑥ 步 postProcessAfterInitialization:
    if (earlyProxyReferences.containsKey(beanName)):
        ← 已经代理过，不重复代理
        return bean   ← 直接返回（之前生成的代理）
    else:
        正常生成代理

  → 保证: 循环依赖拿到的代理 == 最终容器里的代理
     不会"早期生成一次 + 后期又生成一次"导致两个代理
```

### AOP 代理与 @Transactional/@Async 的关系

```
@Transactional:
  → 切面 = TransactionInterceptor
  → 代理生成时，TransactionInterceptor 进入拦截器链
  → 方法调用时，拦截器链执行 → 开事务/提事务

@Async:
  → 切面 = AsyncAnnotationBeanPostProcessor（也是个 AbstractAutoProxyCreator）
  → 代理生成时，AsyncInterceptor 进入拦截器链
  → 方法调用时，拦截器提交任务到线程池

→ @Transactional/@Async 都是 AOP 的应用
   理解了 AOP，事务和异步的原理就通了
```

---

## 六、涉及的设计模式

### 6.1 代理模式（核心）

```
AOP 本质 = 代理模式

  真实对象: UserServiceImpl
  代理对象: $Proxy0 / OrderService$$EnhancerByCGLIB

  代理对象"伪装"成真实对象，在方法调用时插入额外逻辑

  静态代理（手写）: 手动写代理类，方法一多就累
  动态代理（运行时生成）: Spring 用，零手写
```

> **模式**：代理模式。控制对真实对象的访问，附加功能。

### 6.2 责任链模式（拦截器链）

```
多个拦截器组成责任链，依次处理:

  LogInterceptor → TransactionInterceptor → AsyncInterceptor → 目标方法

  每个拦截器调 proceed() 把控制权交给下一个

  ReflectiveMethodInvocation 就是责任链的"调度器"
  currentInterceptorIndex 记录走到哪个了
```

> **模式**：责任链模式。和 Netty 的 Pipeline 一模一样。

### 6.3 策略模式（代理选择）

```
两种代理 = 两种策略:

  有接口 → JDK 策略
  无接口 → CGLIB 策略

  DefaultAopProxyFactory.createAopProxy 是策略选择器
  JdkDynamicAopProxy / CglibAopProxy 是两个策略实现
```

> **模式**：策略模式。根据条件选不同实现。

### 6.4 模板方法模式（proceed 骨架）

```
ReflectiveMethodInvocation.proceed() 定义骨架:

  if (链走完) 调目标方法
  else 取下一个拦截器，调它的 invoke(this)

  具体拦截器（TransactionInterceptor 等）填空:
  各自在 invoke 里做自己事，再调 proceed 继续

  → proceed 是模板，拦截器是填空
```

### 6.5 适配器模式（Advisor → Interceptor）

```
切面的原始形态是 Advisor（包含 Pointcut + Advice）
拦截器链需要的是 MethodInterceptor

  AdvisorAdvisor → 适配成 MethodInterceptor
  DefaultAdvisorAdapterRegistry 做这个适配

  例: @AfterReturning 是 AfterReturningAdvice
       → 适配成 AspectJAfterReturningMethodInterceptor
```

> **模式**：适配器模式。把"声明式切面"适配成"可执行的拦截器"。

---

## 七、能学到什么

### 7.1 "代理"是控制对象行为的通用手法

```
代理模式不只用于 AOP:

  ┌ 远程代理: RPC 框架（Dubbo）生成 stub，本地调 stub → 转发到远端
  │  → 和 Spring AOP 代理结构一模一样
  │
  ┌ 虚拟代理: 延迟加载大对象（Hibernate 懒加载）
  │  → 第一次访问才真正创建
  │
  ┌ 保护代理: 权限校验（Spring Security）
  │  → 调用前检查权限
  │
  ┌ 智能引用代理: 引用计数（C++ 智能指针）
  │
  └ AOP 代理: 横切逻辑（日志/事务/缓存）

  → 学会代理模式，看什么框架都通透
     Dubbo 的 ProxyFactory、MyBatis 的 MapperProxy 都是这套
```

### 7.2 "责任链"是处理"多切面"的天然结构

```
一个方法有多个切面 → 必然要链式处理

  顺序问题:
    外层切面先进入、最后退出（洋葱模型）
    内层切面最后进入、最先退出

  ┌ 和 Netty Pipeline 完全同构:
  │  Netty 的 Inbound 从 HEAD → TAIL
  │  Spring AOP 的拦截器从外 → 内 → 目标 → 内 → 外
  │  → 都是"链式 + proceed/next 触发下一个"
  │
  └ 区别:
     Netty 的链是"双向"（入站+出站）
     Spring AOP 的链是"洋葱"（进+出）
     → 都是责任链的变体
```

### 7.3 "动态生成代码"是性能与灵活的权衡

```
JDK 动态代理 vs CGLIB 的选择本质:

  ┌ JDK: 运行时反射调用 → 慢，但通用（任何接口都行）
  │  适合: 切面少、调用不频繁
  │
  ┌ CGLIB: 生成字节码 → 调用快，但生成慢
  │  适合: 调用频繁（启动一次生成，运行多次调用）
  │
  └ SpringBoot 默认 CGLIB:
     启动慢一点（生成字节码），换来运行快
     → "用启动时间换运行时间"的经典权衡

  → 这和"JIT 编译"思想一致:
     解释执行快启动、慢运行
     JIT 慢启动（编译）、快运行
     → 看场景选策略
```

### 7.4 "切面与业务的解耦"

```
AOP 的本质价值: 把"横切关注点"从业务代码剥离

  ┌ 业务方法只写业务
  │  事务、日志、权限由切面统一处理
  │  → 业务方法可读性极高
  │
  ┌ 切面可复用
  │  一个 LogAspect 适用于所有 service
  │  → 不重复造轮子
  │
  ┌ 切面可插拔
  │  加/减一个 @Aspect 类，不改业务代码
  │  → 这就是 Spring "扩展点优先"思想的体现

  → 这是"关注点分离"原则的工程实现
     和 MVC 分层（Model/View/Controller）是同一种思想
     MVC 按"职责"分层，AOP 按"横切"切片
```

### 7.5 AOP 的"失效场景"思维

```
AOP 失效 = 代理没生效 = "this 调用"绕过代理

  ┌ 自调用失效:
  │  class Service {
  │      @Transactional
  │      public void a() { ... }
  │      public void b() { this.a(); }   ← this 是原始对象，不是代理！
  │  }
  │  → 调 service.b() → this.a() 不走代理 → 事务失效
  │
  ┌ private/final 方法失效:
  │  CGLIB 不能重写 private/final → 代理类没这方法 → 失效
  │
  ┌ 静态方法失效:
  │  静态方法属于类，不属于对象 → 代理拦不住
  │
  └ new 出来的对象失效:
     不是从容器拿的 Bean → 没代理 → 失效

  → 理解了"代理是对方法调用的拦截"
     就能推出所有失效场景的根因
     详见 transaction.md
```

---

## 与其他笔记的串联

```
→ ioc-container.md
    AOP 在 Bean 生命周期第 ⑥ 步（postProcessAfterInitialization）生成代理
    → 学了 IoC 才懂 AOP "插在哪个环节"

→ circular-dependency.md
    循环依赖时 AOP 在 getEarlyBeanReference 提前生成代理
    earlyProxyReferences 保证"早期代理 == 最终代理"

→ transaction.md
    @Transactional = TransactionInterceptor（AOP 的一种应用）
    → 学了 AOP，事务的"调用链"就清晰了

→ netty/pipeline.md
    Netty Pipeline 责任链 vs Spring AOP 拦截器链
    → 两种工业级框架都用责任链做横切逻辑

→ connection-pool/pool-analysis.md
    @Transactional 背后从 HikariCP 拿连接
    AOP 拦截 → 拿连接 → 开事务 → 业务 → 提交 → 归还

→ data-structures/skip-list.md
    跳表的"概率多层" vs AOP 的"动态多层代理"
    → 都是"按需分层"的思想
```
