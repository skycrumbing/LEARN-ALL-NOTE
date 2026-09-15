# Java 线程池源码解析

## 一、核心参数

```java
public ThreadPoolExecutor(
    int corePoolSize,          // 核心线程数
    int maximumPoolSize,       // 最大线程数
    long keepAliveTime,        // 空闲线程存活时间
    TimeUnit unit,             // 时间单位
    BlockingQueue<Runnable> workQueue,  // 任务队列
    ThreadFactory threadFactory,        // 线程工厂
    RejectedExecutionHandler handler    // 拒绝策略
)
```

| 参数 | 含义 | 常见值 |
|------|------|--------|
| `corePoolSize` | 核心线程数，即使空闲也不回收 | CPU 核数 ~ CPU×2 |
| `maximumPoolSize` | 最大线程数，队列满了才创建新线程 | corePoolSize 的 2~4 倍 |
| `keepAliveTime` | 非核心线程空闲多久后回收 | 60s |
| `workQueue` | 存储等待执行的任务 | `LinkedBlockingQueue`（无界）/ `ArrayBlockingQueue`（有界） |
| `threadFactory` | 创建线程的工厂 | `Executors.defaultThreadFactory()` |
| `handler` | 队列满 + 线程满时的拒绝策略 | 见第五节 |

## 二、线程池状态机

线程池用一个 `AtomicInteger ctl` 同时存储**运行状态**和**工作线程数**：

```
ctl 是一个 int（32 位）:

  ┌──────────┬────────────────────────────────┐
  │  高 3 位  │           低 29 位              │
  │  运行状态  │         工作线程数              │
  └──────────┴────────────────────────────────┘
```

```java
// 源码中的状态定义（高 3 位）
private static final int COUNT_BITS = Integer.SIZE - 3;  // 29
private static final int CAPACITY   = (1 << COUNT_BITS) - 1; // 约 5 亿

// 五种状态（值从大到小）
private static final int RUNNING    = -1 << COUNT_BITS;  // 111... 接受新任务
private static final int SHUTDOWN   =  0 << COUNT_BITS;  // 000... 不接受新任务，处理队列中
private static final int STOP       =  1 << COUNT_BITS;  // 001... 不接受新任务，中断所有线程
private static final int TIDYING    =  2 << COUNT_BITS;  // 010... 过渡状态
private static final int TERMINATED =  3 << COUNT_BITS;  // 011... 彻底终止
```

状态流转：

```
    RUNNING ──shutdown()──► SHUTDOWN ──队列空──► TIDYING ──► TERMINATED
       │                      │
       │                      │
    shutdownNow()          shutdownNow()
       │                      │
       ▼                      ▼
      STOP ───────────────► TIDYING ──► TERMINATED
```

| 状态 | 值（高 3 位） | 接受新任务？ | 处理队列中任务？ | 触发方式 |
|------|-------------|-----------|---------------|---------|
| RUNNING | 111 | ✅ | ✅ | new 出来就是 |
| SHUTDOWN | 000 | ❌ | ✅ | `shutdown()` |
| STOP | 001 | ❌ | ❌ | `shutdownNow()` |
| TIDYING | 010 | ❌ | ❌ | 过渡态 |
| TERMINATED | 011 | ❌ | ❌ | `terminated()` 回调后 |

## 三、`execute()` 完整流程

这是线程池最核心的方法，决定了任务如何被调度：

```java
public void execute(Runnable command) {
    if (command == null) throw new NullPointerException();

    int c = ctl.get();  // 获取当前状态 + 工作线程数

    // ===== 步骤 1：当前线程数 < 核心线程数 =====
    if (workerCountOf(c) < corePoolSize) {
        // 直接创建新的核心线程来执行任务
        if (addWorker(command, true))
            return;  // 成功，结束
        c = ctl.get();  // 失败，重新读取状态
    }

    // ===== 步骤 2：线程数 >= 核心线程数，尝试入队 =====
    if (isRunning(c) && workQueue.offer(command)) {
        int recheck = ctl.get();

        // 双重检查：入队后线程池可能关闭了
        if (!isRunning(recheck) && remove(command))
            reject(command);  // 已关闭，拒接任务
        else if (workerCountOf(recheck) == 0)
            // 线程池还在运行，但没有工作线程了
            // （可能所有线程都恰好死了）
            addWorker(null, false);  // 创建一个新线程
    }

    // ===== 步骤 3：队列满了，尝试创建新线程（不超过最大线程数）=====
    else if (!addWorker(command, false))
        // 创建失败 = 线程数已达到 maximumPoolSize
        reject(command);  // 执行拒绝策略
}
```

**流程图**：

```
execute(task)
    │
    ├── 线程数 < corePoolSize？
    │   ├── YES → addWorker(task) → 新线程执行 ✅
    │   └── NO  ↓
    │
    ├── workQueue.offer(task) 成功？
    │   ├── YES → 入队等待 ✅
    │   └── NO  ↓（队列满了）
    │
    ├── 线程数 < maximumPoolSize？
    │   ├── YES → addWorker(task) → 新线程执行 ✅
    │   └── NO  ↓
    │
    └── reject(task) → 拒绝策略 ❌
```

## 四、双重检查的必要性

`execute()` 中有两处双重检查，理解它们的关键在于：**状态检查和任务操作之间存在时间窗口，这个窗口里其他线程可能改变线程池状态**。

### 4.1 第一处双重检查：步骤 2 中的 `recheck`

```java
// ===== 步骤 2：线程数 >= 核心线程数，尝试入队 =====
if (isRunning(c) && workQueue.offer(command)) {
    int recheck = ctl.get();  // ← 再次读取状态

    if (!isRunning(recheck) && remove(command))
        reject(command);
    else if (workerCountOf(recheck) == 0)
        addWorker(null, false);
}
```

#### 为什么必须双重检查？

```
时间线（两个线程并发执行）：

  线程 A（提交任务）              线程 B（关闭线程池）
  ─────────────────              ─────────────────

  c = ctl.get()      ①
  → RUNNING ✓

                         shutdown() ②
                         → ctl 变为 SHUTDOWN

  isRunning(c) ?     ③
  → 仍然 RUNNING ✓  （读取的是①的旧值）

  workQueue.offer()  ④
  → 入队成功 ✓

  int recheck = ctl.get() ⑤
  → SHUTDOWN ✗    ← 状态已经变了！

  !isRunning(recheck) ?
  → true → remove() → reject()
```

**问题的根源**：

| 步骤 | 说明 |
|------|------|
| ① 读取 `c` | 获取 RUNNING 状态 |
| ② `shutdown()` | 另一个线程将状态改为 SHUTDOWN |
| ③ `isRunning(c)` | 用的还是①的旧值 `c`，仍然为 RUNNING |
| ④ `offer()` | 任务已经入队了 |
| ⑤ `recheck` | 此时才真正读到 SHUTDOWN |

#### 如果不双重检查会怎样？

```
没有 recheck 的情况：

  任务已经入队（在 SHUTDOWN 状态下）
  → 但是 SHUTDOWN 状态下不会再创建新线程
  → 任务永远不会被执行
  → 任务被"静默丢失"，调用者不会收到任何异常

  更严重的是 STOP 状态：
  → STOP 状态下队列中的任务会被丢弃，不执行
  → 任务直接丢失，调用者毫不知情
```

#### 为什么要 `remove()` 再 `reject()`？

```
如果只检查但不 remove：

  任务留在队列中，线程池已关闭
  → 在 SHUTDOWN 状态：队列中已有任务会被执行，但这个任务本不应被执行
    → 业务逻辑错误：用户以为任务被拒了，实际执行了

  在 STOP 状态：队列任务不会被处理
    → 任务永远卡在队列里 → 内存泄漏
    → 且调用者没有收到异常 → 完全静默

  remove() + reject() 的作用：
    → remove()：把任务从队列中拿走，防止被意外执行
    → reject()：触发拒绝策略，调用者能感知到任务被拒
```

#### 为什么 `remove()` 成功了才 `reject()`？

```java
if (!isRunning(recheck) && remove(command))
```

`remove()` 返回 false 的情况极少但需要防御：

```
  极端情况：任务刚好被某个Worker从队列取走了
  → remove() 返回 false（任务已不在队列里）
  → 不需要 reject，任务正在执行中

  如果此时仍然 reject：
  → 调用者收到"被拒绝"的异常
  → 但实际上任务正在执行 → 误导性错误
```

### 4.2 第二处双重检查：`workerCountOf(recheck) == 0`

```java
else if (workerCountOf(recheck) == 0)
    addWorker(null, false);
```

这是一个常被忽略的边缘场景：

```
  线程 A（提交任务）              线程 B（所有Worker）
  ─────────────────              ─────────────────

  isRunning(c) ?     ①
  → RUNNING ✓

  workQueue.offer()  ②
  → 入队成功 ✓

  recheck            ③
  → RUNNING，但 workerCount = 0

                         所有 Worker 刚好同时死亡 ④
                         （比如全部抛异常、被中断、超时退出）
                         → workerCount = 0

  队列里有任务，但没有 Worker 取任务
  → 任务永远执行不了！

  → 需要 create 一个新 Worker 来"捡起来"
```

**这个检查保护的是"空窗期"**：

| 场景 | 说明 |
|------|------|
| 线程池刚创建 | 还没有任何 Worker，第一个任务入队了，需要启动一个 Worker |
| 所有 Worker 恰好同时死亡 | 极端但可能（比如全部因 OOM 崩溃），需要补一个 |
| 刚执行完 `shutdownNow()` 后又恢复？ | 不会恢复，但 SHUTDOWN 状态下若队列非空，允许创建 Worker 处理队列 |

### 4.3 两处检查的关系总结

```
┌─────────────────────────────────────────────────────────┐
│                 execute() 的双重检查                      │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  第一次 isRunning(c)      ← 入队前检查，决定能不能入队    │
│       │                                                 │
│       ▼                                                 │
│  workQueue.offer()      ← 入队操作，需要时间              │
│       │                                                 │
│       ▼                                                 │
│  第二次 recheck = ctl.get()  ← 入队后复查，确保状态没变   │
│       │                                                 │
│       ├─ 状态变了（关闭了）→ remove + reject            │
│       └─ 状态没变                                │
│            │                                           │
│            └─ workerCount == 0 ? → addWorker(null)    │
│                                        │               │
│                                        └─ 正常等待       │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

| 检查点 | 检查时机 | 目的 | 失败后果 |
|--------|---------|------|---------|
| 第一次 `isRunning(c)` | 入队**前** | 决定是否入队 | — |
| 第二次 `recheck` | 入队**后** | 确认状态没变 | 任务静默丢失 / 内存泄漏 |
| `workerCount == 0` | 入队后 | 确保有人取任务 | 任务无人执行 |

**核心思想**：线程池是多线程环境，状态在**任何两个操作之间**都可能变化。双重检查 = 在状态变更敏感的操作前后各检查一次，形成"检查 → 操作 → 再检查"的防御模式。

## 五、Worker：线程如何保活

这是你问题的核心。

### 5.1 Worker 的结构

```java
private final class Worker
        extends AbstractQueuedSynchronizer  // 用 AQS 实现独占锁
        implements Runnable {

    final Thread thread;   // 🔑 真正执行任务的线程
    Runnable firstTask;    // 创建时指定的第一个任务（可为 null）
    volatile long completedTasks;  // 已完成任务数

    Worker(Runnable firstTask) {
        setState(-1);  // 禁止中断，直到线程启动
        this.firstTask = firstTask;
        // 🔑 用线程工厂创建线程，传入自己（this）作为 Runnable
        this.thread = getThreadFactory().newThread(this);
    }
}
```

**关键设计**：`Worker` 实现了 `Runnable`，它把自己传给了 `Thread`。当 `thread.start()` 被调用时，执行的是 `Worker.run()`。

### 5.2 `addWorker()`：创建并启动线程

```java
private boolean addWorker(Runnable firstTask, boolean core) {
    // 1. 自旋增加 workerCount
    retry:
    for (;;) {
        int c = ctl.get();
        int rs = runStateOf(c);

        // 检查线程池状态是否允许创建新线程
        if (rs >= SHUTDOWN &&
            !(rs == SHUTDOWN && firstTask == null && !workQueue.isEmpty()))
            return false;

        for (;;) {
            int wc = workerCountOf(c);
            // 检查是否超过容量限制
            if (wc >= CAPACITY ||
                wc >= (core ? corePoolSize : maximumPoolSize))
                return false;
            // CAS 增加 workerCount
            if (compareAndIncrementWorkerCount(c))
                break retry;
            c = ctl.get();  // 重新读取
            if (runStateOf(c) != rs)
                continue retry;
        }
    }

    // 2. 创建 Worker 并启动线程
    boolean workerStarted = false;
    boolean workerAdded = false;
    Worker w = null;
    try {
        w = new Worker(firstTask);         // 创建 Worker
        final Thread t = w.thread;         // 取出线程
        if (t != null) {
            final ReentrantLock mainLock = this.mainLock;
            mainLock.lock();
            try {
                int rs = runStateOf(ctl.get());
                if (rs < SHUTDOWN ||
                    (rs == SHUTDOWN && firstTask == null)) {
                    if (t.isAlive()) throw new IllegalThreadStateException();
                    workers.add(w);         // 加入 workers 集合
                    int s = workers.size();
                    if (s > largestPoolSize)
                        largestPoolSize = s;
                    workerAdded = true;
                }
            } finally {
                mainLock.unlock();
            }
            if (workerAdded) {
                t.start();  // 🔑 启动线程，执行 Worker.run()
                workerStarted = true;
            }
        }
    } finally {
        if (!workerStarted)
            addWorkerFailed(w);
    }
    return workerStarted;
}
```

### 5.3 `Worker.run()`：核心循环，线程永不退出

```java
public void run() {
    runWorker(this);
}

final void runWorker(Worker w) {
    Thread wt = Thread.currentThread();
    Runnable task = w.firstTask;
    w.firstTask = null;
    w.unlock();  // 允许中断
    boolean completedAbruptly = true;

    try {
        // 🔑 核心循环：只要 task 不为 null 或 getTask() 返回不为 null
        while (task != null || (task = getTask()) != null) {
            w.lock();

            // 检查线程池状态，如果需要中断则中断
            if ((runStateAtLeast(ctl.get(), STOP) ||
                 (Thread.interrupted() && runStateAtLeast(ctl.get(), STOP))) &&
                !wt.isInterrupted())
                wt.interrupt();

            try {
                beforeExecute(wt, task);
                Throwable thrown = null;
                try {
                    task.run();  // 🔑 执行任务
                } catch (RuntimeException x) {
                    thrown = x; throw x;
                } catch (Error x) {
                    thrown = x; throw x;
                } catch (Throwable x) {
                    thrown = x; throw new Error(x);
                } finally {
                    afterExecute(task, thrown);
                }
            } finally {
                task = null;
                w.completedTasks++;
                w.unlock();
            }
        }
        completedAbruptly = false;
    } finally {
        // 🔑 循环退出 = 线程即将死亡
        processWorkerExit(w, completedAbruptly);
    }
}
```

**线程不死的秘密就在这个 `while` 循环里**：

```
while (task != null || (task = getTask()) != null) {
    // 执行 task
    task.run();
    task = null;  // 当前任务执行完，置空
    // 下一轮循环：task == null，走 getTask()
}
```

执行完一个任务后，`task = null`，下一轮循环走 `getTask()` 从队列取下一个任务。

### 5.4 `getTask()`：阻塞等待任务

```java
private Runnable getTask() {
    boolean timedOut = false;

    for (;;) {
        int c = ctl.get();
        int rs = runStateOf(c);

        // 检查线程池状态：是否应该停止取任务
        if (rs >= SHUTDOWN && (rs >= STOP || workQueue.isEmpty())) {
            decrementWorkerCount();
            return null;  // 🔑 返回 null，线程会退出
        }

        int wc = workerCountOf(c);

        // 🔑 是否允许超时？
        // allowCoreThreadTimeOut=true 或者当前线程数 > corePoolSize
        boolean timed = allowCoreThreadTimeOut || wc > corePoolSize;

        // 检查是否需要回收当前线程
        if ((wc > maximumPoolSize || (timed && timedOut))
            && (wc > 1 || workQueue.isEmpty())) {
            if (compareAndDecrementWorkerCount(c))
                return null;  // 🔑 返回 null，线程被回收
            continue;
        }

        try {
            // 🔑 核心就在这里！
            Runnable r = timed ?
                workQueue.poll(keepAliveTime, TimeUnit.NANOSECONDS) :  // 超时等待
                workQueue.take();  // 🔑 永久阻塞！
            if (r != null)
                return r;
            timedOut = true;  // 超时了，下轮循环可能被回收
        } catch (InterruptedException retry) {
            timedOut = false;
        }
    }
}
```

**线程保活的核心机制**：

```
核心线程（默认 allowCoreThreadTimeOut = false）：
  → workQueue.take()  ← 永久阻塞，队列为空时线程一直等着
  → 线程不会退出，不会被 GC

非核心线程（或 allowCoreThreadTimeOut = true）：
  → workQueue.poll(keepAliveTime)  ← 超时等待
  → 超时后返回 null → getTask() 返回 null
  → runWorker() 的 while 循环退出
  → processWorkerExit() 清理线程
  → 线程死亡
```

### 5.5 为什么不回收核心线程

```
核心线程内部：

  while (true) {
      task = workQueue.take();  // ← 阻塞在这里
      task.run();               // 有任务，执行
      task = null;              // 执行完，再循环
  }

take() 内部是一个 Condition.await() → 线程进入 WAITING 状态
→ 线程不占用 CPU
→ 线程对象仍然被 Worker.thread 引用
→ Worker 对象在 workers 集合中
→ GC 不会回收（有强引用）
```

**引用链**：

```
ThreadPoolExecutor
  └── workers (HashSet<Worker>)
        └── Worker
              └── thread (Thread) ← 强引用，GC 不会回收
              └── Worker 本身（Runnable）
```

## 六、拒绝策略

当线程池**已经关闭**或**线程数 = max + 队列满**时，执行拒绝策略。

### 6.1 四种内置策略

```java
// 接口定义
public interface RejectedExecutionHandler {
    void rejectedExecution(Runnable r, ThreadPoolExecutor executor);
}
```

| 策略 | 类名 | 行为 |
|------|------|------|
| 抛异常 | `AbortPolicy` | 抛出 `RejectedExecutionException`，**默认策略** |
| 调用者执行 | `CallerRunsPolicy` | 由提交任务的线程自己执行 |
| 直接丢弃 | `DiscardPolicy` | 什么都不做，静默丢弃 |
| 丢弃最旧 | `DiscardOldestPolicy` | 丢弃队列中最旧的任务，重试提交 |

### 6.2 AbortPolicy（默认）

```java
public static class AbortPolicy implements RejectedExecutionHandler {
    public void rejectedExecution(Runnable r, ThreadPoolExecutor e) {
        throw new RejectedExecutionException("Task " + r.toString() +
            " rejected from " + e.toString());
    }
}
```

### 6.3 CallerRunsPolicy

```java
public static class CallerRunsPolicy implements RejectedExecutionHandler {
    public void rejectedExecution(Runnable r, ThreadPoolExecutor e) {
        if (!e.isShutdown()) {
            r.run();  // 🔑 由提交任务的线程（调用者）直接执行
        }
    }
}
```

**这个策略的巧妙之处**：调用者线程执行任务时，无暇提交新任务，客观上起到了**限流**的作用。

```
正常情况：
  线程 A 提交任务 → 线程池处理

CallerRunsPolicy：
  线程 A 提交任务 → 线程池满了 → 线程 A 自己执行任务
  → 线程 A 在忙，暂时不会提交更多任务
  → 系统压力自然降低
```

### 6.4 DiscardPolicy

```java
public static class DiscardPolicy implements RejectedExecutionHandler {
    public void rejectedExecution(Runnable r, ThreadPoolExecutor e) {
        // 什么都不做
    }
}
```

### 6.5 DiscardOldestPolicy

```java
public static class DiscardOldestPolicy implements RejectedExecutionHandler {
    public void rejectedExecution(Runnable r, ThreadPoolExecutor e) {
        if (!e.isShutdown()) {
            e.getQueue().poll();  // 🔑 丢弃队列头（最旧的任务）
            e.execute(r);         // 重新提交新任务
        }
    }
}
```

## 七、核心线程 vs 非核心线程

线程池里**没有"核心线程"和"非核心线程"的身份标记**。所有线程都是平等的 Worker。

区别只在于 `getTask()` 中的 `timed` 判断：

```java
// 核心线程 vs 非核心线程的判断逻辑：
boolean timed = allowCoreThreadTimeOut || wc > corePoolSize;

// 如果当前线程数 > corePoolSize：
//   timed = true → 使用 poll(keepAliveTime) → 超时后线程死亡
//
// 如果当前线程数 <= corePoolSize（且 allowCoreThreadTimeOut = false）：
//   timed = false → 使用 take() → 永久阻塞 → 线程不死
```

**通俗理解**：

```
线程池里有一群工人在等活：

  工人数量 <= corePoolSize：
    工人坐在工位上"永久等待"（take() 阻塞）
    来活了就干，干完继续等

  工人数量 > corePoolSize（即额外的工人）：
    工人等 keepAliveTime 时间
    这个时间内没活就"下班回家"（线程死亡）
```

## 八、线程池完整生命周期

```
创建线程池
    │
    ▼
RUNNING 状态
    │
    │  execute(task)
    │    ├── 线程 < core → 创建核心线程
    │    ├── 队列未满 → 入队
    │    ├── 队列满，线程 < max → 创建临时线程
    │    └── 队列满，线程 = max → 拒绝策略
    │
    ├── shutdown()
    │     → SHUTDOWN: 不再接受新任务，处理完队列中的任务
    │     → 队列空 → TIDYING → TERMINATED
    │
    └── shutdownNow()
          → STOP: 中断所有线程，不处理队列
          → TIDYING → TERMINATED
```

## 九、总结

| 问题 | 答案 |
|------|------|
| 线程怎么保证不回收 | `Worker.run()` 中 `while + getTask().take()` 永久阻塞，有强引用链 |
| 非核心线程怎么回收 | `getTask()` 中 `poll(keepAliveTime)` 超时返回 null，`while` 退出 |
| 拒绝策略怎么执行 | `execute()` 最后一步调用 `handler.rejectedExecution(task, executor)` |
| 核心和非核心的区别 | 没有身份标记，只看 `workerCount > corePoolSize` 时用 `poll` 还是 `take` |