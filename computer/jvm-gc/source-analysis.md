# Java GC 底层源码剖析

> 本文聚焦两个核心问题：
> 1. **什么时候一个对象被认为可以回收？**（可达性分析、引用类型、Finalizer 干扰）
> 2. **什么时候触发 GC？**（内存分配失败、JVM 内部触发、外部调用、Young GC vs Full GC）

---

## 目录

1. [对象何时可以被回收](#一对象何时可以被回收)
2. [触发 GC 的所有条件](#二触发-gc-的所有条件)
3. [GC 源码剖析](#三gc-源码剖析)
4. [总结与实战建议](#四总结与实战建议)

---

## 一、对象何时可以被回收

### 1.1 可达性分析：判断"垃圾"的官方标准

JVM 判断一个对象是否存活，使用的是 **可达性分析（Reachability Analysis）**，不是引用计数。

```
可达性分析的原理：

  从一组"GC Roots"开始，沿着引用链向下搜索
  能到达的对象 → 存活
  不能到达的对象 → 可回收（垃圾）
```

**GC Roots 包括哪些对象？**

> **⚠️ 常见误区：GC Roots 不是 main() 方法，也不是某个特定方法。**
> **GC Roots 是"当前时刻，所有正在运行的线程栈帧 + 全局状态"中的存活引用集合。**

```java
GC Roots 集合（代码层面）:
├── 所有线程栈帧中引用的对象（局部变量、方法参数、操作数栈）
├── 方法区中类静态属性引用的对象
├── 方法区中常量引用的对象
├── 本地方法栈中 JNI 全局引用的对象
└── 被同步锁（synchronized）持有的对象
```

#### GC Roots ≠ main() 方法

```
❌ 错误理解：
   main() 方法是 GC Roots 的起点，从 main() 开始找引用链

✅ 正确理解：
   GC Roots 是"当前时刻，所有正在运行的线程栈帧 + 全局状态"
   中的存活引用。main() 中的局部变量只是其中的一部分。

   即使没有 main() 方法（比如 Applet 环境），
   只要线程在运行，栈帧中的引用就是 GC Root。
```

#### 用多线程视角看 GC Roots

```java
public class GCRootExample {

    // ① 静态变量：方法区中的引用 → GC Root
    public static Object root;

    public static void main(String[] args) {
        // ② main 线程栈帧中的局部变量
        root = new Object();        // root 引用（方法区）+ 栈帧引用 → GC Root ✅

        Object local = new Object(); // ③ 只有 main 栈帧引用 → GC Root ✅

        doSomething(local);          // ④ 调用中，local 还在 main 栈帧
                                     //    同时 doSomething 栈帧有 param 副本 → GC Root ✅

        local = null;                // ⑤ local 断开
        // 下次 GC：③ 的对象不可达 → 可回收

        root = null;                 // ⑥ 静态变量断开
        // 下次 GC：① 的对象不可达 → 可回收

        // 启动另一个线程
        new Thread(() -> {
            // ⑦ 子线程栈帧中的引用也是 GC Root
            Object inOtherThread = new Object();  // ← GC Root ✅
            System.out.println("other thread");
        }).start();
        // 即使 main() 返回，子线程还在运行
        // inOtherThread 仍然是 GC Root

        // main() 执行完，main 栈帧弹出
        // main 栈帧中的所有引用消失
        // 但其他线程的栈帧仍在 → 那些线程的引用仍然是 GC Root
    }

    static void doSomething(Object param) {
        // ④ param 在 doSomething 栈帧中 → GC Root ✅
        // 只要 doSomething 还没返回，param 指向的对象就一定存活
        System.out.println("doing...");
        // doSomething 返回后，param 出栈，不再可达
    }
}
```

**GC Roots 的关键特征**：

```
┌──────────────────────────────────────────────────────────┐
│                                                          │
│  GC Roots 不是一个"起点方法"                                │
│  而是"所有存活引用的快照"                                   │
│                                                          │
│  GC 触发那一刻:                                            │
│    所有线程正在执行的栈帧                                   │
│    + 所有已加载类的静态字段                                 │
│    + 所有 JNI 全局引用                                    │
│    + 所有锁持有的对象                                     │
│                                                          │
│  = GC Roots                                              │
│                                                          │
└──────────────────────────────────────────────────────────┘
```

**完整例子：时间线展示**

```
T1: root = new Object()
    GC Roots 包含：static root + main 栈帧 local
    → 两个对象都可达，存活

T2: doSomething(local) 调用中
    GC Roots 包含：static root + main 栈帧 local + doSomething 栈帧 param
    → local 通过栈帧链仍然可达
    → 参数 param 也持有引用

T3: local = null
    GC Roots 包含：static root + main 栈帧 local(=null)
    → ③ 的对象从 GC Roots 中消失
    → 下次 GC 会被回收

T4: main() 返回
    main 栈帧被弹出
    → main 栈帧中的所有引用消失
    → 但子线程的栈帧引用仍然存在 → 仍然是 GC Root
```

#### HotSpot 源码：可达性分析的实现

HotSpot 中可达性分析由 **Root Scanner** 实现，源码在：

```
hotspot/src/share/vm/gc/shared/
  ├── rootProcessor.cpp          ← 根集合的扫描调度
  ├── oopClosure.hpp             ← 对象扫描的闭包接口
  └── genCollectedHeap.cpp       ← 代际堆的根扫描

hotspot/src/share/vm/gc/shared/
  └── genRemSet.cpp              ← 代际引用集的管理
```

**核心流程**：

```cpp
// 伪代码：HotSpot 可达性分析
// 真实源码在 genCollectedHeap::do_collection() 中调用

// Step 1: 收集所有 GC Roots
RootPolicy* rootPolicy = new GenCollectedHeapRootsPolicy();
rootPolicy->setup();

// Step 2: 对每个 Root 应用 OopClosure 扫描
rootProcessor->roots_at_safepoint(
    rootPolicy,
    is_alive_closure,   // 判断对象是否存活
    keep_alive_closure, // 标记存活对象
    !trace_including_unloaded_classes
);

// Step 3: OopClosure 递归遍历引用链
class IsAliveClosure : public BoolObjectClosure {
    bool do_object_b(oop p) {
        // 检查对象是否已经在存活集合中
        if (CollectedHeap::is_object_in_space(p)) {
            return is_marked(p);  // 标记位判断
        }
        return false;
    }
};
```

**标记过程**：

```
可达性分析的标记流程（以 Serial GC 为例）：

  GC Roots 集合
       │
       ▼  对所有 Root 调用 IsAliveClosure
  [Root1] ──引用──► [ObjA] ──► 标记 A 为存活
       │                │
       │                ▼
       │           [ObjB] ──► 标记 B 为存活
       │                │
       │                ▼
       │           [ObjC] ──► 标记 C 为存活（但 C 没有出度）
       │
       ▼
  [Root2] ──引用──► [ObjD] ──► 标记 D 为存活
       │
       ▼
  [未标记的对象] → 判定为垃圾，标记为可回收
```

---

### 1.2 为什么不用引用计数？

```java
// 引用计数的问题：循环引用

// 两个对象互相引用，引用计数永远不为 0
class A { B b; }
class B { A a; }

A a = new A();
B b = new B();
a.b = b;  // A 引用 B
b.a = a;  // B 引用 A

a = null;
b = null;
// 引用计数：A 的引用计数 = 1，B 的引用计数 = 1
// 即使已经没有外部引用，两者都不会被回收 → 内存泄漏
// 可达性分析：从 GC Root 出发，A 和 B 都不可达 → 被回收 ✅
```

---

### 1.3 四种引用类型

这是判断对象能否被回收的关键分水岭：

```java
// java.lang.ref 包下的四种引用
┌─────────────┬────────────────────────────────────────────────────┐
│ 引用类型      │ 何时可回收                                          │
├─────────────┼────────────────────────────────────────────────────┤
│ Strong       │ 永远不会被回收，除非对象完全不可达                      │
│ Reference    │                                                  │
├─────────────┼────────────────────────────────────────────────────┤
│ Soft         │ 内存不足时回收                                       │
│ Reference    │ JVM 根据内存压力决定是否回收                            │
├─────────────┼────────────────────────────────────────────────────┤
│ Weak         │ GC 发生时，无论内存是否充足，一律回收                    │
│ Reference    │ 下次 GC 必然回收                                      │
├─────────────┼────────────────────────────────────────────────────┤
│ Phantom      │ 对象被回收后，通过 ReferenceQueue 通知程序               │
│ Reference    │ 对象已被标记为可回收，但还没被真正回收                     │
└─────────────┴────────────────────────────────────────────────────┘
```

```java
// 四种引用的使用示例

Object obj = new Object();

// 1. 强引用（默认）
StrongReference: obj = new Object();
// 永远不会被回收，除非 obj = null 且没有其他引用

// 2. 软引用（缓存）
SoftReference<Object> softRef = new SoftReference<>(new Object());
// JVM 内存不足时自动回收
// 适合做内存敏感的高速缓存

// 3. 弱引用
WeakReference<Object> weakRef = new WeakReference<>(new Object());
// 下次 GC 时必然回收
// HashMap 的弱引用 Key（WeakHashMap）就是用它

// 4. 虚引用
PhantomReference<Object> phantomRef =
    new PhantomReference<>(new Object(), new ReferenceQueue<>());
// 任何时候都会被回收
// 回收前会放入 ReferenceQueue，程序可以感知到"即将被回收"
```

#### HotSpot 中引用类型的处理

源码位置：`hotspot/src/share/vm/memory/referenceProcessor.cpp`

```cpp
// ReferenceProcessor::process_discovered_references()
// GC 发现软/弱/虚引用后，根据 GC 类型和引用强度决定回收策略

template <class T, class GCTraceTime>
void ReferenceProcessor::process_discovered_references(
    OopClosure* ref_oops_closure,      // 继续扫描引用的对象
    KeepAliveClosure* keep_alive,      // 标记为存活
    STWIsAliveClosure* is_alive,       // 可达性判断
    bool clear_soft_refs,              // 是否清理软引用
    T* work_queue,
    GCTraceTime tr) {

    // 遍历所有发现的引用对象
    while (!is_empty()) {
        oop p = next_reference_in_discovered_list();

        if (is_alive->do_object_b(ref)) {
            // 引用的对象仍然可达 → 保留引用
            keep_alive->do_object_b(ref);
        } else {
            // 引用的对象不可达 → 处理回收
            if (is_enqueued(p)) {
                // 已经被处理过了
                continue;
            }

            // 根据引用类型和 GC 类型决定是否回收
            bool can_clear = false;

            if (is_soft_reference(p)) {
                // 软引用：检查是否超过最大内存阈值
                can_clear = clear_soft_refs;
                // 或者对象大小超过 SoftRefLRUPolicy 计算出的阈值
                can_clear |= should_clear_reference(p, _num_soft_refs_processed);
            }
            // 弱引用和虚引用：无条件回收
            // can_clear = true;

            if (can_clear) {
                enqueue_reference(p);  // 放入队列等待清理
                clear_reference(p);    // 清除引用
            }
        }
    }
}
```

**关键理解**：
- 软引用不是"内存满了才回收"，而是有**LRU 策略**，根据剩余内存和对象大小计算阈值
- 弱引用和虚引用在**任何一次 GC** 中都会被回收，不需要等待内存不足

---

### 1.4 Finalizer 对可达性的干扰

这是很多人忽略的"复活"机制：

```java
class Resurrection {
    static Resurrection saved;

    @Override
    protected void finalize() throws Throwable {
        // 在这个对象被回收前，finalize() 会被调用
        // 可以在 finalize() 中把自己重新赋值给一个 GC Root
        saved = this;  // 对象"复活"了！
    }
}

Resurrection obj = new Resurrection();
obj = null;

// 第一次 GC：
//   obj 不可达 → 加入 F-Queue → Finalizer 线程调用 finalize()
//   finalize() 中 saved = this → 对象重新可达 → 对象存活

// 第二次 GC：
//   saved 仍在，对象仍然可达
//   但 finalize() 只会执行一次，所以第二次不会再"复活"
//   但如果 saved 仍然存在，对象会一直被保留
```

#### HotSpot 中 Finalizer 的处理

```cpp
// 源码位置：hotspot/src/share/vm/gc/shared/finalizerRegistry.cpp
// 源码位置：hotspot/src/share/vm/runtime/finalizer.cpp

// Step 1: GC 发现对象有 finalize() 方法
// Step 2: 对象不可达 → 加入 F-Queue（Finalizer 队列）
// Step 3: Finalizer 守护线程从 F-Queue 取对象，调用 finalize()

// FinalizerThread 源码（伪代码）：
// hotspot/src/share/vm/runtime/finalizer.cpp
void Finalizer::run() {
    while (true) {
        // 从 Finalizer 队列中取一个待最终化的对象
        oop obj = Finalizer::dequeue();

        if (obj != NULL) {
            // 调用 finalize() 方法
            oop result = Finalizer::invoke_finalize_method(obj);

            // 注意：finalize() 执行完后，对象会被标记为"可再次回收"
            // 如果 finalize() 中没有重新引用，下次 GC 就会被回收
            FreeFinalize::register_finalized(oop(result));
        } else {
            // 队列为空，等待
            synchronized(_lock) {
                _lock.wait(5000);  // 最多等 5s
            }
        }
    }
}
```

> **⚠️ Finalizer 的问题**：
> 1. `finalize()` 执行时机不确定，不能依赖它做资源清理
> 2. `finalize()` 可以"复活"对象，延迟回收
> 3. `finalize()` 抛出异常会静默忽略
> 4. JDK 9+ `finalize()` 已被标记为 `@Deprecated`，推荐用 `Cleaner` 替代

---

### 1.5 可达性分析的"逃生舱"：可达性与引用的关系

```java
// 即使被引用，也可能被回收

// 场景：弱引用的对象
WeakReference<String> weak = new WeakReference<>(new String("Hello"));
// weak 引用了 "Hello"，但这是弱引用
// 下次 GC 时，"Hello" 即使被弱引用着，也会被回收

// 场景：软引用的对象
SoftReference<String> soft = new SoftReference<>(new String("World"));
// 内存不足时，即使被软引用着，也会被回收

// 总结：
// 可达性分析判断"可回收" = 没有从 GC Root 出发的强引用链
// 软引用/弱引用/虚引用 ≠ GC Root 的强引用链
```

---

## 二、触发 GC 的所有条件

### 2.1 触发 Young GC（Minor GC）的条件

Young GC 发生在新生代，频率最高。触发条件：

#### 条件 1：Eden 区满

```
新生代结构：

┌────────────────────────────────────────────────────────┐
│                   Young Generation                       │
│                                                        │
│  ┌──────────┐  ┌────────────┐  ┌──────────────────┐  │
│  │   Eden   │  │   S0       │  │  S1              │  │
│  │  (80%)   │  │  (10%)     │  │  (10%)           │  │
│  │          │  │            │  │                  │  │
│  └──────────┘  └────────────┘  └──────────────────┘  │
│                                                        │
└────────────────────────────────────────────────────────┘

S0 和 S1 都是 Survivor 区，两者对称，没有本质区别。
在任何一个 Young GC 时刻，其中一个被称为 "From"（源区），
另一个被称为 "To"（目标区）。
GC 结束后，两者角色互换。
```

**为什么用两个 Survivor 区？**

> 原文旧版说法"无法复制 → 算法崩溃"是有误的。
> 用两个 Survivor 区不是"理论必然"，而是"复制算法的必然选择"。
> 用一种算法，就要服从它的约束。

```
复制算法（Copying GC）的工作原理：
═══════════════════════════════════════

  从 From 区读取存活对象 → 同时写入 To 区
  读和写必须同时进行，不能串行

  如果只有一个 Survivor 区:
    边读边写 → 读到的数据可能被刚写入的数据覆盖
    → 数据错乱

  所以需要两个区：
    From 负责被读（只读）
    To  负责被写（只写）
    两者职责分离，不会冲突


一个 Survivor 区的替代方案（可行，但 HotSpot 没选）：
═══════════════════════════════════════

  方案：标记-整理（Mark-Compact，原地压缩）

  Step 1: 标记所有存活对象
  Step 2: 将存活对象原地向前压缩（消除碎片）
  Step 3: 释放压缩后多余的空间

  不需要第二个区域，一个 Survivor 区就能工作。

  为什么 HotSpot 不选这个方案？

  新生代的特殊性：
    ├── 99% 的对象朝生夕灭
    ├── 存活对象极少，复制的开销微乎其微
    └── 复制算法分配内存 = bump pointer（指针递增）
       → 无锁，无碎片，速度极快

  标记-整理的代价：
    ├── 需要移动存活对象到前面
    ├── 移动后需要修正所有指向它的引用
    │    这一步开销比复制算法大得多
    └── 实现更复杂

  结论：
    两个 Survivor 区不是"必须"
    而是"用复制算法时必须的工程选择"
    HotSpot 选了复制算法，所以选了两个 Survivor 区
```

**完整的两次 GC 周期（理解 S0/S1 的关键）**：

```
第 1 次 GC 前:
═══════════════════════════════════════

  Eden    [Obj1  Obj2  Obj3  Obj4  Obj5]  ← 满
  S0(From)[]                       ← 空（上一次 GC 后清空）
  S1(To)  [Obj6  Obj7]             ← 上一次 GC 的存活对象

  Eden 满 → 触发 Young GC

  Young GC 过程:
    1. 扫描 Eden + S0(From) 中的所有对象
       - Eden 的存活对象: Obj1, Obj3
       - S0 的存活对象: 无（S0 为空）
    2. 将存活对象复制到 S1(To)
       S1 现在有: [Obj6  Obj7  Obj1  Obj3]
       所有存活对象年龄 + 1
    3. 回收 Eden 空间，清空 S0
    4. 角色互换: S1 变成新的 From，S0 变成新的 To

第 1 次 GC 后 / 第 2 次 GC 前:
═══════════════════════════════════════

  Eden    []                       ← 空，开始新分配
  S0(To)  []                       ← 空（刚才被清空）
  S1(From)[Obj6  Obj7  Obj1  Obj3]

  新对象继续分配到 Eden: Obj8, Obj9, Obj10, Obj11, Obj12

第 2 次 GC 前:
═══════════════════════════════════════

  Eden    [Obj8  Obj9  Obj10  Obj11  Obj12]  ← 又满了
  S0(To)  []                                ← 空（等待接收）
  S1(From)[Obj6  Obj7  Obj1  Obj3]          ← 有上次存活的对象

  Eden 满 → 触发 Young GC

  Young GC 过程:
    1. 扫描 Eden + S1(From) 中的所有对象
       - Eden 的存活对象: Obj8, Obj10
       - S1 的存活对象: Obj7, Obj1（假设 Obj6, Obj3 已不可达）
    2. 将存活对象复制到 S0(To)  ← 注意：这次是 S0 接收！
       S0 现在有: [Obj7  Obj1  Obj8  Obj10]
       存活对象年龄 + 1
    3. 回收 Eden 空间，清空 S1
    4. 角色互换: S0 变成新的 From，S1 变成新的 To

第 2 次 GC 后:
═══════════════════════════════════════

  Eden    []
  S0(From)[Obj7  Obj1  Obj8  Obj10]   ← 这次 S0 有数据了
  S1(To)  []
```

**回到你的问题**：

```
"为什么没有用到 S0？"

答案：文档中展示的是第 1 次 GC，恰好在这个快照中：
  - S0 是 From 角色，但此时恰好为空
  - S0 仍然参与了扫描（只是扫描结果为空）
  - 在第 2 次 GC 中，S0 变成 To，是接收存活对象的目标区

原文中 "将 Eden 中存活的对象复制到 S1（S0 为空）" 的描述
有误导性，容易让人以为 S0 没用。

准确说法应该是:
  扫描 Eden + From（无论有数据与否）
  存活对象 → 复制到 To
  然后清空 Eden 和 From，角色互换
```

```cpp
// HotSpot 源码：Eden 分配失败触发 GC
// 位置：hotspot/src/share/vm/gc/shared/genCollectedHeap.cpp

void* GenCollectedHeap::par_allocate(size_t size, unsigned int t) {
    // 尝试从 Eden 区分配内存
    void* result = young_gen->par_allocate(size, t);

    if (result == NULL) {
        // Eden 分配失败
        // 检查是否需要 Full GC
        if (needs_full_gc_for_allocation_failure()) {
            result = full_allocate(size);
        } else {
            // 🔑 Eden 满 → 触发 Young GC
            result = mangle_and_eden_allocate(size, t, true);
            // mangle_and_eden_allocate() 内部会：
            //   1. 触发 GC
            //   2. GC 后再尝试从 Eden 分配
            //   3. 如果还失败，从 Old 区分配（大对象直接进 Old）
        }
    }

    return result;
}
```

#### 条件 2：Metaspace 满触发（间接）

```
Metaspace 分配失败：
  1. Metaspace 空间不足
  2. 触发 Full GC（不是 Young GC）
  3. Full GC 回收方法区中的无用类
  4. 如果还不足 → 抛出 OutOfMemoryError: Metaspace
```

#### 条件 3：JVM 内部统计触发

```cpp
// HotSpot 还有一个"预测性"触发机制：
// 如果 JVM 预测很快会满，会提前触发 GC

// 位置：hotspot/src/share/vm/gc/shared/genCollectedHeap.cpp
// 在 gen_copy_to_survivor_space() 中

if (young_gen->should_concurrent_collect()) {
    // 新生代即将满，提前触发并发 GC
    // 避免等到真的满了才 GC，减少停顿时间
}
```

---

### 2.2 触发 Full GC（Major GC）的条件

Full GC 回收整个堆（新生代 + 老年代 + 方法区），代价巨大。触发条件：

#### 条件 1：Old 区满

```
┌────────────────────────────────────────────────────┐
│  Old Generation 满                                   │
│                                                      │
│  Young GC 存活对象晋升到 Old                          │
│      对象年龄达到 MaxTenuringThreshold（默认 15）    │
│      Survivor 区放不下，提前晋升                       │
│      大对象直接进 Old（PretenureSizeThreshold）       │
│                                                      │
│  Old 满了 → 触发 Full GC                             │
└────────────────────────────────────────────────────┘
```

#### 条件 2：分配大对象到 Old 失败

```cpp
// 当 Eden 放不下，且对象很大时，直接尝试在 Old 中分配
// 如果 Old 也放不下 → Full GC

void* GenCollectedHeap::allocate_in_tlab_or_eden(
    size_t size, unsigned int t) {

    // 1. 尝试从 Eden 分配
    void* obj = eden_allocate(size, t);

    if (obj == NULL) {
        // 2. Eden 分配失败，检查对象是否够大，可以进 Old
        if (is_in_old_gen_allocation(size)) {
            obj = old_gen->allocate(size);
            if (obj == NULL) {
                // 3. Old 也分配失败 → Full GC
                trigger_full_gc();
            }
        } else {
            // 4. 对象不够大 → Young GC
            trigger_young_gc();
        }
    }

    return obj;
}
```

#### 条件 3：Metaspace 空间不足

```
Metaspace 是类元数据的存储区域（JDK 8+ 替代永久代）

Metaspace 满 → Full GC

触发时机：
  1. 加载新类时，Metaspace 空间不足
  2. 方法区中的常量池、String 等增长
  3. 反射、动态代理创建大量类
```

#### 条件 4：System.gc() 调用

```java
// 显式调用
System.gc();

// 等价于
Runtime.getRuntime().gc();
```

```cpp
// HotSpot 中 System.gc() 的处理
// 位置：hotspot/src/share/vm/runtime/globals.hpp

// 默认配置：
//   +UseGCOverheadLimit（默认开启）
//   +ExplicitGCInvokesConcurrent（默认关闭）
//   -ExplicitGCIsShutDown（默认关闭，System.gc() 生效）

// 如果使用 Parallel GC / CMS GC：
//   System.gc() → Full GC

// 如果使用 G1 GC / ZGC：
//   System.gc() → Full GC（即使这些是并发 GC）
```

> **⚠️ 最佳实践：永远不要手动调用 `System.gc()`**
> 1. 它是一个**建议**，JVM 可以不执行（设置 `-XX:+DisableExplicitGC` 后完全不生效）
> 2. 如果执行，一定是 Full GC，代价巨大
> 3. 会打断 JVM 的自适应调节

#### 条件 5：GC 开销超限

```cpp
// JVM 有一个开销监控机制：
// 如果 GC 花费的时间超过 98%（默认），且回收空间不足 2%，
// 就抛出 OutOfMemoryError

// 源码位置：hotspot/src/share/vm/gc/shared/genCollectedHeap.cpp

// 参数控制：
//   -XX:+UseGCOverheadLimit（默认开启）
//   -XX:GCTimeRatio=1（默认 1，即 99% 时间运行业务，1% 时间 GC）
//   -XX:GCHeapFreeLimit=2（默认 2%，GC 后如果堆回收不到 2% 就抛异常）

// 计算公式：
if (gc_time_ratio <= GCHeapFreeLimit / (100 - GCTimeRatio)) {
    // 抛异常
    THROW_MSG(vmSymbols::java_lang_OutOfMemoryError(),
              "GC overhead limit exceeded");
}
```

#### 条件 6：Minor GC 后 Survivor 放不下

```
Young GC 过程中，Eden + From Survivor 中的存活对象需要复制到 To Survivor：

  存活对象大小 > To Survivor 容量
    → 存活对象直接晋升到 Old

  如果 Old 也放不下
    → 触发 Full GC
```

#### 条件 7：Java 堆内存分配失败（最极端的条件）

```
所有 GC 都回收不了，堆还是分配失败：
  → 抛出 OutOfMemoryError: Java heap space

这发生在：
  1. 堆满了，GC 后仍然无法分配
  2. 堆配置太小（-Xmx）
  3. 存在大量不可回收的内存泄漏
```

---

### 2.3 各 GC 收集器触发条件汇总

```
┌──────────────┬──────────────────────────────────────────────────┐
│ GC 类型       │ 触发条件                                          │
├──────────────┼──────────────────────────────────────────────────┤
│ Young GC      │                                                    │
│ (Minor GC)   │                                                    │
│              │ 1. Eden 区满（最常见）                              │
│              │ 2. Eden 分配失败                                    │
│              │ 3. JVM 预测新生代即将满                              │
│              │ 4. 对象晋升后 Old 放不下（连带触发）                  │
├──────────────┼──────────────────────────────────────────────────┤
│ Full GC       │                                                    │
│ (Major GC)   │                                                    │
│              │ 1. Old 区满                                        │
│              │ 2. Old 分配大对象失败                               │
│              │ 3. Metaspace 空间不足                               │
│              │ 4. System.gc() 调用                                │
│              │ 5. GC 开销超限（>98% 时间 GC，回收 <2%）           │
│              │ 6. Minor GC 后 Survivor 放不下，Old 也放不下        │
│              │ 7. 堆分配最终失败（OOM 前的最后一搏）                 │
│              │ 8. JDK 版本升级时的类加载元数据更新                  │
└──────────────┴──────────────────────────────────────────────────┘
```

---

### 2.4 GC 的完整调用链路（源码层面）

```
GC 触发的完整调用链：

1. 触发点（以 Eden 满为例）:
═══════════════════════════════════════

  Java 代码：new Object()
      │
      ▼
  TLAB（线程本地分配缓冲区）分配失败
      │
      ▼
  Heap::par_allocate()
      │
      ▼
  GenCollectedHeap::par_allocate()
      │  1. young_gen->par_allocate() → 失败
      │  2. needs_full_gc_for_allocation_failure() → false
      │  3. mangle_and_eden_allocate()
      │
      ▼
  CollectedHeap::mangle_and_eden_allocate()
      │
      ▼
  GenCollectedHeap::collect_as_vm_thread()
      │  设置 GC 类型：_gc_cause = _gcCause
      │  _gcCause = "Allocation Failure"
      │
      ▼
  GenCollectedHeap::do_collection()
      │
      ▼
  GenCollectedHeap::ref_process_discovered_references()
      │  处理引用队列（软/弱/虚引用）
      │
      ▼
  GenCollectedHeap::gen_process_strong_roots()
      │  可达性分析，从 GC Roots 开始扫描
      │
      ▼
  GenCollectedHeap::do_generic_collection()
      │
      ▼
  GenCollectedHeap::copy_to_survivor_space()
      │  将存活对象复制到 Survivor 区
      │
      ▼
  GenCollectedHeap::mark_sweep()
      │  标记-清除（老年代）或 标记-整理（老年代）
      │
      ▼
  GenCollectedHeap::end_of_mark_compact()
      │  GC 完成，堆空间释放
```

---

### 2.5 GC Cause：JVM 如何知道为什么 GC

HotSpot 用一个枚举记录每次 GC 的触发原因：

```cpp
// 位置：hotspot/src/share/vm/gc/shared/gcCause.hpp

enum GCCause {
    GCCause::__allocation_failure,           // Eden 满，分配失败
    GCCause::_metadata_GC_clear_soft_refs,   // Metaspace 满
    GCCause::_gc_locker,                     // 同步锁等待
    GCCause::_wb_young_gc,                   // Write Barriers 触发
    GCCause::_to_space_full,                 // Survivor 满
    GCCause::_scavenge_before_full_gc,       // Full GC 前的 Young GC
    GCCause::_full_gc_alot,                  // 调试：每 N 秒 Full GC
    GCCause::_allocation_profiler,           // 分配分析器
    GCCause::_heap_inspection,               // HeapDump
    GCCause::_jvm_gc,                        // System.gc()
    GCCause::_user,                          // 用户显式触发
    GCCause::_full_gc_for_ergonomics,        // 自适应 Full GC
    // ... 共 20+ 种原因
};
```

```
可以通过 JMX 或 -verbose:gc 查看每次 GC 的原因：

-verbose:gc -Xlog:gc*

输出示例：
[GC (Allocation Failure) [PSYoungGen: 39680K->3856K(40960K)] 39680K->14008K(125952K), 0.0045211 secs]
       ↑ 这里就是 GC Cause
       意思是：因为分配失败触发的 GC

[Full GC (System.gc()) [PSOldGen: 8152K->7720K(44544K)] 12008K->7720K(85504K)]
       ↑ 意思是：System.gc() 触发的 Full GC
```

---

## 三、GC 源码剖析

### 3.1 Young GC 的核心算法：复制算法

```
复制算法（Copying GC）适用于新生代

原理：
  将新生代分为 Eden + 两个 Survivor（From / To）
  GC 时：
    1. 扫描 Eden 和 From 中的存活对象
    2. 复制到 To 中（连续地址，无碎片）
    3. 清空 Eden 和 From
    4. To 和 From 交换角色
    5. 存活对象年龄 + 1

为什么用复制算法：
  ├── 新生代大多数对象是"朝生夕灭"的（99%）
  ├── 只需要复制少量存活对象，效率高
  ├── 复制后内存连续，无碎片
  └── 分配内存 = 指针递增（bump pointer）
```

#### HotSpot 源码：复制算法

```cpp
// 位置：hotspot/src/share/vm/gc/shared/copy.cpp

template <class StackObjScanClosure, class OopsInHeapClosure,
          class RegionScanClosure, class OopsInEvacuateClosure,
          class FreeOopsInHeapClosure>
static void copy_to_survivor_space(
    const CollectedHeap* heap,
    bool full,
    Generation* young_gen,
    GenerationType type,
    GCCause::Cause cause) {

    // 从年轻代到老年代，从 Eden + From Survivor 复制到 To Survivor

    // Step 1: 对 Eden 和 From 中的每个对象执行扫描
    young_gen->gen_process_strong_roots(
        &keep_alive,      // 存活对象的处理
        &drain_stack,      // 栈对象扫描
        &copy_to_old_gen, // 复制到老年代
        &oops_in_heap
    );

    // Step 2: 复制存活对象到 To Survivor
    void* copy_to_survivor(oop p) {
        // 如果对象年龄超过阈值 → 晋升到 Old
        if (age(p) >= max_tenuring_threshold) {
            copy_to_old_gen(p);
        } else if (To Survivor 还有空间) {
            copy_to_to_survivor(p);
            age(p)++;  // 年龄 + 1
        } else {
            // To Survivor 放不下 → 晋升到 Old
            copy_to_old_gen(p);
        }
    }

    // Step 3: 更新引用（对象被复制后地址变了，需要修正引用）
    // 这就是"写屏障"要做的事
    // 写屏障在对象被复制时，更新所有指向它的引用
}
```

**晋升到 Old 的判断逻辑**：

```
对象是否晋升到 Old（三个条件满足任一）：

  1. 年龄 >= MaxTenuringThreshold（默认 15）
     → 达到最大年龄，晋升

  2. 对象大小 > To Survivor 剩余空间的一半
     → 放不下，提前晋升

  3. 动态年龄阈值：
     → JVM 根据 Survivor 区的实际使用情况
     → 动态调整晋升年龄（可能 < 15）
     → 源码：compute_max_tenuring_threshold()

动态年龄阈值计算（伪代码）：
  int compute_max_tenuring_threshold() {
      int threshold = MaxTenuringThreshold;  // 15

      // 计算 Survivor 中各年龄对象的总大小
      for (age = 1; age < 15; age++) {
          size[age] = total_size_of_objects_with_age(age);
      }

      // 从最小年龄开始累加，看能塞多少进 To Survivor
      int total = 0;
      for (age = 1; age < 15; age++) {
          total += size[age];
          if ((float) total / To_Survivor_Capacity < TargetSurvivorRatio) {
              threshold = age + 1;
          }
      }
      return threshold;
  }
```

---

### 3.2 Full GC 的核心算法：标记-清除 / 标记-整理

```
老年代使用 标记-整理（Mark-Compact）

标记-整理 vs 标记-清除：

  标记-清除：
    1. 标记所有存活对象
    2. 清除所有未标记对象
    → 问题：产生大量碎片，大对象无法分配

  标记-整理：
    1. 标记所有存活对象
    2. 将存活对象向一端移动
    3. 清理端外的空间
    → 优点：无碎片，内存连续
    → 缺点：移动对象需要更新引用，开销大
```

---

## 四、总结与实战建议

### 4.1 两个核心问题的答案

```
问题 1：什么时候一个对象被认为可以回收？
═══════════════════════════════════════

  当一个对象从所有 GC Root 出发，没有任何强引用链可达时
  → 可达性分析判定为"垃圾"

  但以下情况会影响判断：
  ├── 软引用：内存不足时回收，否则保留
  ├── 弱引用：任何一次 GC 都回收
  ├── 虚引用：任何时候都回收
  └── Finalizer：可以"复活"对象，延迟一次回收


问题 2：什么时候触发 GC？
═══════════════════════════════════════

  Young GC：
  ├── Eden 区满（最常见）
  ├── 新生代即将满（JVM 预测）
  └── 对象晋升后 Old 放不下（连带触发）

  Full GC：
  ├── Old 区满
  ├── 大对象在 Old 分配失败
  ├── Metaspace 空间不足
  ├── System.gc() 调用
  ├── GC 开销超限（>98% 时间 GC）
  ├── Minor GC 后 Old 也放不下
  └── 堆分配最终失败（OOM 前）
```

### 4.2 实战建议

```
┌────────────────────────────────────────────────────────────────┐
│  建议 1：永远不要调用 System.gc()                               │
│  → 如果必须用，设置 -XX:+DisableExplicitGC 完全禁用             │
│                                                                  │
│  建议 2：理解你的 GC 日志                                        │
│  → -verbose:gc -Xlog:gc*                                       │
│  → 关注 GC Cause（为什么 GC）和停顿时间                           │
│                                                                  │
│  建议 3：避免大对象直接进 Old                                    │
│  → 大对象占 Old 空间，容易触发 Full GC                          │
│  → 设置 -XX:PretenureSizeThreshold（Serial/ParNew）             │
│                                                                  │
│  建议 4：合理配置 Survivor 区大小                                │
│  → 太小 → 大量对象提前晋升 Old → Full GC 频繁                   │
│  → 太大 → 浪费空间                                               │
│  → 通常 Eden:S0:S1 = 8:1:1                                     │
│                                                                  │
│  建议 5：G1 / ZGC 时代，GC 参数调优优先级降低                   │
│  → 现代 GC 是自适应的，能自动调节                                │
│  → 但理解原理才能正确诊断问题                                    │
└────────────────────────────────────────────────────────────────┘
```