# 三级缓存破解循环依赖

> 循环依赖是 Spring 最经典、也最容易被问倒的设计。
> 本文聚焦：循环依赖是什么、为什么需要三级缓存、getSingleton 完整调用链、为什么构造器循环依赖无解、涉及的设计模式、能学到什么。

---

## 目录

1. [循环依赖是什么](#一循环依赖是什么)
2. [为什么一级缓存解决不了](#二为什么一级缓存解决不了)
3. [三级缓存的结构与职责](#三三级缓存的结构与职责)
4. [getSingleton 完整调用链](#四getsingleton-完整调用链)
5. [构造器循环依赖为什么无解](#五构造器循环依赖为什么无解)
6. [涉及的设计模式](#六涉及的设计模式)
7. [能学到什么](#七能学到什么)

---

## 一、循环依赖是什么

```
A 依赖 B，B 又依赖 A:

  @Component
  class A {
      @Autowired B b;   // A 的创建需要 B
  }
  @Component
  class B {
      @Autowired A a;   // B 的创建需要 A
  }

死锁式悖论:
  造 A → 需要 B → 造 B → 需要 A → 造 A → 需要 B → ...
  → 看似无限循环
```

### Spring 能解决哪些循环依赖

```
┌──────────────────────┬──────────────────────────┐
│ 循环依赖类型          │ Spring 能否解决           │
├──────────────────────┼──────────────────────────┤
│ 字段注入循环          │ ✅ 能（三级缓存）          │
│ (A 的 B 是字段)       │                          │
├──────────────────────┼──────────────────────────┤
│ setter 注入循环       │ ✅ 能（同字段）            │
├──────────────────────┼──────────────────────────┤
│ 构造器注入循环        │ ❌ 不能（见第五章）        │
│ (A 的 B 是构造参数)   │                          │
├──────────────────────┼──────────────────────────┤
│ prototype 作用域循环  │ ❌ 不能（不缓存，每次新建）  │
└──────────────────────┴──────────────────────────┘

  本章只讲【字段/setter 注入循环】的解决。
```

---

## 二、为什么一级缓存解决不了

### 假设只有一级缓存 singletonObjects

```
singletonObjects: Map<Bean名, 完整对象>

造 A 的流程:
  1. getBean("A") → 缓存没有
  2. createBeanInstance("A") → 反射 new A() → 原始对象 a
  3. populateBean("A", a) → 发现要注入 B → getBean("B")
       3.1 createBeanInstance("B") → new B() → 原始对象 b
       3.2 populateBean("B", b) → 发现要注入 A → getBean("A")
            3.2.1 缓存没有 A（A 还在造！没放进缓存）
            3.2.2 又要造 A → 死循环 / 抛 BeanCurrentlyInCreationException
```

### 问题根源

```
A 在"属性填充"阶段（第 ② 步）需要 B
  → A 此时尚未完成（没到第 ⑦ 步注册到 singletonObjects）
  → B 找 A 时，缓存里没有 → 又要造 A → 死循环

  关键: 对象的"实例化"和"完整可用"是两个时间点
       实例化后、完整前，这个时间段的对象需要被别人引用
```

### 朴素解法：实例化后就放缓存

```
思路: 第 ② 步前就把 A 放进 singletonObjects
  → B 找 A 时能从缓存拿到"半成品 A"

问题: singletonObjects 是【完整对象】缓存
  半成品 A 放进去，别人拿到的是没填完属性的 A
  → 用到 A.b 时 NPE（b 还是 null）

  → 不能让半成品污染完整缓存
```

---

## 三、三级缓存的结构与职责

Spring 用**三级缓存**把"半成品"和"成品"分开存：

```java
public class DefaultSingletonBeanRegistry {

    // 一级缓存：完整的单例（属性都填好了）
    private final Map<String, Object> singletonObjects
        = new ConcurrentHashMap<>(256);

    // 二级缓存：早期引用（实例化完，但属性还没填）
    private final Map<String, Object> earlySingletonObjects
        = new HashMap<>(16);

    // 三级缓存：对象工厂（能产出早期引用）
    private final Map<String, ObjectFactory<?>> singletonFactories
        = new HashMap<>(16);

    // 正在创建中的 Bean 名（用于检测循环依赖）
    private final Set<String> singletonsCurrentlyInCreation
        = Collections.newSetFromMap(new ConcurrentHashMap<>(16));
}
```

### 三级缓存的职责

```
一级 singletonObjects:
  ┌ 存什么: 完整对象（属性填充完 + 初始化完 + 可能被代理）
  └ 谁来读: 业务 getBean 时直接命中，所有"正常"拿 Bean 的地方

二级 earlySingletonObjects:
  ┌ 存什么: 早期引用（实例化完，属性没填）
  └ 谁来读: 循环依赖发生时，B 找 A 的早期引用
           （一级没有 A，因为 A 还没造完）

三级 singletonFactories:
  ┌ 存什么: ObjectFactory（一个 lambda，调它才产出早期引用）
  └ 谁来读: B 找 A 时，三级存着 A 的工厂
           调工厂.getObject() → 产出 A 的早期引用
           → 提升到二级，三级移除

为什么三级不是直接存对象?
  因为 A 可能被 AOP 代理，"早期引用"应该是【代理对象】而非原始对象
  → 用 ObjectFactory 延迟到真正需要时才决定产不产代理
  → 保证: 循环依赖里 B 拿到的 A，和最终容器里的 A 是同一个（都是代理）
```

#### 为什么不能用二级缓存？—— ObjectFactory 的不可替代性

```
只有二级缓存（直接存原始对象）会发生什么?

  假设 A 配了 @Transactional（需要 AOP 代理），A 与 B 循环依赖:

  1. 实例化 A → 原始对象 a → earlySingletonObjects.put("A", a)
  2. populateBean(A) → 注入 B → 触发造 B
  3. 造 B → populateBean(B) → 注入 A → 查二级缓存
     → 拿到【原始对象 a】（未代理！）
     → b.a = a   ← B 持有的是没事务切面的原始 A
  4. A 初始化完成 → postProcessAfterInitialization 生成代理 proxyA
     → singletonObjects.put("A", proxyA)

  最终状态:
    B 持有的 a  = 原始对象（无事务切面）
    容器里的 A  = proxyA（有事务切面）
    → 不一致 ❌
    → B 调 a.transfer() 不经过代理 → @Transactional 失效！

  → 核心矛盾: 二级缓存存的是"实例化后的原始对象"
     但正常流程里代理在"初始化之后"才生成
     循环依赖逼着 A 在"生成代理前"被 B 引用
     → B 永远拿到未代理的原始对象


三级缓存（存 ObjectFactory）怎么解决?

  1. 实例化 A → 原始对象 a → singletonFactories.put("A", () -> getEarlyBeanReference("A", a))
     ← 存 lambda，不是 a 本身
  2. B 找 A → 查三级 → 调工厂.getObject()
     → getEarlyBeanReference("A", a) 内部判断:
         需要 AOP → wrapIfNecessary → 生成 proxyA 返回
         不需要   → 返回原始 a
     → B 拿到的是【proxyA（代理）】
  3. proxyA 提升到二级，三级移除
  4. A 初始化完成 → postProcessAfterInitialization
     → 检查 earlyProxyReferences 有 A → 已代理过 → 不重复生成
     → singletonObjects.put("A", proxyA)

  最终状态:
    B 持有的 proxyA == 容器里的 proxyA
    → 一致 ✅ → @Transactional 生效


ObjectFactory 的两个不可替代价值:

  价值 1 · 延迟决策
  ┌ 实例化后立即生成代理（存代理到二级）:
  │   → 每个 Bean 都 wrapIfNecessary，即使没循环依赖 → 浪费
  └ 用工厂延迟:
      → 只有循环依赖真发生才调工厂生成代理
      → 没循环依赖，工厂永不调用，走正常流程

  价值 2 · 一致性记录
  ┌ getEarlyBeanReference 内部:
  │   earlyProxyReferences.put("A", a)   ← 记录"已提前代理"
  └ 之后 postProcessAfterInitialization 检查该集合:
      → 发现已代理 → 不重复生成
      → 保证 B 拿到的代理 == 容器里的代理

一句话: 三级缓存不是"多存一层"的冗余，
        而是"用工厂替代对象"来封装【该不该代理 + 代理一次的记录】。
```

#### 追问：那"二级缓存阶段就提前生成一次代理"不行吗？

> 常见追问："既然问题是代理不一致，那在二级缓存阶段就生成一次代理，存代理对象，不就用不上三级了吗？"
> 答案：**技术上完全可行，最终结果也一致**。Spring 不用它，不在"能不能"，而在"该不该对所有 Bean 都这么做"。

```
你的方案（实例化后立即代理，存二级）:
═══════════════════════════════════════

  实例化 A → 原始 a
  → 立即 wrapIfNecessary(a) → proxyA      ← 无条件提前代理
  → earlySingletonObjects.put("A", proxyA)
  → populateBean(a) 填充 a
  → initMethod(a)
  → postProcessAfterInitialization 发现已代理 → 跳过
  → 一级缓存放 proxyA

  结果: B 拿到 proxyA == 容器里的 proxyA ✅ 一致！


Spring 方案（ObjectFactory 延迟，存三级）:
═══════════════════════════════════════

  实例化 A → 原始 a
  → singletonFactories.put("A", () -> wrapIfNecessary(a))   ← 存工厂，不立即代理
  → populateBean(a) → 要 B → 造 B → B 要 A
    → 调工厂 → wrapIfNecessary(a) → proxyA   ← 这时才代理
    → proxyA 提升二级
  → initMethod(a)
  → postProcessAfterInitialization 发现已代理 → 跳过
  → 一级缓存放 proxyA

  结果: B 拿到 proxyA == 容器里的 proxyA ✅ 一致！
```

**两个方案最终结果完全一样**——proxyA 唯一，B 拿到的一致。区别只有一点：**"立即代理"让【所有 Bean】都提前代理，"延迟"只让【循环依赖的 Bean】提前代理。**

```
问题 1 · 代理包裹的应该是"完整对象"，不是"半成品"
═══════════════════════════════════════

  Spring 约定: 代理在"初始化完成后"生成（postProcessAfterInitialization）

  实例化后（你的方案代理时机）:
    原始 a 只有构造器跑完
    @Autowired 依赖还没注入（populateBean 还没跑）
    @PostConstruct 初始化还没做

  初始化后（Spring 代理时机）:
    a 的依赖注入了，a 的 @PostConstruct 跑完了
    → 此时代理包裹的是"能正常工作的完整对象"

  如果实例化后立即代理:
    代理包裹的是"半成品 a"
    → 虽然 JDK 代理持有 a 引用、最终 a 会被填充
      但"在 a 还没填充完就生成代理"语义上是"代理半成品"

问题 2 · 你的方案会让"没循环依赖的 Bean"也提前代理
═══════════════════════════════════════

  你的方案: 实例化后【立即】生成代理
    → 每个 Bean（不管有没有循环依赖）都要立即 wrapIfNecessary
    → 100 个 Bean，100 个都提前代理

  Spring 方案: 存工厂，循环依赖发生时【才】调工厂
    → 只有卷入循环依赖的 Bean 才提前代理
    → 100 个 Bean，可能只有 2 个提前代理，98 个走正常流程

  ┌ 循环依赖是"罕见场景"
  │  绝大多数 Bean 不循环依赖
  │  → 你的方案让 100% 的 Bean 都改变代理时机
  │  → Spring 方案只让少数 Bean 改变代理时机
  │
  └ 这就是 ObjectFactory 的"延迟"价值:
     不是"能不能提前代理"（能）
     而是"该不该让所有 Bean 都提前代理"（不该）
```

**一句话**：三级缓存的本质是"按需提前"。

```
没有三级缓存（你的方案）:
  提前代理是【无条件】的 → 所有 Bean 都提前代理 → 违反"代理完整对象"约定

有三级缓存（Spring 方案）:
  提前代理是【有条件】的 → 只有循环依赖真正发生，工厂才被调用
  → 正常 Bean 不受影响，走"初始化后代理"的常规流程

类比:
  你的方案    = 所有学生都提前交卷（大部分不需要，且交的是没写完的卷子）
  Spring 方案 = 只让确实要提前的学生提前交，且记录"已交"防重复
```

### 三级缓存配合的"标记位"

```
singletonsCurrentlyInCreation（正在创建的集合）:

  造 A 之前: singletonsCurrentlyInCreation.add("A")
  造 A 之后: singletonsCurrentlyInCreation.remove("A")

  作用: 在 getSingleton 时判断
    if (singletonsCurrentlyInCreation.contains(name)):
        → 这是循环依赖！去二三缓存放早期引用
    else:
        → 正常创建

  → 没有"标记位"，无法区分"该新建"和"该拿早期引用"
```

---

## 四、getSingleton 完整调用链

这是破解循环依赖的核心方法。以 A 依赖 B、B 依赖 A 为例：

### 完整调用链（A 和 B 的视角交错）

```
=== 第一阶段：开始造 A ===

getBean("A")
  │
  ▼
getSingleton("A")                                  ← 入口
  │
  ├─ 查一级 singletonObjects.get("A") = null
  ├─ 查二级 earlySingletonObjects.get("A") = null
  ├─ 查三级 singletonFactories.get("A") = null
  │   （A 还没开始造，三缓存都没有）
  │
  ├─ 标记 A 正在创建: singletonsCurrentlyInCreation.add("A")
  │
  ▼
createBean("A")
  │
  ├─ createBeanInstance("A")                        ← 实例化
  │   new A() → 原始对象 a
  │
  ├─ 把 A 的工厂放入三级缓存                          ★ 关键
  │   singletonFactories.put("A",
  │       () -> getEarlyBeanReference("A", a))
  │   ← 这个 ObjectFactory 决定: 是否要返回代理
  │
  ▼
populateBean("A", a)                                ← 属性填充
  │   发现 @Autowired B → 调 getBean("B")
  │
  │   ╔═══════════════════════════════════════╗
  │   ║  下面进入 B 的创建（嵌套）              ║
  │   ╚═══════════════════════════════════════╝
  │
  ▼
getBean("B")
  │
  ▼
getSingleton("B")
  │
  ├─ 查一级 singletonObjects.get("B") = null
  ├─ 查二级 earlySingletonObjects.get("B") = null
  ├─ 查三级 singletonFactories.get("B") = null
  ├─ 标记 B 正在创建
  │
  ▼
createBean("B")
  ├─ createBeanInstance("B") → new B() → b
  ├─ singletonFactories.put("B", () -> getEarlyBeanReference("B", b))  ★
  │
  ▼
populateBean("B", b)
  │   发现 @Autowired A → 调 getBean("A")          ★★★ 循环点
  │
  │   ╔═══════════════════════════════════════╗
  │   ║  这里要拿 A，但 A 还在造！              ║
  │   ╚═══════════════════════════════════════╝
  │
  ▼
getSingleton("A")                                   ← 第二次查 A
  │
  ├─ 查一级 singletonObjects.get("A") = null       （A 没造完）
  ├─ 查二级 earlySingletonObjects.get("A") = null
  ├─ 查三级 singletonFactories.get("A") = 有!       ★ 命中三级
  │   │
  │   ▼
  │   singletonFactories.remove("A").getObject()    ← 调工厂产出早期引用
  │   │   ↑ 这里调 getEarlyBeanReference
  │   │     └─ 如果 A 配了 AOP，这里生成代理对象并返回
  │   │        否则返回原始对象 a
  │   │
  │   ├─ 把早期引用放入二级: earlySingletonObjects.put("A", earlyA)
  │   └─ 三级移除: singletonFactories.remove("A")
  │
  └─ 返回 earlyA                                     ← B 拿到了 A 的早期引用!
  │
  ▼
b.a = earlyA                                        ← B 的 a 字段填上
  │
  ▼
initializeBean("B", b)                               ← B 的初始化
  │   （如果 B 有 AOP，这里生成 B 的代理对象 proxyB）
  │
  ▼
singletonObjects.put("B", proxyB 或 b)               ← B 进一级缓存
earlySingletonObjects.remove("B"); singletonFactories.remove("B")
  │
  ▼
返回 proxyB 给 A 的 populateBean
  │
  ▼
a.b = proxyB                                         ← A 的 b 字段填上
  │
  ▼
initializeBean("A", a)                               ← A 的初始化
  │
  ▼
singletonObjects.put("A", earlyA 或 proxyA)          ← A 进一级缓存
  │   ↑ 注意: 如果早期已经生成过代理（三级缓存命中时）
  │     这里注册的就是【同一个代理对象】，不会重新生成
  │
  ▼
返回 A 给调用方
```

### 关键洞察：早期引用的一致性

```
循环依赖里最微妙的一点:

  B 拿到 A 的早期引用时（三级缓存命中）:
    → 如果 A 需要 AOP 代理，getEarlyBeanReference 生成 proxyA
    → B 的 a 字段 = proxyA

  A 自己初始化完成时:
    → AbstractAutoProxyCreator 发现"早期已经代理过"（记录在 earlyProxyReferences）
    → 不再重复生成代理
    → 注册到一级缓存的也是 proxyA

  ┌ 保证: B 持有的 A 和容器里最终的 A 是【同一个对象】
  │  → 否则 B 拿原始 A，容器里是代理 A，事务/切面就对 B 失效
  │
  └ 这就是为什么必须用 ObjectFactory（三级缓存）而不是直接存对象
     延迟到"真正需要时"才决定代理与否，并记录这个决定
```

---

## 五、构造器循环依赖为什么无解

### 字段循环依赖能解的本质

```
字段循环: new A() 先造出原始对象（构造器不需要 B）
         → 再 @Autowired 填 B
         → 填 B 时可以暴露 A 的早期引用（因为 A 已经 new 出来了）

  关键: "实例化"和"依赖注入"是分开的两步
        实例化不需要依赖，依赖在实例化后才填
        → 所以能在"实例化后、填依赖前"暴露早期引用
```

### 构造器循环依赖的死结

```
构造器循环: A 的构造方法参数是 B

  class A {
      A(B b) { ... }   // 构造 A 必须先有 B
  }
  class B {
      B(A a) { ... }   // 构造 B 必须先有 A
  }

造 A 的流程:
  createBeanInstance("A")
    → 推断构造方法: A(B)
    → 要调 new A(b)，但 b 还没有 → getBean("B")
      → 造 B: 推断构造方法 B(A)
      → 要调 new B(a)，但 a 还没有 → getBean("A")
        → A 在创建中（singletonsCurrentlyInCreation 有 A）
        → 查二三缓存 → 都没有
           （A 还没 new 出来，连原始对象都没有，哪来的早期引用）
        → 抛 BeanCurrentlyInCreationException ❌

  死结:
    A 的 new 需要 B 的 new，B 的 new 需要 A 的 new
    → 谁也无法先 new 出来 → 无法暴露早期引用 → 无解
```

### 三级缓存为什么救不了构造器循环

```
三级缓存的暴露点: createBeanInstance 之后、populateBean 之前

  createBeanInstance ─────► [暴露早期引用到三级]
                              │
                              ▼
  populateBean ─────────────► 这里才需要依赖

  构造器循环的问题: 依赖在 createBeanInstance 【之前】就要（构造参数）
                    还没到暴露点就需要依赖 → 三级缓存还没来得及放 → 无解

  字段循环: 依赖在 populateBean（暴露点之后）才需要 → 三级缓存已有 → 能解
```

### 解决方案：改用字段/setter 注入

```
把构造器循环改成字段循环:

  @Component
  class A {
      @Autowired
      private B b;          // 改成字段，构造器不需要 B
      public A() {}          // 无参构造
  }

  @Component
  class B {
      @Autowired
      private A a;
      public B() {}
  }

  → Spring 能解决（走三级缓存）
  → 这也是为什么 Spring 官方虽推荐构造器注入，
     但循环依赖场景下不得不回退到字段注入
```

---

## 六、涉及的设计模式

### 6.1 对象工厂模式（ObjectFactory）

```java
@FunctionalInterface
public interface ObjectFactory<T> {
    T getObject() throws BeansException;
}

// 三级缓存存的就是 ObjectFactory
singletonFactories.put("A", () -> getEarlyBeanReference("A", a));
```

> **模式**：工厂模式 + 延迟初始化。把"产出对象"这个动作封装起来，等到真正需要时才执行。这就是为什么三级缓存能"延迟决定是否代理"。

### 6.2 备忘录模式 / 缓存快照

```
三级缓存本质是"对象在不同创建阶段的快照":

  三级 singletonFactories     → "工厂态"快照（还没产出）
  二级 earlySingletonObjects  → "半成品态"快照（实例化完，属性没填）
  一级 singletonObjects       → "成品态"快照（完整可用）

  → 把对象生命周期的不同阶段缓存下来
     这是"渐进式缓存"思想
```

### 6.3 标记位 + 状态机

```
singletonsCurrentlyInCreation 是个状态标记:

  未创建 → 创建中（入集合）→ 创建完（出集合）

  getSingleton 时根据"是否在创建中"决定:
    在创建中 → 这是循环依赖，去拿早期引用
    不在创建中 → 正常创建

  → 用集合模拟状态机，这是并发场景下常见的做法
```

### 6.4 提前暴露（Early Exposure）

```
这不是 GoF 模式，但是 Spring 独创的工程手法:

  在对象"还没完成"时就暴露它的引用
  前提: 暴露的是【安全的部分】（实例化完的部分）
  风险: 拿到半成品的人不能用未完成的部分

  Spring 的保证: 只让循环依赖内部拿早期引用
                 不让普通 getBean 拿到半成品
  → 通过 singletonsCurrentlyInCreation 隔离
```

---

## 七、能学到什么

### 7.1 "分阶段缓存"思想

```
不要一个缓存搞定所有事:

  ┌ 一级: 成品（正常读）
  ┌ 二级: 半成品（循环依赖读）
  ┌ 三级: 工厂（决定怎么产半成品）

  每级解决一个特定问题:
    一级 → 性能（命中直接返回）
    二级 → 隔离（半成品不污染成品）
    三级 → 延迟（代理与否延后决定）

  ┌ 类比 CPU 多级缓存:
  │  L1/L2/L3 不是冗余，是不同速度/容量的权衡
  │  Spring 三级缓存也不是冗余，是不同"成熟度"的隔离
  │
  └ 工程上"一个 Map 搞定"往往不够，
     复杂场景需要"分阶段、分职责"的多级缓存
```

### 7.2 "延迟决策"的威力

```
三级缓存用 ObjectFactory 而不是直接存对象:

  立即决策（直接存对象）:
    → 创建时就决定是否代理
    → 但循环依赖还没发生，不知道会不会发生
    → 万一不发生，白白生成代理，浪费

  延迟决策（存工厂）:
    → 只有真正被循环依赖找到时，才调工厂
    → 此时已知 A 是否需要代理（getEarlyBeanReference 判断）
    → 按需生成，且记录决定，保证一致性

  ┌ 这是"懒求值"思想:
  │  能推迟的决定就推迟
  │  到最后一刻信息最全，决策最优
  │
  └ 类比: 跳表的 randomLevel() 也是延迟到插入时才决定层数
     Spring 的 ObjectFactory 也是延迟到循环发生才决定代理
```

### 7.3 "一致性"问题的工程处理

```
循环依赖最难的点: 保证"B 拿到的 A" 和 "容器里的 A" 是同一个

  朴素方案会出 bug:
    B 拿原始 A，容器里是代理 A
    → B 调 a.method() 走原始方法，绕过 AOP
    → 事务、日志、权限全失效

  Spring 的解法: 早期引用生成时记录决定
    earlyProxyReferences 记录"这个 Bean 已经代理过"
    → 后续 initializeBean 不再重复代理
    → 保证全局唯一

  ┌ 工程教训: 涉及"同一个对象"的场景，必须显式管理"对象的身份"
  │  不能多次 new / 多次代理
  │  用"标记 + 记录"保证唯一性
  │
  └ 类似并查集的"代表元": 一个集合只有一个根
     Spring 一个 Bean 只有一个最终对象（原始或代理，二选一）
```

### 7.4 "什么能解，什么不能解"的边界意识

```
Spring 明确告知: 构造器循环依赖无解

  ┌ 为什么不强行解?
  │  因为它违反了"实例化"和"依赖注入"的分离
  │  构造器循环把依赖绑死在实例化里，没有暴露点
  │
  └ 工程教训: 有些问题不是"更聪明的算法"能解的
     是"约束本身不允许"
     → 解法是【改变约束】（构造器改字段），而不是硬解

  这和"并查集构造器循环依赖"一样:
    某些动态连通性问题，并查集解不了，要换数据结构
    → 认清工具的能力边界
```

### 7.5 调试循环依赖的思路

```
实战中遇到循环依赖报错:

  BeanCurrentlyInCreationException
  → 看是不是构造器注入 → 改字段注入

  没报错但 Bean 不完整（属性 null）
  → 可能是三级缓存的早期引用被错误使用
  → 检查有没有在 @PostConstruct 里用了还没注入的依赖

  @Async + 循环依赖报错
  → @Async 代理在第六步生成
  → 和循环依赖的早期代理冲突
  → 解法: 用 @Lazy 打破循环

  → 认识生命周期 + 认识缓存分层 = 能定位任何"Bean 不完整"问题
```

---

## 与其他笔记的串联

```
→ ioc-container.md
    本章承接第三章 Bean 生命周期
    "② 属性填充"就是触发循环依赖的点

→ aop.md
    三级缓存的 getEarlyBeanReference 决定是否代理
    → 理解了循环依赖，才懂 AOP 代理"哪一步生成"

→ transaction.md
    @Transactional 也是 AOP 代理
    → 如果 Bean 卷入循环依赖，代理生成时机影响事务
    → 所以 @Transactional + 循环依赖 有坑

→ connection-pool/pool-analysis.md
    三级缓存 = 多级缓存思想
    HikariCP 的 availableConnections + activeConnections 也是分级
    → 都是"分职责缓存"的工程手法

→ algorithms/union-find.md
    并查集的"代表元唯一" vs Spring 的"Bean 最终对象唯一"
    → 都要保证"一个逻辑实体对应一个物理对象"
```
