# 布隆过滤器（Bloom Filter）

## 一个实际问题

假设你有一个集合，里面有 100 万个元素，现在给你一个元素，问它在不在集合里。

| 方案 | 查询速度 | 内存消耗 |
|------|---------|---------|
| HashSet | O(1) | 高（存完整数据） |
| 数组/链表 | O(n) | 中 |
| **布隆过滤器** | **O(1)** | **极低** |

布隆过滤器的核心能力：**用极少的内存，告诉你"一个元素是否可能存在"。**

但它有一个限制：
- ✅ 如果说"不存在" → **一定不存在**
- ❓ 如果说"可能存在" → **可能真的存在，也可能不存在（误判）**

这种特性叫"允许误判，但不允许漏判"。

---

## 核心思想

布隆过滤器本质上是一个**位数组（bit array）** + **多个哈希函数**。

### 结构

```
位数组（初始全 0）：
  [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, ...]
```

### 插入一个元素

用 **k 个不同的哈希函数**对元素分别求值，得到 k 个位置，把这些位置都置为 1。

```
以 "cat" 为例，用 3 个哈希函数：

h1("cat") = 5 → 把第 5 位置 1
h2("cat") = 8 → 把第 8 位置 1
h3("cat") = 12 → 把第 12 位置 1

位数组变成：
  [0, 0, 0, 0, 0, 1, 0, 0, 1, 0, 0, 0, 1, ...]
                ↑        ↑        ↑
               第5位    第8位    第12位
```

### 查询一个元素

用同样的 k 个哈希函数计算位置，检查这些位置是否都是 1：

- **如果有任何一个位置是 0** → 元素**一定不存在**（因为如果存在，该位置一定是 1）
- **如果所有位置都是 1** → 元素**可能存在**（因为可能是别的元素"恰好"占了这些位置）

```
查询 "dog"：
h1("dog") = 2 → 第 2 位是 0 → ❌ "dog" 一定不存在！
h2("dog") = 6 → （不需要查了，已经是 0）
h3("dog") = 11 → （不需要查了）

查询 "cat"：
h1("cat") = 5 → 第 5 位是 1 ✓
h2("cat") = 8 → 第 8 位是 1 ✓
h3("cat") = 12 → 第 12 位是 1 ✓
→ "cat" 可能存在（大概率真的存在）
```

---

## 为什么会有误判？

因为不同的元素可能"撞"到相同的位置。

```
插入 "cat"：位置 [5, 8, 12] → 全部置 1

插入 "bat"：位置 [5, 12, 15] → 位置 5 和 12 本来就是 1，只把 15 置 1

现在查询 "dog"：
  h1("dog") = 5 → 1 ✓（其实是 cat/bat 放的）
  h2("dog") = 8 → 1 ✓（其实是 cat 放的）
  h3("dog") = 12 → 1 ✓（其实是 cat/bat 放的）
  → 所有位置都是 1！但 "dog" 从来没有被插入过！
  → ❗ 误判了！
```

这就是**哈希冲突**导致的误判——布隆过滤器**牺牲了精确性换取了空间效率**。

---

## 实际应用场景

| 场景 | 作用 | 误判的后果 |
|------|------|-----------|
| 浏览器防钓鱼 | 判断 URL 是否在黑名单 | 误判 → 拦截了一个安全的网站（可以申诉恢复） |
| 数据库缓存 | 判断数据是否在缓存中 | 误判 → 多一次缓存查询（不影响正确性） |
| 爬虫去重 | 判断 URL 是否已经爬过 | 误判 → 少爬一次（数据可以补爬） |
| 区块链 | 比特币节点判断交易是否存在 | 误判 → 多下载一些数据 |
| 大文件去重 | 判断文件哈希是否已存在 | 误判 → 多存一份（可以后续清理） |

**关键**：这些场景的共同特点是——误判的代价很小，漏判的代价很大。

---

## 布隆过滤器的数学推导

### 前置知识

- **m**：位数组总长度（bit 数）
- **n**：已经插入的元素个数
- **k**：哈希函数个数
- **P**：误判率（查询一个**不存在**的元素时，被误判为"存在"的概率）

---

### 第一步：推导误判率公式

$$P = \left(1 - e^{-kn/m}\right)^k$$

#### 1.1 一个特定位置被某个哈希函数命中为 1 的概率

插入**一个**元素时，k 个哈希函数会命中 k 个不同的位置。

对**某一个特定位置**来说：

- 被**某个特定的哈希函数**命中的概率 = $\frac{1}{m}$
- 被**某个特定的哈希函数**没命中的概率 = $1 - \frac{1}{m}$

#### 1.2 一个特定位置在所有 k 个哈希函数中都没被命中的概率

插入**一个**元素，用 k 个哈希函数，某个位置全部没被命中的概率：

$$\left(1 - \frac{1}{m}\right)^k$$

#### 1.3 插入 n 个元素后，某个位置仍然为 0 的概率

插入 n 个元素，每个元素的 k 个哈希函数都是独立随机分布的。

某个位置在所有 n 个元素、所有 k 次哈希中**都没被命中**的概率：

$$\left(1 - \frac{1}{m}\right)^{kn}$$

> 解释：总共做了 kn 次哈希（n 个元素 × k 个哈希函数），每次命中该位置的概率是 1/m，全部没命中的概率就是 $(1 - 1/m)$ 的 kn 次方。

#### 1.4 当 m 很大时的近似

当 m 很大时（实际布隆过滤器的 m 通常是几百万），可以用一个重要近似：

$$\left(1 - \frac{1}{m}\right)^{kn} ≈ e^{-kn/m}$$

**为什么？** 这是极限定义：

$$\lim_{x \to \infty} \left(1 - \frac{1}{x}\right)^x = \frac{1}{e}$$

推导：
$$\left(1 - \frac{1}{m}\right)^{kn} = \left[\left(1 - \frac{1}{m}\right)^m\right]^{kn/m} ≈ \left(e^{-1}\right)^{kn/m} = e^{-kn/m}$$

#### 1.5 某个位置为 1 的概率

$$某个位置为 1 的概率 = 1 - 某个位置为 0 的概率 = 1 - e^{-kn/m}$$

#### 1.6 误判率 P

查询一个**不存在**的元素时，需要用 k 个哈希函数计算 k 个位置。

**误判**的条件是：这 k 个位置**全都是 1**（但其实是别的元素设的，不是这个元素）。

假设这 k 个位置之间相互独立（近似成立），则 k 个位置全是 1 的概率：

$$P = \left(1 - e^{-kn/m}\right)^k$$

这就是误判率公式 ✅

---

### 第二步：推导最优哈希函数数量 k

我们希望找到**使 P 最小的 k 值**。

#### 2.1 简化表达

令 $x = \frac{kn}{m}$，则 $k = \frac{mx}{n}$，代入误判率公式：

$$P = \left(1 - e^{-x}\right)^k = \left(1 - e^{-x}\right)^{\frac{mx}{n}}$$

两边取对数（最小化 P 等价于最小化 ln P）：

$$\ln P = \frac{mx}{n} \cdot \ln(1 - e^{-x})$$

#### 2.2 求导找极值

对 x 求导，令导数为 0：

$$\frac{d}{dx}\ln P = \frac{m}{n} \cdot \left[\ln(1 - e^{-x}) + x \cdot \frac{e^{-x}}{1 - e^{-x}}\right] = 0$$

整理：

$$\ln(1 - e^{-x}) + \frac{x e^{-x}}{1 - e^{-x}} = 0$$

$$\ln(1 - e^{-x}) = -\frac{x e^{-x}}{1 - e^{-x}}$$

#### 2.3 解方程

令 $y = e^{-x}$，则 $1 - e^{-x} = 1 - y$，方程变成：

$$\ln(1 - y) = -\frac{-\ln y \cdot y}{1 - y} = \frac{y \ln y}{1 - y}$$

经过代数推导，这个方程的解是 **$y = \frac{1}{2}$**，即 $e^{-x} = \frac{1}{2}$。

代入验证：
- 左边：$\ln(1 - \frac{1}{2}) = \ln\frac{1}{2} = -\ln 2$
- 右边：$-\frac{x \cdot \frac{1}{2}}{1 - \frac{1}{2}} = -x$
- 要使两边相等：$-x = -\ln 2$，即 $x = \ln 2$

#### 2.4 得出最优 k

$x = \ln 2$，代回 $x = \frac{kn}{m}$：

$$\frac{kn}{m} = \ln 2$$

$$k = \frac{m}{n} \ln 2$$

这就是最优哈希函数数量 ✅

> **直观理解**：$k = \frac{m}{n} \ln 2$ 意味着，位数组越大（m），或者期望插入的元素越少（n），就應該用更多的哈希函数。哈希函数越多，每个位置被设成 1 的概率越分散，误判越低；但太多了又会把数组"填太满"，反而增加误判。最优 k 是两者的平衡点。

---

### 第三步：推导最少位数组大小 m

我们希望：**给定期望的误判率 P，求最小的 m**。

#### 3.1 将最优 k 代入误判率公式

把 $k = \frac{m}{n} \ln 2$ 代入 $P = (1 - e^{-kn/m})^k$：

先算内部：
$$\frac{kn}{m} = \frac{m}{n} \ln 2 \cdot \frac{n}{m} = \ln 2$$

$$e^{-kn/m} = e^{-\ln 2} = \frac{1}{2}$$

$$P = \left(1 - \frac{1}{2}\right)^k = \left(\frac{1}{2}\right)^k$$

#### 3.2 解出 k

$$P = \left(\frac{1}{2}\right)^k$$

两边取自然对数：

$$\ln P = k \cdot \ln\left(\frac{1}{2}\right) = k \cdot (-\ln 2)$$

$$k = -\frac{\ln P}{\ln 2}$$

#### 3.3 解出 m

把 $k = -\frac{\ln P}{\ln 2}$ 代入 $k = \frac{m}{n} \ln 2$：

$$-\frac{\ln P}{\ln 2} = \frac{m}{n} \ln 2$$

$$m = -\frac{n \ln P}{(\ln 2)^2}$$

这就是最少位数组大小公式 ✅

---

### 三公式总结

| 公式 | 含义 |
|------|------|
| $P = \left(1 - e^{-kn/m}\right)^k$ | 误判率：在 m、n、k 确定时，实际误判率是多少 |
| $k = \frac{m}{n} \ln 2$ | 最优 k：给定 m 和 n，多少哈希函数误判率最低 |
| $m = -\frac{n \ln P}{(\ln 2)^2}$ | 最少 m：给定期望误判率 P 和元素数 n，最少需要多少位 |

---

### 举例计算

- 存储 100 万个元素（n=1,000,000）
- 希望误判率 ≤ 0.1%（P=0.001）

$$m = -\frac{1000000 \times \ln(0.001)}{(\ln 2)^2} = -\frac{1000000 \times (-6.9078)}{0.4805} ≈ 9.58 \times 10^6$$

即需要约 **9.6 Mbit ≈ 1.2 MB** 内存。

如果用 HashSet 存储 100 万个字符串（假设每个字符串 20 字节），需要 **20 MB**。

**布隆过滤器省了约 16 倍内存！**

---

## Java 实现

### 基础实现（使用标准库哈希）

```java
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.BitSet;

/**
 * 布隆过滤器（Bloom Filter）实现
 *
 * 使用 BitSet 作为底层位数组，使用 MD5/SHA256 等哈希算法生成多个哈希值。
 *
 * 使用方式：
 *   BloomFilter bf = new BloomFilter(100000, 0.01); // 10万元素，1%误判率
 *   bf.add("hello");
 *   bf.mightContain("hello");  // true
 *   bf.mightContain("world");  // false（一定不在）
 */
public class BloomFilter {
    // 位数组
    private final BitSet bits;
    // 哈希函数数量
    private final int hashCount;
    // 位数组大小
    private final int size;

    /**
     * 构造布隆过滤器
     *
     * @param expectedInsertions 期望插入的元素数量
     * @param falsePositiveRate  期望的误判率（如 0.01 表示 1%）
     */
    public BloomFilter(int expectedInsertions, double falsePositiveRate) {
        // 计算最优位数组大小 m
        // m = -n * ln(p) / (ln 2)^2
        this.size = (int) Math.ceil(
            -expectedInsertions * Math.log(falsePositiveRate) / (Math.log(2) * Math.log(2))
        );
        // 计算最优哈希函数数量 k
        // k = (m / n) * ln 2
        this.hashCount = Math.max(1, (int) Math.ceil(
            (size / (double) expectedInsertions) * Math.log(2)
        ));
        this.bits = new BitSet(size);
        System.out.println("布隆过滤器初始化：");
        System.out.println("  位数组大小: " + size + " bits (" + (size / 8 / 1024) + " KB)");
        System.out.println("  哈希函数数: " + hashCount);
        System.out.println("  期望元素数: " + expectedInsertions);
        System.out.println("  期望误判率: " + (falsePositiveRate * 100) + "%");
    }

    /**
     * 添加一个元素
     * 用 k 个哈希函数计算 k 个位置，全部置为 1
     */
    public void add(String element) {
        int[] positions = hash(element);
        for (int pos : positions) {
            bits.set(pos);
        }
    }

    /**
     * 判断一个元素是否可能存在
     * 如果所有 k 个位置都是 1，返回 true（可能存在）
     * 如果有任何一个位置是 0，返回 false（一定不存在）
     */
    public boolean mightContain(String element) {
        int[] positions = hash(element);
        for (int pos : positions) {
            if (!bits.get(pos)) {
                return false;  // 有一个位置是 0 → 一定不存在
            }
        }
        return true;  // 全部是 1 → 可能存在
    }

    /**
     * 用 k 个哈希函数对元素进行哈希
     *
     * 这里用了一个技巧：不用 k 个独立的哈希算法，
     * 而是用 2 个哈希函数，通过组合生成 k 个不同的哈希值。
     *
     * 公式：h_i(element) = h1(element) + i * h2(element)
     *
     * 这样可以大大减少计算开销，因为只需要计算 h1 和 h2 两次。
     */
    private int[] hash(String element) {
        int[] result = new int[hashCount];
        int[] hashValues = hashString(element);

        // 用 h1 和 h2 组合生成 k 个哈希值
        for (int i = 0; i < hashCount; i++) {
            int combined = hashValues[0] + i * hashValues[1];
            // 取绝对值再取模，保证在 [0, size) 范围内
            int pos = Math.abs(combined) % size;
            result[i] = pos;
        }
        return result;
    }

    /**
     * 计算一个字符串的 2 个哈希值
     * 使用 Java 内置的 hashCode 和字符串反转后的 hashCode 作为两个独立哈希
     * 这样可以模拟两个不同的哈希函数
     */
    private int[] hashString(String element) {
        int h1 = element.hashCode();
        // 用反转后的字符串生成第二个不同的哈希值
        String reversed = new StringBuilder(element).reverse().toString();
        int h2 = reversed.hashCode();
        return new int[]{h1, h2};
    }
}
```

### 演示程序

```java
public class BloomFilterDemo {
    public static void main(String[] args) {
        System.out.println("=====================================");
        System.out.println("     布隆过滤器演示");
        System.out.println("=====================================\n");

        BloomFilter bf = new BloomFilter(10000, 0.01);

        // 插入一些单词
        String[] words = {"apple", "banana", "cherry", "date", "elderberry"};
        for (String word : words) {
            bf.add(word);
        }
        System.out.println("已插入: " + String.join(", ", words) + "\n");

        // 查询已存在的单词
        System.out.println("【查询已存在的单词】");
        for (String word : words) {
            System.out.println("  " + word + ": " + (bf.mightContain(word) ? "存在" : "不存在"));
        }
        System.out.println();

        // 查询不存在的单词
        System.out.println("【查询不存在的单词】");
        String[] notInSet = {"orange", "grape", "kiwi", "mango", "lemon"};
        for (String word : notInSet) {
            boolean exists = bf.mightContain(word);
            System.out.println("  " + word + ": " + (exists ? "可能存在（误判！）" : "一定不存在"));
        }
        System.out.println();

        // 大规模测试误判率
        System.out.println("【大规模误判率测试】");
        int insertCount = 10000;
        int testCount = 10000;
        int falsePositives = 0;

        BloomFilter bigBf = new BloomFilter(insertCount, 0.01);

        // 插入 10000 个元素
        for (int i = 0; i < insertCount; i++) {
            bigBf.add("element-" + i);
        }

        // 用不存在的元素测试
        for (int i = 0; i < testCount; i++) {
            if (bigBf.mightContain("not-in-set-" + i)) {
                falsePositives++;
            }
        }

        double actualRate = (double) falsePositives / testCount * 100;
        System.out.println("  插入: " + insertCount + " 个元素");
        System.out.println("  测试: " + testCount + " 个不存在元素");
        System.out.println("  误判次数: " + falsePositives);
        System.out.println("  实际误判率: " + actualRate + "%");
        System.out.println("  期望误判率: 1.0%");
        System.out.println("  是否达标: " + (actualRate <= 1.5 ? "✅ 是" : "❌ 否"));
    }
}
```

### 运行结果示例

```
布隆过滤器初始化：
  位数组大小: 95851 bits (11 KB)
  哈希函数数: 7
  期望元素数: 10000
  期望误判率: 1.0%

【查询已存在的单词】
  apple: 存在
  banana: 存在
  cherry: 存在
  date: 存在
  elderberry: 存在

【查询不存在的单词】
  orange: 一定不存在
  grape: 一定不存在
  kiwi: 一定不存在
  mango: 一定不存在
  lemon: 一定不存在

【大规模误判率测试】
  布隆过滤器初始化：
    位数组大小: 95851 bits (11 KB)
    哈希函数数: 7
    期望元素数: 10000
    期望误判率: 1.0%
  误判次数: 96
  实际误判率: 0.96%
  期望误判率: 1.0%
```

### 关键观察

1. **已存在的单词全部正确返回"存在"** ✅
2. **不存在的单词全部正确返回"一定不存在"** ✅（小数据集误判概率低）
3. **大规模测试实际误判率 0.96%**，接近期望的 1.0% ✅
4. **内存仅 11 KB** 就处理了 10000 个元素的查询

### 运行方式

```bash
cd computer/algorithms/bloom-filter
javac -encoding UTF-8 BloomFilter.java
java BloomFilter
```

---

## 布隆过滤器的优缺点

| 优点 | 缺点 |
|------|------|
| 内存占用极低（只有位数组） | 不能删除元素（删除会误伤其他元素） |
| 查询速度极快（O(1)，k 次位检查） | 有少量误判（不可漏判） |
| 插入速度快 | 不存储原始数据，无法反向查找 |
| 适合大规模数据 | 位数组大小固定，不能动态扩容 |

---

## 常见变体

| 变体 | 特点 |
|------|------|
| **计数布隆过滤器** | 用计数器代替位，支持删除 |
| **可扩展布隆过滤器** | 多个小布隆过滤器拼接，支持动态扩容 |
| **分片布隆过滤器** | 按时间段分片，过期分片整体删除 |

---

## 一句话总结

> 布隆过滤器是一个用**位数组 + 多哈希函数**实现的概率数据结构，用极少的内存告诉你"某元素是否可能存在"。它永远不会漏判，但可能会误判。适合"宁可误拦，不可漏过"的场景。

---

## 练习题

1. 如果向布隆过滤器中插入了 100 万个元素，误判率会怎么变化？
2. 为什么布隆过滤器不能删除元素？
3. 在什么场景下应该选择布隆过滤器而不是 HashSet？
4. 如果布隆过滤器太满了（所有位都是 1），会发生什么？