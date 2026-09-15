# 跳表（Skip List）

> 跳表是一种**用空间换时间的多层链表**，通过"索引层"实现 O(log n) 的搜索、插入、删除。
> 它是 Redis ZSet、LevelDB/RocksDB MemTable 的核心数据结构。

---

## 目录

1. [为什么需要跳表](#一为什么需要跳表)
2. [跳表的结构](#二跳表的结构)
3. [搜索操作](#三搜索操作)
4. [插入操作](#四插入操作)
5. [删除操作](#五删除操作)
6. [时间复杂度分析](#六时间复杂度分析)
7. [跳表 vs 红黑树](#七跳表-vs-红黑树)
8. [完整 Java 实现](#八完整-java-实现)

---

## 一、为什么需要跳表

### 链表的痛点

```
有序链表：搜索只能从头遍历，O(n)

  head → 1 → 5 → 9 → 17 → 25 → 33 → 41 → null

  搜索 33：必须走 6 步
```

### 加索引层 → 跳表的诞生

```
给部分节点建"快车道"，一层一层向上抽取：

第3层(顶层): head ────────────────────────→ 33 ──→ null
                │                            │
第2层:       head ──────────→ 17 ────────────→ 33 ──→ null
                │              │               │
第1层(底层): head → 1 → 5 → 9 → 17 → 25 → 33 → 41 → null

搜索 33：
  第3层: head → 33   ✅ 找到，只走 2 步！

搜索 25：
  第3层: head → 33   33 > 25，退回，下一层
  第2层: 17 → 33     33 > 25，退回，下一层
  第1层: 17 → 25     ✅ 找到

核心思想：
  上层是下层的"索引"，像高速公路的快速路 → 普通路逐级下沉
  每层过滤掉一半元素 → 整体 O(log n)
```

> **一句话理解**：跳表 = 给有序链表加了 B+树式的"多级索引"，但用随机数决定谁上索引层。

---

## 二、跳表的结构

```java
// 节点结构
class Node {
    int value;
    Node[] next;    // next[i] = 该节点在第 i 层的下一个节点（灵活层数！）

    Node(int value, int level) {
        this.value = value;
        this.next = new Node[level];
    }
}
```

```
关键设计：每个节点的层数不同

  第3层:      head ───────────────────→ 33(null)
                 │                       │
  第2层:      head ──────→ 17 ──────────→ 33
                 │           │            │
  第1层:      head → 1 → 5 → 17 → 25 → 33 → 41
                              │
              17 有 2 层      │
              33 有 3 层     25 只有 1 层

层数怎么定？—— 抛硬币（随机化）：

  int randomLevel() {
      int level = 1;
      while (random() < 0.5) {   // 每次抛硬币，正面则升一层
          level++;
      }
      return level;
  }

  概率分布：
    层数 1 : 50%
    层数 2 : 25%
    层数 3 : 12.5%
    ...
    → 平均每层节点数是上一层的 1/2，天然形成"金字塔"
```

### 常见误区澄清

#### 误区 1："插到第几层"——不存在选定层，抛硬币决定的是【高度】

```
❌ 错误理解：
   插入时"选中"某一层（比如第 2 层），然后从该层补到底层

✅ 正确理解：
   randomLevel() 返回的是节点的【高度】k，
   节点自动占据第 1 到第 k 层的所有位置。

   每个节点都是一座从地面（第 1 层）盖起的塔，
   抛硬币只决定塔盖多高，不决定盖在哪。
```

```java
// randomLevel() 返回的是高度，不是位置！
int level = randomLevel();          // 假设 = 2
Node newNode = new Node(value, 2); // 这个节点占据第 1、2 两层

for (int i = 0; i < newLevel; i++) {   // ← 从第 1 层开始接线，直到第 newLevel 层
    newNode.next[i] = update[i].next[i];
    update[i].next[i] = newNode;
}
// 循环范围 [0, newLevel)，即第 1~newLevel 层全部接入
// 不存在"只出现在第 2 层但缺席第 1 层"的节点
```

**为什么必须"从底往上连续占层"，不能跳跃？**

```
原因 1：搜索算法是自上而下逐层下沉的

  第3层: head ──────────────→ 55
  第2层:      ??? ← 如果 28 只在第 3 层出现会怎样？
  第1层: ... → 20 → 30 ...

  搜索路径：高层找到踪迹后要"下沉"继续精确导航
  如果中间某层突然没有这个节点，下沉时就会丢失目标
  → 整个结构失去意义


原因 2：第 1 层必须包含全部元素

  第 1 层是完整的有序链表，这是：
  ├── 范围查询的基础（ZRANGEBYSCORE 扫的就是这层）
  └── 数据本体所在（上层只是索引，不存额外副本）
```

#### 误区 2："多层 = 多份数据拷贝"？上层不存数据的副本

```
很多人以为跳表长这样（错误想象）：

  第3层: [33 的副本]
  第2层: [17 的副本] [33 的副本]
  第1层: [1][5][9][17][25][33][41]

实际是这样（正确）：

  第3层: ─────────────→ ┌────┐
                        │ 33 │ ← 同一个对象
  第2层: ──→ ┌────┐ ──→ │    │
             │ 17 │      │    │
  第1层: ──→ │    │ ──→ │    │
       ┌───→ └────┘      └────┘
       │ [1][5][9]

  17 和 33 各只有一个对象实例
  多出来的只是几个 next 指针（8 字节/个）

所以"多层"的代价 = 几个额外的指针
                ≠ 多份数据拷贝
```

#### 空间账本：到底多用多少空间？

跳表确实是**空间换时间**，但代价有精确上界：

```
每个节点的期望指针数：

  P(层数 ≥ 1) = 1        → 1 个指针
  P(层数 ≥ 2) = 1/2      → 0.5 个指针
  P(层数 ≥ 3) = 1/4      → 0.25 个指针
  P(层数 ≥ 4) = 1/8      → 0.125 个指针
  ...

  E[总指针数] = 1 + 1/2 + 1/4 + 1/8 + ...
             = 1/(1-0.5)
             = 2 个/节点


对比红黑树：

┌────────────┬─────────────────────────────────┐
│ 跳表节点    │ value + next[] 数组（期望长度 2）  │
│            │ + Java 数组对象头 ~16B 额外开销    │
├────────────┼─────────────────────────────────┤
│ 红黑树节点  │ value + left + right + color     │
│            │ （+ parent，视实现而定）           │
└────────────┴─────────────────────────────────┘

结论：跳表平均每个节点多出约 0~1 个指针的开销
     总空间仍然是 O(n)，常数因子略大
     并不是"每层复制一份数据"那种爆炸式增长
```

#### 小数指针从哪来？—— 期望值的含义

> 上面的"0.5 个指针""0.125 个指针"不是某个真实节点有半根指针，
> 而是**数学期望（全体平均）**。单个节点的指针数永远是整数。

```
任何一个具体的节点：
  要么有第 2 层的 next 指针（1 根）
  要么没有（0 根）
  绝对不存在"半根指针"

但 0.5 是什么？
  —— 是"每个节点平摊下来的平均值"
```

**小数的来源：抛硬币的概率**

```java
int randomLevel() {
    int level = 1;
    while (random() < 0.5) {   // 正面 → 再升一层
        level++;
    }
    return level;
}
```

```
一个节点要拥有第 2 层指针，条件是第一次抛硬币出正面：

P(层数 ≥ 1) = 1               ← 所有节点至少在第 1 层，必然事件
P(层数 ≥ 2) = 1/2             ← 第 1 次抛出正面的概率
P(层数 ≥ 3) = 1/2 × 1/2       ← 连续两次正面
P(层数 ≥ 4) = 1/2 × 1/2 × 1/2 ← 连续三次正面

规律：P(层数 ≥ k) = (1/2)^(k-1)
```

**用 8 个节点算一笔具体的账**

```
n = 8 个节点（运气完全符合期望时）：

  有第 1 层指针的：8 个          （人人都有）
  有第 2 层指针的：8 × 1/2  = 4 个
  有第 3 层指针的：8 × 1/4  = 2 个
  有第 4 层指针的：8 × 1/8  = 1 个
  有第 5 层指针的：8 × 1/16 ≈ 0~1 个（期望 0.5）

总指针数：
  第 1 层贡献: 8
  第 2 层贡献: 4
  第 3 层贡献: 2
  第 4 层贡献: 1
  ─────────────────
  合计        ≈ 15 ~ 16 根

平摊到每个节点：
  16 ÷ 8 = 2 根/节点
```

回头看表格就通了：

```
P(层数 ≥ 2) = 1/2 → 0.5 个指针

意思是：
  全体 n 个节点中，有 n/2 个节点各带一根"第 2 层指针"
  平摊下来 = 每个节点贡献了 0.5 根

它描述的是"分摊比例"，不是任何单个节点的物理结构。
就像"中国人均 0.x 辆车" —— 没有人开半辆车，
但总数 ÷ 人口 就是小数。
```

**为什么能加总成几何级数**

```
E[每个节点的总指针数]
  = Σ P(层数 ≥ k)          对 k = 1, 2, 3, ...
  = 1 + 1/2 + 1/4 + 1/8 + ...
  = 1 / (1 - 0.5)          ← 等比数列求和公式 a/(1-r)
  = 2

这就是"跳表每节点平均 2 个指针"的全部来源。

顺带验证 Redis 选 p=0.25 的账：
  E[指针数] = 1 + 1/4 + 1/16 + ...
           = 1/(1-0.25)
           = 4/3 ≈ 1.33 根/节点     ← 比 p=0.5 省 1/3 指针
  代价：每层只剩 1/4 元素，搜索要多下沉几层
```

**空间还可以用参数 p 来调节**：

```
randomLevel() 中的晋升概率 p 是可调的旋钮：

p = 0.5（经典值）:
  E[指针数/节点] = 2
  每层过滤一半元素，搜索比较次数少

p = 0.25（省内存）:
  E[指针数/节点] = 1/(1-0.25) ≈ 1.33
  但层数分布更平，搜索要多走几步

Redis 的选择：p = 0.25
  ZSet 元素往往很大（member 字符串本身可能几十字节）
  相比之下省下的指针开销更划算
  → 这就是"通过调整 p 在时间和空间之间权衡"的具体含义
```

---

## 三、搜索操作

### 算法：从最高层开始，能跳就跳，不能跳就下沉

```java
Node search(int target) {
    Node curr = head;
    // 从最高层开始
    for (int i = maxLevel - 1; i >= 0; i--) {
        // 在当前层向右走，直到下一个节点 >= target
        while (curr.next[i] != null && curr.next[i].value < target) {
            curr = curr.next[i];
        }
        // 下沉到下一层
    }
    // 到底后，检查下一个是否就是目标
    curr = curr.next[0];
    return (curr != null && curr.value == target) ? curr : null;
}
```

### 完整搜索过程演示

```
跳表结构：

第3层: head ──────────────────────────→ 55 ──→ null
          │                              │
第2层: head ──────→ 15 ─────────────────→ 55 ──→ null
          │             │                  │
第1层: head → 5 → 10 → 15 → 20 → 30 → 40 → 55 → 60 → null

搜索 40：

第3层: head → 55        55 > 40，不能前进，下沉 ↓
第2层: head → 15 → 55   15 < 40 前进；55 > 40 停止，下沉 ↓
第1层: 15 → 20 → 30 → 40 ✅ 找到！

对比普通链表：要走 7 步
跳表：走了 2 + 2 + 4 = 但比较次数明显减少
      实际移动步数 ≈ log n 量级
```

---

## 四、插入操作

插入分两步：**找到插入位置** + **随机层数并接链**。

```java
void insert(int value) {
    // 1. 抛硬币决定新节点的层数
    int newLevel = randomLevel();

    // 2. 记录每层的插入位置（update 数组）
    Node[] update = new Node[MAX_LEVEL];
    Node curr = head;

    for (int i = maxLevel - 1; i >= 0; i--) {
        while (curr.next[i] != null && curr.next[i].value < value) {
            curr = curr.next[i];
        }
        update[i] = curr;   // 记录第 i 层的前驱节点
    }

    // 3. 已存在则不插入
    if (curr.next[0] != null && curr.next[0].value == value) {
        return;
    }

    // 4. 创建新节点，逐层接入
    if (newLevel > maxLevel) maxLevel = newLevel;
    Node newNode = new Node(value, newLevel);

    for (int i = 0; i < newLevel; i++) {
        newNode.next[i] = update[i].next[i];   // 新节点指向后继
        update[i].next[i] = newNode;           // 前驱指向新节点
    }
}
```

### 插入过程图解

```
在跳表中插入 28，假设 randomLevel() = 2：

第3层: head ──────────────────────────→ 55
          │                              │
第2层: head ──────→ 15 ─────────────────→ 55
          │             │                  │
第1层: ... → 20 → 30 → 40 → ...

Step 1: 从上往下找每层的前驱
  第2层前驱: 15（15.next = 55 > 28）
  第1层前驱: 20（20.next = 30 > 28）
  update = [20, 15]

Step 2: 新节点 28（2 层），逐层接线

  第2层: 15 → [28] → 55
  第1层: 20 → [28] → 30

结果：

第3层: head ─────────────────────────────→ 55
          │                                │
第2层: head ──────→ 15 → 28 ─────────────→ 55
          │             │    │              │
第1层: ... → 20 → 28 → 30 → 40 → ...

注意：不需要任何旋转和再平衡！
     随机层数从概率上保证了树的平衡性
```

---

## 五、删除操作

删除同样先定位，再把该节点从**所有出现的层**中摘除。

```java
void remove(int value) {
    Node[] update = new Node[MAX_LEVEL];
    Node curr = head;

    // 1. 和插入一样，找每层的前驱
    for (int i = maxLevel - 1; i >= 0; i--) {
        while (curr.next[i] != null && curr.next[i].value < value) {
            curr = curr.next[i];
        }
        update[i] = curr;
    }

    // 2. 目标节点不存在
    curr = curr.next[0];
    if (curr == null || curr.value != value) {
        return;
    }

    // 3. 从每一层摘除该节点
    for (int i = 0; i < maxLevel; i++) {
        if (update[i].next[i] == curr) {   // 该层确实有这个节点
            update[i].next[i] = curr.next[i];
        }
    }

    // 4. 如果最高层空了，降低 maxLevel
    while (maxLevel > 1 && head.next[maxLevel - 1] == null) {
        maxLevel--;
    }
}
```

```
删除 28：

第3层: head ─────────────────────────────→ 55
          │                                │
第2层: head ──────→ 15 → 28 ─────────────→ 55
          │             ↑    │              │
第1层: ... → 20 → 28 → 30 → 40 → ...

摘除动作（无需修复平衡！）：
  第2层: 15 → 55      （跨过 28）
  第1层: 20 → 30      （跨过 28）

对比红黑树删除：需要"双倍黑"+ 四种情况修复
跳表删除：直接摘除，零维护成本
```

---

## 六、时间复杂度分析

```
为什么期望复杂度是 O(log n)？

关键：随机层数让每层节点数期望减半

  第 k 层的期望节点数 ≈ n / 2^k
  从顶层到底层的路径长度 ≈ log₂n

概率证明（直观版）：
  一个节点有 2 层的概率 = 1/4
  一个节点有 3 层的概率 = 1/8
  ...
  这和完美二叉树的节点分布完全同构！

┌──────────┬──────────────┬──────────────────┐
│ 操作      │ 时间复杂度     │ 说明               │
├──────────┼──────────────┼──────────────────┤
│ 搜索      │ O(log n) 期望 │ 最坏 O(n)，概率极低 │
│ 插入      │ O(log n) 期望 │ 定位 + 接线         │
│ 删除      │ O(log n) 期望 │ 定位 + 摘除         │
│ 范围查询   │ O(log n + m) │ 定位起点 + 链表顺序扫│
├──────────┼──────────────┼──────────────────┤
│ 空间复杂度 │ O(n) 期望     │ 每个节点平均 2 个指针│
└──────────┴──────────────┴──────────────────┘

注意：跳表是"概率平衡"，不是"强制平衡"
  极端情况下（运气极差）可能退化，但概率随 n 增大指数级衰减
  工程上可以设置 MAX_LEVEL 封顶（Redis 是 32 / 64）
```

---

## 七、跳表 vs 红黑树

这是面试高频题。结论先行：**功能等价（都是有序结构），工程取舍不同。**

### 对比总表

| 维度 | 跳表 | 红黑树 |
|------|------|--------|
| 搜索 | O(log n) 期望 | O(log n) 最坏保证 |
| 插入 | O(log n)，只改前后指针 | O(log n)，变色 + 最多 3 次旋转 |
| 删除 | O(log n)，直接摘除 | O(log n)，双倍黑 + 四种情况修复 |
| 范围查询 | ⭐ 天然支持，底层就是有序链表 | 需要中序遍历，实现繁琐 |
| 平衡保证 | 概率平衡（极小概率退化） | 强制平衡（严格最坏 O(log n)） |
| 空间开销 | 每节点平均 ~2 个指针 | 每节点 2 指针 + 1 颜色位 |
| 并发友好度 | ⭐ 高（局部锁即可，CAS 友好） | 低（旋转会波及整棵树） |
| 实现难度 | ⭐ 简单（链表思维，~200 行） | 复杂（旋转+变色，~400 行） |
| 内存局部性 | 差（指针跳跃，缓存不友好） | 同样差（也是指针结构） |

### 跳表的优势

```
优势 1：范围查询天然高效
═══════════════════════════════════════

  Redis ZRANGEBYSCORE leaderboard 100 500

  跳表：定位到 100 所在节点 → 底层链表一路向右扫
        就是一个普通的链表遍历 ✅

  红黑树：中序遍历，需要栈/递归或线索化，代码复杂


优势 2：实现极其简单
═══════════════════════════════════════

  跳表：本质是有序链表 + 多级索引
        插入删除就是改指针，没有旋转概念

  红黑树：insertFixup 三种情况 × 左右对称 = 6 分支
         deleteFixup 四种情况 × 左右对称 = 8 分支
         边界条件极多，容易写错


优势 3：并发场景更友好
═══════════════════════════════════════

  跳表插入：只修改新节点及其前驱的后继指针
    → 锁粒度可以很小，甚至无锁（Java ConcurrentSkipListMap 就是 lock-free）

  红黑树插入：旋转会改变祖先链上的父子关系
    → 影响范围大，难以细粒度加锁


优势 4：层数灵活，按需分配
═══════════════════════════════════════

  热点数据可以被"人为"提升层数（虽然标准实现不用这招）
  结构本身支持动态伸缩
```

### 跳表的劣势

```
劣势 1：没有严格的最坏复杂度保证
═══════════════════════════════════════

  跳表：O(log n) 是期望值，理论上可能退化到 O(n)
        （虽然概率低到可以忽略）

  红黑树：数学证明的最坏 O(log n)
        对延迟敏感的硬实时系统，这个保证很重要


劣势 2：空间常数略大
═══════════════════════════════════════

  跳表：每个节点要存一个指针数组
        数组长度随机（1, 2, 3...），平均 ~2
        还有数组对象头的额外开销

  红黑树：固定 2 个子指针 + 1 个颜色位（可压缩进指针低位）


劣势 3：CPU 缓存不友好（两者都有的问题，跳表更甚）
═══════════════════════════════════════

  跳表搜索：高层跳跃时，每次都是不连续内存访问
  B+树反而因节点紧凑而缓存更友好
```

### 为什么 Redis ZSet 选跳表而不是红黑树？

```
Redis 作者 antirez 的理由（原话大意）：

  1. 范围查询需求：ZSet 核心操作是 ZRANGE/ZRANGEBYSCORE，
     跳表的底层有序链表天然支持

  2. 实现简单：调试容易、代码可读，redis 代码追求简洁

  3. 无旋转：并发扩展更容易

  4. 内存可控：可以通过调整 p（晋升概率）控制索引密度，
     在时间和空间之间权衡

  补充：Redis 还给每个节点维护了 span（跨度）字段，
       可以 O(log n) 按排名查询 —— ZRANK 命令的实现基础
```

### 各场景真实选型回顾

| 场景 | 数据结构 | 原因 |
|------|---------|------|
| JDK `TreeMap` | 红黑树 | 单机内存，需要严格最坏保证 |
| JDK `ConcurrentSkipListMap` | 跳表 | 并发场景，跳表无锁化容易 |
| Redis ZSet | 跳表 | 范围查询 + 实现简单 + span 支持排名 |
| Linux 内核 CFS 调度器 | 红黑树 | 内核环境稳定压倒一切 |
| LevelDB/RocksDB MemTable | 跳表 | 写入频繁，无旋转开销 |

---

## 八、完整 Java 实现

```java
import java.util.Random;

public class SkipList {

    private static final int MAX_LEVEL = 32;
    private static final double P = 0.5;

    static class Node {
        int value;
        Node[] next;

        Node(int value, int level) {
            this.value = value;
            this.next = new Node[level];
        }
    }

    private final Node head = new Node(Integer.MIN_VALUE, MAX_LEVEL);
    private int maxLevel = 1;
    private final Random random = new Random();
    private int size = 0;

    // 抛硬币决定层数
    private int randomLevel() {
        int level = 1;
        while (level < MAX_LEVEL && random.nextDouble() < P) {
            level++;
        }
        return level;
    }

    // ===== 搜索 =====
    public boolean search(int target) {
        Node curr = head;
        for (int i = maxLevel - 1; i >= 0; i--) {
            while (curr.next[i] != null && curr.next[i].value < target) {
                curr = curr.next[i];
            }
        }
        curr = curr.next[0];
        return curr != null && curr.value == target;
    }

    // ===== 插入 =====
    public void insert(int value) {
        Node[] update = new Node[MAX_LEVEL];
        Node curr = head;

        for (int i = maxLevel - 1; i >= 0; i--) {
            while (curr.next[i] != null && curr.next[i].value < value) {
                curr = curr.next[i];
            }
            update[i] = curr;
        }

        if (curr.next[0] != null && curr.next[0].value == value) {
            return;  // 已存在
        }

        int newLevel = randomLevel();
        if (newLevel > maxLevel) {
            maxLevel = newLevel;
        }

        Node newNode = new Node(value, newLevel);
        for (int i = 0; i < newLevel; i++) {
            newNode.next[i] = update[i].next[i];
            update[i].next[i] = newNode;
        }
        size++;
    }

    // ===== 删除 =====
    public void remove(int value) {
        Node[] update = new Node[MAX_LEVEL];
        Node curr = head;

        for (int i = maxLevel - 1; i >= 0; i--) {
            while (curr.next[i] != null && curr.next[i].value < value) {
                curr = curr.next[i];
            }
            update[i] = curr;
        }

        curr = curr.next[0];
        if (curr == null || curr.value != value) {
            return;  // 不存在
        }

        for (int i = 0; i < maxLevel; i++) {
            if (update[i].next[i] == curr) {
                update[i].next[i] = curr.next[i];
            }
        }

        while (maxLevel > 1 && head.next[maxLevel - 1] == null) {
            maxLevel--;
        }
        size--;
    }

    // ===== 范围查询（跳表的招牌能力）=====
    public void rangeQuery(int lo, int hi) {
        Node curr = head;
        for (int i = maxLevel - 1; i >= 0; i--) {
            while (curr.next[i] != null && curr.next[i].value < lo) {
                curr = curr.next[i];
            }
        }
        curr = curr.next[0];   // 到达第一个 >= lo 的节点
        while (curr != null && curr.value <= hi) {
            System.out.print(curr.value + " ");
            curr = curr.next[0];   // 底层链表顺序扫描
        }
        System.out.println();
    }

    public void print() {
        for (int i = maxLevel - 1; i >= 0; i--) {
            System.out.print("L" + (i + 1) + ": head");
            Node curr = head.next[i];
            while (curr != null) {
                System.out.print(" → " + curr.value);
                curr = curr.next[i];
            }
            System.out.println(" → null");
        }
    }
}
```

### 使用示例

```java
public class Main {
    public static void main(String[] args) {
        SkipList list = new SkipList();

        int[] values = {5, 10, 15, 20, 30, 40, 55, 60};
        for (int v : values) {
            list.insert(v);
        }

        list.print();                    // 查看随机生成的多层结构
        System.out.println(list.search(30));   // true
        System.out.println(list.search(99));   // false

        list.rangeQuery(15, 40);         // 15 20 30 40 ← 范围查询

        list.remove(20);
        System.out.println(list.search(20));   // false
    }
}
```
