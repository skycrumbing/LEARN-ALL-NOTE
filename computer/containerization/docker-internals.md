# Docker 是如何工作的？为什么轻量？

## 问题拆解

你的问题其实包含两问：

1. **Docker 怎么做到不依赖操作系统的**？—— 它**依赖操作系统**，但不是你想的那样
2. **为什么这么轻量**？—— 因为它**不是虚拟机**，它复用了宿主机的内核

---

## 一、先纠正一个常见误解

Docker 容器的环境**不是从零开始的**，它**依赖宿主机的 Linux 内核**。

```
你以为的：                     实际上的：
┌───────────┐                  ┌─────────────────────┐
│ Docker    │                  │    宿主机操作系统      │
│ 容器      │                  │   ┌───────────────┐ │
│ (完整OS)  │                  │   │ Docker 容器    │ │
│           │                  │   │ (只拷贝了      │ │
│ 自己的内核 │                  │   │  用户空间文件) │ │
│ 自己的驱动 │                  │   │               │ │
│ 自己的FS   │                  │   │ 共享内核       │ │
└───────────┘                  │   └───────┬───────┘ │
                               │   ┌───────┴───────┐ │
                               │   │  宿主机内核     │ │
                               │   └───────────────┘ │
                               └─────────────────────┘
```

**关键结论：Docker 容器没有自己的内核，它和宿主机共享同一个 Linux 内核。**

这就是为什么：
- 在 Windows 上运行 Linux 容器需要 WSL2（本质是跑了一个轻量 Linux VM）
- 容器里的进程在宿主机上直接用 `ps aux` 就能看到

---

## 二、隔离环境靠什么？

Docker 从零创建出一个隔离的环境，靠的是 Linux 内核的 **3 大技术**：

### 技术一：Namespaces（命名空间）— "你看到的世界是假的"

Namespaces 给每个容器的进程创建了一个**独立的世界**。同一个进程，在不同 namespace 里看到的东西完全不一样。

| Namespace 类型 | 隔离什么 | 效果 |
|---------------|---------|------|
| **PID** | 进程 ID | 容器里的 PID 1 在宿主机上是 PID 12345 |
| **NET** | 网络 | 容器有自己独立的网卡、IP、端口 |
| **MNT** | 挂载点 | 容器看到自己的文件系统（容器里的 / 不是宿主机的 /） |
| **UTS** | 主机名 | 容器可以有自己的 hostname |
| **IPC** | 进程间通信 | 容器的共享内存和信号量隔离 |
| **USER** | 用户 | 容器里的 root 在宿主机上是普通用户 |
| **Cgroup** | 控制组 | 独立的资源视图 |

**PID namespace 举例**：

```
宿主机视角（ps aux）：
  PID 12345  /usr/sbin/nginx  ← 这是容器里的 nginx
  PID 12346  /usr/sbin/mysqld ← 这是容器里的 mysql

容器视角（docker exec 进去 ps aux）：
  PID 1      /usr/sbin/nginx  ← 容器以为自己是 PID 1
  PID 2      /usr/sbin/mysqld
```

同一批进程，只是**视角不同**。PID 1 只是这个 namespace 里的"第一个进程"，在全局 namespace 里它就是个普通进程。

### 技术二：Cgroups（控制组）— "你能用多少资源我说了算"

Namespaces 负责"看不着别人"，Cgroups 负责"抢不走太多"。

Cgroups 限制了容器可以用多少 CPU、内存、磁盘 I/O。

```
cgroup 配置示例（概念）：
  /sys/fs/cgroup/docker/容器ID/
    ├── cpu.max        "200000 1000000"  ← 最多用 20% CPU
    ├── memory.max     "536870912"       ← 最多用 512 MB 内存
    └── io.max         "8MiB/s"          ← 磁盘读写限速
```

**没有 Cgroups 的后果**：一个容器里的进程如果死循环，会把整个宿主机 CPU 吃满。

**有了 Cgroups**：超过限制就自动限流，不影响其他容器。

### 技术三：UnionFS（联合文件系统）— "镜像分层，共享底版"

这是 Docker 镜像"轻量"和"快"的核心原因。Docker 使用的一种特殊文件系统，能把**多个目录层叠在一起**，看起来像一个文件系统。

#### 如何工作

```
最终看到的容器文件系统（/）：
┌─────────────────────────┐
│  容器可写层（最上层）      │  ← 只有修改过的文件才在这里
├─────────────────────────┤
│  应用层：apt install nginx│  ← 在基础镜像上加装的
├─────────────────────────┤
│  基础层：ubuntu:22.04    │  ← 几十 MB 的 rootfs
└─────────────────────────┘

从下往上看（底层 → 顶层）：基础层 → 应用层 → 可写层
从容器里看：所有层叠在一起，像只有一个文件系统
```

**写时复制（Copy-on-Write）**：

```
容器想要修改 /etc/nginx/nginx.conf：
  1. 这个文件在"基础层"里（只读）
  2. 容器不能修改只读层（其他容器也在用）
  3. 所以 Docker 先把这个文件"拷"到可写层
  4. 在可写层里修改
  5. 容器以后读这个文件时，可写层覆盖了基础层

这就是 Copy-on-Write：只在真正写入时才复制
```

**不同容器的共享**：

```
     容器A                    容器B
  ┌──────────┐            ┌──────────┐
  │ 可写层A  │            │ 可写层B  │    ← 各有各的可写层
  ├──────────┤            ├──────────┤
  │          │            │          │
  │   共享的只读镜像层      │    ← 两个容器共享！
  │    (ubuntu:22.04)    │        只存了一份
  │          │            │          │
  └──────────┘            └──────────┘
```

**这就是轻量的核心原因：100 个容器跑同一个镜像，基础层只需要存一份。**

---

## 三、Docker vs 虚拟机：一张图看懂

```
虚拟机：                              Docker：
┌────────────────────┐              ┌────────────────────┐
│  App A  │  App B   │              │  App A  │  App B   │
├────────────────────┤              ├────────────────────┤
│  Bin/Libs          │              │  Bin/Libs          │
├────────────────────┤              │        │           │
│  Guest OS (Ubuntu)  │              │  Docker Engine      │
│  完整操作系统 + 自己内核│              │        │           │
├────────────────────┤              ├────────────────────┤
│  Hypervisor        │              │  宿主机 Linux 内核   │
├────────────────────┤              ├────────────────────┤
│  宿主机 OS          │              │  宿主机硬件          │
├────────────────────┤              └────────────────────┘
│  宿主机硬件          │
└────────────────────┘
```

| 对比维度 | 虚拟机 | Docker 容器 |
|---------|--------|------------|
| 启动速度 | 分钟级（要启一个完整 OS） | **秒级**（只启动进程） |
| 内存占用 | 每个 VM 至少 512MB~2GB | **几十 MB 就够了** |
| 磁盘占用 | 每个 VM 几 GB 的 OS 镜像 | **共享镜像层，增量很小** |
| 内核 | 每个 VM 有自己的内核 | **共享宿主机内核** |
| 隔离强度 | 强（硬件虚拟化） | 中（内核 namespace 隔离） |

---

## 四、Docker 到底是怎么"从零开始创建环境"的？

以 `docker run ubuntu:22.04` 为例，Docker 逐步做了什么：

```
1. 拉取镜像
   → 下载 ubuntu:22.04 的镜像层（本质上是一个 Ubuntu 用户空间文件系统的压缩包）

2. 创建容器的根文件系统
   a. Docker 在宿主机上创建一个空目录（比如 /var/lib/docker/overlay2/xxx/）
   b. 把 ubuntu 镜像的所有层用 UnionFS 叠到这个目录上
   c. 在最上面加一个空的"可写层"
   d. 现在这个目录看起来就是一个完整的 Ubuntu 文件系统
   → 但！这里面没有 Linux 内核，只有 /bin, /usr, /etc, /lib 等用户空间文件

3. 创建隔离环境（namespace）
   a. 创建 PID namespace → 容器里从 PID 1 开始
   b. 创建 NET namespace → 给容器分配虚拟网卡和独立 IP
   c. 创建 MNT namespace → 把第2步的目录当作容器的根 /
   d. 创建 UTS namespace → 设置容器的主机名

4. 设置资源限制（cgroup）
   → 如果有 --memory=512m，就设置 memory.max = 512MB

5. 启动容器里的进程
   → 用 clone() 系统调用，在这个 namespace 里启动 /bin/bash（或 Dockerfile 里的 CMD）
   → 进程以为自己是 PID 1，以为自己的根目录就是 /
   → 实际上它的文件系统是 UnionFS 叠出来的，它的 PID 是假的
```

---

## 五、回到你的问题

### "怎么做到不依赖操作系统的？"

**它依赖操作系统的内核。** Docker 容器里的 Ubuntu 镜像**不是完整的 Ubuntu OS**——它只是 Ubuntu 的用户空间文件（/bin, /usr, /lib, /etc），不包含 Linux 内核。容器里的进程直接运行在宿主机内核上。

你可以验证：

```bash
# 在容器里
uname -r
# 输出：5.15.0-91-generic

# 在宿主机上
uname -r
# 输出：5.15.0-91-generic  ← 一模一样！
```

### "为什么轻量？"

1. **没有自己的内核** — 省了最重的部分（内核通常几百 MB 以上）
2. **镜像分层共享** — 100 个容器跑同一个镜像，基础层只存一份
3. **Copy-on-Write** — 只复制被修改的文件，没改的文件全部共享
4. **只启动进程** — 没有 init 系统，没有后台服务，没有虚拟硬件初始化

---

## 六、深入：UnionFS 怎么把多个目录"叠"在一起？

### 先直观感受

假设你有三个目录：

```
lower/                  upper/                  work/
├── a.txt (内容:A)      ├── b.txt (内容:B)      (临时工作目录)
├── c.txt (内容:C)      └── d.txt (内容:D)
└── sub/
    ├── x.txt
    └── y.txt
```

把 `lower` 和 `upper` 通过 overlay2 叠起来，挂载到 `merged/`：

```bash
mount -t overlay overlay \
  -o lowerdir=lower,upperdir=upper,workdir=work \
  merged/
```

**merged/ 里看到的效果**：

```
merged/
├── a.txt (内容:A)   ← 来自 lower/
├── b.txt (内容:B)   ← 来自 upper/
├── c.txt (内容:C)   ← 来自 lower/
├── d.txt (内容:D)   ← 来自 upper/
└── sub/
    ├── x.txt        ← 来自 lower/
    └── y.txt        ← 来自 lower/
```

**规则**：同名文件 upper 覆盖 lower，不同名文件合并显示。

### work 目录是做什么的？

在上面的 `mount` 命令中，除了 `lowerdir` 和 `upperdir`，还有一个 `workdir=work`。这个目录**用户看不到内容**，它是 overlay2 内核模块在**内部做"原子操作"时用的临时空间**。

核心场景：**Copy-on-Write 的"copy up"操作不是一瞬间完成的**。

```
修改 /etc/nginx.conf 的 copy-up 过程：

1. 发现文件在 lower 层，需要拷贝到 upper 层
2. 内核先在 work/ 目录里创建一个文件副本
3. 在 work/ 里做完所有修改（确保数据完整）
4. 再用原子操作把 work/ 里的文件 rename 到 upper/

如果第2步写到一半突然断电：
  work/ 里留的是垃圾 → 重启后清理掉，不影响 upper/
  upper/ 里没被污染 → 下次容器启动，重新做 copy-up 即可

如果不用 work 直接写 upper：
  写到一半断电 → upper/ 里的文件是坏的一半 → 永久损坏
```

| 目录 | 作用 | 用户能看到吗 |
|------|------|------------|
| `lowerdir` | 只读的底层文件 | ✅ 能，但不能改 |
| `upperdir` | 可写层，存放所有修改 | ✅ 能 |
| `workdir` | 内核内部临时空间，保证操作原子性 | ❌ 始终为空 |
| `merged` | 叠加后的最终视图 | ✅ 这就是容器里看到的 `/` |

**要求**：`workdir` 和 `upperdir` 必须在同一个文件系统上（同一个磁盘分区），因为原子 rename 只在同一文件系统内有效。

> 类比：你用 Word 编辑文档，如果 Word 直接改写原文件，写到一半断电文件就坏了。所以 Word 的做法是：先写到一个临时文件 `.~temp.docx`，全部写完之后，再把临时文件重命名为正式文件名。work 目录就是 overlay2 的"临时草稿区"。

### Docker 的多层叠加

Docker 镜像通常有多个 layer，overlay2 把它们串成一条链：

```
layer5 (可写层) ─────────┐
layer4 (apt install nginx)──┤
layer3 (apt update) ────────┤  ← 从左到右优先级递增
layer2 (COPY app) ──────────┤    右边的文件覆盖左边
layer1 (ubuntu 基础层) ──────┤
                           ↓
                  最终容器看到的 /
```

**从容器视角打开一个文件时，overlay2 做了这些**：

```
打开 /etc/nginx/nginx.conf：

step1: 问 layer5（可写层）：有这个文件吗？→ 没有
step2: 问 layer4：有这个文件吗？→ 有！（之前 apt install nginx 安装的）
step3: 从 layer4 读取文件内容，返回
       ↑
       后面的层不需要查了，就像函数调用栈一样
```

**修改文件时的 Copy-on-Write**：

```
修改 /etc/nginx/nginx.conf：

step1: 问 layer5（可写层）：有这个文件吗？→ 没有
step2: 问 layer4：有这个文件吗？→ 有
step3: 从 layer4 复制到 layer5   ← "copy up"
step4: 在 layer5 中修改
step5: 以后打开这个文件，layer5 有 → 直接返回修改后的版本
```

### overlay2 在宿主机上的真实样子

```bash
ls /var/lib/docker/overlay2/

# 每个目录就是一个"层"
abc123.../      ← 镜像层（只读）
  ├── diff/     ← 该层的文件内容
  │   ├── bin/
  │   ├── usr/
  │   └── etc/
  └── link      ← 软链接，记录该层的短标识符

def456.../      ← 另一个镜像层
  ├── diff/
  └── link

xyz789...-init/ ← 容器的 init 层（配置 hostname, /etc/hosts 等）
xyz789.../      ← 容器的可写层
  ├── diff/     ← 容器里修改过的文件都在这里
  ├── link
  ├── lower     ← 文件！内容是指向所有只读层的路径
  └── merged/   ← 最终叠加后的挂载点（容器通过这里看到完整文件系统）
```

**lower 文件的内容**：

```
l/ABC123:l/DEF456:l/GHI789
```

这是一个以 `:` 分隔的路径列表，最左边是最底层（优先级最低），最右边是最顶层（优先级最高，但低于可写层）。



---

## 七、不同镜像之间能共享层吗？能叠加无限层吗？

### 7.1 不同镜像可以共享同一层 —— 这是 Docker 的日常操作

```
docker pull ubuntu:22.04
# 下载了 layer1 (ubuntu 基础), layer2, layer3

docker pull nginx:latest    ← nginx 镜像是基于 debian 的
# 发现 debian 基础层 = ubuntu 的 layer1 一模一样！
# → 跳过下载，直接用已有的 ✅
# 只下载 nginx 专属的 layer4, layer5

磁盘上：
  layer1: 1 份     ← ubuntu 和 nginx 共享
  layer2: 1 份     ← 只有 ubuntu 用
  layer3: 1 份     ← 只有 ubuntu 用
  layer4: 1 份     ← 只有 nginx 用
  layer5: 1 份     ← 只有 nginx 用

实际存储：5 层，约 300 MB
如果每层各存一份：10 层，约 600 MB → 省了一半
```

**共享的本质就是多层目录叠加**——内核的 overlay2 驱动允许同一个 lowerdir 目录同时被多个容器挂载为只读层。因为它只读，所以不会有冲突。

### 7.2 共享的判断依据：内容哈希（Content Hash）

Docker 不是按"文件名"判断是否共享，而是按**内容的哈希值**：

```
Dockerfile:
  FROM ubuntu:22.04          → 这一层的哈希 = abc123
  RUN apt update             → 这一层的哈希 = def456
  RUN apt install -y nginx   → 这一层的哈希 = ghi789
  COPY . /app                → 这一层的哈希 = jkl012

生成镜像 ID: sha256:a1b2c3d4...
```

| 镜像 ID 由所有层的哈希拼接而成 |
|-------------------------------|

如果两个 Dockerfile 的前三步完全相同（FROM + 第一条 RUN + 第二条 RUN 完全一样），前三层共享，只有最后一层不同。

**用 `docker history` 可以看到**：

```bash
docker history nginx:latest
# IMAGE          CREATED BY                     SIZE
# abc123def456   COPY . /app                   10MB   ← 可能只有这层不共享
# ghi789jkl012   RUN apt install -y nginx      25MB   ← 这层和其他基于 debian 的共享
# mno345pqr678   /bin/sh -c #(nop) ADD debian  74MB   ← 基础层，N多个镜像共享
```

### 7.3 能叠加无限层吗？—— 不能，有硬性限制

| 限制类型 | 具体数值 | 原因 |
|---------|---------|------|
| **overlay2 的最大层数** | **最多叠加 500 层**（lowerdir 的路径长度限制） | overlay2 用 `lowerdir=layer1:layer2:...` 传递层列表，这个字符串的长度不能超过内核的路径上限（4096 字节） |
| **实际 Docker 限制** | **Docker 限制 127 层**（官方建议） | 超过 127 层性能会明显下降 |
| **性能退化** | 每多一层，打开文件就要多查一层 | 层数太少浪费共享空间，太多影响性能 |

**打开一个文件的开销 = O(n)，n 是层数**：

```
1 层：  查 1 次
10 层： 查 10 次（几乎不可感知）
50 层： 查 50 次（轻微卡顿）
100 层：查 100 次（明显变慢）
500 层：查 500 次（每打开一个文件都要做 500 次查找！）
```

### 7.4 叠加的规则

| 规则 | 说明 |
|------|------|
| **只读层在下，可写层在顶** | lowerdir（只读）在最下面，upperdir（可写）一定是最上层 |
| **同名文件上层覆盖下层** | 上层有 `/etc/nginx.conf`，下层有没有都不重要——上层说了算 |
| **删除 = 白板覆盖** | 删除文件时，不是真删。而是在上层创建一个"白板文件"（whiteout），标记此文件"不存在"。下层同名文件被屏蔽 |
| **只读层不可修改** | 下层文件如果要改，必须先 copy-up 到可写层 |
| **层顺序固定** | 层的叠加顺序由 Dockerfile 的指令顺序决定，不能随意调换 |
| **workdir 必须和 upperdir 在同一文件系统** | 否则原子 rename 不生效 |

### 7.5 白板文件（Whiteout）—— 删除是怎么实现的

```
镜像的 layer2 里有 /etc/old-config.conf

容器里执行 rm /etc/old-config.conf

此时 overlay2：
  不能真的删除 layer2 里的文件（只读！其他容器可能也在用）
  所以在可写层创建一个白板文件：
    可写层/etc/old-config.conf → 不是真实文件，是一个特殊的字符设备文件
    (major=0, minor=0)

下次容器读 /etc/old-config.conf 时：
  overlay2 查层 -> 可写层有！→ 发现是白板文件 → 返回"文件不存在"
  实际文件在 layer2 里还完好无损
```

> 这和之前学的"一切皆文件"呼应上了——overlay2 用特殊字符设备文件（0,0）来模拟"不存在的文件"。

### 7.6 实际优化建议

```
✅ 好的 Dockerfile：                     ❌ 差的 Dockerfile：
FROM ubuntu:22.04                       FROM ubuntu:22.04
RUN apt-get update && \                 RUN apt-get update
    apt-get install -y \                RUN apt-get install -y nginx  ← 分成多条RUN
    nginx \                             RUN apt-get install -y curl   ← 每层都很大
    curl && \                           RUN rm -rf /var/lib/apt/lists/*
    rm -rf /var/lib/apt/lists/*         ↑ 即使最后删了临时文件，
↑ 一条RUN只产生1层                        中间层也已经"胖"了
  最终镜像只有1层增量
```

> 减少层数意味着：查文件更快（少查几层）、拉镜像更快（少下载）、磁盘更省（层数少）。

### 7.7 `docker run` 命令 vs Dockerfile 的 `RUN` 指令——本质完全不一样

虽然都叫 "run"，但它们是**两个完全不同的东西**，发生在两个完全不同的阶段。

| | `RUN`（Dockerfile 指令） | `docker run`（CLI 命令） |
|--|--------------------------|--------------------------|
| **执行阶段** | `docker build` 时 | `docker run` 时 |
| **作用** | 在镜像中执行命令，**固化结果**为新镜像层 | 从镜像**启动一个容器进程** |
| **产物** | 一个新的镜像层（只读，持久保存） | 一个运行中的容器（有可写层） |
| **可以交互吗？** | ❌ 不能，无人值守自动执行 | ✅ 可以（`-it`），可以进 bash |
| **网络能用吗？** | ❌ 默认没有网络 | ✅ 有独立网络栈 |
| **举例** | `RUN apt install -y nginx` | `docker run -d -p 80:80 nginx` |

**用一个完整的生命周期串起来：**

```
Dockerfile:
  FROM ubuntu:22.04
  RUN apt update           ← 第1步: docker build 时执行，结果存为镜像层
  RUN apt install -y nginx ← 第2步: docker build 时执行，结果存为镜像层
  COPY index.html /var/www/html/
  CMD ["nginx", "-g", "daemon off;"]

docker build -t my-nginx .   ← 执行 RUN，产出镜像

docker run -d -p 8080:80 my-nginx  ← 用镜像启动容器，执行 CMD 启动 nginx
                    ↑          ↑
                    docker run 命令     镜像名
```

**最核心的区别就一句话**：

```
RUN（Dockerfile）     → "在构建时跑一条命令，把结果拍成照片（镜像层）"
docker run（CLI）     → "用已经拍好的照片，启动一个活着的进程（容器）"
```

**验证**：

```bash
# docker build 里的 RUN 执行完就结束了，不会留下进程
docker build -t test .
# 构建完毕，apt install 做完了，但没有任何 apt 进程在运行

# docker run 会持续运行 CMD 指定的进程
docker run -d nginx
# nginx 进程一直在跑，直到 docker stop
```

### 7.8 每次 `docker run` 会创建新层吗？

**先分清楚两个概念：**

| | `docker build`（构建镜像） | `docker run`（启动容器） |
|--|--------------------------|------------------------|
| 产生什么层？ | **镜像层**（image layer），持久保存 | **容器可写层**（container layer），随容器生灭 |
| 其他容器能看到吗？ | ✅ 共享，拉取同一镜像时复用 | ❌ 各容器独立，互不可见 |
| 存在多久？ | 永久（直到 `docker rmi` 删除镜像） | 容器删除即消失（`docker rm`） |

**用一个具体例子**：

```
# 构建镜像
docker build -t my-nginx .

  镜像层栈（只读，持久保存）：
  ┌─────────────────────┐
  │ layer3: COPY app    │  ← 由 Dockerfile 的 COPY 产生，永久存在
  ├─────────────────────┤
  │ layer2: RUN apt...  │  ← 由 Dockerfile 的 RUN 产生，永久存在
  ├─────────────────────┤
  │ layer1: ubuntu 基础  │
  └─────────────────────┘

# 启动三个容器
docker run --name web1 my-nginx
docker run --name web2 my-nginx
docker run --name web3 my-nginx

  三个容器各自的文件系统视图：
  ┌──────────────┐   ┌──────────────┐   ┌──────────────┐
  │ 可写层-web1  │   │ 可写层-web2  │   │ 可写层-web3  │  ← 各有一份，独立！
  ├──────────────┤   ├──────────────┤   ├──────────────┤
  │  layer3      │   │  layer3      │   │  layer3      │  ← 共享，同一份
  │  layer2      │   │  layer2      │   │  layer2      │  ← 共享，同一份
  │  layer1      │   │  layer1      │   │  layer1      │  ← 共享，同一份
  └──────────────┘   └──────────────┘   └──────────────┘
      容器 web1          容器 web2          容器 web3
```

**关键结论**：
- `docker run` 不产生新的**镜像层**（`docker images` 列表不变）
- 但每个容器得到一个**独立的可写层**（在 `/var/lib/docker/overlay2/` 下各有一个 -init/ 和当前层目录）
- 三个容器共享同一个镜像的三层只读层，磁盘上只存一份
- web1 在可写层里创建 `/tmp/a.txt`，web2 完全看不到——隔离！

**所以回答你的问题**：是的，每 `docker run` 一次都会在镜像层之上叠一个新的可写层，但这个可写层是**容器专属、独立、临时的**，不是共享的镜像层。这就是为什么容器之间文件系统相互隔离——它们各有各的薄薄一层"草稿纸"。

### 7.9 常见 Docker 命令本质详解

这四个概念经常被搞混——它们的本质分别是什么，什么时候执行，谁调用谁。

#### 总览

```
                    执行时机              本质
                    ────────            ──────────
RUN (Dockerfile)    docker build 时      立即执行，结果固化为镜像层
CMD (Dockerfile)    docker run 时        不执行！是镜像元数据里的"默认参数"
ENTRYPOINT (Dockerfile)  docker run 时   不执行！是镜像元数据里的"固定入口"
docker run (CLI)    终端敲命令时          启动容器，读取 ENTRYPOINT + CMD 拼接出最终命令
```

#### CMD —— 镜像的"默认参数"

CMD 有三种写法，但**推荐只用 exec 形式**：

```dockerfile
# ✅ exec 形式（推荐）：JSON 数组
CMD ["nginx", "-g", "daemon off;"]

# ⚠️ shell 形式：会包一层 /bin/sh -c
CMD nginx -g 'daemon off;'

# ❌ 给 ENTRYPOINT 传参时才用的形式：
CMD ["--port=8080"]   ← 此时 CMD 只是参数，不是完整命令
```

**CMD 的本质**：它不是在 `docker build` 时执行的，它只是**写在镜像 JSON 元数据里的一个字符串**。真正执行它的是 `docker run`。

```bash
# 查看镜像的默认 CMD
docker inspect nginx:latest | jq '.[0].Config.Cmd'
# ["nginx", "-g", "daemon off;"]   ← 只是元数据！

# docker run 时，读取这个元数据，作为默认启动命令
docker run nginx
# 等价于：docker run nginx nginx -g 'daemon off;'

# 在 docker run 后面写命令，会覆盖 CMD
docker run nginx bash
# 实际执行：bash  ← CMD 被覆盖了！
```

#### ENTRYPOINT —— 镜像的"固定入口"

**和 CMD 的区别**：CMD 会被 `docker run` 后面的参数**整个替换掉**，ENTRYPOINT **不会被替换**。

```dockerfile
# 场景：做一个"检查工具"镜像
FROM ubuntu:22.04
COPY check-tool /usr/local/bin/check-tool
ENTRYPOINT ["check-tool"]
CMD ["--help"]    ← CMD 作为 ENTRYPOINT 的默认参数
```

```bash
docker run check-img
# 实际执行：check-tool --help
# = ENTRYPOINT + CMD 拼接

docker run check-img --verbose /etc/config
# 实际执行：check-tool --verbose /etc/config
# CMD 被替换了，但 ENTRYPOINT 还在！
# = ENTRYPOINT + (docker run 后面的参数)
```

**和 RUN 的区别**：

```
ENTRYPOINT ["nginx"]
  → 不执行！只是记录"这个镜像启动时默认跑 nginx"
  → 每次 docker run 都会读取并执行它

RUN apt install -y nginx  
  → 立即执行！在 docker build 阶段安装 nginx
  → 执行一次，结果永久固化在镜像层里
```

#### 三种组合模式

**模式 1：只 CMD（最常见）**

```dockerfile
FROM ubuntu:22.04
CMD ["bash"]
# docker run my-img           → 执行 bash
# docker run my-img ls -la    → 执行 ls -la（CMD 被覆盖）
```

**模式 2：ENTRYPOINT + CMD（做工具镜像）**

```dockerfile
FROM ubuntu:22.04
COPY scanner /usr/local/bin/scanner
ENTRYPOINT ["scanner"]
CMD ["--scan-dir=/app"]
# docker run scan-img                        → scanner --scan-dir=/app
# docker run scan-img --scan-dir=/data       → scanner --scan-dir=/data
# docker run scan-img bash                   → scanner bash  ← ！bash 成了 scanner 的参数
#  想进 bash 需要：docker run --entrypoint bash scan-img
```

**模式 3：只 ENTRYPOINT**

```dockerfile
FROM ubuntu:22.04
ENTRYPOINT ["/usr/sbin/nginx", "-g", "daemon off;"]
# docker run my-nginx            → nginx -g 'daemon off;'
# docker run my-nginx -t         → nginx -g 'daemon off;' -t  ← 参数会追加
```

#### 四个命令的完整对比

| | RUN | CMD | ENTRYPOINT | docker run |
|--|-----|-----|-----------|------------|
| **什么时候执行** | `docker build` | `docker run` 时读取 | `docker run` 时读取 | 终端输入时 |
| **执行次数** | 构建时执行1次，结果固化 | 每次启动容器都执行 | 每次启动容器都执行 | 每次敲命令执行 |
| **会被覆盖吗** | 不适用 | ✅ 会被 `docker run` 后面的参数覆盖 | ❌ 不会被覆盖（`--entrypoint` 除外） | 不适用 |
| **产生产物** | 镜像层 | 无（只是元数据） | 无（只是元数据） | 运行中的容器 |
| **存在于** | 镜像的文件系统里 | 镜像的 Config.Cmd 元数据里 | 镜像的 Config.Entrypoint 元数据里 | — |
| **类比** | 施工队砌墙（永久改变） | 门牌上写的"推"（默认动作） | 门禁系统（必须先过这关） | 推门的人 |

#### 一张图总结

```
docker build 阶段：
  FROM ubuntu       → 下载基础镜像
  RUN apt install   → 🏗️ 立即执行，结果固化为镜像层
  COPY app /app     → 🏗️ 文件复制，固化为镜像层
  ENTRYPOINT [...]  → 📝 只写在元数据里，不执行
  CMD [...]         → 📝 只写在元数据里，不执行
                ↓
           产出镜像（一堆层 + 元数据）

docker run 阶段：
  读取镜像元数据：
    ENTRYPOINT = ["nginx"]
    CMD        = ["-g", "daemon off;"]
                ↓
  拼接最终命令：nginx -g 'daemon off;'
                ↓
  docker run 后面的参数如果写了东西 →
    有 ENTRYPOINT → 替换 CMD，追加到 ENTRYPOINT 后面
    无 ENTRYPOINT → 整个替换 CMD
                ↓
           🚀 启动容器进程
```

---

## 八、容器网络隔离

### 8.1 回顾：网络隔离靠 NET namespace

在 [第二节](#二隔离环境靠什么) 中提到，Docker 用 **NET namespace** 实现网络隔离。

```
宿主机                            容器 A                    容器 B
┌──────────────┐               ┌──────────────┐         ┌──────────────┐
│ eth0         │               │ eth0         │         │ eth0         │
│ 192.168.1.10 │               │ 172.17.0.2   │         │ 172.17.0.3   │
│              │               │              │         │              │
│ 路由表        │               │ 路由表         │         │ 路由表         │
│ 默认网关      │               │ 默认网关        │         │ 默认网关        │
│              │               │ 172.17.0.1    │         │ 172.17.0.1    │
└──────────────┘               └──────┬───────┘         └──────┬───────┘
       │                              │                        │
       │                       veth pair                  veth pair
       │                     (网线两端)                  (网线两端)
       │                              │                        │
       └──────────────────────────────┼────────────────────────┘
                                      │
                              ┌───────┴───────┐
                              │  docker0 网桥  │
                              │  172.17.0.1    │
                              └───────────────┘
```

**关键机制：veth pair（虚拟网线）**

veth pair 是一对虚拟网卡，像一个管道——这头进，那头出。一头插在容器里（eth0），另一头插在宿主机的 docker0 网桥上。

### 8.2 四种网络通信场景

#### 场景一：容器 ↔ 容器（同一宿主机，同一网桥）

```
容器 A (172.17.0.2) → ping 容器 B (172.17.0.3)

1. 容器 A: 目标 IP 172.17.0.3，查路由表 → 不在本网段？在！直接 ARP
2. ARP 请求从 veth 发到 docker0 网桥
3. docker0 网桥像交换机一样广播 ARP："谁是 172.17.0.3？"
4. 容器 B 的 veth 收到，回复 MAC 地址
5. 数据包直接通过网桥转发，不经过宿主机路由
```

> 这和之前学的 [IP 地址与子网掩码](ip-subnetting/subnet-mask.md) 对应：**同一网段直接通信，不需要路由。**

#### 场景二：容器 → 宿主机

```
容器 A (172.17.0.2) → ping 宿主机 (192.168.1.10)

1. 容器: 目标 192.168.1.10，查路由表 → 不在 172.17.0.0/16 网段
2. 网关是 172.17.0.1 (docker0)，发到网关
3. docker0 收到，查宿主机的路由表
4. 发现 192.168.1.10 是本机 → 直接投递给本地进程
```

> 注意：容器访问宿主机用的是 docker0 的 IP（172.17.0.1），不是宿主机的物理网卡。

#### 场景三：容器 → 外网（如 8.8.8.8）

```
容器 A (172.17.0.2) → ping 8.8.8.8

1. 容器: 目标 8.8.8.8，查路由表 → 不在本网段
2. 发到网关 172.17.0.1 (docker0)
3. docker0 收到，查宿主机路由表 → 不在本机
4. 发到宿主机默认网关 (192.168.1.1，家里的路由器)
5. 但！源 IP 是 172.17.0.2（私有 IP），外网不认识！

这里需要 NAT（网络地址转换）：
5. 宿主机 iptables 做 SNAT：源 IP 172.17.0.2 → 192.168.1.10
6. 外网回复时，目标 IP 是 192.168.1.10
7. 宿主机 iptables 做 DNAT：目标 IP 192.168.1.10 → 172.17.0.2
8. 容器收到回复
```

#### 场景四：外网 → 容器（端口映射）

```
curl http://192.168.1.10:8080 → 容器里的 nginx (172.17.0.2:80)

docker run -p 8080:80 nginx  # ← 关键：做了端口映射

1. 外网请求到达宿主机 192.168.1.10:8080
2. 宿主机的 iptables DNAT 规则：
   目标 192.168.1.10:8080 → 目标 172.17.0.2:80
3. 数据包转发到 docker0 网桥
4. docker0 投递到容器的 veth
5. 容器里的 nginx 处理请求，按场景三回复
```

### 8.3 Docker 的四种网络模式

| 模式 | 命令 | 效果 |
|------|------|------|
| **bridge**（默认） | `docker run` | 分配独立 IP，通过 docker0 网桥通信，需要端口映射才能被外界访问 |
| **host** | `--net=host` | **完全不用 NET namespace**，容器直接用宿主机的网络栈。最快，但没有隔离 |
| **none** | `--net=none` | 只创建 lo（回环），没有任何对外网络。完全隔离 |
| **container** | `--net=container:NAME` | 和另一个容器**共享同一个 NET namespace**。两个容器共用一个 IP，通过 localhost 互相访问 |

```
host 模式：                       container 模式：
容器和宿主机                     容器 B 共享容器 A 的网络栈
共用eth0                       
┌─────────────────┐             ┌─────────────────┐
│ 宿主机           │             │ 容器A (172.17.0.2)│
│ eth0:192.168.1.10│            │   容器B 没有自己的IP
│     ↑            │             │   localhost 访问 A │
│   容器也用这个    │             └─────────────────┘
│   可绑定1024以下  │
│   端口 危险！⚠️  │
└─────────────────┘
```

### 8.4 docker0 网桥的本质

docker0 是 Docker 守护进程启动时在宿主机上创建的一个**虚拟网桥**，本质上等于一个软件交换机。

```bash
# 在宿主机上可以看到
ip link show docker0
# docker0: <BROADCAST,MULTICAST,UP> mtu 1500 ...

# 容器的 veth 会插到它上面
brctl show docker0
# bridge name    bridge id           STP enabled    interfaces
# docker0        8000.0242...        no             veth12345
#                                                   veth67890
```

### 8.5 自定义网络：为什么不用默认的 docker0？

默认的 docker0 网桥上的容器**只能用 IP 通信**，不能用容器名互相访问。生产环境中都创建自定义网络：

```bash
docker network create my-net

docker run --net=my-net --name=web nginx
docker run --net=my-net --name=db  mysql

# 现在 web 容器可以直接 ping db
# ping db  ← 容器名！不是 IP！
# Docker 内置 DNS 服务器自动解析
```

### 8.6 完整数据流总结

```
容器 A (172.17.0.2) curl http://google.com:

1. 容器内查路由表 → 目标不在 172.17.0.0/16 → 发到网关 172.17.0.1
2. 数据包通过 veth pair → 到达宿主机的 docker0 网桥
3. docker0 查宿主机路由表 → 发到默认网关 192.168.1.1
4. iptables SNAT: 源 IP 172.17.0.2 → 宿主机公网 IP
5. 数据包出 eth0 → 互联网
6. 回复经过 iptables DNAT → 还原成 172.17.0.2
7. docker0 网桥转发到正确的 veth
8. 容器收到回复
```

---

## 九、不同 Linux 发行版能跑同一个镜像吗？Ubuntu 能跑 CentOS 镜像吗？

### 短答案

**能，因为容器共享的是宿主机内核，不是镜像的"系统"。**

### 为什么能？

Docker 镜像里**没有 Linux 内核**，只有用户空间程序（如 `bash`, `yum`, `apt`, glibc 等）。

```
CentOS 镜像的内容：               Ubuntu 宿主机：
┌──────────────────┐            ┌──────────────────┐
│ /bin/bash        │            │ 内核 5.15         │
│ /usr/bin/yum     │            │ (Docker 容器也用   │
│ /etc/yum.conf    │            │  这一份内核)       │
│ /lib/libc.so     │            └────────┬─────────┘
│ (CentOS 的)      │                     │
│                  │     容器进程直接调用宿主
│ ❌ 没有内核       │     机内核，通过系统调用
│ ❌ 没有驱动       │
└──────────────────┘
```

**所以 CentOS 镜像在 Ubuntu 宿主机上运行时**：

```bash
# 在 Ubuntu 22.04 上
docker run centos:7 cat /etc/redhat-release
# 输出：CentOS Linux release 7.9.2009 (Core) ✅ 能跑

docker run centos:7 uname -r
# 输出：5.15.0-91-generic  ← 这是 Ubuntu 的内核！不是 CentOS 的！
```

### 兼容性的关键：内核版本 vs glibc 版本

虽然 cross-distro 运行通常没问题，但有一个硬性限制：

| 层级 | 说明 | 例子 |
|------|------|------|
| **Linux 内核** | 由宿主机提供，所有容器共享 | 内核 5.15 |
| **glibc（C 标准库）** | 在**镜像里**，由镜像决定版本 | CentOS 7 带 glibc 2.17 |
| **用户程序** | 在**镜像里**，由镜像决定版本 | yum (CentOS), apt (Ubuntu) |

**关键规则**：**glibc 是向前兼容的，但离不开内核支持。**

```
旧 glibc + 新内核 = ✅ 可以
  例：CentOS 7 镜像（glibc 2.17） 在 Ubuntu 22.04 宿主机（内核 5.15）上能跑

新 glibc + 旧内核 = ❌ 不行
  例：Ubuntu 24.04 镜像（glibc 2.39）在 CentOS 7 宿主机（内核 3.10）上可能跑不了
  因为 glibc 2.39 可能依赖了只有新内核才有的系统调用
```

### 不同发行版的真正区别

| | Ubuntu 镜像 | CentOS 镜像 | Alpine 镜像 |
|--|-----------|------------|------------|
| 包管理器 | apt (deb 格式) | yum (rpm 格式) | apk |
| C 标准库 | glibc | glibc | musl libc |
| init 系统 | systemd | systemd | openrc |
| 镜像大小 | ~28 MB | ~200 MB | **~3 MB** |
| 内核 | **没有**（共享宿主机的） | **没有** | **没有** |

它们只是**不同的用户空间文件集合**，内核都是宿主机的。

### 实际验证

```bash
# 1. Ubuntu 宿主机跑 CentOS — ✅ 完全正常
docker run -it centos:7 bash
# [root@abc123 /]# yum install curl  ← 用 CentOS 的包管理器

# 2. CentOS 宿主机跑 Ubuntu — ✅ 也正常（内核够新的话）
docker run -it ubuntu:22.04 bash
# [root@def456 /]# apt install curl  ← 用 Ubuntu 的包管理器

# 3. 任何宿主机跑 Alpine — ✅ 更没问题
docker run -it alpine:3.19 sh
# / # apk add curl  ← 用 Alpine 的包管理器
```

### 唯一不兼容的情况

| 情况 | 能不能跑 | 原因 |
|------|---------|------|
| Ubuntu 宿主机 + CentOS 镜像 | ✅ | glibc 向前兼容 |
| CentOS 宿主机 + Ubuntu 镜像 | 看情况 | 需要宿主机内核够新 |
| x86 宿主机 + ARM 镜像 | ❌ | 指令集不兼容（除非用 QEMU 模拟）|
| Linux 宿主机 + Windows 镜像 | ❌ | 需要 Windows 内核（Windows 容器只能在 Windows 上跑）|
| macOS 宿主机 + Linux 镜像 | ✅（通过虚拟机）| Docker Desktop 在后台跑了一个轻量 Linux VM |

---

## 十、这和之前学的文件系统有什么关系？

回想之前学的 [文件系统的核心概念](file-system-basics.md)：

| 之前学的 | 在 Docker 中的体现 |
|---------|------------------|
| 元数据 vs 数据 | 镜像的 manifest（元数据）描述各层，层本身是压缩包（数据） |
| 目录结构 | 容器里的 / 是 UnionFS 叠出来的"合成品" |
| ext4/NTFS | 宿主机上用 ext4，容器里看到的却是 UnionFS（overlay2） |
| 路径解析 | 容器打开 `/etc/nginx.conf` → VFS → UnionFS 驱动 → 从各层找文件 |
| 一切皆文件 | Docker 把 /var/run/docker.sock 暴露为 socket 文件，来控制 Docker daemon |

---

## 练习题

1. 在 Linux 宿主机上开两个容器跑同一个 ubuntu 镜像，另一个删除了 `/bin/bash`，第一个容器的 `/bin/bash` 还在吗？为什么？
2. Docker 容器里跑 `top` 看到的 CPU 使用率和宿主机上看到的有何不同？这涉及哪种 namespace？
3. 为什么在 macOS 上跑 Docker 比 Linux 上慢？
4. Docker 镜像的一层只能往已有的文件系统"加东西"，不能直接修改下层已有的文件。这是 Copy-on-Write 的什么特性导致的？