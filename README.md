# AI 学习计划

> 用 AI 辅助系统学习四个学科：计算机科学、数学、网络、物理。

本项目是一个 **AI 辅助学习仓库**，旨在通过 AI 工具（如 Claude）帮助系统性地学习四个核心学科。

| 目录 | 学科 | 当前状态 |
|------|------|----------|
| [`computer/`](computer/README.md) | 计算机科学 | 🟡 16 个主题，IO + Netty + 线程池 + Tomcat/WebFlux + GC + 红黑树 + 连接池 + Spring + 计算机视觉 |
| [`math/`](math/README.md) | 数学 | ⚪ 待开始 |
| [`network/`](network/README.md) | 网络 | 🟢 3 个主题，核心内容已完成 |
| [`physics/`](physics/README.md) | 物理 | 🟢 1 个主题，飞行原理已完成 |

---

## 📚 知识索引

点击下方链接可直接跳转到对应知识点。

### 💻 计算机科学 (`computer/`)

#### 计算机体系结构 ([`→`](computer/computer-architecture/README.md))

| 笔记 | 说明 | 状态 |
|------|------|------|
| [`clock-frequency-64bit.md`](computer/computer-architecture/clock-frequency-64bit.md) | CPU 时钟、频率、64 位架构 | ✅ |
| [`computer-organization.md`](computer/computer-architecture/computer-organization.md) | 冯·诺依曼架构、CPU、内存层次、流水线、中断、虚拟内存等 | ✅ |

#### 文件系统 ([`→`](computer/file-system/README.md))

| 笔记 | 说明 | 状态 |
|------|------|------|
| [`file-system-basics.md`](computer/file-system/file-system-basics.md) | 核心概念、元数据、目录、Win/Linux 对比 | ✅ |

#### 容器化技术 ([`→`](computer/containerization/README.md))

| 笔记 | 说明 | 状态 |
|------|------|------|
| [`docker-internals.md`](computer/containerization/docker-internals.md) | Docker 隔离原理（namespace / cgroup / UnionFS） | ✅ |

#### 进制系统 ([`→`](computer/number-systems/README.md))

| 笔记 | 说明 | 状态 |
|------|------|------|
| [`binary-decimal.md`](computer/number-systems/binary-decimal.md) | 二进制与十进制互转 | ✅ |
| [`floating-point.md`](computer/number-systems/floating-point.md) | 浮点数的二进制表示 | ✅ |

#### 机器学习 / AI ([`→`](computer/machine-learning/README.md))

| 笔记 | 说明 | 状态 |
|------|------|------|
| [`gradient-descent.md`](computer/machine-learning/gradient-descent.md) | 梯度下降法：原理、手算、三种变体 | ✅ |
| [`attention-mechanism.md`](computer/machine-learning/attention-mechanism.md) | 注意力机制：Q/K/V、多头、缩放点积 | ✅ |
| [`neural-network-basics.md`](computer/machine-learning/neural-network-basics.md) | 神经网络基础：前向/反向传播、训练全流程 | ✅ |
| [`transformer-architecture.md`](computer/machine-learning/transformer-architecture.md) | Transformer：编/解码器、残差、LayerNorm | ✅ |

#### 计算机视觉 / 目标检测 ([`→`](computer/computer-vision/README.md))

| 笔记 | 说明 | 状态 |
|------|------|------|
| [`image-basics.md`](computer/computer-vision/image-basics.md) | 图像如何变成数字：像素矩阵、RGB/BGR、灰度、预处理 | ✅ |
| [`cnn-basics.md`](computer/computer-vision/cnn-basics.md) | 卷积神经网络：卷积核、特征图、池化、感受野、手算、CNN 简史 | ✅ |
| [`detection-concepts.md`](computer/computer-vision/detection-concepts.md) | 检测核心概念：bbox、IoU、NMS、置信度、mAP | ✅ |
| [`detection-algorithms.md`](computer/computer-vision/detection-algorithms.md) | 算法演进：Haar → R-CNN 系 → YOLO/SSD → DETR | ✅ |
| [`face-recognition.md`](computer/computer-vision/face-recognition.md) | 人脸专项：检测 vs 识别、MTCNN、FaceNet、ArcFace | ✅ |
| [`license-plate.md`](computer/computer-vision/license-plate.md) | 车牌专项：LPR 流程、LPRNet、CTC、中国车牌结构 | ✅ |
| [`cat-from-scratch.md`](computer/computer-vision/cat-from-scratch.md) | 从 0 手写识别猫：7 步全流程 + 数学公式 + 手算示例 + dying ReLU 实战坑 | ✅ |
| [`exercises.md`](computer/computer-vision/exercises.md) | 目标检测自测题（含答案） | ✅ |
| [`code/`](computer/computer-vision/code/) | 8 个可运行代码示例（像素/卷积/IoU/NMS/Haar/YOLO/YuNet/车牌定位/手写猫识别） | ✅ |

#### 算法 ([`→`](computer/algorithms/README.md))

| 笔记 | 说明 | 状态 |
|------|------|------|
| [`navigation/amap-navigation.md`](computer/algorithms/navigation/amap-navigation.md) | 高德导航：A\*、分层路网、CH、实时路况 | ✅ |
| [`bloom-filter/bloom-filter.md`](computer/algorithms/bloom-filter/bloom-filter.md) | 布隆过滤器 | ✅ |
| [`integer-rounding.md`](computer/algorithms/integer-rounding.md) | 取整的艺术："余数去哪了"心智模型、切一刀 vs 分名额、二分死循环与取整方向、溢出/负数坑 | ✅ |
| [`union-find.md`](computer/algorithms/union-find.md) | 并查集：动态连通性、路径压缩+按秩合并、O(α(n)) 证明、Kruskal/岛屿/冗余连接应用、与红黑树/堆/跳表的平衡策略对照 | ✅ |

#### Java IO ([`→`](computer/io/README.md))

| 笔记 | 说明 | 状态 |
|------|------|------|
| [`overview.md`](computer/io/overview.md) | IO 全景：BIO/NIO/AIO 演变、线程模型瓶颈 | ✅ |
| [`bio.md`](computer/io/bio.md) | 阻塞 IO：InputStream/OutputStream、一连接一线程 | ✅ |
| [`nio.md`](computer/io/nio.md) | 非阻塞 IO：Channel/Buffer/Selector、多路复用 | ✅ |
| [`aio.md`](computer/io/aio.md) | 异步 IO：CompletionHandler、Linux 上的真相 | ✅ |
| [`comparison.md`](computer/io/comparison.md) | 三种 IO 对比、场景选型 | ✅ |

#### Netty ([`→`](computer/netty/README.md))

| 笔记 | 说明 | 状态 |
|------|------|------|
| [`architecture.md`](computer/netty/architecture.md) | 架构全景、为什么需要 Netty | ✅ |
| [`bootstrap.md`](computer/netty/bootstrap.md) | Bootstrap 启动流程、关键选项 | ✅ |
| [`thread-model.md`](computer/netty/thread-model.md) | EventLoop 线程模型、单线程无锁 | ✅ |
| [`pipeline.md`](computer/netty/pipeline.md) | Pipeline 责任链、Inbound/Outbound Handler | ✅ |
| [`bytebuf.md`](computer/netty/bytebuf.md) | ByteBuf 内存模型、堆内/堆外、引用计数 | ✅ |
| [`zero-copy.md`](computer/netty/zero-copy.md) | Netty 四种零拷贝方式 | ✅ |
| [`network-issues.md`](computer/netty/network-issues.md) | 粘包/拆包、空闲连接检测、连接风暴、IoT百万连接 | ✅ |

#### 消息队列 ([`→`](computer/mq/README.md))

| 笔记 | 说明 | 状态 |
|------|------|------|
| [`mq-analysis.md`](computer/mq/mq-analysis.md) | RabbitMQ、Kafka、RocketMQ 原理、异同、优劣对比 | ✅ |

#### Redis ([`→`](computer/redis/README.md))

| 笔记 | 说明 | 状态 |
|------|------|------|
| [`redis-analysis.md`](computer/redis/redis-analysis.md) | Redis 数据存储、分布式锁、IO 模型、最佳实践、常见问题 | ✅ |

#### Java 线程池 ([`→`](computer/thread-pool/README.md))

| 笔记 | 说明 | 状态 |
|------|------|------|
| [`source-analysis.md`](computer/thread-pool/source-analysis.md) | 线程池源码：状态机、execute()、Worker 保活、拒绝策略 | ✅ |

#### Tomcat NIO vs Spring WebFlux ([`→`](computer/tomcat-webflux/README.md))

| 笔记 | 说明 | 状态 |
|------|------|------|
| [`source-analysis.md`](computer/tomcat-webflux/source-analysis.md) | Tomcat NIO 与 WebFlux 底层源码剖析：线程模型、连接处理链路、背压、选型 | ✅ |

#### Java GC 源码剖析 ([`→`](computer/jvm-gc/README.md))

| 笔记 | 说明 | 状态 |
|------|------|------|
| [`source-analysis.md`](computer/jvm-gc/source-analysis.md) | 对象可回收判定（可达性分析、四种引用）、GC 触发条件（Young/Full）、GC 算法源码 | ✅ |

#### 数据结构 ([`→`](computer/data-structures/README.md))

| 笔记 | 说明 | 状态 |
|------|------|------|
| [`red-black-tree.md`](computer/data-structures/red-black-tree.md) | 红黑树原理、五条性质、左旋右旋、插入/搜索/删除操作、完整 Java 实现、vs B+树选型 | ✅ |
| [`skip-list.md`](computer/data-structures/skip-list.md) | 跳表原理、多层链表索引、搜索/插入/删除、与红黑树优劣对比、Redis ZSet 选型分析、Java 实现 | ✅ |
| [`heap.md`](computer/data-structures/heap.md) | 堆原理、数组存储、上浮/下沉、O(n) 建堆证明、Top-K/定时任务/中位数应用、Java 实现 | ✅ |
| [`trie.md`](computer/data-structures/trie.md) | Trie 字典树、插入/搜索/前缀补全/删除、压缩 Trie/后缀树/AC自动机变种、与红黑树/堆/并查集/布隆的串联 | ✅ |

#### 连接池专题 ([`→`](computer/connection-pool/README.md))

| 笔记 | 说明 | 状态 |
|------|------|------|
| [`pool-analysis.md`](computer/connection-pool/pool-analysis.md) | 连接池通用抽象、HikariCP 三处提速设计、HTTP 连接池、RabbitMQ 连接池（AMQP 心跳/Channel 复用）、五种协议保活机制对比、四大参数坑 | ✅ |

#### Spring 核心专题 ([`→`](computer/spring/README.md))

| 笔记 | 说明 | 状态 |
|------|------|------|
| [`ioc-container.md`](computer/spring/ioc-container.md) | IoC 容器、refresh() 12 步调用链、Bean 生命周期 9 步、扩展点与设计模式 | ✅ |
| [`circular-dependency.md`](computer/spring/circular-dependency.md) | 三级缓存破解循环依赖、getSingleton 调用链、构造器循环依赖为何无解、ObjectFactory 不可替代性 | ✅ |
| [`aop.md`](computer/spring/aop.md) | AOP 动态代理、JDK vs CGLIB 调用链、拦截器链执行流程、代理选择策略 | ✅ |
| [`transaction.md`](computer/spring/transaction.md) | @Transactional 调用链、Connection 绑定 ThreadLocal、7 种失效场景根因 | ✅ |
| [`design-patterns.md`](computer/spring/design-patterns.md) | Spring 用到的 11 种设计模式盘点、综合学习收获 | ✅ |

#### 系统设计（实战）

| 笔记 | 说明 |
|------|------|
| [`系统设计方案.md`](computer/system-design/支付账户系统设计方案.md) | 支付账户系统设计 |
| [`秒杀商城.md`](computer/system-design/秒杀商城.md) | 秒杀商城系统设计 |

---

### 🌐 网络 (`network/`)

#### IP 地址与子网划分 ([`→`](network/ip-subnetting/README.md))

| 笔记 | 说明 | 状态 |
|------|------|------|
| [`subnet-mask.md`](network/ip-subnetting/subnet-mask.md) | 子网掩码、网段、CIDR、子网划分 | ✅ |

#### Linux 网络实战 ([`→`](network/linux-networking/README.md))

| 笔记 | 说明 | 状态 |
|------|------|------|
| [`linux-network-guide.md`](network/linux-networking/linux-network-guide.md) | ip 命令、veth+namespace、路由、iptables、tcpdump、排障 | ✅ |

#### SSL/TLS 证书与 HTTPS ([`→`](network/ssl-tls/README.md))

| 笔记 | 说明 | 状态 |
|------|------|------|
| [`godaddy-ssl-qa-record.md`](network/ssl-tls/godaddy-ssl-qa-record.md) | GoDaddy SSL 证书续期与 Nginx 部署实战：有效期/订阅期、证书三件套、信任链、TLS 混合加密握手、公共/私有 CA、openssl 验证命令 | ✅ |

---

### 📐 数学 (`math/`)

> 待学习。计划覆盖：高等数学、线性代数、概率统计、离散数学。

---

### ⚛️ 物理 (`physics/`)

#### 飞行原理 ([`→`](physics/flight-physics/README.md))

| 笔记 | 说明 | 状态 |
|------|------|------|
| [`flight-principles.md`](physics/flight-physics/flight-principles.md) | 四大飞行力、固定翼、直升机、火箭、VTOL 原理 | ✅ |

#### 机械结构 ([`→`](physics/mechanical/README.md))

| 笔记 | 说明 | 状态 |
|------|------|------|
| [`manual-transmission.md`](physics/mechanical/manual-transmission.md) | 手动变速箱：齿轮传动、扭矩/转速/功率守恒、低档力气大/高档速度快、换挡踩离合、起步半联动 | ✅ |
| [`nanometer-precision.md`](physics/mechanical/nanometer-precision.md) | 芯片组装纳米级精度：普通机械臂为何到不了、测量—反馈—补偿闭环、四大支柱（低误差结构/微动/温控/隔振）、矩阵算法（齐次变换/最小二乘/单应SVD/状态空间/雅可比协方差） | ✅ |
| [`nanometer-precision-math.md`](physics/mechanical/nanometer-precision-math.md) | 纳米级精度的矩阵推导姊妹篇：齐次变换、伪逆最小二乘、Kabsch/SVD、AX=XB 手眼标定、单应/DLT、LQR/里卡提、卡尔曼滤波、Σ_out=JΣJᵀ 误差传播、Kφ=ω²Mφ 模态、亚像素重心，逐条完整推导 | ✅ |

---

## 为什么用 AI 学习？

- **按需讲解** — 遇到不懂的概念，AI 可以用不同角度反复解释，直到理解为止。
- **即时出题** — 学完一个知识点，AI 可以立刻生成习题并批改答案。
- **知识串联** — AI 能看到学科之间的联系，帮助建立跨学科的知识网络。
- **进度自定** — 完全按照自己的节奏推进，不受课程表的限制。

### 推荐学习流程

```
1. 选定主题 → 2. 创建笔记 → 3. AI 讲解 → 4. 记笔记
    ↑                                    ↓
    7. 复习总结 ← 6. AI 批改 ← 5. AI 出题
```

### 关键原则

1. **先自己写，再让 AI 批改** — 不要直接让 AI 给答案。
2. **笔记要自己整理** — 笔记的文字必须是你自己理解后写下的。
3. **定期回顾** — 利用 `summary.md` 做阶段性总结，让 AI 帮忙检查遗漏。
4. **跨学科连接** — 学到一个概念时，问问 AI 它在其他学科中的对应物。

---

## 目录结构规范

```
AI/
├── README.md              # 本文件：项目说明 + 知识索引
├── computer/              # 计算机科学
│   ├── <topic>/README.md   # 主题学习大纲
│   ├── <note>.md          # 学习笔记
│   └── exercises.md       # 习题
├── math/                  # 数学
├── network/               # 网络
└── physics/               # 物理
```

**文件命名**：全小写 + 连字符（如 `data-structures.md`），每个目录入口统一叫 `README.md`。

---

## 快速开始

```bash
# 1. 创建主题文件夹
mkdir -p computer/my-topic

# 2. 创建笔记文件
touch computer/my-topic/README.md

# 3. 在 Claude 中提问，开始学习
```

---

> **学习是一场马拉松，不是短跑。AI 是你的陪跑员，不是代跑者。**