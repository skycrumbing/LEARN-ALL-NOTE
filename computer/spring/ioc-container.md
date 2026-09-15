# IoC 容器与 Bean 生命周期

> 这是 Spring 的地基。理解了 Bean 怎么被"造出来"，后面的循环依赖、AOP、事务才有依附的骨架。
> 本文聚焦：容器结构 + `refresh()` 调用链 + Bean 生命周期 9 步 + 每步涉及的设计模式 + 能学到什么。

---

## 目录

1. [容器两大接口：BeanFactory vs ApplicationContext](#一容器两大接口beanfactory-vs-applicationcontext)
2. [refresh()：容器启动的核心调用链](#二refresh容器启动的核心调用链)
3. [Bean 生命周期：9 步调用链](#三bean-生命周期9-步调用链)
4. [每一步的扩展点与设计模式](#四每一步的扩展点与设计模式)
5. [能学到什么](#五能学到什么)

---

## 一、容器两大接口：BeanFactory vs ApplicationContext

### 结构关系

```
BeanFactory（最基础的容器接口，只管 getBean）
    ↑ 继承
HierarchicalBeanFactory（支持父子容器）
    ↑ 继承
ListableBeanFactory（可列举所有 Bean）
    ↑ 继承
ApplicationContext（企业级容器，多了事件/国际化/资源加载）
    ↑ 实现
  ClassPathXmlApplicationContext / AnnotationConfigApplicationContext
```

### 核心区别

| 维度 | BeanFactory | ApplicationContext |
|------|-------------|-------------------|
| Bean 加载时机 | **懒加载**（getBean 时才创建） | **饿加载**（启动时创建所有单例） |
| 完整性 | 只提供基础 IoC | + 事件发布 + 国际化 + 资源加载 + 注解扫描 |
| 使用场景 | 很少直接用 | 99% 的业务都用它 |
| 性能 | 启动快（啥也不干） | 启动慢（提前建好 Bean） |

> **为什么 ApplicationContext 要饿加载？**
> 启动时发现问题，比运行时崩好。早建早暴露配置错误（比如循环依赖、缺类）。

### 容器的内部数据结构（核心就几个 Map）

```java
// DefaultListableBeanFactory 的核心字段（简化）
public class DefaultListableBeanFactory {

    // Bean 定义注册表：Bean 名 → BeanDefinition（元信息）
    private final Map<String, BeanDefinition> beanDefinitionMap
        = new ConcurrentHashMap<>(256);

    // 单例缓存：Bean 名 → 完整对象
    private final Map<String, Object> singletonObjects
        = new ConcurrentHashMap<>(256);

    // 早期引用（循环依赖用，见 circular-dependency.md）
    private final Map<String, Object> earlySingletonObjects
        = new HashMap<>(16);

    // 单例工厂（循环依赖用）
    private final Map<String, ObjectFactory<?>> singletonFactories
        = new HashMap<>(16);
}
```

> **洞察**：IoC 容器本质 = 几个 `ConcurrentHashMap` + 一套创建流程。
> 你学过的 HashMap 在这里就是核心数据结构。

---

## 二、refresh()：容器启动的核心调用链

`AnnotationConfigApplicationContext` 启动时，最终调到 `AbstractApplicationContext.refresh()`，这是整个 Spring 启动的总入口。

### 完整调用链

```
main()
  └─ new AnnotationConfigApplicationContext(AppConfig.class)
       └─ this.refresh()                                    ← 总入口
            │
            ├─ 1. prepareRefresh()                           ← 准备环境
            │     清空旧状态、校验必要属性
            │
            ├─ 2. obtainFreshBeanFactory()                  ← 拿到 BeanFactory
            │     加载 BeanDefinition（读注解/扫描包）
            │     └─ registerBean(...)                      ← 注册到 beanDefinitionMap
            │
            ├─ 3. prepareBeanFactory()                     ← 配置 BeanFactory
            │     注册 ApplicationContextAware/BeanPostProcessor
            │
            ├─ 4. postProcessBeanFactory()                  ← 子类扩展点（空实现）
            │
            ├─ 5. invokeBeanFactoryPostProcessors()         ← ★ 处理 BeanFactoryPostProcessor
            │     比如 @Configuration 的解析、@MapperScan 扫描
            │     在所有 Bean 实例化前执行
            │
            ├─ 6. registerBeanPostProcessors()             ← ★ 注册 BeanPostProcessor
            │     这些会在 Bean 生命周期的"前后"被调用（见第三章）
            │
            ├─ 7. initMessageSource()                       ← 国际化
            ├─ 8. initApplicationEventMulticaster()        ← 事件广播器
            ├─ 9. onRefresh()                              ← 子类扩展（SpringBoot 在这启动 Tomcat）
            │     SpringBoot 的 ServletWebServerApplicationContext
            │     在这里 createEmbeddedWebServer() → 启动 Tomcat
            │
            ├─ 10. registerListeners()                     ← 注册监听器
            │
            ├─ 11. finishBeanFactoryInitialization()      ← ★★★ 实例化所有非懒加载单例
            │     └─ for each beanDefinition:
            │          getBean(name) → createBean → 完整生命周期（见第三章）
            │     这里是 90% 的启动耗时
            │
            └─ 12. finishRefresh()                         ← 发布 ContextRefreshedEvent
                  通知所有 ApplicationListener：容器就绪了
```

### 关键洞察

```
refresh() 的执行顺序里有几个"分水岭":

  第 5 步之前: BeanDefinition 阶段（只有元信息，还没造对象）
  第 6 步:     BeanPostProcessor 注册好（这是 Bean 生命周期的钩子）
  第 11 步:    才真正造 Bean ← Bean 生命周期的入口

  ┌ 顺序不能错:
  │  必须先注册 BeanPostProcessor（6），再造 Bean（11）
  │  否则 Bean 造出来时没有 PostProcessor 处理，AOP/事务全失效
  │
  └ 这就是为什么 @Configuration 类的 @Bean 方法里拿到的依赖是完整的
     —— 因为 @Configuration 本身在 11 步被实例化时，它依赖的 Bean 也在 11 步实例化
```

---

## 三、Bean 生命周期：9 步调用链

这是 Spring 最核心的知识。一个单例 Bean 从无到有，经历 9 步：

### 完整调用链（以 `getBean("userService")` 为例）

```
getBean("userService")
  │
  ▼
1. getSingleton(name)                        ← 先查缓存，有就直接返回
   │  查 singletonObjects → 有? 返回
   │  查 earlySingletonObjects → 有? 返回
   │  查 singletonFactories → 有? 提前暴露早期引用（循环依赖用）
   │
   │  缓存没有，要新建:
   ▼
2. getMergedBeanDefinition(name)             ← 合并 BeanDefinition
   │  合并父子 BeanDefinition（<bean parent="..."/>）
   ▼
3. createBeanInstance(name)                  ← ① 实例化（调构造方法）
   │  → 推断构造方法（有 @Autowired 构造器优先）
   │  → 反射 newInstance() → 得到"原始对象"（还没注入属性）
   │  → 把 ObjectFactory 放入 singletonFactories（三级缓存，循环依赖用）
   │
   ▼
4. populateBean(name, bean)                  ← ② 属性填充（依赖注入）
   │  → 处理 @Autowired/@Resource
   │  → 对每个依赖，递归调 getBean(dependency)
   │     （这里可能触发循环依赖，见 circular-dependency.md）
   │  → InstantiationAwareBeanPostProcessor.postProcessProperties
   │
   ▼
5. initializeBean(name, bean)               ← 初始化（内部又分 4 小步）
   │
   ├─ 5.1 invokeAwareMethods                 ← ③ Aware 接口回调
   │      BeanNameAware.setBeanName(name)
   │      BeanFactoryAware.setBeanFactory(this)
   │      ApplicationContextAware（由 ApplicationContextAwareProcessor 处理）
   │
   ├─ 5.2 applyBeanPostProcessorsBeforeInitialization  ← ④ 前置处理
   │      BeanPostProcessor.postProcessBeforeInitialization
   │      ← @PostConstruct 在这里被 CommonAnnotationBeanPostProcessor 处理
   │
   ├─ 5.3 invokeInitMethods                  ← ⑤ 初始化方法
   │      InitializingBean.afterPropertiesSet()
   │      custom init-method（<bean init-method="..."/>）
   │
   └─ 5.4 applyBeanPostProcessorsAfterInitialization   ← ⑥ 后置处理
          BeanPostProcessor.postProcessAfterInitialization
          ← ★ AOP 在这里！生成代理对象返回（见 aop.md）
          ← ★ @Async 的代理也在这里加
   │
   ▼
6. 容器持有最终对象                            ← ⑦ 注册到 singletonObjects
   │  注意: 如果第 5.4 步生成了代理，注册的是【代理对象】不是原始对象
   │
   ▼
   （Bean 就绪，可被业务使用）

=== 销毁阶段（容器关闭时）===

7. DisposableBean.destroy()                  ← ⑧ 销毁回调
   │
   ├─ 7.1 @PreDestroy（由 CommonAnnotationBeanPostProcessor 处理）
   ├─ 7.2 DisposableBean.destroy()
   └─ 7.3 custom destroy-method
   │
   ▼
8. 注册的 DestructionAwareBeanPostProcessor   ← ⑨ 销毁前钩子
   postProcessBeforeDestruction
```

### 9 步速记表

| 步 | 阶段 | 方法 | 干什么 |
|----|------|------|--------|
| ① | 实例化 | createBeanInstance | 调构造方法，得原始对象 |
| ② | 属性填充 | populateBean | @Autowired 注入依赖 |
| ③ | Aware 回调 | invokeAwareMethods | 注入容器引用（BeanName/Factory/Context） |
| ④ | 前置处理 | postProcessBeforeInitialization | @PostConstruct |
| ⑤ | 初始化方法 | invokeInitMethods | afterPropertiesSet + init-method |
| ⑥ | 后置处理 | postProcessAfterInitialization | ★ AOP 代理生成 |
| ⑦ | 注册完成 | addSingleton | 放入 singletonObjects |
| ⑧ | 销毁回调 | destroy | @PreDestroy + DisposableBean |
| ⑨ | 销毁前钩子 | postProcessBeforeDestruction | 资源清理 |

---

## 四、每一步的扩展点与设计模式

### 4.1 BeanPostProcessor：贯穿生命周期的"钩子"

```
BeanPostProcessor 是 Spring 最核心的扩展点，它在第 ④⑥ 步出现:

  ④ postProcessBeforeInitialization   ← 初始化前
  ⑥ postProcessAfterInitialization    ← 初始化后（AOP 代理生成点）

Spring 内置大量 BeanPostProcessor:

  ┌ CommonAnnotationBeanPostProcessor
  │   处理 @PostConstruct / @PreDestroy / @Resource
  │
  ┌ AutowiredAnnotationBeanPostProcessor
  │   处理 @Autowired / @Value（在第 ② 步 populateBean 里）
  │
  ┌ ApplicationContextAwareProcessor
  │   处理 ApplicationContextAware 等 Aware 接口（第 ③ 步）
  │
  ┌ ConfigurationClassPostProcessor
  │   处理 @Configuration/@Bean/@ComponentScan（在 refresh 第 5 步）
  │
  ┌ AbstractAutoProxyCreator（AOP 的核心）
  │   在第 ⑥ 步决定是否生成代理，生成什么代理（见 aop.md）
  └
```

### 4.2 BeanDefinition：建造者模式 + 注册表模式

```java
// BeanDefinition = Bean 的"图纸"（建造者模式产物）
BeanDefinition bd = new RootBeanDefinition();
bd.setBeanClassName("com.example.UserService");
bd.setScope("singleton");
bd.setInitMethodName("init");
bd.setLazyInit(false);

// BeanDefinitionRegistry = 注册表模式
registry.registerBeanDefinition("userService", bd);
```

> **设计模式**：建造者模式（一步步组装 BeanDefinition）、注册表模式（beanDefinitionMap）。

### 4.3 FactoryBean：工厂方法模式

```java
// FactoryBean 本身就是工厂方法模式的体现
@Component
public class MyFactoryBean implements FactoryBean<Connection> {
    @Override
    public Connection getObject() {
        // 工厂方法：决定造什么、怎么造
        return createConnection();
    }
    @Override
    public Class<?> getObjectType() {
        return Connection.class;
    }
}

// getBean("myFactoryBean") → 返回 Connection（工厂产物）
// getBean("&myFactoryBean") → 返回 MyFactoryBean 本身（工厂本身）
```

> **设计模式**：工厂方法模式。MyBatis 的 `MapperFactoryBean` 就是这个，把接口代理成 Bean。

### 4.4 Aware 接口：回调模式

```java
// 让 Bean "感知"容器，靠实现接口被动接收
@Component
public class MyBean implements BeanNameAware, ApplicationContextAware {
    @Override
    public void setBeanName(String name) {
        // 容器在第 ③ 步回调这个方法
        // 不需要 Bean 主动去找容器，是容器"推"过来
    }
    @Override
    public void setApplicationContext(ApplicationContext ctx) {
        // 由 ApplicationContextAwareProcessor 在第 ③ 步处理
    }
}
```

> **设计模式**：回调模式（控制反转——Bean 不主动获取容器，而是被注入）。

### 4.5 InitializingBean：模板方法模式

```java
// Spring 定义了初始化的"骨架"，Bean 填空
public interface InitializingBean {
    void afterPropertiesSet();  // Bean 自己实现这个方法
}

// AbstractAutowireCapableBeanFactory.invokeInitMethods 是模板:
//   if (bean instanceof InitializingBean) bean.afterPropertiesSet();
//   if (init-method 配了) 反射调 init-method;
//   ← 顺序固定，这就是模板方法
```

> **设计模式**：模板方法模式（Spring 定流程，Bean 填空）。

### 4.6 @PostConstruct vs InitializingBean vs init-method

三个都做初始化，**执行顺序固定**：

```
① @PostConstruct                    （CommonAnnotationBeanPostProcessor 处理，第 ④ 步）
② InitializingBean.afterPropertiesSet()  （第 ⑤ 步）
③ <bean init-method="init"/>        （第 ⑤ 步，在 afterPropertiesSet 之后）

为什么 @PostConstruct 在前?
  它在 postProcessBeforeInitialization（第 ④ 步）
  afterPropertiesSet 在 invokeInitMethods（第 ⑤ 步）
  第 ④ 步在第 ⑤ 步之前
```

### 4.7 作用域与 Map 缓存

```
singleton:  全容器唯一，缓存在 singletonObjects（Map）
prototype:  每次 getBean 新建，不缓存
request:    每个 HTTP 请求一个，缓存在 RequestScope（ThreadLocal + Map）
session:    每个 Session 一个，缓存在 SessionScope

→ 都是"Map + 生命周期"的组合
```

---

## 五、能学到什么

### 5.1 工程哲学：用 Map + 流程造一切

```
IoC 容器 = ConcurrentHashMap + 一套创建流程
Bean 生命周期 = 反射 + 回调 + 责任链（PostProcessor）

  ┌ 你不需要复杂的数据结构就能造一个工业级容器
  │  Spring 全程最高级的数据结构就是 ConcurrentHashMap 和三层 Map
  │
  └ 复杂度藏在"流程"里：什么时候注册、什么时候实例化、
     什么时候暴露早期引用——这是"调用编排"的功力，不是数据结构的功力
```

### 5.2 设计模式的实战范本

```
Spring 是设计模式教科书:

  ┌ 单例模式      → singleton 作用域 + singletonObjects 缓存
  ┌ 工厂方法模式  → FactoryBean
  ┌ 建造者模式    → BeanDefinition
  ┌ 模板方法模式  → InitializingBean / refresh() 骨架
  ┌ 观察者模式    → ApplicationEvent + ApplicationListener
  ┌ 责任链模式    → BeanPostProcessor 链
  ┌ 适配器模式    → HandlerAdapter（MVC）
  ┌ 装饰器模式    → BeanWrapper
  ┌ 策略模式      → 代理选择（JDK vs CGLIB）、作用域实现

  → 一个框架把 23 种设计模式用了大半，学 Spring = 学设计模式实战
```

### 5.3 "扩展点优先"的架构思想

```
Spring 几乎不写死流程，而是留扩展点:

  BeanFactoryPostProcessor → 改 BeanDefinition（建对象前）
  BeanPostProcessor         → 改 Bean 实例（建对象前后）
  SmartInitializingSingleton → 所有单例建完后

  ┌ 对比 Tomcat: Tomcat 也留 Valve/Pipeline 扩展点
  │  和 Spring 的 PostProcessor 是同一种思想
  │  → "框架定骨架，业务填血肉"是工业级框架的共性
  │
  └ 这就是为什么 Spring 能集成一切
     MyBatis、Dubbo、Redis 都只是往 Spring 塞 PostProcessor
```

### 5.4 生命周期思维：理解"对象怎么长大"

```
普通 new:  new UserService()  → 一步到位
Spring:    实例化 → 注入 → Aware → 前置 → 初始化 → 后置 → 注册
            │       │       │       │        │        │
            原始对象 此时才能用容器 此时能改初始化 此时能换代理

  ┌ 为什么拆这么细?
  │  每一步都可能被扩展点拦截、修改
  │  → AOP 在"后置"换代理
  │  → @Autowired 在"注入"递归拿依赖
  │  → @PostConstruct 在"前置"做初始化
  │
  └ 把"造对象"拆成流水线，每道工序可插拔
     这是 Spring 应对复杂度的核心手法
```

### 5.5 缓存分级的思维（为下一章铺垫）

```
singletonObjects + earlySingletonObjects + singletonFactories
  → 三级缓存不是过度设计，是为解决循环依赖

  为什么不直接放一级?
    一级放"完整对象"，但造对象的过程里需要暴露"半成品"
    → 半成品不能进完整对象缓存（会污染）
    → 单独开二级存早期引用，三级存工厂

  → 这是"分层缓存"思想，下一章 circular-dependency.md 详讲
```

---

## 与其他笔记的串联

```
→ circular-dependency.md
    本章 Bean 生命周期的"② 属性填充"会触发循环依赖
    三级缓存就是为破解它而生

→ aop.md
    本章 Bean 生命周期的"⑥ 后置处理"是 AOP 代理的生成点
    理解了 Bean 怎么造，才知道代理是"哪一步"换上去的

→ transaction.md
    @Transactional 靠 AOP 代理
    代理在 ⑥ 步生成，所以"没代理就没事务"

→ connection-pool/pool-analysis.md
    Bean 生命周期里的 BeanPostProcessor 链 = 责任链模式
    和 Netty 的 Pipeline 是同一种设计

→ netty/pipeline.md
    Netty Pipeline 责任链 vs Spring BeanPostProcessor 责任链
    两种工业级框架都用责任链做扩展
```
