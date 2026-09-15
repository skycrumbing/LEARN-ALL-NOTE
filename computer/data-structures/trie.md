# Trie（字典树 / 前缀树）

> Trie 专门高效处理"前缀匹配"类问题——查一个长 L 的字符串只要 L 步，
> **和字典里有多少词无关**。它是自动补全、敏感词过滤、IP 路由的核心结构。

---

## 目录

1. [它解决什么问题](#一它解决什么问题)
2. [核心结构](#二核心结构)
3. [插入操作](#三插入操作)
4. [搜索操作](#四搜索操作)
5. [删除操作](#五删除操作)
6. [变种：压缩 Trie / 后缀 Trie](#六变种压缩-trie--后缀-trie)
7. [复杂度分析](#七复杂度分析)
8. [完整 Java 实现](#八完整-java-实现)
9. [与其他结构的串联](#九与其他结构的串联)

---

## 一、它解决什么问题

### 传统结构做前缀匹配的痛点

```
场景：有 100 万个英文单词，要判断"ca"是否是某个词的前缀

红黑树（BST）:
  按"整体顺序"组织，前缀匹配只能中序遍历所有词逐个比较
  → O(n × L)，100 万词全扫一遍

哈希表:
  O(1) 精确查找，但前缀匹配做不到
  "ca" 不是完整 key，哈希定位不到

排序数组 + 二分:
  能定位前缀范围，但每次比较仍要逐字符比
  → O(L × log n)
```

### Trie 的思路：按"字符路径"组织

```
不按整体顺序排，而是【共享前缀】

插入 "cat", "car", "card", "dog" 后：

         (root)
        /      \
       c        d
      /          \
     a            o
    / \            \
   r   t            g
  / \   ↓          ↓
 d   (cat)       (dog)
 ↓
(card)
↑
(car)
```

**关键洞察**：相同前缀的词共享路径，只在分叉处分开。

```
查 "ca" 是否有匹配的前缀:
  走 c→a，2 步确认 ✅
  和字典里有 100 万词还是 10 个词无关

查 "card" 是否存在:
  走 c→a→r→d(end)，4 步 ✅
  步数 = 字符串长度 L，与字典大小 n 无关 → O(L)
```

---

## 二、核心结构

```java
class TrieNode {
    // 每个节点最多 26 个子节点（a-z）
    // children[i] 非 null 表示有一条 'a'+i 的出边
    TrieNode[] children = new TrieNode[26];

    boolean isEnd;   // 是否是某个单词的结尾
                     // 例：插入 "car" 后，r 节点的 isEnd = true

    // 扩展：如果要支持删除时统计子节点数，可加：
    int childCount;  // 该节点有几个非空 children
}
```

### 节点的两种角色

```
Trie 中每个节点同时扮演两个角色:

  角色 1 · 路径中转站
    "car" 走到 r 时，r 是 "ca" 的终点，也是继续走向 "card" 的中转
    → r 的 isEnd = true（"car" 结尾）+ children['d'] 非空（可继续走）

  角色 2 · 单词结尾标记
    插入 "cat" 后，t 的 isEnd = true
    插入 "car" 后，r 的 isEnd = true

⚠️ 关键区别:
  isEnd = true   → 这是一个完整单词的结尾
  isEnd = false  → 只是前缀路径上的中间节点（"ca" 走到 a，但 "ca" 本身不是字典里的词）
```

### 一个常被忽略的细节：前缀本身是否算词？

```
字典: ["app", "apple"]

插入后:
      root
       |
       a
       |
       p
       |
       p (isEnd=true, "app" 结尾)
       |
       l
       |
       e (isEnd=true, "apple" 结尾)

问："app" 在字典里吗？→ 看 p 节点的 isEnd → true ✅
问："ap" 在字典里吗？  → 走到 p，但中间的 p 没有 isEnd → false ❌
问："appl" 在字典里吗？→ 走到 l，但 l 的 isEnd = false → false ❌

isEnd 标记的是"这个节点对应一个完整词"，和"路径走到这"是两回事
```

---

## 三、插入操作

### 算法：逐字符走，走不到就建新节点

```java
void insert(String word) {
    TrieNode curr = root;
    for (int i = 0; i < word.length(); i++) {
        int idx = word.charAt(i) - 'a';   // 字符映射到 0~25
        if (curr.children[idx] == null) {
            curr.children[idx] = new TrieNode();  // 路径不存在 → 建新节点
        }
        curr = curr.children[idx];                 // 往下走
    }
    curr.isEnd = true;   // 标记最后一个字符为单词结尾
}
```

### 插入过程图解

插入 "cat", "car", "card" 三个词：

```
Step 1: insert("cat")
  从 root 出发
  'c' → children[2] = null → 建节点 C，走到 C
  'a' → children[0] = null → 建节点 A，走到 A
  't' → children[19] = null → 建节点 T，走到 T
  T.isEnd = true

      root
       |
       c
       |
       a
       |
       t (end)


Step 2: insert("car")
  从 root 出发
  'c' → children[2] = C（已存在）→ 复用，走到 C
  'a' → children[0] = A（已存在）→ 复用，走到 A
  'r' → children[17] = null → 建节点 R，走到 R
  R.isEnd = true

      root
       |
       c
       |
       a
      / \
     t   r (end)
   (end)


Step 3: insert("card")
  从 root 出发
  'c' → 复用 C
  'a' → 复用 A
  'r' → 复用 R（已存在，且 isEnd=true）
  'd' → children[3] = null → 建节点 D，走到 D
  D.isEnd = true

      root
       |
       c
       |
       a
      / \
     t   r (end)
   (end)  |
          d (end)
```

**核心观察：前缀相同的词共享路径**

```
"cat" "car" "card" 三个词都以 "ca" 开头
  → "ca" 这段路径只建一次
  → 越多词共享前缀，越省空间

对比哈希表存这三个词:
  "cat" "car" "card" 各占独立空间，"ca" 部分重复存储 3 次
```

---

## 四、搜索操作

Trie 的搜索有两种，**别搞混**：

### 4.1 精确搜索：这个词在不在字典里

```java
boolean search(String word) {
    TrieNode node = walk(word);
    return node != null && node.isEnd;
    //                ↑ 必须是单词结尾才算"存在"
}
```

### 4.2 前缀搜索：有没有词以这个串为前缀

```java
boolean startsWith(String prefix) {
    TrieNode node = walk(prefix);
    return node != null;
    //          ↑ 只要走到这，就说明有词以它为前缀（不管 isEnd）
}
```

### 公共的"走"逻辑

```java
// 沿字符路径走，走不通就返回 null
private TrieNode walk(String s) {
    TrieNode curr = root;
    for (int i = 0; i < s.length(); i++) {
        int idx = s.charAt(i) - 'a';
        if (curr.children[idx] == null) {
            return null;   // 路径断了 → 肯定不存在
        }
        curr = curr.children[idx];
    }
    return curr;  // 走到头，返回终点节点
}
```

### 两种搜索的区别（关键！）

```
字典: ["app", "apple"]

search("app")     → 走到 p，p.isEnd=true  → true  ✅
search("apple")   → 走到 e，e.isEnd=true  → true  ✅
search("ap")      → 走到 p，但 p 是 "app" 中间那个 p，isEnd=false → false ❌
search("appl")    → 走到 l，l.isEnd=false  → false ❌

startsWith("app") → 走到 p，非 null → true  ✅（"app"/"apple" 都以它为前缀）
startsWith("ap")  → 走到 p，非 null → true  ✅（"app" 以它为前缀）
startsWith("appx")→ 走到 p 后要继续走 x，x=null → false ❌

⚠️ search 必须查 isEnd，startsWith 不查
   这是 Trie 最容易写错的边界
```

### 前缀补全：列出所有以某前缀开头的词

```java
// "输入 ca，给我所有以 ca 开头的词"
List<String> suggest(String prefix) {
    List<String> result = new ArrayList<>();
    TrieNode start = walk(prefix);
    if (start == null) return result;   // 前缀都不存在，没建议

    dfs(start, prefix, result);  // 从前缀终点开始 DFS 收集所有词
    return result;
}

private void dfs(TrieNode node, String path, List<String> result) {
    if (node.isEnd) {
        result.add(path);   // 到一个词尾 → 收集
    }
    for (int i = 0; i < 26; i++) {
        if (node.children[i] != null) {
            dfs(node.children[i], path + (char)('a' + i), result);
        }
    }
}
```

```
对 "ca" 调 suggest("ca"):
  walk 到 A 节点，从 A 开始 DFS
  → A→r(d), A→t

  DFS(A, "ca"):
    A 不是 end
    走 r: DFS(R, "car")
      R 是 end → 收集 "car"
      走 d: DFS(D, "card")
        D 是 end → 收集 "card"
    走 t: DFS(T, "cat")
      T 是 end → 收集 "cat"

  结果: ["car", "card", "cat"]  ← 所有以 "ca" 开头的词
```

> 这就是搜索框输入 "ca" 弹出候选词的原理。

---

## 五、删除操作

删除比插入/搜索复杂，因为要判断"能不能删节点"。

### 三个原则

```
删除 "card"，字典当前是 ["cat", "car", "card"]:

  删除前:
      root
       |
       c
       |
       a
      / \
     t   r (end)
   (end)  |
          d (end)

原则 1 · 要删的词不是别人的前缀 → 删掉独占的节点
  "card" 后面没有更长的词以它为前缀
  → d 节点可以直接删，r 的 children['d'] 置空

原则 2 · 要删的词是别人的前缀 → 只清 isEnd，不删节点
  假设删 "car"，但 "card" 还在
  → 不能删 r 节点（"card" 还要用）
  → 只把 r.isEnd = false

原则 3 · 删完发现父节点变空且不是词尾 → 递归往上删
  删 "card" 后，d 是叶子且不是词尾 → 删 d
  但 r 还是 "car" 的词尾，isEnd=true → r 保留
```

### 删除算法（递归回溯）

```java
// 返回 true 表示"调用方可以把当前节点删掉"
boolean delete(TrieNode node, String word, int depth) {
    // Base case: 走到词尾
    if (depth == word.length()) {
        if (!node.isEnd) return false;  // 词不存在，无操作
        node.isEnd = false;             // 先清结尾标记
        return isEmpty(node);           // 若该节点无子节点 → 可删
    }

    int idx = word.charAt(depth) - 'a';
    TrieNode child = node.children[idx];
    if (child == null) return false;    // 路径不存在，词不存在

    // 递归删子节点
    boolean shouldDeleteChild = delete(child, word, depth + 1);

    if (shouldDeleteChild) {
        node.children[idx] = null;     // 子节点可删 → 断开
        childCount--;
        // 当前节点能否删？= 自己不是词尾 + 没有其他子节点
        return !node.isEnd && isEmpty(node);
    }
    return false;
}

private boolean isEmpty(TrieNode node) {
    for (int i = 0; i < 26; i++) {
        if (node.children[i] != null) return false;
    }
    return true;
}
```

### 删除的两种情况演示

```
情况 A · 删 "card"（不是别人的前缀）
  字典 ["cat", "car", "card"] → 删 "card"

  delete(root, "card", 0)
    → 走 c → a → r → d，到词尾
    → d.isEnd = false，d 无子节点 → 返回 true
    → r 把 children['d'] 置空
    → r.isEnd = true（"car" 还在）→ r 不删，返回 false
    → a, c, root 都不删

  结果:
      root
       |
       c
       |
       a
      / \
     t   r (end)    ← "card" 的 d 节点被删，r 保留
   (end)


情况 B · 删 "car"（是 "card" 的前缀）
  字典 ["cat", "car", "card"] → 删 "car"

  delete(root, "car", 0)
    → 走 c → a → r，到词尾
    → r.isEnd = false
    → r 有子节点 d → isEmpty(r)=false → 返回 false
    → a, c, root 都不删

  结果:
      root
       |
       c
       |
       a
      / \
     t   r             ← r 的 isEnd 清掉了，但节点保留（"card" 还要用）
   (end)  |
          d (end)
```

---

## 六、变种：压缩 Trie / 后缀 Trie

### 6.1 压缩 Trie（Patricia Trie / Radix Tree）

```
标准 Trie 的问题: 一条单链路径浪费节点

  插入 "romane", "romanus", "romulus":
      root
       |
       r
       |
       o
       |
       m       ← "rom" 这段只有一个分支，却建了 3 个节点
       |
      ...

压缩 Trie: 把单链路径压缩成一个"边标签"

      root
       |
      "rom"
       /    \
    "ane"  "ulus"
              |
            "an" → "us"  ...

  节点数大幅减少，适合字典词多但前缀重复度高的场景
  IP 路由表（最长前缀匹配）就用 Patricia Trie
```

### 6.2 后缀 Trie / 后缀树

```
把一个字符串的所有后缀都建到 Trie 里:

  "banana" 的后缀: "banana", "anana", "nana", "ana", "na", "a"

  后缀 Trie:
      root
      / | \
     b  a  n
     |  |  |
     a  n  a
     |  |  |
     n  a  n
     |  |  |
     ... ... ...

  应用:
    判断 "an" 是不是 "banana" 的子串 → 走 a→n，2 步
    比 KMP / 暴力匹配都快，适合"一个文本多次查询多个模式串"场景
    （但建树 O(n²) 空间，Ukkonen 算法能 O(n) 建后缀树）
```

### 6.3 AC 自动机（Trie + KMP 思想）

```
敏感词过滤的工业级方案:

  把所有敏感词建 Trie
  + 在 Trie 上加 fail 指针（类似 KMP 的 next 数组）
  → 文本流一次扫描就能匹配所有敏感词

  vs 单纯 Trie:
    单纯 Trie: 每个起点都要从头扫一遍 → O(n × L)
    AC 自动机: 借 fail 指针复用已匹配前缀 → O(n + 匹配数)
```

---

## 七、复杂度分析

```
设 m = 字典词数，L = 单词平均长度，Σ = 字符集大小（如 26）

┌──────────────┬─────────────┬──────────────────────────────┐
│ 操作          │ 时间         │ 说明                          │
├──────────────┼─────────────┼──────────────────────────────┤
│ 插入          │ O(L)        │ 走 L 个字符建/复用节点         │
│ 精确搜索      │ O(L)        │ 走 L 个字符                   │
│ 前缀搜索      │ O(L)        │ 走 L 个字符确认前缀存在        │
│ 前缀补全      │ O(L + 结果) │ 定位前缀 + DFS 收集所有词      │
│ 删除          │ O(L)        │ 走到词尾 + 回溯删空节点        │
├──────────────┼─────────────┼──────────────────────────────┤
│ 空间          │ O(m × L × Σ)│ 最坏每节点 Σ 个指针            │
│              │             │ 前缀共享时实际更小             │
└──────────────┴─────────────┴──────────────────────────────┘

关键对比:
  红黑树查找: O(L × log m)  每次 key 比较要逐字符
  哈希表查找: O(L)         但不支持前缀匹配
  Trie 查找:  O(L)         且支持前缀匹配 ✅

  → Trie 的查找时间和字典大小 m 无关，只和词长 L 有关
     这是它对 BST/哈希的最大优势
```

### 空间换时间的代价

```
Trie 节点数 = 所有词的字符总数 - 共享前缀数

  字典 ["cat", "car", "card"]:
    总字符 = 3+3+4 = 10
    共享前缀 "ca" 省 2 个节点（两个词共享）
    实际节点 ≈ 6

  最坏情况: 词之间无公共前缀（如 "a", "b", "c", ...）
    → 每个词独立一条路径，节点数 = 总字符数

每个节点 26 个指针:
  → 指针本身占空间（8B × 26 = 208B/节点）
  → 词多但前缀重复度低时，Trie 比哈希表更费空间

优化: 用 HashMap 代替数组存 children
  children: HashMap<Character, TrieNode>
  → 稀疏节点省空间，但查找多一次哈希开销
```

---

## 八、完整 Java 实现

```java
public class Trie {

    static class TrieNode {
        TrieNode[] children = new TrieNode[26];
        boolean isEnd;

        boolean isEmpty() {
            for (TrieNode c : children) {
                if (c != null) return false;
            }
            return true;
        }
    }

    private final TrieNode root = new TrieNode();

    // ===== 插入 =====
    public void insert(String word) {
        TrieNode curr = root;
        for (char ch : word.toCharArray()) {
            int idx = ch - 'a';
            if (curr.children[idx] == null) {
                curr.children[idx] = new TrieNode();
            }
            curr = curr.children[idx];
        }
        curr.isEnd = true;
    }

    // ===== 精确搜索 =====
    public boolean search(String word) {
        TrieNode node = walk(word);
        return node != null && node.isEnd;
    }

    // ===== 前缀搜索 =====
    public boolean startsWith(String prefix) {
        return walk(prefix) != null;
    }

    // 公共的走路径逻辑
    private TrieNode walk(String s) {
        TrieNode curr = root;
        for (char ch : s.toCharArray()) {
            int idx = ch - 'a';
            if (curr.children[idx] == null) return null;
            curr = curr.children[idx];
        }
        return curr;
    }

    // ===== 前缀补全 =====
    public java.util.List<String> suggest(String prefix) {
        java.util.List<String> result = new java.util.ArrayList<>();
        TrieNode start = walk(prefix);
        if (start == null) return result;
        dfs(start, prefix, result);
        return result;
    }

    private void dfs(TrieNode node, String path, java.util.List<String> result) {
        if (node.isEnd) result.add(path);
        for (int i = 0; i < 26; i++) {
            if (node.children[i] != null) {
                dfs(node.children[i], path + (char)('a' + i), result);
            }
        }
    }

    // ===== 删除 =====
    public void delete(String word) {
        delete(root, word, 0);
    }

    private boolean delete(TrieNode node, String word, int depth) {
        if (depth == word.length()) {
            if (!node.isEnd) return false;  // 词不存在
            node.isEnd = false;
            return node.isEmpty();           // 没子节点 → 可删
        }

        int idx = word.charAt(depth) - 'a';
        TrieNode child = node.children[idx];
        if (child == null) return false;    // 路径不存在

        if (delete(child, word, depth + 1)) {
            node.children[idx] = null;      // 子节点可删 → 断开
            return !node.isEnd && node.isEmpty();
        }
        return false;
    }
}
```

### 使用示例

```java
public class Main {
    public static void main(String[] args) {
        Trie trie = new Trie();
        trie.insert("cat");
        trie.insert("car");
        trie.insert("card");
        trie.insert("dog");

        System.out.println(trie.search("car"));       // true
        System.out.println(trie.search("ca"));        // false（"ca" 不是完整词）
        System.out.println(trie.startsWith("ca"));    // true（有词以 "ca" 为前缀）
        System.out.println(trie.startsWith("dox"));   // false

        System.out.println(trie.suggest("ca"));       // [car, card, cat]

        trie.delete("card");
        System.out.println(trie.search("card"));      // false
        System.out.println(trie.search("car"));       // true（"car" 还在）
    }
}
```

---

## 九、与其他结构的串联

```
Trie 和已学结构的对照:

┌──────────────┬──────────────────────────────────────────────┐
│ 维度         │ 对照                                          │
├──────────────┼──────────────────────────────────────────────┤
│ 组织方式     │                                              │
│ 红黑树/跳表  │ 按"整体顺序"组织（BST 性质）                  │
│ 堆           │ 按"优先级"组织（完全二叉树）                   │
│ Trie         │ 按"字符路径"组织（共享前缀）                  │
├──────────────┼──────────────────────────────────────────────┤
│ 数组存树     │                                              │
│ 堆           │ 用下标公式 parent=(i-1)/2 表达完全二叉树       │
│              │ → 见 integer-rounding.md 的推导               │
│ Trie         │ 用 children[26] 数组表达 26 叉树              │
│              │ → 两种"用数组存树"的不同形态                   │
├──────────────┼──────────────────────────────────────────────┤
│ 数组存森林   │                                              │
│ 并查集       │ parent[] 往上找根（子→父方向）                │
│ Trie         │ children[] 往下找叶（父→子方向）              │
│              │ → 方向相反的两种"数组存森林/树"               │
├──────────────┼──────────────────────────────────────────────┤
│ 概率 vs 精确 │                                              │
│ 布隆过滤器   │ 概率判断"可能在集合里"（有假阳性）            │
│ Trie         │ 精确判断"在/不在" + 前缀匹配                  │
│              │ → 前缀匹配是布隆做不到的                      │
├──────────────┼──────────────────────────────────────────────┤
│ 自平衡思想   │                                              │
│ 红黑树       │ 旋转 + 变色维持 O(log n)                      │
│ 跳表         │ 概率多层索引维持期望 O(log n)                 │
│ Trie         │ 不需要平衡！结构由词本身决定，天然无退化       │
│              │ → 这是 Trie 的独特优势                       │
└──────────────┴──────────────────────────────────────────────┘
```

### 选型速查

| 场景 | 用什么 | 理由 |
|------|--------|------|
| 有序集合 + 精确查找 | 红黑树 / 跳表 | BST 性质，范围查询好 |
| 优先级 / Top-K | 堆 | O(1) 取最值 |
| 动态连通性 | 并查集 | O(α) ≈ O(1) |
| 存在性（可容忍假阳性） | 布隆过滤器 | 省空间 |
| **前缀匹配 / 自动补全** | **Trie** | O(L) 与字典大小无关 |
| 敏感词过滤（多模式匹配） | AC 自动机 | Trie + KMP 思想 |
| IP 路由（最长前缀匹配） | Patricia Trie | 压缩 Trie |

### 关联笔记

```
computer/data-structures/heap.md
  → 都是"用数组表达树形结构"的形态对照
  → 堆用下标公式，Trie 用 children 数组

computer/algorithms/union-find.md
  → 都是"用数组存森林/树"
  → 并查集 parent[] 向上，Trie children[] 向下

computer/algorithms/bloom-filter/bloom-filter.md
  → 概率 vs 精确的对照
  → 布隆查"可能在"，Trie 查"在不在 + 前缀匹配"

computer/algorithms/integer-rounding.md
  → 堆的下标公式 (i-1)/2 在这里有推导
  → Trie 不涉及下标公式，但和堆同属"数组存树"家族
```
