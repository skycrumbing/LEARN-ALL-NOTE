# Netty 的零拷贝

## 一、什么是零拷贝

```
传统 IO 的数据流转（4 次拷贝 + 3 次上下文切换）：

┌─────────┐     ┌──────────────┐     ┌──────────────┐     ┌─────────┐
│ 磁盘/   │     │ 内核缓冲区    │     │  用户空间     │     │ 内核发送 │
│ 网络    │────►│ (Kernel Buf) │────►│ (User Buffer) │────►│ 缓冲区   │
│ 数据    │     │              │     │              │     │(SendBuf) │
└─────────┘     └──────────────┘     └──────────────┘     └─────────┘
      │               │                     │                   │
      ▼               ▼                     ▼                   ▼
     读入             read()               应用程序             write()
   内核缓冲区       拷贝到用户空间         拷贝到发送缓冲      拷贝到内核
```

```
零拷贝的目标：减少数据在内核态和用户态之间的拷贝次数
```

## 二、Netty 的四种零拷贝方式

| # | 方式 | 说明 |
|---|------|------|
| 1 | `CompositeByteBuf` | 多个 Buffer 逻辑合并，不物理复制 |
| 2 | `ByteBuf.duplicate()` / `slice()` | 视图操作，共享底层内存 |
| 3 | `ByteBuf.transferTo()` | 堆外 Buffer 直接发给 OS，零拷贝 |
| 4 | `FileRegion` | 文件传输直接 `sendfile`，绕过用户空间 |

---

## 三、方式一：CompositeByteBuf（逻辑合并）

```
传统方式：把多个 Buffer 合并成一个

┌─────────┐  ┌─────────┐  ┌─────────┐
│ Header   │  │ Length   │  │ Body     │
│ 4 bytes  │  │ 4 bytes  │  │ N bytes  │
└─────────┘  └─────────┘  └─────────┘
      │            │            │
      ▼            ▼            ▼
  创建一个大 Buffer，把三个 Buffer 的数据逐个复制进去
  → 3 次内存拷贝！

CompositeByteBuf 方式：

┌─────────────────────────────────────────────┐
│         CompositeByteBuf（逻辑合并）          │
│                                              │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐    │
│  │ Header   │  │ Length   │  │ Body     │   │
│  │ (Buf A)  │  │ (Buf B)  │  │ (Buf C)  │   │
│  └─────────┘  └─────────┘  └─────────┘    │
│     三个独立 Buffer，逻辑上视为一个           │
│     没有数据拷贝！                            │
└─────────────────────────────────────────────┘
```

```java
CompositeByteBuf composite = Unpooled.compositeBuffer();

ByteBuf header = Unpooled.copiedBuffer("HDR", CharsetUtil.UTF_8);
ByteBuf length = Unpooled.buffer(4);
length.writeInt(100);
ByteBuf body = Unpooled.copiedBuffer("body data", CharsetUtil.UTF_8);

composite.addComponent(header);  // 没有拷贝，只是记录了引用
composite.addComponent(length);
composite.addComponent(body);

// 现在 composite 就像一个包含全部数据的单一 Buffer
// 读取时自动遍历内部的多个 Buffer
System.out.println(composite.readableBytes());  // 4 + 4 + 9 = 17
```

## 四、方式二：duplicate() / slice()（视图）

```
duplicate()：创建一个新的 ByteBuf，共享底层内存，但索引独立

┌─────────────────────────────────────────────┐
│  原始 ByteBuf                                │
│  [reader=0, writer=10]                      │
│  H E L L O W O R L D                        │
└─────────────────────────────────────────────┘
         │
         ▼ duplicate()
┌─────────────────────────────────────────────┐
│  新 ByteBuf（共享内存，独立索引）             │
│  [reader=0, writer=10]                      │
│  H E L L O W O R L D                        │
│                                              │
│  修改新 Buffer 的数据，原 Buffer 也会变！     │
│  但移动索引互不影响                            │
└─────────────────────────────────────────────┘

slice(offset, length)：创建一个子 Buffer 视图

┌─────────────────────────────────────────────┐
│  原始 ByteBuf                                │
│  H E L L O W O R L D                        │
│  [0,1,2,3,4,5,6,7,8,9,10]                   │
│                    │                         │
│                    ▼ slice(5, 5)             │
└─────────────────────────────────────────────┘
┌─────────────────────────────────────────────┐
│  子 Buffer（slice）                          │
│  W O R L D                                  │
│  [0,1,2,3,4]                                │
└─────────────────────────────────────────────┘
```

```java
ByteBuf original = Unpooled.copiedBuffer("Hello World", CharsetUtil.UTF_8);

// duplicate：共享内存，独立索引
ByteBuf dup = original.duplicate();
dup.writeInt(0);  // 修改 dup 的数据，original 也变
// 但 dup.readerIndex(0) 不影响 original.readerIndex

// slice：截取一段
ByteBuf slice = original.slice(6, 5);
System.out.println(slice.toString(CharsetUtil.UTF_8));  // "World"
```

## 五、方式三：堆外 Buffer 直接发送（NIO transferTo）

```
堆内 Buffer 发数据（2 次拷贝）：

┌─────────┐     ┌──────────────┐     ┌──────────────┐
│  用户态  │────►│  内核发送缓冲  │────►│   网卡       │
│  堆内    │     │              │     │              │
└─────────┘     └──────────────┘     └──────────────┘
    │                  │
    ▼                  ▼
  write()          内核再拷贝一次到 socket
  拷贝到堆外

堆外 Buffer 发数据（1 次拷贝）：

┌─────────┐     ┌──────────────┐     ┌──────────────┐
│  用户态  │────►│   网卡        │
│  堆外    │     │              │
└─────────┘     └──────────────┘
    │
    ▼
  NIO transferTo()
  直接从堆外内存发送到网卡
```

```java
// Netty 内部，当使用 DirectBuffer（堆外）时：
// SocketChannel.write(ByteBuf) → 直接调用 NIO 的 transferTo
// 数据从堆外内存直接发送到内核，无需拷贝到堆内
```

## 六、方式四：FileRegion（文件传输）

```
传统文件传输（多次拷贝）：

磁盘 ──► 内核读缓冲 ──► read() ──► 用户 Buffer ──► write() ──► 内核发送缓冲 ──► 网卡
             │                                      │
             └────────── 2 次内核拷贝 ──────────────┘

FileRegion（sendfile）：

磁盘 ──► 内核缓冲区 ──────────────────────────────► 内核发送缓冲 ──► 网卡
                            │
                            └── OS 内核内部直接传输，绕过用户空间
```

```java
// 在 Netty 的 ChannelHandler 中发送文件
@Override
public void channelActive(ChannelHandlerContext ctx) {
    RandomAccessFile file = new RandomAccessFile("large-file.zip", "r");
    FileRegion region = new DefaultFileRegion(file.getChannel(), 0, file.length());
    ctx.writeAndFlush(region);  // 使用 sendfile，零拷贝传输
}
```

## 七、零拷贝总结

```
┌─────────────────────────────────────────────────────────────┐
│                    零拷贝方式对比                               │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  方式 1: CompositeByteBuf                                    │
│  场景: 协议组装（Header + Length + Body）                    │
│  本质: 逻辑合并，不物理拷贝                                   │
│                                                              │
│  方式 2: duplicate() / slice()                               │
│  场景: 需要多个 Buffer 引用同一段数据                         │
│  本质: 视图，共享底层内存                                     │
│                                                              │
│  方式 3: DirectBuffer + transferTo                           │
│  场景: 网络发送                                               │
│  本质: 堆外内存直接发给 OS，减少一次拷贝                      │
│                                                              │
│  方式 4: FileRegion + sendfile                               │
│  场景: 大文件传输                                             │
│  本质: OS 内核内部直接传输，绕过用户空间                       │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

> **Netty 零拷贝的核心思想**：能逻辑合并就不物理合并，能共享内存就不复制内存，
> 能让 OS 内核直接传输就不经过用户空间。