# ByteBuf 内存管理

## 一、为什么不用 ByteBuffer？

```
Java NIO 的 ByteBuffer 有哪些问题？

┌─────────────────────────────────────────────────────┐
│  1. 需要手动 flip() / clear()                        │
│     → 容易忘记，导致数据读不到或读到脏数据            │
│                                                         │
│  2. capacity 不可变                                    │
│     → 数据不够？手动创建更大的 Buffer 并复制          │
│     → 数据太多？手动创建更大的 Buffer 并复制          │
│                                                         │
│  3. 没有复合缓冲区                                     │
│     → 多个 Buffer 合并需要手动操作                    │
│                                                         │
│  4. 自动扩容机制缺失                                   │
│     → 每次扩容都要自己处理                            │
└─────────────────────────────────────────────────────┘
```

Netty 的 `ByteBuf` 解决了所有这些问题：

```
┌─────────────────────────────────────────────────────┐
│  1. 独立的读索引和写索引                              │
│     → 不需要 flip()，读写互不干扰                    │
│                                                         │
│  2. 自动扩容                                            │
│     → 写空间不够时自动扩容                             │
│                                                         │
│  3. 复合缓冲区（CompositeByteBuf）                    │
│     → 多个 Buffer 逻辑合并，零拷贝                    │
│                                                         │
│  4. 引用计数（Reference Counting）                    │
│     → 手动管理生命周期，减少 GC 压力                   │
└─────────────────────────────────────────────────────┘
```

## 二、ByteBuf 内存模型

### ByteBuffer 的问题

```
ByteBuffer 的索引模型：

写模式:
┌────────────────────────────────────┐
│ [0, position)  [position, capacity) │
│   已写入数据       剩余空间          │
│       │            │               │
│       ▼            ▼               │
│    position    position(=limit)    │
└────────────────────────────────────┘

flip() 后:
┌────────────────────────────────────┐
│ [0, position)  [limit, capacity)   │
│   可读取数据     已写入数据(不动)    │
│       │                              │
│       ▼                              │
│    position=0, limit=写入位置       │
└────────────────────────────────────┘

❌ 只有一个 position，读写共用，必须 flip
```

### ByteBuf 的改进

```
ByteBuf 的索引模型：

┌──────────────────────────────────────────┐
│ [0, readerIndex) [reader, writer) [writer, capacity) │
│     已读数据        可读数据          剩余空间        │
│         │              │              │               │
│         ▼              ▼              ▼               │
│      readerIndex  readerIndex      writerIndex       │
│                                     (可写)           │
└──────────────────────────────────────────────────────┘

✅ 独立的 readerIndex 和 writerIndex
✅ 读和写各走各的，互不影响
✅ 不需要 flip()！
```

### 三个关键索引

| 索引 | 说明 | 默认值 | 变化方向 |
|------|------|--------|----------|
| `readerIndex` | 读位置 | 0 | 向后移动（读数据时） |
| `writerIndex` | 写位置 | 0 | 向后移动（写数据时） |
| `capacity` | 总容量 | 创建时指定 | 自动扩容 |

### 操作方法

```java
ByteBuf buf = Unpooled.buffer(1024);

// ===== 写入 =====
buf.writeByte(0x01);         // writerIndex 后移
buf.writeInt(12345);          // writerIndex 后移 4
buf.writeCharSequence("Hello", CharsetUtil.UTF_8);
// 写入后：readerIndex=0, writerIndex=数据长度

// ===== 读取 =====
int length = buf.readableBytes();  // writerIndex - readerIndex
byte b = buf.readByte();           // readerIndex 后移
int i = buf.readInt();              // readerIndex 后移 4

// ===== 跳读 =====
buf.skipBytes(2);       // readerIndex 后移 2，不读取

// ===== 重置 =====
buf.readerIndex(0);     // 重置读位置到开头
buf.clear();            // readerIndex=0, writerIndex=0
```

### 不需要 flip 的例子

```java
// ByteBuffer：需要 flip
ByteBuffer nioBuf = ByteBuffer.allocate(1024);
nioBuf.putInt(42);
nioBuf.flip();              // ← 手动切换
int value = nioBuf.getInt();

// ByteBuf：不需要 flip
ByteBuf nettyBuf = Unpooled.buffer(1024);
nettyBuf.writeInt(42);      // writerIndex 自动移动
int value = nettyBuf.readInt();  // readerIndex 自动移动，无需 flip！
```

## 三、堆内 vs 堆外内存

```
┌─────────────────────────────────────────────────────┐
│              JVM 内存布局                             │
├─────────────────────────────────────────────────────┤
│                                                     │
│  堆内内存（Heap Buffer）                              │
│  ┌───────────────────────────────────┐              │
│  │  JVM Heap                          │              │
│  │  ┌─────────────────────────────┐  │              │
│  │  │  ByteBuf (堆内)              │  │              │
│  │  │  被 GC 管理                  │  │              │
│  │  │  访问快，GC 有压力           │  │              │
│  │  └─────────────────────────────┘  │              │
│  └───────────────────────────────────┘              │
│                                                     │
│  堆外内存（Direct Buffer）                            │
│  ┌───────────────────────────────────┐              │
│  │  Native Memory                     │              │
│  │  ┌─────────────────────────────┐  │              │
│  │  │  ByteBuf (堆外/Direct)       │  │              │
│  │  │  不受 GC 管理               │  │              │
│  │  │  GC 无压力，直接内存操作     │  │              │
│  │  └─────────────────────────────┘  │              │
│  └───────────────────────────────────┘              │
│                                                     │
└─────────────────────────────────────────────────────┘
```

### 两种 Buffer 的创建

```java
// 堆内 Buffer（默认）
ByteBuf heapBuffer = Unpooled.buffer(1024);

// 堆外 Buffer（Direct）
ByteBuf directBuffer = Unpooled.directBuffer(1024);

// Netty 会自动选择（基于传输类型）
// NIO 传输 → 默认使用 Direct Buffer（减少一次拷贝）
```

### 堆外内存是如何创建的

Java 通过 `sun.misc.Unsafe` 类调用操作系统内核的系统调用来分配堆外内存。

#### 底层调用链

```
ByteBuffer.allocateDirect(1024)
  → new DirectByteBuffer(1024)
    → unsafe.allocateMemory(1024)     // Java 层：Unsafe 方法
      → OS mmap(1024)                 // Linux 内核：分配 native 内存
        → 返回一个 long 类型的地址
```

#### 核心机制

```java
// DirectByteBuffer 的核心字段（简化版）
public class DirectByteBuffer extends ByteBuffer {
    final long address;  // ← native 内存的起始地址
    final long capacity; // ← 分配的字节数

    DirectByteBuffer(int cap) {
        this.address = unsafe.allocateMemory(cap);  // ← 系统调用 mmap
        unsafe.setMemory(address, cap, (byte) 0);   // ← 清零
        this.capacity = cap;
    }
}
```

**关键点**：Java 对象 `DirectByteBuffer` 本身很小（存放在 JVM 堆上），只是一个 **"句柄"**。真正的数据存放在 `address` 字段指向的 native 内存中（JVM 堆外）。

#### 内存布局

```
┌────────────────────────────────────────────────────────┐
│  JVM 堆上（Java 对象，很小）                            │
│                                                        │
│  ┌──────────────────────────┐                         │
│  │ DirectByteBuffer         │                         │
│  │  .address = 0x7f8a2000L │──── 指针 ────► native 内存
│  │  .capacity = 1024        │            (JVM 堆外)   │
│  └──────────────────────────┘                         │
│                                                        │
└────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────┐
│  Native 内存（OS 管理，JVM 堆外）                       │
│                                                        │
│  ┌───────────────────────────────────┐                 │
│  │  0x7f8a2000 ~ 0x7f8a2400           │                 │
│  │  [数据 1024 字节]                    │                 │
│  └───────────────────────────────────┘                 │
│                                                        │
│  ⚠️ GC 不知道这块内存的存在！                             │
└────────────────────────────────────────────────────────┘
```

Netty 内部通过 `PlatformDependent` 统一封装了不同平台的堆外内存分配，核心仍然是 `Unsafe.allocateMemory()`（分配）+ `Unsafe.freeMemory()`（释放）。

### 对比

| 维度 | 堆内 Buffer | 堆外 Buffer（Direct） |
|------|-------------|---------------------|
| **存放位置** | JVM 堆内 | JVM 堆外（OS native 内存） |
| **分配方式** | JVM 内部分配 | `Unsafe.allocateMemory()` → OS `mmap()` |
| **Java 对象** | 对象本身 = 数据 | 对象 = 句柄（很小），数据在 native |
| **GC 压力** | 有（GC 需要扫描） | 无（GC 不知道它的存在） |
| **创建速度** | 快 | 慢（需要 OS 系统调用） |
| **访问速度** | 快（直接 JVM 内存访问） | 稍慢（通过 `Unsafe.getByte()` 访问） |
| **Socket 传输** | 需要拷贝到堆外再发 | 零拷贝（直接发给 OS） |
| **释放方式** | GC 自动回收 | **必须手动 `release()`** |

### ⚠️ 堆外内存泄漏

```java
// 堆外内存必须手动释放！
ByteBuf buf = Unpooled.directBuffer(1024);
// 使用 buf...
buf.release();  // 🔑 必须释放，否则内存泄漏！

// 在 Netty 中，Pipeline 会自动释放 Inbound 消息
// 但如果你在 Handler 中复制了引用，需要手动释放
```

#### 三层释放保障

```
┌────────────────────────────────────────────────────────┐
│              堆外内存释放保障                              │
├────────────────────────────────────────────────────────┤
│                                                        │
│  第一层（最可靠）：手动 release()                         │
│    buf.release()                                       │
│    → refCnt 减 1，归零时调用 unsafe.freeMemory()        │
│    → freeMemory() 内部调用 OS munmap()，释放 native      │
│    → ✅ 推荐方式，时机可控                                │
│                                                        │
│  第二层（备用）：Cleaner/Reference 机制                   │
│    DirectByteBuffer 被 GC 回收时，Cleaner 自动触发       │
│    → 但 GC 回收时间不可控                                │
│    → 大量堆外内存未及时释放时可能 OOM                     │
│    → ⚠️ 不可依赖，仅作兜底                               │
│                                                        │
│  第三层（最后防线）：进程退出                              │
│    → OS 回收所有 native 内存                             │
│    → 意味着程序运行期间泄漏的内存直到进程退出才释放        │
│                                                        │
└────────────────────────────────────────────────────────┘
```

#### 为什么必须手动释放？

```
堆内内存：
  Java 对象 → 无引用时 → GC 回收 → 内存释放 ✅
  （GC 知道所有堆内对象的存在）

堆外内存：
  Java 对象（句柄）→ 无引用时 → GC 回收句柄
  → 但 native 内存还在！GC 不知道它的存在 ❌
  → 必须通过 Cleaner 或手动 release() 释放
  → Netty 用 refCnt 管理，refCnt=0 时释放
```

**规则总结**：
- **Netty 创建的入站消息**：不用管，Pipeline 会自动 release
- **你自己 `new` 的 Buffer**：用完后必须 `release()`
- **传给其他地方的 Buffer**：`retain()` 增加引用，对方用完 `release()`

#### `release()` 内部做了什么

```
buf.release()
  │
  ▼
ReferenceCounted.release()
  │
  ▼
refCnt.decrementAndCheck()    // 引用计数原子减 1
  │
  ├── refCnt > 0  →  返回，什么也不做
  │                  （还有其他引用，不能释放）
  │
  └── refCnt == 0 →  调用 deallocate()
```

`refCnt` 是一个原子整数，多个线程同时 release 也不会出错（`compareAndSet` 保证线程安全）。

#### `deallocate()` 的两种行为

是否池化决定了一切：

```
PooledByteBuf（默认，已池化）:

  deallocate()
    │
    ▼
  归还内存块到内存池（Chunk）
    │
    ▼
  标记为"空闲可复用"
    │
    ▼
  不调用 unsafe.freeMemory()
  不调用 OS munmap()
  native 内存仍然存在，只是不再"被使用"
  ── 这就是池化的本质：内存不释放，下次复用 ──

UnpooledByteBuf（未池化）:

  deallocate()
    │
    ▼
  unsafe.freeMemory(address)
    │
    ▼
  OS munmap() 系统调用
    │
    ▼
  native 内存真正归还给操作系统
```

| 维度 | Pooled（已池化） | Unpooled（未池化） |
|------|----------------|------------------|
| `release()` 做了什么 | 归还到池 | 释放 native 内存 |
| 是否调用 `munmap` | ❌ 不调用 | ✅ 调用 |
| native 内存 | 仍存在，标记为空闲 | 被 OS 回收 |
| 下次 `allocate` | 从池直接拿，零系统调用 | 重新 `mmap` 系统调用 |
| 性能 | ✅ 极快 | ❌ 慢 |

#### 完整执行链路

```
buf.release()
  → refCnt: 1 → 0
    → deallocate()
      → 池化：归还 Chunk（不释放 native）
      → 未池化：unsafe.freeMemory() → OS munmap()
```

这也是为什么 Netty 默认启用内存池——池化 Buffer 的 `release()` 只是一次"归还标记"操作，不需要任何系统调用；而未池化的每次 `release()` 都要触发 `munmap`，在高并发下会成为严重瓶颈。

## 四、引用计数（Reference Counting）

```
ByteBuf 的引用计数模型：

refCnt = 0  →  内存已释放，不可用
refCnt = 1  →  正常状态
refCnt > 1  →  被多处引用
```

```java
ByteBuf buf = Unpooled.buffer(1024);

buf.refCnt();         // = 1，初始引用计数

buf.retain();         // refCnt = 2，增加引用
buf.retain(3);        // refCnt = 5，增加 3 个引用

buf.release();        // refCnt = 4，减少 1 个引用
buf.release(4);       // refCnt = 0，释放内存！
```

### 自动释放 vs 手动释放

```java
// 情况 1：Inbound 消息（自动释放）
public void channelRead(ChannelHandlerContext ctx, Object msg) {
    ByteBuf buf = (ByteBuf) msg;
    // 读取数据...
    // Netty 会自动 release(msg)，无需手动处理
}

// 情况 2：自己创建的 Buffer（必须手动释放）
ByteBuf buf = Unpooled.buffer(1024);
// 使用...
buf.release();  // 🔑 必须释放！

// 情况 3：传递给下游的 Buffer
public void channelRead(ChannelHandlerContext ctx, Object msg) {
    ByteBuf buf = (ByteBuf) msg;
    buf.retain();  // 🔑 增加引用，因为要传给其他地方
    ctx.fireChannelRead(buf);  // 传给下一个 Handler
    // 注意：此时引用计数 = 2
    // 下游消费完后会 release 一次
    // 你需要在合适的时机 release 另一次
}
```

## 五、内存池（PooledByteBufAllocator）

```
Netty 默认使用内存池，减少内存分配和 GC 压力：

┌─────────────────────────────────────────────────────┐
│              PooledByteBufAllocator                    │
│                                                      │
│  内存页 (Page = 8KB)                                 │
│  ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐                  │
│  │Chunk│ │Chunk│ │Chunk│ │Chunk│  (每个 Chunk      │
│  │8KB  │ │8KB  │ │8KB  │ │8KB  │   = 16 个 Page)  │
│  └──┬──┘ └──┬──┘ └──┬──┘ └──┬──┘                  │
│     │        │        │        │                     │
│     ▼        ▼        ▼        ▼                     │
│  子页 (SubPage) 分配策略：                            │
│  512B | 256B | 128B | 64B | 32B | 16B              │
│  小块内存从 SubPage 分配，大块从 Page 分配           │
└─────────────────────────────────────────────────────┘
```

### 内存池的好处

```
不使用内存池：
  每次 new ByteBuf → 分配内存 → 用完后 GC → 下次又分配...
  → 频繁 GC，性能差

使用内存池：
  第一次分配 → 从池借内存 → 用完归还池 → 下次从池借
  → 减少 GC，性能提升
```

### 配置内存池

```java
// 默认就是 PooledAllocator
EventLoopGroup group = new NioEventLoopGroup();
// 内部使用 PooledByteBufAllocator.DEFAULT

// 如果需要关闭内存池（不推荐）
EventLoopGroup group = new NioEventLoopGroup(1,
    new DefaultThreadFactory("nio"),
    SelectorProvider.provider(),
    Epoll.ensureAvailability(),
    new DefaultEventExecutor(null, 0, null),
    null,
    UnpooledByteBufAllocator.DEFAULT  // 不池化
);
```

#### 内存池对堆外内存更关键

```java
// Netty 默认使用 PooledByteBufAllocator
// 同时对堆内和堆外内存做池化

PooledByteBufAllocator
  ├── PooledHeapByteBuf     ← 池化的堆内 Buffer
  └── PooledDirectByteBuf   ← 池化的堆外 Buffer
```

**为什么堆外内存更需要池化？**

| 原因 | 说明 |
|------|------|
| **分配昂贵** | 每次 `allocateMemory()` = 一次 OS 系统调用（`mmap`），比堆内分配慢几十到几百倍 |
| **释放昂贵** | 每次 `freeMemory()` = 一次 OS 系统调用（`munmap`），同样昂贵 |
| **不能靠 GC** | GC 不管堆外内存，泄漏风险高，必须及时归还池 |
| **复用更高效** | 池化后只需第一次系统调用，后续从大块内存中切割，零系统调用 |

```
不使用内存池：
  每次需要 Buffer：
    → unsafe.allocateMemory()    (OS 系统调用)
    → 用完 → unsafe.freeMemory() (OS 系统调用)
    → 频繁系统调用，性能极差

使用内存池：
  第一次：allocateMemory() 分配大块内存（如 16MB）
    → 后续：从大块内存中切割小块使用
    → 用完：归还给池（不释放，直接复用）
    → 几乎零系统调用，性能大幅提升
```

Netty 默认使用 `PooledByteBufAllocator`，同时池化堆内和堆外内存。关闭池化（`UnpooledByteBufAllocator`）仅适用于短生命周期应用（如命令行工具），生产环境不建议使用。

## 六、ByteBuf 常用方法速查

| 方法 | 说明 |
|------|------|
| `writeByte/Int/Long/Double()` | 写入数据，writerIndex 后移 |
| `readByte/Int/Long/Double()` | 读取数据，readerIndex 后移 |
| `writeBytes(readableBuf)` | 写入另一个 Buffer 的内容 |
| `readBytes(writableBuf)` | 读取到另一个 Buffer |
| `readableBytes()` | 可读字节数 = writerIndex - readerIndex |
| `writableBytes()` | 可写字节数 = capacity - writerIndex |
| `capacity()` | 总容量 |
| `clear()` | readerIndex=0, writerIndex=0 |
| `discardReadBytes()` | 丢弃已读数据，释放前部空间 |
| `retain()` / `release()` | 引用计数管理 |
| `isReadable()` / `isWritable()` | 是否可读/可写 |
| `slice()` | 创建一个视图（共享底层内存） |
| `duplicate()` | 创建独立索引的视图 |