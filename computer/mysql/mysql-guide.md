# MySQL 全面学习指南

> 涵盖：数据存储 | 排序 | 事务 | 一致性 | 查询优化
> 每部分包含：算法原理 + 底层机制 + 代码实战

---

## 一、数据存储

### 1.1 为什么用 B+ 树？

MySQL（InnoDB）用 **B+ 树** 作为索引的底层数据结构，而不是二叉树、哈希表或红黑树。原因：

```
磁盘 I/O 是数据库性能的最大瓶颈。

一次磁盘 I/O 读取一个"页"（InnoDB 默认 16KB）
→ 索引结构的目标：用尽可能少的 I/O 次数找到目标数据
→ 树越矮（层数越少），需要的 I/O 次数越少

B+ 树相比其他结构：

  B+ 树 vs 二叉树：
    → 二叉树每节点 1 个键 → 树高 log₂(n)，n=1亿行时树高 ≈ 27 层
    → B+ 树每节点可容纳 100~200 个键（16KB 页）→ 树高仅 3~4 层
    → I/O 次数从 27 次降到 3~4 次

  B+ 树 vs 哈希表：
    → 哈希表 O(1) 查找，但无法范围查询（"找 100~200 之间的所有值"）
    → B+ 树天然支持范围查询（叶子节点链表）

  B+ 树 vs 红黑树：
    → 红黑树每节点 1 个键 → 树太高
    → B+ 树是多路平衡树 → 树矮 → I/O 少
```

### 1.1.1 为什么 B+ 树每个节点能容纳 100~200 个键？

> ❓ **问题 1**：为什么 B+ 树可以每层容纳那么多节点，而二叉树只能 1 个？

答案要从磁盘的物理结构讲起。

#### 磁盘不是按"字节"读取的

```
磁盘的最小 I/O 单位是"扇区"，不是"字节"：

  传统磁盘：1 个扇区 = 512 字节
  SSD/现代磁盘：1 个扇区 = 4KB

  无论你要读 1 字节还是 1MB，磁盘都按扇区为单位读取
  → 读 1 字节的代价 = 读 1 个扇区的代价

  这就像：去书店买书，书店按"整本书"卖，不按"字"卖
  你买 1 个字，也得付整本书的钱
```

#### 数据库的"页" = 利用了这个特性

```
既然磁盘按扇区读取，那就尽量每次读"更多有用的数据"：

  InnoDB 把 16KB 的数据打包成一个"页"（Page）
  一次磁盘 I/O 读取 1 个页 = 16KB

  为什么是 16KB？
    → 16KB = 32 个 512 字节扇区
    → 一次 I/O 读了 32 个扇区 → 充分利用了"读了就白读"的特性
    → 不是随便定的，是磁盘物理特性和内存带宽的平衡结果
```

#### B+ 树的节点 = 一个页

```
关键设计：B+ 树的一个节点 = 数据库的一个页 = 16KB

非叶子节点只存"键值 + 子节点指针"，不存实际数据：

  每个键值对占多少空间？

  以 INT 主键为例：
    键值（主键）= 4 字节
    子节点指针 = 6 字节（InnoDB 用 page_number + slot）
    ─────────────────
    每个键占    = 10 字节

  16KB = 16384 字节
  16384 / 10 = 1638 个键/节点

  实际使用中键更大（如 8 字节主键 + 额外元数据）：
    每个键约 80~160 字节
    16384 / 80 = 204 个键/节点
    16384 / 160 = 102 个键/节点

  → 所以每个节点约 100~200 个键
```

```
对比二叉树/红黑树：

  二叉树的节点存：1 个键 + 2 个指针（左/右子节点）
  → 一个节点 = 1 个键
  → 16KB 能装 16384 个节点？不对！

  问题在于：二叉树的节点太"碎"了
  → 每个节点只有 1 个键 + 2 个指针
  → 分散在内存各处
  → 访问一个节点需要一次 I/O
  → 27 层 = 27 次 I/O

  B+ 树的节点存：100~200 个键 + 100~201 个指针
  → 一个节点 = 16KB = 一次 I/O
  → 4 层 = 4 次 I/O

  核心区别：
    二叉树：每次 I/O 只带来 1 个键的信息
    B+ 树：每次 I/O 带来 100~200 个键的信息
```

#### 为什么 B+ 树节点能"装这么多"

```
根本原因：B+ 树节点和磁盘 I/O 的"页"是同一个东西

  B+ 树节点 = 16KB 页
    → 一次 I/O 读整个节点 = 读 100~200 个键
    → 节点内部用二分查找 → 200 个键只需 8 次比较
    → 每次比较都在内存里完成（零 I/O）

  这就是"扇区读取特性"被完全利用的样子：
    磁盘说：我一次给你 16KB，你爱用多少用多少
    B+ 树说：我把 100~200 个键全塞进去，全部有用
```

### 1.1.2 为什么树高越低 I/O 越少？

> ❓ **问题 2**：为什么高度低就意味着 I/O 少？

答案：**在 B+ 树中，每下降一层 = 1 次磁盘 I/O。**

#### 查找过程就是 I/O 过程

```
假设查询 WHERE id = 500：

  B+ 树结构（4 层）：

            [1000, 50000, ...]           ← 根节点（第 1 层）
              /        \
    [200,1000,...]   [50000,80000,...]   ← 非叶子（第 2 层）
      /      \          /      \
   [..500..]           [..50000..]        ← 叶子（第 3 层）

  查找过程：

    第 1 步：从磁盘读根节点
      → I/O 次数：1
      → 在内存中比较：500 < 1000？否。500 < 50000？是。
      → 知道该走左子树，拿到左子节点的位置

    第 2 步：从磁盘读左子节点
      → I/O 次数：2
      → 在内存中比较：500 < 200？否。500 < 1000？是。
      → 知道该走对应的叶子节点

    第 3 步：从磁盘读叶子节点
      → I/O 次数：3
      → 在内存中比较：找到 500
      → 返回结果

    总 I/O：3 次
    总时间：3 × 磁盘 I/O 时间
```

```
关键规则：
  磁盘上的页 ≠ 当前内存中的页 → 需要一次 I/O 读取
  树下降一层 = 读取一个新页 = 1 次 I/O

  所以：
    树高 3 层 → 3 次 I/O
    树高 4 层 → 4 次 I/O
    树高 27 层 → 27 次 I/O

  树高直接等于 I/O 次数
```

#### 磁盘 I/O 到底有多慢？

```
这是理解问题的关键——磁盘 I/O 的代价极大：

  内存读取：约 100 纳秒 = 0.0000001 秒
  SSD 读取：约 0.1 毫秒 = 0.0001 秒
  HDD 读取：约 10 毫秒  = 0.01 秒

  磁盘 I/O 比内存慢 10 万倍！

  这就是为什么：
    27 次 I/O × 10ms = 270ms（0.27 秒）
    3 次  I/O × 10ms = 30ms （0.03 秒）

    270ms / 30ms = 9 倍差距

  对数据库来说，0.27 秒的查询 = 灾难
  QPS（每秒查询数）从 33 降到 3
```

#### 为什么内存快、磁盘慢？

```
内存（RAM）：
  → 电子信号传输，没有机械运动
  → 随机访问，任意地址访问时间相同
  → 速度 = 光速级别

硬盘（HDD）：
  → 磁头需要"移动"到数据所在位置（寻道时间）
  → 磁盘需要"旋转"到数据所在的扇区（旋转延迟）
  → 机械运动 = 物理限制
  → 平均一次 I/O = 寻道时间 + 旋转延迟 ≈ 10ms

SSD：
  → 闪存芯片，没有机械运动
  → 快得多，但随机读取仍然比内存慢 1000 倍
  → 因为需要电气寻址，不是电子信号直接读取
```

#### 树高和 I/O 的数学关系

```
树高 h = log_m(n)

  n = 数据总量
  m = 每个节点的分支数（即节点能容纳的键数 + 1）

  B+ 树（m = 200）：
    n = 1亿行
    h = log_200(100,000,000) = ln(10^8) / ln(200) = 18.4 / 5.3 ≈ 4 层
    I/O = 4 次

  二叉树（m = 2）：
    n = 1亿行
    h = log_2(100,000,000) = 18.4 / 0.7 ≈ 27 层
    I/O = 27 次

  差距：27 / 4 ≈ 7 倍 I/O

  注意：这个 7 倍差距不是"感觉"上的，是 7 倍的实际耗时
  因为 I/O 占总查询时间的 90% 以上
```

#### 为什么 B+ 树能做到 m = 200？

```
这又回到了问题 1 的答案：

  每个节点的分支数 m = 页大小 / 每个键的空间
  m = 16384 / 80 ≈ 200

  二叉树的 m = 2（固定）
  B+ 树的 m = 200（由页大小决定）

  这就是为什么 B+ 树是"专门为磁盘设计的树"：
    它把"每次 I/O 读一页"这个物理特性变成了"每个节点 200 个分支"
    让树高降到最低
    让 I/O 次数降到最少
```

---

### 1.2 B+ 树结构

```
B+ 树结构（3 层示例）：

              ┌──────────────┐
              │  [100, 300]  │   ← 根节点（非叶子，只存索引键）
              └──────┬───────┘
                    /   \
           ┌───────┘     └──────┐
       ┌──────────┐        ┌──────────┐
       │ [30,100] │        │[300,500] │  ← 非叶子节点（只存索引键）
       └────┬─────┘        └────┬─────┘
            /  \                 /  \
    ┌──────┘    └───┐    ┌──────┘    └───┐
    │ 10,20,30,50  │    │ 350,400,500  │
    └──────────────┘    └──────────────┘  ← 叶子节点（存实际数据或主键引用）
    ─ ─ ─ ─ ─ ─ ─ ─ →  ─ ─ ─ ─ ─ ─ ─ →    ← 叶子节点之间用指针连接（链表）
```

```
关键设计：
  ① 只有叶子节点存储实际数据（或主键值）
  ② 非叶子节点只存储"索引键"，作为"路标"
  ③ 叶子节点之间用双向链表连接 → 支持高效范围扫描
  ④ 所有叶子节点在同一层 → 查询次数固定（可预测）
```

### 1.3 聚簇索引 vs 非聚簇索引

```
InnoDB 有两种索引：

【聚簇索引（Clustered Index）】
  → 按主键顺序存储实际数据行
  → 数据本身就在叶子节点里
  → 每张表只能有一个聚簇索引（因为数据只能按一种顺序存）
  → 通常就是主键索引

  结构：
    叶子节点 = 主键值 + 整行数据
    [1, "张三", 25]
    [2, "李四", 30]
    [3, "王五", 28]

【非聚簇索引（Secondary Index）】
  → 只存储"索引列 + 主键值"
  → 查数据需要"回表"：先查非聚簇索引拿到主键，再用主键查聚簇索引

  结构（以 age 列建索引为例）：
    叶子节点 = age 值 + 主键 id
    [25, 1]
    [28, 3]
    [30, 2]

  查询 WHERE age = 25：
    Step 1：查 age 索引 → 得到主键 id = 1
    Step 2：用 id = 1 查聚簇索引 → 得到整行数据
    → 多了一次 I/O（回表）
```

```
覆盖索引（避免回表）：
  如果查询的列全部在索引里 → 不需要回表

  例：SELECT id, age FROM user WHERE age = 25
    → id 和 age 都在 age 索引的叶子节点里
    → 不需要回表 → 速度极快
    → EXPLAIN 中 Extra 列显示 "Using index"

  对比：SELECT * FROM user WHERE age = 25
    → * 包含所有列，age 索引里没有全部列
    → 需要回表 → 多一次 I/O
    → EXPLAIN 中 Extra 列显示 "Using where"
```

### 1.4 数据页（Page）结构

```
InnoDB 数据页 = 磁盘 I/O 的基本单位 = 16KB（默认）

一个 16KB 页的结构：

┌────────────────────────────────────┐
│ Page Header (约 56 字节)           │
│ - 页号、页类型、事务 ID            │
├────────────────────────────────────┤
│ File Segment Header (20 字节)      │
├────────────────────────────────────┤
│ 空闲空间 (Free Space)              │
├────────────────────────────────────┤
│ 数据区 (Record Area)               │
│ 每条记录 (Row)                     │
│   ┌───────────────────────────┐    │
│   │ infimum (最小边界)          │    │
│   │ 记录1: [主键, 数据]        │    │
│   │ 记录2: [主键, 数据]        │    │
│   │ ...                       │    │
│   │ supremum (最大边界)        │    │
│   └───────────────────────────┘    │
├────────────────────────────────────┤
│ 页目录 (Page Directory)            │
│ 快速定位记录位置的索引             │
├────────────────────────────────────┤
│ 事务日志 (Insert Buffer)           │
├────────────────────────────────────┤
│ 页尾 (Page Trailer)                │
└────────────────────────────────────┘
```

```
页分裂（当页满了）：

  一个页存了 100 条记录，再来第 101 条：

  【分裂前】
  [1~100]  ← 一个页，满了

  【分裂后】
  [1~50]  [51~101]  ← 分成两个页
  原来的页存前 50 条，新页存后 51 条
  父节点中插入新页的指针

  这就是为什么：数据量增长时，B+ 树会向右扩展（新页），但高度几乎不变
```

### 1.5 Buffer Pool（内存缓存）

```
Buffer Pool 是 InnoDB 最重要的内存结构：

  作用：缓存数据页和索引页，减少对磁盘的 I/O

  工作机制：
    1. 查询数据 → 先查 Buffer Pool
    2. 命中 → 直接从内存返回（极快）
    3. 未命中 → 从磁盘读取，放入 Buffer Pool，再返回
    4. Buffer Pool 满 → 用 LRU 算法淘汰最久未使用的页

  配置：
    innodb_buffer_pool_size = 12G（建议设为物理内存的 70~80%）

  命中率：
    理想命中率 > 99% → 几乎所有查询都在内存完成
    命中率低 → 大量磁盘 I/O → 性能急剧下降
```

### 1.6 代码实战：创建表和理解存储

```sql
-- 建表：默认使用 InnoDB 引擎，聚簇索引 = 主键
CREATE TABLE user (
    id      INT PRIMARY KEY AUTO_INCREMENT,
    name    VARCHAR(50) NOT NULL,
    age     INT NOT NULL,
    email   VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_age (age),           -- 非聚簇索引
    INDEX idx_name_email (name, email)  -- 联合索引
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 插入数据
INSERT INTO user (name, age, email) VALUES
('张三', 25, 'zhang@example.com'),
('李四', 30, 'li@example.com'),
('王五', 28, 'wang@example.com');

-- 理解存储结构：
-- 聚簇索引（按 id 排序）：
--   叶子节点：[1, "张三", 25, "zhang@example.com", ...]
--            [2, "李四", 30, "li@example.com", ...]
--            [3, "王五", 28, "wang@example.com", ...]

-- 非聚簇索引 idx_age（按 age 排序）：
--   叶子节点：[25, 1]  [28, 3]  [30, 2]
--   每个节点 = age 值 + 主键 id

-- 联合索引 idx_name_email（先按 name，再按 email）：
--   叶子节点：["李四", "li@example.com", 2]
--            ["王五", "wang@example.com", 3]
--            ["张三", "zhang@example.com", 1]
```

---

## 二、排序

### 2.1 排序的两种策略

```
MySQL 执行 ORDER BY 时有两种策略：

策略 1：利用索引排序（最快）
  → 如果索引的排列顺序 = 查询的排序顺序
  → 直接按索引顺序读取，无需额外排序
  → EXPLAIN 中 Extra = "Using index"

策略 2：Filesort（文件排序）
  → 无法利用索引排序时
  → 先把数据读出来，再在内存或磁盘上排序
  → EXPLAIN 中 Extra = "Using filesort"
  → 性能远低于策略 1
```

### 2.2 Filesort 算法

```
Filesort 不真的写文件（名字叫 Filesort 是历史遗留），实际分两种：

【双路排序（MySQL 4.1 之前）】

  每行记录需要排序的两步：
    Step 1：从磁盘读取需要排序的列 → 排序
    Step 2：排序完成后，再回表读取其他需要的列

  缺点：需要两次 I/O，慢

【单路排序（MySQL 4.1 之后，默认）】

  一次性读取所有需要的列，一起排序：
    Step 1：从磁盘读取所有需要的列
    Step 2：在内存中排序
    Step 3：返回排序结果

  缺点：每次排序需要更多内存
  优点：只需一次 I/O

  控制参数：
    max_length_for_sort_data = 1024
    → 如果所有列的总长度 > 这个值 → 回退到双路排序
    → 如果 <= 这个值 → 用单路排序
```

### 2.3 内存不够时的归并排序

```
当排序数据量 > sort_buffer_size 时：

  sort_buffer_size 默认 = 256KB（按连接分配）

  【情况 1：数据量 <= sort_buffer_size】
    → 全部在内存中排序（快速排序/归并排序）
    → 极快

  【情况 2：数据量 > sort_buffer_size】
    → 分批排序：
      Step 1：读一部分数据 → 内存排序 → 写入临时文件
      Step 2：读下一部分 → 内存排序 → 写入临时文件
      Step 3：...
      Step N：对所有临时文件做归并排序（Multi-way Merge Sort）
    → 慢，因为涉及磁盘 I/O

  归并排序过程：
    文件1: [1, 5, 9]
    文件2: [2, 4, 8]
    文件3: [3, 6, 7]
              ↓ 归并
    结果:   [1, 2, 3, 4, 5, 6, 7, 8, 9]
```

### 2.4 什么时候能避免 Filesort？

```
【规则 1：ORDER BY 列有索引】

  ✅ 无 Filesort：
    SELECT * FROM user ORDER BY id;          -- id 是主键索引
    SELECT * FROM user ORDER BY age;         -- age 有索引
    SELECT * FROM user ORDER BY name, email; -- name,email 有联合索引

  ❌ 有 Filesort：
    SELECT * FROM user ORDER BY email;       -- email 没有单独索引
    SELECT * FROM user ORDER BY email, name; -- 索引顺序不匹配
```

```
【规则 2：排序方向一致】

  联合索引 idx_name_email (name, email)：

  ✅ 无 Filesort：
    ORDER BY name ASC, email ASC   -- 和索引方向一致
    ORDER BY name DESC, email DESC -- 和索引方向一致

  ⚠️ 可能有 Filesort：
    ORDER BY name ASC, email DESC  -- 方向不一致（MySQL 8.0+ 可优化）
```

```
【规则 3：WHERE 条件和 ORDER BY 配合】

  ✅ 无 Filesort：
    SELECT * FROM user WHERE age = 25 ORDER BY name;
    -- age 过滤后，name 仍可按索引排序

  ❌ 有 Filesort：
    SELECT * FROM user WHERE email = "x" ORDER BY age;
    -- email 过滤后，age 需要重新排序
```

### 2.5 排序优化代码

```sql
-- ❌ 慢：order by 列没有索引，触发 filesort
SELECT * FROM user ORDER BY created_at LIMIT 100;

-- ✅ 快：加索引后，利用索引排序
CREATE INDEX idx_created_at ON user(created_at);
SELECT * FROM user ORDER BY created_at LIMIT 100;

-- ❌ 慢：排序列和数据列顺序不一致
CREATE INDEX idx_age_name ON user(age, name);
SELECT * FROM user WHERE age > 20 ORDER BY name;  -- age 过滤后，name 不是索引的下一列

-- ✅ 快：ORDER BY 和 WHERE 使用同一个索引
SELECT * FROM user WHERE age = 25 ORDER BY age;   -- age 索引直接排序
SELECT * FROM user WHERE age > 20 ORDER BY age;   -- 按 age 索引顺序扫描

-- ✅ 快：覆盖索引避免回表 + 排序
SELECT age, name FROM user WHERE age > 20 ORDER BY age;
-- 如果建立 idx_age_name (age, name)，既覆盖查询又按 age 排序
```

### 2.6 归并排序原理（小内存排序大数据的核心）

> ❓ **你的疑问**：归并排序怎么用小内存排序大数据？

核心思路就一句话：**内存放不下全部数据，就分批放，每批都在内存里排好，写出去，排完再分批合并。**

#### 2.6.1 两路归并（基础版）

```
示例：sort_buffer 只能放 4 条记录，数据有 9 条

  原始数据：[8, 3, 5, 1, 9, 2, 7, 4, 6]

【第一步：分批排序（Run 阶段）】

  把数据按 sort_buffer 大小切分成多个"块"（叫 Run）

  Run 1：读入 [8,3,5,1] → 内存排序 → [1,3,5,8] → 写入 temp_file_1
  Run 2：读入 [9,2,7,4] → 内存排序 → [2,4,7,9] → 写入 temp_file_2
  Run 3：读入 [6]       → 内存排序 → [6]       → 写入 temp_file_3

  现在磁盘上有 3 个"已排序的小文件"：
    temp_file_1: [1,3,5,8]
    temp_file_2: [2,4,7,9]
    temp_file_3: [6]

【第二步：两两归并】

  从两个文件各取一个"指针"，比较谁小，把小的写入输出

  归并 temp_file_1 和 temp_file_2：

    指针1 → [1,3,5,8]
    指针2 → [2,4,7,9]

    比较 1 vs 2 → 1 小 → 输出 1，指针1前进
    比较 3 vs 2 → 2 小 → 输出 2，指针2前进
    比较 3 vs 4 → 3 小 → 输出 3，指针1前进
    比较 5 vs 4 → 4 小 → 输出 4，指针2前进
    比较 5 vs 7 → 5 小 → 输出 5，指针1前进
    比较 8 vs 7 → 7 小 → 输出 7，指针2前进
    比较 8 vs 9 → 8 小 → 输出 8，指针1前进
    指针1到底 → 把 9 直接输出

    结果：[1,2,3,4,5,7,8,9] → 写入 temp_file_4

  归并 temp_file_4 和 temp_file_3：

    [1,2,3,4,5,7,8,9] + [6] → [1,2,3,4,5,6,7,8,9] → 写入 temp_file_5

  最终结果：temp_file_5 = [1,2,3,4,5,6,7,8,9] ✓
```

```
关键观察：
  - 归并时，内存只需要存"每个输入文件的当前指针位置 + 输出缓冲区"
  - 不需要同时加载所有数据到内存
  - 这是"小内存排序大数据"的核心：内存只放"正在比较的那几个元素"
```

#### 2.6.2 多路归并（K 路归并，MySQL 实际做法）

```
两路归并的问题：文件越多，归并轮次越多

  3 个文件 → 归并 2 轮
  10 个文件 → 归并 4 轮
  100 个文件 → 归并 7 轮
  ...每多一轮 = 多一次全量数据扫描 = 多一次磁盘 I/O

优化：一次归并多个文件（K 路归并）

  K 路归并：同时从 K 个文件中读取，每次选最小的输出

  示例：K = 3，同时归并 3 个文件

    temp_file_1: [1,3,5,8]
    temp_file_2: [2,4,7,9]
    temp_file_3: [6]

    指针1 → 1    指针2 → 2    指针3 → 6
    比较 1,2,6 → 最小是 1 → 输出 1

    指针1 → 3    指针2 → 2    指针3 → 6
    比较 3,2,6 → 最小是 2 → 输出 2

    指针1 → 3    指针2 → 4    指针3 → 6
    比较 3,4,6 → 最小是 3 → 输出 3

    ...继续直到所有文件读完

  结果：1 轮完成 3 个文件的归并，而不是 2 轮
```

#### 2.6.3 K 路归并怎么找最小值？——堆排序

```
K 路归并的核心操作：在 K 个指针中找最小值

【暴力法】
  每次比较 K 个值 → O(K)
  总复杂度：O(n × K)

【堆优化（MySQL 实际做法）】
  用最小堆维护 K 个指针的当前值

  堆结构：
      3 (最小，堆顶)
     / \
    4   6
   / \
  7   9

  操作：
    1. 堆顶就是 K 个值中最小的 → 直接输出 → O(1)
    2. 对应文件指针前进 → 新值放入堆顶 → 调整堆 → O(log K)
    3. 重复

  总复杂度：O(n × log K)

  K = 2 时：O(n × log 2) = O(n)      ← 两路
  K = 16 时：O(n × log 16) = O(4n)   ← 16 路
  K = 128 时：O(n × log 128) = O(7n) ← 128 路

  K 越大 → 轮次越少 → 但每轮比较代价略增
  MySQL 需要在"轮次减少"和"每轮代价增加"之间找平衡
```

#### 2.6.4 完整流程：1000 万条数据，sort_buffer 只有 256KB

```
假设：
  数据总量：1000 万条记录
  每条记录：100 字节
  总数据量：约 1GB
  sort_buffer：256KB = 约 2500 条记录
  K = 16（16 路归并）

【第一轮：生成 Run】

  1GB / 256KB = 4000 个 Run

  Run 1：读 256KB → 内存排序 → 写磁盘
  Run 2：读 256KB → 内存排序 → 写磁盘
  ...
  Run 4000：读 256KB → 内存排序 → 写磁盘

  磁盘 I/O：读 1GB + 写 1GB = 2GB

【第二轮：16 路归并】

  4000 个 Run → 每次取 16 个归并 → 生成 4000/16 = 250 个更大的 Run

  归并过程：
    同时打开 16 个输入文件 + 1 个输出文件
    用最小堆维护 16 个指针
    每次输出一个元素
    输出缓冲区满了 → 写磁盘
    输入文件读完了 → 换下一组 16 个

  磁盘 I/O：读 1GB + 写 1GB = 2GB

【第三轮：16 路归并】

  250 个 Run → 每次 16 个 → 生成 250/16 ≈ 16 个 Run

  磁盘 I/O：读 1GB + 写 1GB = 2GB

【第四轮：16 路归并】

  16 个 Run → 一次 16 路归并 → 生成 1 个最终文件

  磁盘 I/O：读 1GB + 写 1GB = 2GB

【总结】

  总轮次：1（生成 Run）+ 3（归并）= 4 轮
  总磁盘 I/O：4 × 2GB = 8GB
  内存占用：始终只有 256KB + 少量堆空间
  时间复杂度：O(n × log n)
```

```
为什么轮次是 log_K（Run 数量）？

  每轮归并后，Run 数量除以 K
  轮数 = log_K(初始 Run 数)

  4000 个 Run，K=16：
    log_16(4000) = ln(4000)/ln(16) ≈ 8.3/2.8 ≈ 3 轮

  对比 K=2（两路）：
    log_2(4000) ≈ 12 轮 → 多 9 轮 → 多 18GB 磁盘 I/O

  所以 K 越大 → 轮次越少 → 磁盘 I/O 越少 → 越快
```

#### 2.6.5 sort_buffer 大小的影响

```
sort_buffer_size 默认 = 256KB（按连接分配）

【sort_buffer 太小】
  → Run 数量多 → 归并轮次多 → 磁盘 I/O 多 → 慢
  → 但不浪费内存

【sort_buffer 太大】
  → Run 数量少 → 归并轮次少 → 快
  → 但占用大量内存（每个连接一个 buffer）
  → 并发连接多时可能内存溢出

【MySQL 8.0+ 的新机制】
  → sort_buffer 不再按连接固定分配
  → 按需动态分配，用完释放
  → 减少了内存浪费
```

#### 2.6.6 总结

```
┌──────────────────────────────────────────────────────────────────┐
│                                                                  │
│  小内存排序大数据的核心 = 外部归并排序                            │
│                                                                  │
│  原理：                                                         │
│    内存放不下 → 分批排 → 写磁盘 → 分批归并                      │
│    内存只存"正在比较的那几个元素"，不是全部数据                    │
│                                                                  │
│  关键参数：                                                     │
│    sort_buffer_size = 每批能放多少数据                           │
│    K（归并路数）= 一次同时合并几个文件                           │
│                                                                  │
│  权衡：                                                         │
│    sort_buffer 大 → Run 少 → 轮次少 → 快 → 但费内存             │
│    K 大 → 轮次少 → 快 → 但每轮比较代价略增                      │
│                                                                  │
│  最终复杂度：                                                    │
│    时间：O(n × log n × log K)                                   │
│    空间：O(sort_buffer_size + K)                                │
│    磁盘 I/O：O(n × log_K(Run数))                                │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

---

## 三、事务

### 3.1 事务的 ACID

```
A - Atomicity（原子性）：
  事务中的操作要么全部成功，要么全部失败

  实现：undo log
    每个操作前先记录"反向操作"
    失败时 → 用 undo log 回滚

C - Consistency（一致性）：
  事务执行前后，数据库从一个一致状态变为另一个一致状态

  例：A 转给 B 100 元
    转账前：A=1000, B=1000，总和=2000
    转账后：A=900,  B=1100，总和=2000
    一致性：总金额不变

I - Isolation（隔离性）：
  多个事务同时执行时，互不干扰

  实现：锁 + MVCC
    锁：防止并发写冲突
    MVCC：让读操作不阻塞写，写操作不阻塞读

D - Durability（持久性）：
  事务提交后，即使数据库崩溃，数据也不会丢失

  实现：redo log
    先写 redo log → 再写磁盘
    崩溃恢复时 → 用 redo log 重做未写完的数据
```

### 3.2 四种隔离级别

```
┌─────────────────────────────────────────────────────────────────┐
│  隔离级别          │ 脏读 │ 不可重复读 │ 幻读 │ InnoDB 默认  │
├────────────────────┼──────┼───────────┼──────┼──────────────┤
│ 读未提交            │  ❌  │    ❌     │  ❌  │  不推荐       │
│ (Read Uncommitted) │      │           │      │              │
├────────────────────┼──────┼───────────┼──────┼──────────────┤
│ 读已提交            │  ✅  │    ❌     │  ❌  │  Oracle 默认 │
│ (Read Committed)   │      │           │      │              │
├────────────────────┼──────┼───────────┼──────┼──────────────┤
│ 可重复读（默认）    │  ✅  │    ✅     │  ✅  │  InnoDB 默认 │
│ (Repeatable Read)  │      │           │      │              │
├────────────────────┼──────┼───────────┼──────┼──────────────┤
│ 串行化              │  ✅  │    ✅     │  ✅  │  不推荐       │
│ (Serializable)     │      │           │      │  性能极差    │
└────────────────────┴──────┴───────────┴──────┴──────────────┘
```

```
三种异常的解释：

【脏读（Dirty Read）】
  事务 A 修改了数据但未提交
  事务 B 读到了 A 未提交的数据
  → 如果 A 回滚 → B 读到的数据是"假的"

【不可重复读（Non-Repeatable Read）】
  事务 A 读了一行数据
  事务 B 修改了这行数据并提交
  事务 A 再读同一行 → 数据变了
  → 同一事务内读到的数据不一致

【幻读（Phantom Read）】
  事务 A 读了一批数据（如 age=25 的所有人）
  事务 B 插入了一条新数据（age=25）并提交
  事务 A 再读 → 多了一条数据
  → 同一事务内读到的"集合"不一致
```

### 3.3 事务隔离级别的实现原理

```
【读未提交】
  → 不加任何锁，不读版本
  → 直接读最新数据（包括未提交的）
  → 最简单，但完全不可靠

【读已提交（RC）】
  → 每次读都获取"当前最新版本"
  → 版本判断：只读已提交的事务版本
  → 用 MVCC 的"读视图"实现
  → 每次 SELECT 都会生成新的读视图

  原理：
    事务 A 读 → 生成读视图 V1 → 只看到 V1 时刻已提交的数据
    事务 B 提交新数据
    事务 A 再读 → 生成新读视图 V2 → 看到 B 提交的数据
    → 导致不可重复读

【可重复读（RR）—— InnoDB 默认】
  → 事务开始时生成一次读视图
  → 整个事务内都使用同一个读视图
  → 即使其他事务提交了新数据，也看不到
  → 解决了不可重复读

  同时用间隙锁（Gap Lock）解决幻读：
    事务 A 执行 SELECT ... FOR UPDATE WHERE age = 25
    → 锁定 age=25 的行 + 相邻间隙（25~26 之间）
    → 事务 B 插入 age=26 的行 → 被间隙锁阻塞

【串行化（Serializable）】
  → 所有读操作都加共享锁
  → 所有写操作都加排他锁
  → 事务必须排队执行
  → 性能极差，但完全安全
```

### 3.4 MVCC（多版本并发控制）

```
MVCC 是 InnoDB 实现"读不阻塞写，写不阻塞读"的核心机制。

每个数据行有两个隐藏列：
  DB_TRX_ID：最近修改该行的事务 ID
  DB_ROLL_PTR：回滚指针，指向 undo log 中的旧版本

数据行版本链：
  当前版本 [trx=10, age=30] ← undo log
      ← 旧版本 [trx=8, age=25] ← undo log
          ← 旧版本 [trx=5, age=20] ← undo log
```

```
【读视图（Read View）的生成】

  RC 级别：每次 SELECT 生成新的读视图
  RR 级别：事务第一次 SELECT 时生成读视图，之后复用

  读视图包含：
    - 活跃事务列表（还在运行中，未提交的事务 ID）
    - 最小事务 ID（当前活跃事务中最小的）
    - 最大事务 ID（下一个将要分配的事务 ID）

【判断一行数据是否可见】

  给定读视图中的活跃事务列表 = [6, 8, 9]
  最小事务 ID = 6
  最大事务 ID = 10

  判断某行数据（DB_TRX_ID = 8）是否对当前事务可见：

  1. 如果 DB_TRX_ID < 最小事务 ID → 已提交 → 可见 ✅
  2. 如果 DB_TRX_ID >= 最大事务 ID → 以后创建的 → 不可见 ❌
  3. 如果 DB_TRX_ID 在活跃事务列表中 → 未提交 → 不可见 ❌
  4. 如果 DB_TRX_ID = 当前事务 ID → 自己写的 → 可见 ✅
```

### 3.5 锁机制

```
InnoDB 的锁层级：
  表锁 > 行锁 > 间隙锁

【行锁（Record Lock）】
  锁定索引记录本身
  SELECT ... FOR UPDATE WHERE id = 1 → 锁定 id=1 这行
  如果 id 列有索引 → 只锁这一行
  如果 id 列没有索引 → 锁整张表！
```

```
【间隙锁（Gap Lock）—— 解决幻读的关键】

  锁定索引记录之间的"间隙"（不包含记录本身）

  数据：[1, 5, 10, 15, 20]

  间隙：(-∞, 1) (1, 5) (5, 10) (10, 15) (15, 20) (20, +∞)

  事务 A：SELECT * FROM t WHERE id BETWEEN 5 AND 15 FOR UPDATE
    → 锁定记录：5, 10, 15
    → 锁定间隙：(5, 10), (10, 15)
    → 事务 B 插入 id=12 → 被间隙锁阻塞！
    → 事务 B 插入 id=16 → 被间隙锁阻塞！
```

```
【Next-Key Lock = 行锁 + 间隙锁】

  这是 InnoDB RR 级别下的默认锁

  锁定范围 = 记录本身 + 记录之前的间隙
  形式：(prev, current]

  数据：[1, 5, 10, 15, 20]

  Next-Key Lock 的区间：
    (-∞, 1] (1, 5] (5, 10] (10, 15] (15, 20] (20, +∞]

  SELECT * FROM t WHERE id > 5 FOR UPDATE
    → 锁定：(5, 10] (10, 15] (15, 20] (20, +∞]
    → 即锁定 10, 15, 20 以及 > 20 的间隙
    → 新插入的 > 5 的行都会被阻塞
```

### 3.6 undo log 和 redo log

```
两个 log 解决两个不同的问题：

【undo log —— 保证原子性】
  作用：记录操作的"反向操作"，用于回滚
  生命周期：事务提交后，如果不在 MVCC 中需要，可被清理

  操作          undo log 记录
  ─────────    ─────────────────
  INSERT       DELETE 对应行
  DELETE       INSERT 对应行
  UPDATE       记录修改前的旧值

  例：UPDATE user SET age = 30 WHERE id = 1
    undo log 记录：id=1 的旧 age = 25
    如果事务回滚 → 用 undo log 恢复 age = 25

【redo log —— 保证持久性】
  作用：记录"物理日志"（数据页做了什么修改），用于崩溃恢复
  生命周期：循环写入，满了覆盖（已刷盘的可以覆盖）

  工作原理：
    事务提交时：
      Step 1：写 redo log（顺序写，极快）
      Step 2：标记事务已提交
      Step 3：脏页（修改过的页）稍后刷到磁盘（WAL 机制）

    崩溃恢复时：
      Step 1：读取 redo log
      Step 2：重做（Redo）所有已提交事务的修改
      Step 3：数据库恢复到崩溃前的状态

  顺序写 vs 随机写：
    redo log 是顺序写（追加到文件末尾）
    数据页是随机写（页可能分散在磁盘各处）
    顺序写比随机写快 10~100 倍
    → 先写 redo log，再写数据页 → 提交速度极快
```

### 3.7 代码实战

```sql
-- 查看当前隔离级别
SELECT @@transaction_isolation;

-- 设置隔离级别
SET TRANSACTION ISOLATION LEVEL READ COMMITTED;

-- 开始事务
START TRANSACTION;

-- 转账示例：保证原子性
UPDATE account SET balance = balance - 100 WHERE user_id = 1;
UPDATE account SET balance = balance + 100 WHERE user_id = 2;

-- 如果两条都成功
COMMIT;

-- 如果有任何一条失败
ROLLBACK;

-- 悲观锁：SELECT ... FOR UPDATE
START TRANSACTION;
SELECT * FROM inventory WHERE product_id = 1 FOR UPDATE;
-- 其他事务修改这条记录会被阻塞
-- 事务提交后锁释放

-- 悲观锁：SELECT ... LOCK IN SHARE MODE
START TRANSACTION;
SELECT * FROM config WHERE id = 1 LOCK IN SHARE MODE;
-- 其他事务可读但不能写
```

---

## 四、一致性

### 4.1 数据库一致性的层次

```
一致性不是单一概念，有多个层次：

┌─────────────────────────────────────────────────┐
│ 层次 1：事务一致性（ACID 中的 C）                 │
│  单个事务执行前后，数据满足业务规则               │
│  实现：锁 + undo log + MVCC                     │
├─────────────────────────────────────────────────┤
│ 层次 2：主从一致性                               │
│  主库和从库数据是否完全一致                       │
│  实现：Binlog + 半同步复制                      │
├─────────────────────────────────────────────────┤
│ 层次 3：分布式一致性（CAP）                      │
│  多节点之间数据的一致性                          │
│  实现：Paxos / Raft / 2PC                      │
└─────────────────────────────────────────────────┘
```

### 4.2 Binlog（二进制日志）—— 主从复制的基础

```
Binlog 是 MySQL 的主从复制核心。

【Binlog 是什么】
  → 记录所有"修改数据"的 SQL 语句（或行变更）
  → 不记录 SELECT
  → 按顺序追加写入
  → 主从复制时，从库读取主库的 Binlog 重放

【三种格式】

  STATEMENT（语句格式）：
    记录 SQL 语句本身
    优点：日志体积小
    缺点：某些函数（如 NOW()、UUID()）主从结果不一致

  ROW（行格式）：
    记录每行数据的具体变化
    优点：数据绝对一致
    缺点：日志体积大（UPDATE 100万行 = 100万条日志）
    → MySQL 5.7+ 默认格式

  MIXED（混合格式）：
    大多数情况用 STATEMENT
    遇到不一致风险时自动切到 ROW
```

```
【Binlog 结构】

  一个 Binlog 文件 = 多个 Event 的集合

  ┌────────────────────────────┐
  │ Binlog Header              │
  │ - 版本号、创建时间          │
  ├────────────────────────────┤
  │ Query Event                │
  │ BEGIN（事务开始）           │
  ├────────────────────────────┤
  │ Rows Query Event           │
  │ UPDATE user SET age=30 ... │
  ├────────────────────────────┤
  │ Table Map Event            │
  │ 表结构信息                  │
  ├────────────────────────────┤
  │ Write Rows Event           │
  │ [id=1, name="张三", age=30]│
  ├────────────────────────────┤
  │ XID Event                  │
  │ COMMIT（事务提交）          │
  └────────────────────────────┘
```

### 4.3 主从复制原理

```
【异步复制（默认，最快）】

  主库：
    Step 1：执行事务 → 写 Binlog
    Step 2：提交事务 → 返回"成功"给客户端
    Step 3：（异步）通知从库

  从库：
    Step 1：接收主库的 Binlog
    Step 2：写入 Relay Log
    Step 3：SQL 线程重放 Relay Log

  问题：主库提交后，从库可能还没收到 → 主库崩溃 → 数据丢失

【半同步复制（推荐）】

  主库：
    Step 1：执行事务 → 写 Binlog
    Step 2：等待至少一个从库确认收到 Binlog
    Step 3：提交事务 → 返回"成功"给客户端

  从库收到 Binlog 后 → 立即确认

  优点：主库崩溃时，至少有一个从库有最新数据
  缺点：多了一次网络往返 → 延迟增加
  → 适合对一致性要求高的场景

  配置：
    主库：INSTALL PLUGIN rpl_semi_sync_master SONAME 'semisync_master.so';
          SET GLOBAL rpl_semi_sync_master_enabled = 1;
    从库：INSTALL PLUGIN rpl_semi_sync_slave SONAME 'semisync_slave.so';
          SET GLOBAL rpl_semi_sync_slave_enabled = 1;

【GTID（全局事务标识符）】

  每个事务有一个全局唯一的 ID：
    GTID = 服务器 UUID + 事务序列号

  例：3E11FA47-71CA-11E1-9E33-C80AA9429562:23

  优点：
    → 主从切换时无需找 Binlog 位置
    → 从库自动找到从哪里继续复制
    → 数据一致性更容易保证
```

### 4.4 主从延迟

```
主从延迟 = 从库落后于主库的时间

【延迟产生的原因】

  1. 网络延迟：主库发送 Binlog 到从库需要时间
  2. 从库写入 Relay Log 的 I/O 压力
  3. 从库 SQL 线程是单线程重放 → 主库并发写入 → 从库串行重放
  4. 从库有大查询（慢 SQL）阻塞了重放

【监控延迟】

  SHOW SLAVE STATUS\G
  → Seconds_Behind_Master: 0  → 无延迟
  → Seconds_Behind_Master: 30 → 延迟 30 秒

【减少延迟的方法】

  1. 开启半同步复制
  2. 从库开启并行复制（MySQL 5.7+）：
     SET GLOBAL slave_parallel_workers = 4;
  3. 避免在从库执行大查询
  4. 主从分开（读写分离）
  5. 升级硬件（SSD、大内存）
```

### 4.5 CAP 理论

```
CAP 理论：分布式系统无法同时满足以下三点

  C - Consistency（一致性）：所有节点同一时刻数据相同
  A - Availability（可用性）：每个请求都能得到响应
  P - Partition Tolerance（分区容错性）：网络分区时系统仍能运行

  三者最多满足两个：

  CP（一致性 + 分区容错）：
    → 网络分区时，牺牲可用性，保证一致性
    → 分区期间部分节点不服务
    → 例：ZooKeeper、HBase

  AP（可用性 + 分区容错）：
    → 网络分区时，牺牲一致性，保证可用性
    → 分区期间各节点继续服务，但数据可能不一致
    → 例：Cassandra、DynamoDB

  MySQL 主从：
    → 默认异步复制 = AP（主库挂了从库继续服务，但可能缺数据）
    → 半同步复制 = 向 CP 靠近（但仍有极小丢失窗口）
```

### 4.6 代码实战

```sql
-- 查看主库 Binlog 状态
SHOW MASTER STATUS;
-- 输出：File: mysql-bin.000001, Position: 154

-- 从库配置复制
CHANGE MASTER TO
    MASTER_HOST = '192.168.1.100',
    MASTER_USER = 'repl',
    MASTER_PASSWORD = 'password',
    MASTER_LOG_FILE = 'mysql-bin.000001',
    MASTER_LOG_POS = 154;

START SLAVE;

-- 查看从库状态
SHOW SLAVE STATUS\G
-- 关注：
--   Slave_IO_Running: Yes     → IO 线程正常（拉取 Binlog）
--   Slave_SQL_Running: Yes    → SQL 线程正常（重放）
--   Seconds_Behind_Master: 0  → 延迟 0 秒

-- 开启 GTID
-- my.cnf:
--   gtid_mode = ON
--   enforce_gtid_consistency = ON

-- 开启并行复制（从库）
SET GLOBAL slave_parallel_type = 'LOGICAL_CLOCK';
SET GLOBAL slave_parallel_workers = 4;
```

---

## 五、查询优化

### 5.1 EXPLAIN —— 优化第一步

```sql
-- 查看 SQL 执行计划
EXPLAIN SELECT * FROM user WHERE age = 25 ORDER BY name;
```

```
EXPLAIN 输出关键字段解释：

┌──────────┬────────────────────────────────────────────────┐
│ 字段      │ 含义                                            │
├──────────┼────────────────────────────────────────────────┤
│ id        │ 查询中 SELECT 的序号，id 越大越先执行           │
│ type      │ 访问类型（最重要的字段）                        │
│ possible │ 可能用到的索引                                  │
│ keys      │ 实际用到的索引                                  │
│ rows      │ 预估扫描行数                                    │
│ filtered  │ 条件过滤的百分比                                │
│ Extra     │ 额外信息（Using index / filesort / 等）        │
└──────────┴────────────────────────────────────────────────┘
```

```
type 字段（从好到坏）：

  system     → 表只有一行（系统表）
  const      → 主键/唯一索引查询，最多一行
  eq_ref     → 唯一索引，每行最多匹配一条
  ref        → 非唯一索引，可能匹配多行
  range      → 范围查询（>, <, BETWEEN, IN）
  index      → 全索引扫描（比 ALL 快）
  ALL        → 全表扫描（最慢！）

  优化目标：让 type 至少达到 range
```

```
Extra 字段（关键信息）：

  ✅ 好的信号：
    Using index       → 覆盖索引，无需回表
    Using where       → 用 WHERE 条件过滤
    Using filesort    → ⚠️ 需要文件排序

  ❌ 坏的信号：
    Using filesort    → 需要排序（可能慢）
    Using temporary   → 需要临时表（GROUP BY / DISTINCT）
    Using where       → 没用到索引时出现
    Impossible WHERE  → 条件永远为假
```

### 5.2 索引优化

```sql
-- ❌ 慢：全表扫描
EXPLAIN SELECT * FROM user WHERE email = 'x@example.com';
-- type: ALL, rows: 1000000

-- ✅ 快：加索引后
CREATE INDEX idx_email ON user(email);
EXPLAIN SELECT * FROM user WHERE email = 'x@example.com';
-- type: ref, rows: 1

-- 最左前缀原则（联合索引）：
CREATE INDEX idx_name_age ON user(name, age);

  ✅ 命中索引：
    WHERE name = '张三'                    -- 用第 1 列
    WHERE name = '张三' AND age = 25       -- 用第 1、2 列

  ❌ 不命中（或只部分命中）：
    WHERE age = 25                         -- 跳过第 1 列，索引失效
    WHERE name LIKE '%张三'                -- 前导通配符，索引失效
    WHERE name LIKE '张%'                  -- 命中！前缀匹配可用索引
```

```sql
-- 索引下推（Index Condition Pushdown, MySQL 5.6+）

  优化前：
    WHERE name LIKE '张%' AND age > 20

    MySQL 5.5：
      Step 1：用索引找 name LIKE '张%' 的所有行
      Step 2：回表读所有行
      Step 3：在服务器端过滤 age > 20

    MySQL 5.6+（索引下推）：
      Step 1：用索引找 name LIKE '张%' 的行
      Step 2：在存储引擎层同时判断 age > 20
      Step 3：只回表满足两个条件的行
      → 减少回表次数
```

### 5.3 JOIN 优化

```sql
-- 两张表的 JOIN 方式：

【Nested Loop Join（嵌套循环，默认）】

  SELECT * FROM order o JOIN user u ON o.user_id = u.id;

  原理：
    对 order 表的每一行：
      用 user_id 去 user 表查对应行
    → 外层行数 × 内层行数 = 总扫描次数

  优化：驱动表（外层）应该是最小的表！

  ❌ 慢：order 100万行 × user 100行 = 1亿次扫描
  ✅ 快：user 100行 × order 100万行（但 user_id 有索引）= 100次索引查找

【Index Nested Loop Join（优化版）】

  如果内层表的连接列有索引：
    对 order 表的每一行：
      用 user_id 索引 → 直接定位 user 表对应行（O(log n)）
    → 总扫描 = 外层行数 × log(内层行数)

  关键：被驱动表的连接列必须有索引！
```

```sql
-- JOIN 优化实战

  -- ❌ 慢：被驱动表没有索引
  CREATE TABLE order (id INT PRIMARY KEY, user_id INT, amount DECIMAL);
  CREATE TABLE user (id INT PRIMARY KEY, name VARCHAR(50));
  -- 注意：order.user_id 没有索引！

  EXPLAIN
  SELECT * FROM user u JOIN order o ON u.id = o.user_id;
  -- user 100行，对每行都要扫描 order 全表 100万行 = 1亿次

  -- ✅ 快：给被驱动表加索引
  CREATE INDEX idx_order_user_id ON order(user_id);
  EXPLAIN
  SELECT * FROM user u JOIN order o ON u.id = o.user_id;
  -- user 100行，每行用索引查 order = 100 × log(100万) ≈ 2000 次
```

```sql
-- JOIN 类型选择

  INNER JOIN  → 只返回两表匹配的行（最快，因为不需要处理不匹配行）
  LEFT JOIN   → 返回左表所有行 + 右表匹配行
  → LEFT JOIN 通常比 INNER JOIN 慢，因为需要处理 NULL

  优化建议：能用 INNER JOIN 就不用 LEFT JOIN
```

### 5.4 慢查询优化

```sql
-- 开启慢查询日志
SET GLOBAL slow_query_log = 'ON';
SET GLOBAL slow_query_log_file = '/var/log/mysql/slow.log';
SET GLOBAL long_query_time = 1;  -- 超过 1 秒的查询记录

-- 分析慢查询
mysqldumpslow -t 10 /var/log/mysql/slow.log
-- 输出：最慢的 10 个查询（按频率排序）
```

```sql
-- 常见慢查询及优化

-- ❌ 1. 全表扫描
SELECT * FROM user WHERE email = 'x@example.com';
-- 优化：CREATE INDEX idx_email ON user(email);

-- ❌ 2. 回表太多
SELECT * FROM user WHERE age > 20 ORDER BY name LIMIT 1000;
-- 优化：CREATE INDEX idx_age_name ON user(age, name);
--       覆盖索引 + 索引排序，避免回表和 filesort

-- ❌ 3. 函数导致索引失效
SELECT * FROM user WHERE YEAR(created_at) = 2023;
-- YEAR(created_at) 对每行都调用函数 → 索引失效
-- 优化：
SELECT * FROM user WHERE created_at BETWEEN '2023-01-01' AND '2023-12-31';
-- 范围查询可以直接用索引

-- ❌ 4. 隐式类型转换
SELECT * FROM user WHERE phone = 13800138000;  -- phone 是 VARCHAR
-- 数字 13800138000 和字符串比较 → MySQL 把 phone 转成数字 → 全表扫描
-- 优化：
SELECT * FROM user WHERE phone = '13800138000';  -- 加引号

-- ❌ 5. OR 导致索引失效
SELECT * FROM user WHERE name = '张三' OR email = 'x@example.com';
-- 两个列都有索引，但 OR 可能让优化器放弃索引
-- 优化：
SELECT * FROM user WHERE name = '张三'
UNION ALL
SELECT * FROM user WHERE email = 'x@example.com';
```

### 5.5 分页优化

```sql
-- ❌ 深分页：偏移量很大时极慢
SELECT * FROM user ORDER BY id LIMIT 1000000, 10;
-- MySQL 需要扫描 1000010 行，然后丢弃前 1000000 行

-- ✅ 优化 1：延迟关联（推荐）
SELECT u.* FROM user u
INNER JOIN (SELECT id FROM user ORDER BY id LIMIT 1000000, 10) tmp
ON u.id = tmp.id;
-- 内层只查 id（覆盖索引），外层回表只查 10 行

-- ✅ 优化 2：游标法（适合连续翻页）
SELECT * FROM user WHERE id > 1000000 ORDER BY id LIMIT 10;
-- 不扫描前面的行，直接从 id > 1000000 开始
-- 需要客户端记住上次最后一条的 id
```

### 5.6 索引设计原则总结

```
┌────────────────────────────────────────────────────────────────┐
│                                                                │
│  1. 最左前缀原则                                               │
│     联合索引 (a, b, c)：                                       │
│       WHERE a = ? AND b = ? → 命中                            │
│       WHERE a = ? AND c = ? → 只命中 a                        │
│       WHERE b = ? → 不命中                                    │
│                                                                │
│  2. 区分度高的列放前面                                         │
│     区分度 = 不同值的数量 / 总行数                             │
│     例：gender（2个值）vs email（几乎唯一）                    │
│     → email 放前面更高效                                      │
│                                                                │
│  3. 覆盖索引                                                   │
│     SELECT 的列都在索引里 → 无需回表                           │
│     把常用查询列都放索引里                                     │
│                                                                │
│  4. 避免过度索引                                               │
│     每个索引都有成本：占用空间 + 写操作变慢                    │
│     只给常用查询列建索引                                      │
│                                                                │
│  5. 索引失效场景                                               │
│     - 对索引列使用函数：WHERE YEAR(date) = 2023               │
│     - 隐式类型转换：WHERE varchar_col = 123                   │
│     - 前导通配符：WHERE name LIKE '%张'                       │
│     - OR 条件混合索引和非索引列                               │
│     - 索引列运算：WHERE age + 1 = 25                         │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

---

## 六、实战案例：设备激活 1213 死锁（短事务 + RC 隔离）

> 把「事务 / 隔离级别 / 锁机制」的理论落到真实生产问题：
> 并发创建设备触发 MySQL 1213 死锁，最终方案 = **短事务 + READ COMMITTED（去行锁）**。

### 6.1 背景

```
问题场景：不同设备、同一产品并发创建设备。

  device 表存在非唯一索引：device_indexs(product_key, device_name)

  并发执行「查重 → 插入」时，该索引上的间隙锁发生 S → X 升级，
  导致 MySQL 错误 1213（死锁）。

  Redis 锁（按设备名）只能拦住「同一设备名」，拦不住「不同设备」。

用户诉求：
  ① 并发很大 → 不要按产品串行化（去掉行锁）
  ② 不要死锁重试
```

### 6.2 死锁根因：S 间隙锁 → X 升级

```
在 RR（可重复读）隔离级别下，查重 SELECT 会走 Next-Key Lock（间隙锁 + 行锁）：

  两个事务同时对同一间隙加锁：

    事务 A：SELECT ... FOR UPDATE WHERE product_key = ? AND device_name = ?
      → 对 device_indexs 索引的间隙持有 S（共享）间隙锁

    事务 B：同样执行
      → 对同一间隙持有 S 间隙锁

    事务 A：INSERT ...
      → 需要把 S 间隙锁升级为 X（写）锁
      → 但间隙已被 B 的 S 锁占用 → A 阻塞等待 B

    事务 B：INSERT ...
      → 同样需要升级 X → 被 A 的 S 锁阻塞

  结果：A 等 B、B 等 A → 死锁 → InnoDB 检测到后回滚一方 → 报 1213
```

```
什么是「同一间隙」？—— 用具体索引布局解释

  device_indexs(product_key, device_name) 是二级索引，
  叶子节点按 (product_key, device_name) 排序存储：

    索引叶子已有记录：
      (P1, dev_005)  (P1, dev_010)  (P1, dev_015)  (P1, dev_020)

    相邻两条记录之间的「空隙」就是一个间隙（Gap）：

      (P1,dev_005) → (P1,dev_010)  → 间隙 G1
      (P1,dev_010) → (P1,dev_015)  → 间隙 G2
      (P1,dev_015) → (P1,dev_020)  → 间隙 G3
      (P1,dev_020) → (+∞)          → 间隙 G4

  并发创建两个「不同设备」：
    设备 dev_012 → 会插入到 G2（dev_010 与 dev_015 之间）
    设备 dev_013 → 也会插入到 G2（同一个间隙！）

  → 两个事务的查重 SELECT（RR 下）都在 G2 上加了 S 间隙锁
  → 各自的 INSERT 都落在 G2 → 都要把 G2 的 S 锁升级为 X 锁
  → 互相等待 → 死锁

  对比：若并发设备落在不同间隙（如 dev_012 → G2、dev_017 → G3），
  锁的是不同间隙 → 不会互相阻塞 → 不会死锁。

  ⚠️ 关键认识：
    问题不是「同一设备名」，而是「落点落在同一间隙的不同设备」。
    product_key 相同 + device_name 相邻 → 极易落在同一间隙。
```

```
关键点：间隙锁 / Next-Key Lock 只在 RR（及以上）隔离级别产生。

  RC 下非锁定读（SELECT 查重）不加任何锁；
  INSERT 的插入意向锁互相兼容。
  → 并发 check-then-insert 不冲突。
```

### 6.3 最终方案：短事务 + RC 隔离

```
在「方案 3 短事务重构」基础上：
  ① createLocal 短事务隔离级别改为 READ COMMITTED

→ 全并发、无死锁、无重试。
```

### 6.4 原理（已与用户多轮确认）

```
① 间隙锁只在 RR 隔离产生；RC 下非锁定读（SELECT 查重）不加间隙锁；
   INSERT 的插入意向锁互相兼容 → 并发插入不冲突。
② device 索引为非唯一，RC 下无「唯一键重复检查」的间隙锁残留。
③ 隔离级别只作用于 createLocal 这一个 REQUIRES_NEW 短事务，
   不影响全库其他逻辑。
④ 主键点 UPDATE（saveDeviceAllFields、increaseDeviceCount）本身无间隙锁，天然安全。
```

**1. DeviceLocalCreateService.java**

```java
// 增加隔离级别：REQUIRES_NEW 短事务 + READ_COMMITTED
@Transactional(propagation = Propagation.REQUIRES_NEW, isolation = Isolation.READ_COMMITTED)
public Device createLocal(Device device, String productId, DeviceVo vo, String iotInstance, boolean inStock) {}
```



### 6.6 并发 / 死锁效果

| 指标 | 结果 |
|---|---|
| 同产品并发创建 | 全并发（无排队、无串行） |
| 死锁（1213） | 消除（RC 无间隙锁） |
| 失败 | 无（无需重试） |
| deviceCount | 原子递增，无丢失更新 |
| 调用模式 | create()/各调用方不变，HTTP 端点不变 |

### 6.7 注意事项

```
① 同设备名并发直连 create()：
   RC 下查重为一致读，极端并发同名单可能插重（无唯一约束，与历史行为一致，
   active() 路径由 Redis ACTIVE_LOCK 兜底）。如需彻底防重，后续可考虑
   (product_key, device_name) 唯一索引（需先清理历史重复数据）。

② 未来隐患：
   若新增按 device_name 等二级索引的范围 UPDATE/DELETE，RC 下仍需注意
   （范围写操作在 RC 也会锁匹配记录），但主键点操作天然安全。

③ REQUIRES_NEW 占第二个连接池连接：
   高并发时评估连接池大小。
```

---

## 附录：知识体系总览

```
MySQL 核心知识树：

数据存储
├── B+ 树索引（为什么用、结构、聚簇/非聚簇）
├── 数据页（16KB 页结构、页分裂）
└── Buffer Pool（内存缓存、LRU 淘汰）

排序
├── 利用索引排序（最优先）
├── Filesort（单路/双路排序）
└── 归并排序（内存不够时）

事务
├── ACID（undo log + redo log）
├── 隔离级别（4 种 + MVCC）
├── 锁机制（行锁、间隙锁、Next-Key Lock）
└── redo log + undo log

一致性
├── Binlog（3 种格式）
├── 主从复制（异步/半同步/GTID）
├── 主从延迟（原因 + 优化）
└── CAP 理论（CP vs AP）

查询优化
├── EXPLAIN（type、Extra、rows）
├── 索引优化（最左前缀、覆盖索引、索引下推）
├── JOIN 优化（驱动表选择、被驱动表索引）
├── 慢查询（日志、分析、优化）
└── 分页优化（延迟关联、游标法）

实战案例
└── 设备激活 1213 死锁（短事务 + RC 隔离，去行锁）
```
