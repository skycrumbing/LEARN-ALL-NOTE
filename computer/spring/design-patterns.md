# Spring 设计模式总览 + 综合收获

> 前四章讲了 IoC、循环依赖、AOP、事务的具体机制。本章退一步，盘点 Spring 用了多少经典设计模式，以及从整个 Spring 专题能学到什么。
> 这既是"设计模式实战速查"，也是 Spring 专题的总结。

---

## 目录

1. [Spring 用到的 11 种设计模式](#一spring-用到的-11-种设计模式)
2. [每种模式在 Spring 中的具体体现](#二每种模式在-spring-中的具体体现)
3. [从 Spring 专题能学到什么（综合收获）](#三从-spring-专题能学到什么综合收获)
4. [Spring 学习路径建议](#四spring-学习路径建议)

---

## 一、Spring 用到的 11 种设计模式

| # | 模式 | Spring 中的体现 | 出处 |
|---|------|----------------|------|
| 1 | 单例模式 | singleton 作用域 + singletonObjects 缓存 | ioc-container.md |
| 2 | 工厂方法模式 | FactoryBean（如 MapperFactoryBean） | ioc-container.md |
| 3 | 建造者模式 | BeanDefinition 的组装 | ioc-container.md |
| 4 | 模板方法模式 | AbstractApplicationContext.refresh / InitializingBean / 事务管理器 | ioc / transaction.md |
| 5 | 观察者模式 | ApplicationEvent + ApplicationListener | 本章节 |
| 6 | 责任链模式 | BeanPostProcessor 链 / AOP 拦截器链 | ioc / aop.md |
| 7 | 策略模式 | 代理选择（JDK/CGLIB）/ 事务传播行为 | aop / transaction.md |
| 8 | 适配器模式 | HandlerAdapter / AdvisorAdapter | aop.md |
| 9 | 装饰器模式 | BeanWrapper / TransactionAwareCache | 本章节 |
| 10 | 代理模式 | AOP 动态代理（核心） | aop.md |
| 11 | 备忘录模式 | 三级缓存（对象各阶段快照） | circular-dependency.md |

---

## 二、每种模式在 Spring 中的具体体现

### 2.1 单例模式

```java
// Spring 的 singleton 作用域 = 容器级别的单例
@Component  // 默认 singleton
public class UserService { }

// 不是 GoF 那种"类自己管自己"，而是"容器帮你管单例"
// singletonObjects: Map<beanName, beanInstance> 保证唯一

// 区别:
//   GoF 单例: 类自己持有一个 static 实例
//   Spring 单例: 容器持有一个 Map，每个 beanName 一个实例
//   → Spring 单例是"每个容器一个"，可以有多容器（父子容器）
```

> **洞察**：Spring 把单例"容器化"了，比 GoF 的类级单例更灵活——同一类可以有不同 beanName 的多个实例。

### 2.2 工厂方法模式

```java
// FactoryBean 是典型工厂方法
public interface FactoryBean<T> {
    T getObject() throws Exception;   // 工厂方法
    Class<?> getObjectType();
}

// MyBatis 的 MapperFactoryBean:
MapperFactoryBean<UserMapper> fb = new MapperFactoryBean<>(UserMapper.class);
UserMapper mapper = fb.getObject();   // 工厂产出代理对象
// → 把一个接口"造"成可用的 Bean

// Spring 自己的 SqlSessionFactoryBean、RedisConnectionFactoryBean 都是这个
```

### 2.3 建造者模式

```java
// BeanDefinition 的组装是建造者
BeanDefinitionBuilder builder = BeanDefinitionBuilder
    .rootBeanDefinition(UserService.class)
    .addPropertyValue("name", "test")
    .setLazyInit(true)
    .setInitMethodName("init");

BeanDefinition bd = builder.getBeanDefinition();
// → 一步步组装出"Bean 的图纸"
```

> **为什么用建造者**：BeanDefinition 有十几个属性，构造器参数太多，用建造者清晰。

### 2.4 模板方法模式

```
Spring 的"模板方法"无处不在:

  AbstractApplicationContext.refresh()           ← 启动骨架
    子类: AnnotationConfigApplicationContext / SpringBoot 的 ServletWebServerApplicationContext
    填空 onRefresh()（SpringBoot 在这启动 Tomcat）

  AbstractAutowireCapableBeanFactory.invokeInitMethods()  ← 初始化骨架
    填空: afterPropertiesSet / init-method

  AbstractPlatformTransactionManager            ← 事务骨架
    子类: DataSourceTransactionManager / JpaTransactionManager
    填空: doBegin / doCommit / doRollback

  JdbcTemplate / RestTemplate / RedisTemplate   ← 命名带 Template 的都是
```

> **洞察**：Spring 命名带 `Template` 的类几乎都是模板方法模式。识别这个规律，看类名就懂它是干什么的。

### 2.5 观察者模式

```java
// 事件: ApplicationEvent
public class UserRegisteredEvent extends ApplicationEvent {
    private User user;
    // ...
}

// 监听者: ApplicationListener
@Component
public class EmailListener implements ApplicationListener<UserRegisteredEvent> {
    public void onApplicationEvent(UserRegisteredEvent event) {
        sendEmail(event.getUser());
    }
}

// 发布: ApplicationEventPublisher
@Service
public class UserService {
    @Autowired ApplicationEventPublisher publisher;

    public void register(User user) {
        save(user);
        publisher.publishEvent(new UserRegisteredEvent(user));   // 发布事件
    }
}

// → 注册用户后，邮件监听器、积分监听器、统计监听器各自响应
//    互不干扰，新增监听器不改 UserService
```

> **模式**：观察者模式 + 事件驱动。和 Netty 的 Channel 事件传播是同一种思想。

### 2.6 责任链模式

```
Spring 的责任链出现在两处:

  ① BeanPostProcessor 链（Bean 生命周期）
     Bean1 → Bean2 → Bean3 → ... → 目标 Bean
     每个 PostProcessor 处理一遍 Bean

  ② AOP 拦截器链（方法调用）
     LogInterceptor → TxInterceptor → AsyncInterceptor → 目标方法
     每个拦截器调 proceed() 继续下一个

  → 两种都是"链 + 触发下一个"的结构
```

> **对比 Netty**：Netty 的 ChannelPipeline 也是责任链，handler 一个接一个。Spring 和 Netty 用同一种模式解决"扩展点"问题。

### 2.7 策略模式

```
Spring 的策略模式多处:

  ① AOP 代理选择
     有接口 → JdkDynamicAopProxy（策略 A）
     无接口 → CglibAopProxy（策略 B）
     选择器: DefaultAopProxyFactory

  ② 事务传播行为
     REQUIRED / REQUIRES_NEW / NESTED ... = 7 种策略
     选择器: AbstractPlatformTransactionManager 根据 propagation 字段选

  ③ 资源加载
     ClassPathResource / FileSystemResource / UrlResource
     统一接口 Resource，不同实现是不同策略

  ④ Bean 作用域
     SingletonScope / PrototypeScope / RequestScope ...
     每种 scope 是一个 Strategy
```

### 2.8 适配器模式

```java
// MVC 的 HandlerAdapter 是典型适配器
// 不同类型的 Controller 接口不一致，用适配器统一

// Controller 形态1: 实现 Controller 接口
// Controller 形态2: @RequestMapping 注解的方法（HandlerMethod）
// Controller 形态3: HttpRequestHandler

// 三种形态方法签名不同 → 用不同 HandlerAdapter 适配
// DispatcherServlet 只调 handlerAdapter.handle()，不关心具体类型

// AOP 里也有: AdvisorAdapter 把 Advice 适配成 MethodInterceptor
```

> **模式**：适配器模式。统一不一致的接口，让上层只调统一接口。

### 2.9 装饰器模式

```java
// BeanWrapper 装饰 Bean，提供类型转换等额外能力
BeanWrapper wrapper = new BeanWrapperImpl(user);
wrapper.setPropertyValue("age", "25");   // 字符串自动转 int

// TransactionAwareCacheDecorator 给 Cache 加事务感知
// → 事务里的缓存操作在提交后才生效，回滚则清缓存

// 装饰器 vs 代理的区别:
//   代理: 控制"是否/何时"访问（加日志、加事务）
//   装饰器: 增强"如何"访问（加功能、加类型转换）
//   → 结构相似，意图不同
```

### 2.10 代理模式

```
AOP 动态代理（见 aop.md）

  原始对象 → 代理对象 → 在方法调用时插入横切逻辑

  JDK 动态代理: 接口代理
  CGLIB: 类代理（生成子类）

  → 代理是 AOP 的核心，也是 @Transactional/@Async 的基础
```

### 2.11 备忘录模式（三级缓存）

```
三级缓存存对象在不同创建阶段的"快照"（见 circular-dependency.md）

  三级 singletonFactories     → 工厂态（未产出）
  二级 earlySingletonObjects  → 半成品态（实例化完，属性没填）
  一级 singletonObjects       → 成品态（完整）

  → 每级保存一个"阶段快照"，这是备忘录思想
     （虽然不是标准 GoF 备忘录，但思想一致）
```

---

## 三、从 Spring 专题能学到什么（综合收获）

### 3.1 工程哲学：用简单数据结构造复杂系统

```
Spring 全程最高级的数据结构:
  ConcurrentHashMap（Bean 缓存）
  HashMap（三级缓存）
  ArrayList（拦截器链）
  Set（正在创建的 Bean 集合）

  → 没有红黑树、没有跳表、没有并查集
     都是 JDK 基础集合

  复杂度不在"数据结构"，在"流程编排":
    refresh() 的 12 步顺序
    Bean 生命周期的 9 步顺序
    三级缓存的"何时读何时写"
    AOP 拦截器链的"何时 proceed"

  ┌ 启示: 大部分工程问题，不需要炫技的数据结构
  │  需要的是"把流程理清楚、把状态管好"
  │  这比"用红黑树"更难，也更值钱
  │
  └ 你学过的数据结构（红黑树/跳表/堆/Trie）是"算法思维"
     Spring 教你的是"系统思维"——两者都重要
```

### 3.2 扩展点思维：框架定骨架，业务填血肉

```
Spring 几乎不写死流程，全靠扩展点:

  BeanFactoryPostProcessor → 建对象前改 BeanDefinition
  BeanPostProcessor         → 建对象前后改 Bean
  ApplicationListener       → 事件发生时响应
  @Aspect                   → 方法调用时插入逻辑

  → Spring 只定"什么时候做什么"
     具体做什么由集成方填

  ┌ 对比:
  │  Tomcat: Valve/Pipeline 扩展点
  │  Netty: ChannelHandler 扩展点
  │  MyBatis: Interceptor/Plugin 扩展点
  │  → 工业级框架都这样设计
  │
  └ 自己设计框架时，也要"定骨架 + 留扩展点"
     不要把所有逻辑写死在主流程
```

### 3.3 生命周期思维：理解"对象怎么长大"

```
Spring 把"造对象"拆成 9 步:

  实例化 → 注入 → Aware → 前置 → 初始化 → 后置 → 注册
  ↓       ↓       ↓       ↓       ↓        ↓
  原始   能用容器  能感知   能改    能换代理

  每一步都是一个"可观察/可干预"的点

  ┌ 这种思维迁移到任何"复杂对象生命周期":
  │  TCP 连接: 建立 → 握手 → 数据传输 → 关闭（Netty 的 channelActive/Read/Inactive）
  │  HTTP 请求: 接收 → 解析 → 处理 → 响应（Servlet Filter 链）
  │  请求线程: 创建 → 执行 → 销毁（ThreadLocal 的 set/remove）
  │  → 都是"拆阶段 + 每阶段留扩展点"
  │
  └ 学会这招，看任何框架都能拆解
```

### 3.4 延迟决策与一致性

```
循环依赖的三级缓存教了:

  ┌ 能推迟的决定就推迟
  │  → ObjectFactory 延迟到循环发生才决定代理
  │  → 信息最全时决策最优
  │
  ┌ 决定了就要记录，保证一致性
  │  → earlyProxyReferences 记录"已代理过"
  │  → 后续不重复代理，保证全局唯一
  │
  └ 这是分布式系统设计里也用得上的思想:
     分布式事务的"两阶段提交"也是"先准备（延迟）、再决定（记录）"
     → 本质都是"延迟决策 + 状态记录"
```

### 3.5 失效场景的统一根因法

```
@Transactional 的 7 种失效，根因都是"绕过 AOP 代理"

  → 学会"抓根因"，不背"现象"
     理解了代理机制，能推出第 8、第 9 种失效

  ┌ 这个方法论适用于一切"机制失效":
  │  Redis 持久化失效 → 根因: 没触发 RDB/AOF 的条件
  │  缓存击穿 → 根因: 热点 key 过期 + 高并发
  │  线程池拒绝 → 根因: 任务速度 > 处理速度
  │  → 先理解机制，再推失效条件
  │
  └ 这是"反向学习法":
     先懂"怎么工作"，反推"什么情况不工作"
```

### 3.6 设计模式的实战范本

```
Spring 是设计模式教科书（11 种模式都用了）

  → 不再是"教科书里抽象的模式定义"
     而是看到了"为什么用这个模式、解决了什么问题"

  例: 工厂方法模式
    教科书: "定义一个创建对象的接口，让子类决定实例化哪个类"
    Spring: FactoryBean 让 MyBatis 把 Mapper 接口"造"成 Bean
    → 一下就懂了"工厂方法"为什么有用

  → 学 Spring = 把设计模式从"概念"变成"直觉"
```

### 3.7 多技术组合的解构能力

```
@Transactional 一个注解 = AOP + ThreadLocal + 连接池 + 异常机制

  看到任何"魔法注解"，都能拆解:
    @Cacheable = AOP + 缓存客户端（Redis）
    @Async = AOP + 线程池
    @Scheduled = AOP + 定时器（ScheduledExecutor）
    @EventListener = 观察者模式 + 事件总线
    @Retryable = AOP + 重试策略

  ┌ 拆解后:
  │  每个注解都不再神秘
  │  都是"已有技术的组合"
  │
  └ 这是"元认知":
     不被框架的注解唬住，能看到背后的机制
     → 这是从"会用"到"会设计"的关键一步
```

---

## 四、Spring 学习路径建议

```
已学（本专题）:
  ✅ IoC 容器 + Bean 生命周期
  ✅ 三级缓存 + 循环依赖
  ✅ AOP + 动态代理
  ✅ 事务管理
  ✅ 设计模式总览

建议下一步:

  ┌ Spring Boot 自动配置（@Conditional + spi）
  │  → 理解 starter 机制，看"约定大于配置"怎么实现
  │
  ┌ Spring MVC（DispatcherServlet 调用链）
  │  → 和 Tomcat NIO 串联，理解一个 HTTP 请求怎么流转
  │
  ┌ Spring 事件机制深入（@TransactionalEventListener）
  │  → 事务相关事件，和事务串联
  │
  ┌ Spring 集成 MyBatis（MapperFactoryBean + SqlSession）
  │  → 和连接池串联，看持久层全链路
  │
  ┌ Spring Cloud（注册中心 + 配置中心 + 网关）
  │  → 微服务层面，分布式版 Spring

  → 这些都是"应用 Spring"的延伸
     本专题的"核心机制"已经打通
```

---

## 与其他笔记的综合串联

```
Spring 是"胶水"，把所有知识点粘起来:

  computer/io/nio.md
    → Bean 生命周期里没直接用 IO，但事务的 Connection 走 socket
    → @Async 用线程池，线程池背后是 IO 模型选择

  computer/netty/
    → Netty Pipeline 责任链 = Spring BeanPostProcessor 责任链
    → 同一种设计模式在不同框架的应用

  computer/thread-pool/source-analysis.md
    → @Async 用线程池执行异步方法
    → ThreadLocal 保证每线程事务隔离

  computer/redis/redis-analysis.md
    → @Cacheable 靠 Redis（AOP + Redis 客户端）
    → Redis 客户端（Jedis/Lettuce）从 Spring 容器拿

  computer/connection-pool/pool-analysis.md
    → @Transactional 从 HikariCP 拿 Connection
    → 事务结束归还连接给池

  computer/mq/mq-analysis.md
    → @RabbitListener / @KafkaListener 靠 Spring 容器管理消费者
    → 消息处理方法里的 @Transactional 把消息消费 + DB 操作绑成事务

  computer/tomcat-webflux/source-analysis.md
    → WebFlux 是 Spring 的响应式分支
    → 传统 Spring MVC（Tomcat 阻塞）vs WebFlux（Netty 非阻塞）
    → 学了 Spring 核心，再回看 WebFlux 会更清晰

  computer/jvm-gc/source-analysis.md
    → Spring 单例 Bean 长期存活 = 长期 GC Root
    → Bean 不被回收，因为它被 singletonObjects 引用

  computer/data-structures/*（红黑树/跳表/堆/Trie）
    → 这些是"算法思维"
    → Spring 教的是"系统思维"
    → 两者结合 = 全栈工程师的知识结构
```
