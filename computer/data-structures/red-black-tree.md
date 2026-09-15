# 红黑树（Red-Black Tree）

> 红黑树是一种**近似平衡的二叉搜索树**，保证任意操作的最坏时间复杂度为 **O(log n)**。
> 它是 JDK `TreeMap`、`ConcurrentSkipListMap` 以及 Linux 内核中大量使用的数据结构。

---

## 目录

1. [为什么需要红黑树](#一为什么需要红黑树)
2. [红黑树的五条性质](#二红黑树的五条性质)
3. [节点结构](#三节点结构)
4. [搜索操作](#四搜索操作)
5. [左旋与右旋](#五左旋与右旋)
6. [插入操作](#六插入操作)
7. [删除操作](#七删除操作)
8. [时间复杂度分析](#八时间复杂度分析)
9. [完整 Java 实现](#九完整-java-实现)
10. [红黑树 vs B+树：存储介质决定数据结构](#十红黑树-vs-b+树存储介质决定数据结构)

---

## 一、为什么需要红黑树

### 二叉搜索树（BST）的退化问题

```
理想 BST：平衡，查找 O(log n)
          50
         /  \
       25    75
      / \    / \
    10  35 60  90

退化 BST：链状，查找 O(n)
         1
          \
           2
            \
             3
              \
               4
                \
                 5
```

```
普通 BST 在有序数据插入时退化为链表：
  插入顺序 1, 2, 3, 4, 5
  → 查找第 5 个元素需要走 5 步 = O(n)

红黑树的解决：
  通过"颜色 + 旋转 + 重新着色"三个手段，
  在插入和删除时强制保持树的近似平衡
  → 任意操作最坏 O(log n)
```

---

## 二、红黑树的五条性质

这五条性质是红黑树所有操作的**法律依据**，插入和删除时违反任何一条，都需要修复。

```
性质 1：每个节点要么是红色，要么是黑色。
性质 2：根节点是黑色。
性质 3：每个叶子节点（NIL）是黑色。
性质 4：如果一个节点是红色，则它的两个子节点都是黑色（不能有连续红节点）。
性质 5：对每个节点，从该节点到其所有叶子节点（NIL）的简单路径上，黑色节点的数目相同（黑高相同）。
```

### 性质图解

```
        [B] 根节点（性质2：根为黑）
        / \
      [R]   [B]
      / \   / \
    [B] [B][R] [B]
     /\  /\ /\  /\
    [B][B][B][B][B][B][B][B]  ← NIL 叶子（性质3：均为黑）

检查性质4：
  红色节点 [R] 的两个子节点都是黑色 ✅
  红色节点 [R] 的两个子节点都是黑色 ✅

检查性质5（黑高）：
  从根出发到任意 NIL：
    路径1: [B]→[R]→[B]→[B] = 3 个黑色
    路径2: [B]→[R]→[B]→[B] = 3 个黑色
    路径3: [B]→[B]→[R]→[B] = 3 个黑色
    路径4: [B]→[B]→[B]→[B] = 4 个黑色  ← 等等，这里不对！
    → 说明这棵树不满足性质5，需要修正
```

> **关键理解**：性质 4 保证没有连续红节点，性质 5 保证任意路径长度不会相差超过 2 倍。
> 这两条性质共同保证了红黑树的高度上限为 **2 log(n+1)**。

---

## 三、节点结构

```java
// 节点颜色枚举
enum Color {
    RED,    // 红
    BLACK   // 黑
}

// 红黑树节点
class Node<K extends Comparable<K>, V> {
    K key;
    V value;
    Color color;           // 节点颜色
    Node<K, V> left;       // 左子节点
    Node<K, V> right;      // 右子节点
    Node<K, V> parent;     // 父节点（用于删除时的向上回溯）

    Node(K key, V value, Color color) {
        this.key = key;
        this.value = value;
        this.color = color;
        this.left = null;
        this.right = null;
        this.parent = null;
    }
}
```

---

## 四、搜索操作

红黑树的搜索**和普通 BST 完全一样**，颜色对搜索没有影响：

```java
// 搜索操作：和普通 BST 一致
Node<K, V> search(Node<K, V> node, K key) {
    if (node == null) {
        return null;
    }

    int cmp = key.compareTo(node.key);

    if (cmp < 0) {
        return search(node.left, key);    // 小于当前节点 → 去左子树
    } else if (cmp > 0) {
        return search(node.right, key);   // 大于当前节点 → 去右子树
    } else {
        return node;                      // 等于 → 找到了
    }
}

// 时间复杂度：O(h)，h 为树的高度
// 红黑树保证 h ≤ 2 log(n+1)，所以最坏 O(log n)
```

```
搜索过程示例：

        [50]
        /    \
      [30]    [70]
      /  \    /  \
    [15] [40][60] [85]

搜索 key = 40：
  50 → 40 < 50，去左子树
  30 → 40 > 30，去右子树
  40 → 40 == 40，找到 ✅
  走了 3 步，树高 3 = O(log 7)

搜索 key = 99：
  50 → 99 > 50，去右子树
  70 → 99 > 70，去右子树
  85 → 99 > 85，去右子树
  null → 不存在 ❌
```

---

## 五、左旋与右旋

左旋和右旋是红黑树的**基本修复手段**，通过旋转改变树的结构来重新平衡。

### 左旋（Left Rotate）

```
左旋：把子节点"提"上来，把当前节点"压"下去

  左旋前：                    左旋后：
       x                        y
      / \                     /   \
     a   y       leftRotate(x)     x
        / \     ──────────►     / \
       b   c                  a   b

x 是旋转中心，y 是 x 的右子节点
y 的左子节点 b 成为 x 的右子节点
```

```java
// 左旋：以 x 为旋转中心
void leftRotate(Node<K, V> x) {
    // 1. 获取 y = x 的右子节点
    Node<K, V> y = x.right;

    // 2. y 的左子节点 b 变成 x 的右子节点
    x.right = y.left;
    if (y.left != null) {
        y.left.parent = x;
    }

    // 3. y 取代 x 的位置
    y.parent = x.parent;
    if (x.parent == null) {
        root = y;  // x 原来是根
    } else if (x == x.parent.left) {
        x.parent.left = y;
    } else {
        x.parent.right = y;
    }

    // 4. x 变成 y 的左子节点
    y.left = x;
    x.parent = y;
}
```

### 右旋（Right Rotate）

```
右旋：把子节点"提"上来，把当前节点"压"下去
（左旋的镜像操作）

  右旋前：                    右旋后：
        y                        x
       / \                   /   \
      x   c   rightRotate(y)     y
     / \                  /   \
    a   b               a     x

y 是旋转中心，x 是 y 的左子节点
x 的右子节点 b 成为 y 的左子节点
```

```java
// 右旋：以 y 为旋转中心
void rightRotate(Node<K, V> y) {
    // 1. 获取 x = y 的左子节点
    Node<K, V> x = y.left;

    // 2. x 的右子节点 b 变成 y 的左子节点
    y.left = x.right;
    if (x.right != null) {
        x.right.parent = y;
    }

    // 3. x 取代 y 的位置
    x.parent = y.parent;
    if (y.parent == null) {
        root = x;  // y 原来是根
    } else if (y == y.parent.left) {
        y.parent.left = x;
    } else {
        y.parent.right = x;
    }

    // 4. y 变成 x 的右子节点
    x.right = y;
    y.parent = x;
}
```

### 旋转的本质

```
左旋 = 右旋的逆操作
右旋 = 左旋的逆操作

旋转不改变中序遍历的顺序（仍然是 BST 性质），
只是改变了树的结构来调整平衡度。

  中序遍历：a → x → b → y → c
  左旋后：  a → x → b → y → c  ← 完全一样！
```

---

## 六、插入操作

插入是红黑树最复杂的操作之一，分为两步：**BST 插入** + **红黑树修复**。

### 6.1 第一步：BST 插入

```java
// 第一步：像普通 BST 一样插入新节点
// 新节点一律着红色（着黑色会破坏性质5，着红色最多破坏性质4）

void insert(K key, V value) {
    // 1. 创建新节点（红色）
    Node<K, V> newNode = new Node<>(key, value, Color.RED);

    // 2. 找到插入位置
    Node<K, V> parent = null;
    Node<K, V> curr = root;

    while (curr != null) {
        parent = curr;
        int cmp = key.compareTo(curr.key);
        if (cmp < 0) curr = curr.left;
        else if (cmp > 0) curr = curr.right;
        else {
            curr.value = value;  // key 已存在，更新值
            return;
        }
    }

    // 3. 链接新节点
    newNode.parent = parent;
    if (parent == null) {
        root = newNode;
    } else if (key.compareTo(parent.key) < 0) {
        parent.left = newNode;
    } else {
        parent.right = newNode;
    }

    // 4. 修复红黑树性质
    insertFixup(newNode);
}
```

### 6.2 第二步：红黑树修复（insertFixup）

新节点插入后，最多破坏**性质4**（不能有连续红节点）和**性质2**（根为黑色）。

修复的核心思路：

```
新插入的节点永远是红色。
如果它的父节点也是红色 → 违反性质4 → 需要修复。

修复分三种情况：
  情况1：叔叔节点是红色 → 变色（父节点和叔叔节点变黑，祖父节点变红，问题上传）
  情况2：叔叔节点是黑色，当前节点和父节点是"同侧" → 旋转
  情况3：叔叔节点是黑色，当前节点和父节点是"异侧" → 先旋转变同侧，再按情况2处理
```

#### 情况 1：叔叔节点是红色

```
  插入前（违反性质4，父节点和当前节点都是红色）:

        [G=红]               [P=红]
          /  \               /   \
        [P=红] [U=红]    [G=红]  [U=红]
        / \     / \       / \     / \
      [N=红] ...      [N=红] ...

  当前节点 N 和父节点 P 都是红色 → 违反性质4
  叔叔节点 U 是红色

  情况1 修复：变色
    P 变黑，U 变黑，G 变红
    → 性质4 恢复了（P 和 U 都是黑，N 和 P 不再冲突）
    → 但 G 变红后，如果 G 的父节点也是红 → 继续向上处理
    → 问题上传到 G 的父节点

  时间复杂度：可能最多 O(log n) 次上传
```

#### 情况 2：叔叔节点是黑色，N 和 P 同侧（LL 或 RR 型）

```
  情况 2a（LL 型，当前节点在左，父节点在左）:

        [G=黑]
        /
      [P=红]
      /
    [N=红]       叔叔 U = 黑（或 NIL）

  情况 2b（RR 型，当前节点在右，父节点在右）:

        [G=黑]
          \
          [P=红]
            \
            [N=红]       叔叔 U = 黑（或 NIL）

  情况2 修复：旋转 + 变色
    LL 型：对 G 做右旋，P 变黑，G 变红
    RR 型：对 G 做左旋，P 变黑，G 变红
    → 性质全部恢复，修复结束
```

#### 情况 3：叔叔节点是黑色，N 和 P 异侧（LR 或 RL 型）

```
  情况 3a（LR 型，父节点在左，当前节点在右）:

        [G=黑]
        /
      [P=红]
          \
          [N=红]       叔叔 U = 黑（或 NIL）

  情况 3b（RL 型，父节点在右，当前节点在左）:

        [G=黑]
          \
          [P=红]
         /
      [N=红]

  情况3 修复：两步旋转
    Step 1: 对 P 做左旋（LR型）或右旋（RL型）
    → 把"异侧"变成"同侧"
    Step 2: 按情况2处理

    最终效果和情况2相同：
      对 G 做相反方向的旋转，P 变黑，G 变红
```

### 完整修复代码

```java
// 插入修复
void insertFixup(Node<K, V> z) {
    // 循环处理，直到父节点为黑或 z 为根
    while (z.parent != null && z.parent.color == Color.RED) {
        if (z.parent == z.parent.parent.left) {
            // 父节点是祖父节点的左子节点
            Node<K, V> uncle = z.parent.parent.right;

            if (uncle != null && uncle.color == Color.RED) {
                // ===== 情况 1：叔叔是红色，变色 =====
                z.parent.color = Color.BLACK;
                uncle.color = Color.BLACK;
                z.parent.parent.color = Color.RED;
                z = z.parent.parent;  // 上传到祖父
            } else {
                // 叔叔是黑色
                if (z == z.parent.right) {
                    // ===== 情况 3：异侧（RL 型）先变同侧 =====
                    z = z.parent;
                    leftRotate(z);  // 对父节点左旋
                }
                // ===== 情况 2：同侧（RR 型），旋转修复 =====
                z.parent.color = Color.BLACK;
                z.parent.parent.color = Color.RED;
                rightRotate(z.parent.parent);
            }
        } else {
            // 父节点是祖父节点的右子节点（对称处理）
            Node<K, V> uncle = z.parent.parent.left;

            if (uncle != null && uncle.color == Color.RED) {
                // ===== 情况 1：叔叔是红色，变色 =====
                z.parent.color = Color.BLACK;
                uncle.color = Color.BLACK;
                z.parent.parent.color = Color.RED;
                z = z.parent.parent;
            } else {
                if (z == z.parent.left) {
                    // ===== 情况 3：异侧（LR 型）先变同侧 =====
                    z = z.parent;
                    rightRotate(z);
                }
                // ===== 情况 2：同侧（LL 型），旋转修复 =====
                z.parent.color = Color.BLACK;
                z.parent.parent.color = Color.RED;
                leftRotate(z.parent.parent);
            }
        }
    }
    // 根节点永远是黑色
    root.color = Color.BLACK;
}
```

### 插入完整示例（逐步演示）

```
插入序列：7, 3, 18, 10, 22, 8, 11, 26

Step 1: 插入 7
  7(黑)
  新节点 7 是根 → 直接置黑 ✅

Step 2: 插入 3
      7(黑)
     /
   3(红)
  3 的父节点 7 是黑 → 性质4 满足 ✅

Step 3: 插入 18
      7(黑)
     /   \
   3(红) 18(红)
  3 和 18 的父节点 7 是黑 → ✅
  18 的父节点 7 是黑 → ✅

Step 4: 插入 10
      7(黑)
     /   \
   3(红) 18(红)
          /
        10(红)
  10 红 + 18 红 → 违反性质4 ❌
  叔叔 3 是红色 → 情况1
    → 18 变黑，3 变黑，7 变红，上传到 7
    → 7 是根 → 7 变黑
      7(黑)
     /   \
   3(黑) 18(黑)
          /
        10(红)  ✅
```

---

## 七、删除操作

删除是红黑树中**最复杂**的操作，因为删除节点后可能需要多次旋转和变色来恢复性质。

### 7.1 第一步：BST 删除

红黑树的删除**完全复用普通 BST 的删除逻辑**，找到要删除的节点后分为三种情况：

```
情况 A：删除节点没有子节点 → 直接删除
情况 B：删除节点只有一个子节点 → 用子节点替代
情况 C：删除节点有两个子节点 → 找后继节点，用后继节点的值替换，然后删除后继节点
```

### 7.2 第二步：红黑树修复（deleteFixup）

BST 删除后，可能破坏性质2、3、4、5。最棘手的是**性质5**（黑高相同）。

修复的核心概念：**"双倍黑"**

```
当我们删除一个黑色节点时，该路径的黑色节点数减少了 1，
破坏了性质5。

修复思路：
  被删除节点的位置需要一个"补偿"——
  让该节点带有"双倍黑"属性（Black + Black），
  然后沿着向上路径，通过旋转和变色把双倍黑"消化"掉。

"双倍黑"不是一个真实颜色，而是修复过程中的一种标记：
  表示这个节点"欠一个黑色"，需要向上修正。
```

#### 删除修复的四种情况

假设 `x` 是"双倍黑"节点，`sibling` 是它的兄弟节点：

```
情况 1：兄弟节点是红色
═══════════════════════════════════════

      [P]
     / \
    [x] [S=红]
        /  \
      [SL] [SR]

  x 是双倍黑，sibling 是红色

  修复：对 P 做旋转，S 变黑，P 变红
  → 兄弟节点变成黑色，转去情况2/3/4

  效果：
      [P=红]
        \
        [S=黑]
       /  \
      [x]  [原结构...]

  现在 x 的兄弟节点是黑色，继续处理


情况 2：兄弟节点是黑色，兄弟的两个子节点都是黑色
═══════════════════════════════════════

      [P]
     / \
    [x] [S=黑]
        /  \
      [SL=黑] [SR=黑]

  x 是双倍黑，sibling 黑，两个侄子都是黑

  修复：S 变红
  → x 的"双倍黑"减少一个变成单黑
  → P 的"黑高"减少，问题上传到 P

  如果 P 原来是红色 → P 变黑，问题消化完毕
  如果 P 原来是黑色 → P 变成双倍黑，继续向上处理


情况 3：兄弟节点是黑色，左侄子红、右侄子黑
═══════════════════════════════════════

      [P]
     / \
    [x] [S=黑]
        /  \
      [SL=红] [SR=黑]

  x 是双倍黑，sibling 黑，左侄子红右侄子黑

  修复：S 变红，SL 变黑，对 S 右旋
  → 左侄子取代兄弟位置，变成"右侄子红"的情况
  → 转入情况 4


情况 4：兄弟节点是黑色，右侄子红（或左侄子红，对称处理）
═══════════════════════════════════════

      [P]
     / \
    [x] [S=黑]
        /  \
      [SL] [SR=红]

  x 是双倍黑，sibling 黑，右侄子红

  修复：S 变 P 的颜色，P 变黑，SR 变黑，对 P 左旋
  → x 的"双倍黑"被消化
  → 所有性质恢复
  → 修复结束！
```

### 删除修复代码

```java
// 删除修复
void deleteFixup(Node<K, V> x) {
    while (x != root && x.color == Color.BLACK) {
        if (x == x.parent.left) {
            // x 是左子节点，兄弟节点在右边
            Node<K, V> sibling = x.parent.right;

            if (sibling.color == Color.RED) {
                // ===== 情况 1：兄弟是红色 =====
                sibling.color = Color.BLACK;
                x.parent.color = Color.RED;
                leftRotate(x.parent);
                sibling = x.parent.right;  // 兄弟变了
            }

            if ((sibling.left == null || sibling.left.color == Color.BLACK)
                && (sibling.right == null || sibling.right.color == Color.BLACK)) {
                // ===== 情况 2：兄弟黑，两个侄子都是黑 =====
                sibling.color = Color.RED;
                x = x.parent;  // 问题上传
            } else {
                if (sibling.right == null || sibling.right.color == Color.BLACK) {
                    // ===== 情况 3：兄弟黑，左侄子红，右侄子黑 =====
                    sibling.left.color = Color.BLACK;
                    sibling.color = Color.RED;
                    rightRotate(sibling);
                    sibling = x.parent.right;  // 兄弟变了
                }
                // ===== 情况 4：兄弟黑，右侄子红 =====
                sibling.color = x.parent.color;
                x.parent.color = Color.BLACK;
                sibling.right.color = Color.BLACK;
                leftRotate(x.parent);
                x = root;  // 修复完成
            }
        } else {
            // x 是右子节点（对称处理）
            Node<K, V> sibling = x.parent.left;

            if (sibling.color == Color.RED) {
                sibling.color = Color.BLACK;
                x.parent.color = Color.RED;
                rightRotate(x.parent);
                sibling = x.parent.left;
            }

            if ((sibling.right == null || sibling.right.color == Color.BLACK)
                && (sibling.left == null || sibling.left.color == Color.BLACK)) {
                sibling.color = Color.RED;
                x = x.parent;
            } else {
                if (sibling.left == null || sibling.left.color == Color.BLACK) {
                    sibling.right.color = Color.BLACK;
                    sibling.color = Color.RED;
                    leftRotate(sibling);
                    sibling = x.parent.left;
                }
                sibling.color = x.parent.color;
                x.parent.color = Color.BLACK;
                sibling.left.color = Color.BLACK;
                rightRotate(x.parent);
                x = root;
            }
        }
    }
    x.color = Color.BLACK;
}
```

### 删除完整示例

```
删除 7（根节点，有左右子树）:

  原树：
        7(黑)
       /   \
     3(红) 18(红)
            /
          10(红)

  Step 1: 找后继节点
    7 的右子树中最小值 = 10
    用 10 的值替换 7

  Step 2: 删除 10
    10 没有子节点 → 直接删除
    10 是红色 → 删除红色不影响黑高 → 修复完成 ✅

  结果：
        10(黑)
       /   \
     3(红) 18(红)

  性质验证：
    根为黑 ✅
    无连续红节点 ✅
    路径1: 10→3 → 2个黑
    路径2: 10→18 → 2个黑 ✅
```

---

## 八、时间复杂度分析

```
操作          平均复杂度    最坏复杂度    说明
─────────────────────────────────────────────────
搜索          O(log n)     O(log n)    红黑树保证高度 ≤ 2 log(n+1)
插入          O(log n)     O(log n)    BST 插入 O(log n) + 修复 O(log n)
删除          O(log n)     O(log n)    BST 删除 O(log n) + 修复 O(log n)

与 AVL 树的对比：
┌──────────────────────────────────────────────────┐
│                                                    │
│  红黑树：                                          │
│    最大高度 = 2 log(n+1)                           │
│    插入最多 3 次旋转                                │
│    删除最多 3 次旋转                                │
│    实现相对简单                                     │
│                                                    │
│  AVL 树：                                          │
│    最大高度 = 1.44 log(n+1)（更平衡）                │
│    插入可能 O(log n) 次旋转                         │
│    删除可能 O(log n) 次旋转                         │
│    实现更复杂                                       │
│                                                    │
│  结论：                                            │
│    读多写少 → AVL 树（搜索更快）                     │
│    写多读少 → 红黑树（插入/删除更快）                │
│                                                    │
└──────────────────────────────────────────────────┘
```

---

## 九、完整 Java 实现

```java
public class RedBlackTree<K extends Comparable<K>, V> {

    enum Color {
        RED, BLACK
    }

    static class Node<K, V> {
        K key;
        V value;
        Color color;
        Node<K, V> left, right, parent;

        Node(K key, V value, Color color) {
            this.key = key;
            this.value = value;
            this.color = color;
        }
    }

    private Node<K, V> root;

    // ===== 搜索 =====
    public V search(K key) {
        Node<K, V> node = searchNode(key);
        return node != null ? node.value : null;
    }

    private Node<K, V> searchNode(K key) {
        Node<K, V> curr = root;
        while (curr != null) {
            int cmp = key.compareTo(curr.key);
            if (cmp < 0) curr = curr.left;
            else if (cmp > 0) curr = curr.right;
            else return curr;
        }
        return null;
    }

    // ===== 插入 =====
    public void insert(K key, V value) {
        Node<K, V> newNode = new Node<>(key, value, Color.RED);
        Node<K, V> parent = null;
        Node<K, V> curr = root;

        while (curr != null) {
            parent = curr;
            int cmp = key.compareTo(curr.key);
            if (cmp < 0) curr = curr.left;
            else if (cmp > 0) curr = curr.right;
            else { curr.value = value; return; }
        }

        newNode.parent = parent;
        if (parent == null) root = newNode;
        else if (key.compareTo(parent.key) < 0) parent.left = newNode;
        else parent.right = newNode;

        insertFixup(newNode);
    }

    private void insertFixup(Node<K, V> z) {
        while (z.parent != null && z.parent.color == Color.RED) {
            if (z.parent == z.parent.parent.left) {
                Node<K, V> uncle = z.parent.parent.right;
                if (uncle != null && uncle.color == Color.RED) {
                    z.parent.color = Color.BLACK;
                    uncle.color = Color.BLACK;
                    z.parent.parent.color = Color.RED;
                    z = z.parent.parent;
                } else {
                    if (z == z.parent.right) {
                        z = z.parent;
                        leftRotate(z);
                    }
                    z.parent.color = Color.BLACK;
                    z.parent.parent.color = Color.RED;
                    rightRotate(z.parent.parent);
                }
            } else {
                Node<K, V> uncle = z.parent.parent.left;
                if (uncle != null && uncle.color == Color.RED) {
                    z.parent.color = Color.BLACK;
                    uncle.color = Color.BLACK;
                    z.parent.parent.color = Color.RED;
                    z = z.parent.parent;
                } else {
                    if (z == z.parent.left) {
                        z = z.parent;
                        rightRotate(z);
                    }
                    z.parent.color = Color.BLACK;
                    z.parent.parent.color = Color.RED;
                    leftRotate(z.parent.parent);
                }
            }
        }
        root.color = Color.BLACK;
    }

    // ===== 左旋 =====
    private void leftRotate(Node<K, V> x) {
        Node<K, V> y = x.right;
        x.right = y.left;
        if (y.left != null) y.left.parent = x;
        y.parent = x.parent;
        if (x.parent == null) root = y;
        else if (x == x.parent.left) x.parent.left = y;
        else x.parent.right = y;
        y.left = x;
        x.parent = y;
    }

    // ===== 右旋 =====
    private void rightRotate(Node<K, V> y) {
        Node<K, V> x = y.left;
        y.left = x.right;
        if (x.right != null) x.right.parent = y;
        x.parent = y.parent;
        if (y.parent == null) root = x;
        else if (y == y.parent.left) y.parent.left = x;
        else y.parent.right = x;
        x.right = y;
        y.parent = x;
    }

    // ===== 删除 =====
    public void remove(K key) {
        Node<K, V> z = searchNode(key);
        if (z == null) return;
        transplant(z, findInOrderSuccessor(z));
    }

    private Node<K, V> findInOrderSuccessor(Node<K, V> node) {
        if (node.right != null) {
            Node<K, V> y = node.right;
            while (y.left != null) y = y.left;
            return y;
        }
        return node;
    }

    private void transplant(Node<K, V> u, Node<K, V> v) {
        if (u.parent == null) root = v;
        else if (u == u.parent.left) u.parent.left = v;
        else u.parent.right = v;

        if (v != null) v.parent = u.parent;

        // 如果删除的是黑色节点且 v 是红色（或 nil），需要修复
        if (u.color == Color.BLACK) {
            if (v == null || v.color == Color.BLACK) {
                // v 是黑色或 nil → 黑高减少，需要修复
                if (v != null) deleteFixup(v);
            }
            // v 是红色 → 把 v 变黑即可，黑高不变
        }
    }

    private void deleteFixup(Node<K, V> x) {
        while (x != root && x.color == Color.BLACK) {
            if (x == x.parent.left) {
                Node<K, V> sibling = x.parent.right;
                if (sibling.color == Color.RED) {
                    sibling.color = Color.BLACK;
                    x.parent.color = Color.RED;
                    leftRotate(x.parent);
                    sibling = x.parent.right;
                }
                if ((sibling.left == null || sibling.left.color == Color.BLACK)
                    && (sibling.right == null || sibling.right.color == Color.BLACK)) {
                    sibling.color = Color.RED;
                    x = x.parent;
                } else {
                    if (sibling.right == null || sibling.right.color == Color.BLACK) {
                        sibling.left.color = Color.BLACK;
                        sibling.color = Color.RED;
                        rightRotate(sibling);
                        sibling = x.parent.right;
                    }
                    sibling.color = x.parent.color;
                    x.parent.color = Color.BLACK;
                    sibling.right.color = Color.BLACK;
                    leftRotate(x.parent);
                    x = root;
                }
            } else {
                Node<K, V> sibling = x.parent.left;
                if (sibling.color == Color.RED) {
                    sibling.color = Color.BLACK;
                    x.parent.color = Color.RED;
                    rightRotate(x.parent);
                    sibling = x.parent.left;
                }
                if ((sibling.right == null || sibling.right.color == Color.BLACK)
                    && (sibling.left == null || sibling.left.color == Color.BLACK)) {
                    sibling.color = Color.RED;
                    x = x.parent;
                } else {
                    if (sibling.left == null || sibling.left.color == Color.BLACK) {
                        sibling.right.color = Color.BLACK;
                        sibling.color = Color.RED;
                        leftRotate(sibling);
                        sibling = x.parent.left;
                    }
                    sibling.color = x.parent.color;
                    x.parent.color = Color.BLACK;
                    sibling.left.color = Color.BLACK;
                    rightRotate(x.parent);
                    x = root;
                }
            }
        }
        x.color = Color.BLACK;
    }

    // ===== 验证工具 =====
    public boolean validate() {
        return validateColor(root)
            && validateBlackHeight(root) == -1;
    }

    private boolean validateColor(Node<K, V> node) {
        if (node == null) return true;
        if (node.color == Color.RED
            && (node.left != null && node.left.color == Color.RED
                || node.right != null && node.right.color == Color.RED)) {
            return false;  // 违反性质4
        }
        return validateColor(node.left) && validateColor(node.right);
    }

    private int validateBlackHeight(Node<K, V> node) {
        if (node == null) return 1;
        int left = validateBlackHeight(node.left);
        int right = validateBlackHeight(node.right);
        if (left != right) return -1;  // 违反性质5
        return left + (node.color == Color.BLACK ? 1 : 0);
    }

    // 中序遍历（验证 BST 性质）
    public void inOrder() {
        inOrder(root);
        System.out.println();
    }

    private void inOrder(Node<K, V> node) {
        if (node == null) return;
        inOrder(node.left);
        System.out.print(node.key + "(" + (node.color == Color.RED ? "R" : "B") + ") ");
        inOrder(node.right);
    }
}
```

### 使用示例

```java
public class Main {
    public static void main(String[] args) {
        RedBlackTree<Integer, String> tree = new RedBlackTree<>();

        // 插入
        tree.insert(7, "seven");
        tree.insert(3, "three");
        tree.insert(18, "eighteen");
        tree.insert(10, "ten");
        tree.insert(22, "twenty-two");
        tree.insert(8, "eight");
        tree.insert(11, "eleven");
        tree.insert(26, "twenty-six");

        // 验证
        System.out.println("红黑树性质验证: " + tree.validate());

        // 中序遍历（应该是有序的）
        System.out.print("中序遍历: ");
        tree.inOrder();

        // 搜索
        System.out.println("搜索 10: " + tree.search(10));   // → ten
        System.out.println("搜索 99: " + tree.search(99));   // → null

        // 删除
        tree.remove(7);
        System.out.println("删除 7 后验证: " + tree.validate());
        tree.inOrder();
    }
}
```

---

## 十、红黑树 vs B+树：存储介质决定数据结构

> 常见疑问："MySQL 用 B+树可以减少磁盘 IO，为什么 TreeMap 不用 B+树？"
>
> 核心答案：**红黑树是为内存设计的，B+树是为磁盘设计的。
> 不是谁更好，而是各自匹配自己的战场。**

### 10.1 成本模型完全不同

```
两种介质的访问速度差距是数量级的：

┌──────────────┬───────────────┬──────────────────┐
│ 操作          │ 耗时           │ 说明              │
├──────────────┼───────────────┼──────────────────┤
│ 内存随机访问   │ ~100 ns       │ 指针跳一次          │
│ SSD 随机读    │ ~100 μs       │ 比内存慢 1000 倍    │
│ HDD 随机读    │ ~10 ms        │ 比内存慢 100000 倍  │
└──────────────┴───────────────┴──────────────────┘

关键结论：
  内存里：多跳几次指针无所谓，结构简单最重要
  磁盘上：每跳一次都是一次 IO，树高 = IO 次数 = 性命攸关
```

所以两者的设计目标相反：

```
红黑树的目标：让"单次跳转"便宜
  → 二叉节点、颜色位、最多 3 次旋转完成修复

B+树的目标：让"跳转次数"最少
  → 一个节点塞几百个键，把树压得又矮又胖
```

### 10.2 扇出决定树高：算一笔账

以 **2000 万行数据** 为例：

```
红黑树（二叉，扇出 = 2）：
═══════════════════════════════════════

  高度 h ≈ log₂(2×10⁷) ≈ 24 层（最坏 48 层）

  在内存中：24 次指针跳转 × 100ns = 2.4 μs ✅ 完全没问题
  在磁盘上：24 次磁盘 IO × 10ms   = 240 ms ❌ 不可接受！


MySQL InnoDB B+树（扇出 ≈ 1170）：
═══════════════════════════════════════

  页大小 16KB，bigint 主键 8B + 指针 6B ≈ 14B
  16384 ÷ 14 ≈ 1170 个键/非叶子节点

  高度 3 的 B+树能容纳：
    根(1170) × 中间层(1170) × 叶子(~16 行/页) ≈ 2200 万行 ✅

  磁盘 IO：3 次 × 10ms = 30ms ✅
  且根节点常驻 Buffer Pool → 实际往往只需 1~2 次 IO
```

```
同样的 2000 万行数据：

              树高        磁盘 IO 次数      总耗时(HDD)
红黑树         ~24         24               ~240ms ❌
B+树           3           3                ~30ms  ✅

差距 = 8 倍 IO 次数 = 数量级的性能差
```

### 10.3 B+树的两个磁盘专属设计

#### 1. 叶子节点链表 → 范围查询神器

```
B+树的所有数据都在叶子层，且叶子间有双向链表：

    [内部索引层]
     /    |    \
   [叶]⇄[叶]⇄[叶]⇄[叶]⇄[叶]   ← 链表串联

查询 WHERE id BETWEEN 100 AND 500：
  ① 从根找到 100 所在叶子     → 3 次 IO
  ② 沿链表向右扫到 500        → 顺序读，极快

红黑树做范围查询：
  中序遍历，在磁盘上意味着到处随机跳转 ❌
```

#### 2. 节点 = 页 → 与磁盘对齐

```
InnoDB 每次 IO 的最小单位就是一个 16KB 页
B+树一个节点正好一个页 → 一次 IO 读回一个完整节点
不存在"读了半截节点"的浪费

红黑树节点只有几十字节
磁盘上按页读 → 一个 16KB 页只装一个 40 字节的节点
→ 空间利用率 0.2%，纯纯浪费 ❌
```

### 10.4 反过来问：内存场景为什么不用 B+树？

```
如果 TreeMap 用 B+树实现会怎样：

  1. 节点按 16KB 页设计？
     → 存 10 个小对象也要占一页 → 内存浪费惨重
     （内存里没有"页"的概念，malloc 要多少给多少）

  2. 插入触发节点分裂？
     → 整页数据搬移；红黑树只需变色 + 最多 3 次旋转

  3. 实现复杂度？
     → B+树的分裂/合并/再平衡远比红黑树的颜色修复复杂

  4. 收益呢？零。
     内存访问不按 IO 计费，矮胖毫无意义
     红黑树 24 层 = 2.4μs，已经够快
```

### 10.5 各场景的真实选型

| 场景 | 数据结构 | 选它的原因 |
|------|---------|-----------|
| JDK `TreeMap`、Linux 内核调度器（CFS）、epoll | **红黑树** | 纯内存，旋转代价低，实现成熟 |
| MySQL InnoDB、PostgreSQL | **B+树** | 磁盘存储，矮胖减 IO，叶子链表支持范围扫描 |
| Redis ZSet | **跳表** | 纯内存，实现比红黑树简单，天然支持范围查询 |
| RocksDB / LevelDB / HBase | **LSM 树** | 磁盘但写多读少，顺序写代替随机写 |
| 文件系统 ext4 / XFS | **B+树变体** | 磁盘块寻址，同 MySQL 逻辑 |

> **记忆口诀**：
> **内存选红黑树（跳表），磁盘选 B+树（LSM）**
> 判断标准只有一个——你的数据住在哪。