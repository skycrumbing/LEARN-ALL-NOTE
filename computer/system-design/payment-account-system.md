# 支付账户系统设计方案

## 一、核心设计理念

### 1.1 复式记账法
- **基本原则**：有借必有贷，借贷必相等
- **优势**：账务天然平衡，任何一笔交易都有明确的资金来源和去向
- **实现方式**：每笔交易至少产生两条账户变动明细（一借一贷）

### 1.2 分层架构
```
┌─────────────────────────────────────┐
│     交易层（快速响应/防重幂等）       │
├─────────────────────────────────────┤
│   账务层（核心一致性/乐观锁/热点隔离） │
├─────────────────────────────────────┤
│  清算结算层（异步处理/T+1对账）       │
└─────────────────────────────────────┘
```

### 1.3 关键约束
- **精度要求**：严禁使用浮点数，必须使用 `DECIMAL(20,2)` 或 `BIGINT`（分）存储金额
- **不可篡改**：流水表采用 Append-only 模式，禁止修改历史数据
- **幂等性**：所有接口通过唯一 `request_id` 保证幂等

---

## 二、核心表结构设计

### 2.1 交易流水表 `t_transaction_log`
```sql
CREATE TABLE t_transaction_log (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    request_id VARCHAR(64) NOT NULL UNIQUE COMMENT '幂等键',
    transaction_no VARCHAR(64) NOT NULL UNIQUE COMMENT '交易流水号',
    merchant_id VARCHAR(32) NOT NULL COMMENT '商户ID',
    user_id VARCHAR(32) COMMENT '用户ID',
    amount DECIMAL(20,2) NOT NULL COMMENT '交易金额（元）',
    currency CHAR(3) DEFAULT 'CNY' COMMENT '币种',
    transaction_type TINYINT NOT NULL COMMENT '交易类型: 1-充值 2-消费 3-提现 4-退款 5-转账',
    status TINYINT NOT NULL DEFAULT 0 COMMENT '状态: 0-处理中 1-成功 2-失败',
    channel_code VARCHAR(32) COMMENT '渠道编码',
    channel_order_no VARCHAR(64) COMMENT '渠道订单号',
    remark VARCHAR(256) COMMENT '备注',
    create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_merchant_status (merchant_id, status),
    INDEX idx_create_time (create_time),
    INDEX idx_channel_order (channel_order_no)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='交易流水表';
```

### 2.2 商户主账户表 `t_merchant_account`
```sql
CREATE TABLE t_merchant_account (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    merchant_id VARCHAR(32) NOT NULL UNIQUE COMMENT '商户ID',
    account_no VARCHAR(64) NOT NULL UNIQUE COMMENT '账户编号',
    balance DECIMAL(20,2) NOT NULL DEFAULT 0.00 COMMENT '可用余额',
    frozen_balance DECIMAL(20,2) NOT NULL DEFAULT 0.00 COMMENT '冻结金额',
    total_income DECIMAL(20,2) NOT NULL DEFAULT 0.00 COMMENT '累计收入',
    total_expense DECIMAL(20,2) NOT NULL DEFAULT 0.00 COMMENT '累计支出',
    version INT NOT NULL DEFAULT 0 COMMENT '乐观锁版本号',
    status TINYINT NOT NULL DEFAULT 1 COMMENT '状态: 1-正常 0-冻结',
    create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_merchant (merchant_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='商户主账户表';
```

### 2.3 待清算账户表 `t_merchant_pending_account`
```sql
CREATE TABLE t_merchant_pending_account (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    merchant_id VARCHAR(32) NOT NULL COMMENT '商户ID',
    pending_amount DECIMAL(20,2) NOT NULL DEFAULT 0.00 COMMENT '待清算金额',
    settlement_date DATE COMMENT '预计清算日期（T+1）',
    status TINYINT NOT NULL DEFAULT 0 COMMENT '状态: 0-待清算 1-已清算',
    create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    settle_time DATETIME COMMENT '实际清算时间',
    INDEX idx_settlement_date (settlement_date),
    INDEX idx_merchant_status (merchant_id, status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='待清算账户表';
```

### 2.4 备付金总账表 `t_channel_reserve_account`
```sql
CREATE TABLE t_channel_reserve_account (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    channel_code VARCHAR(32) NOT NULL UNIQUE COMMENT '渠道编码',
    reserve_balance DECIMAL(20,2) NOT NULL DEFAULT 0.00 COMMENT '备付金余额',
    last_reconcile_date DATE COMMENT '最后对账日期',
    reconcile_diff DECIMAL(20,2) DEFAULT 0.00 COMMENT '对账差异',
    update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_channel (channel_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='渠道备付金总账表';
```

### 2.5 账户变动明细表 `t_account_movement`
```sql
CREATE TABLE t_account_movement (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    movement_no VARCHAR(64) NOT NULL UNIQUE COMMENT '变动流水号',
    transaction_no VARCHAR(64) NOT NULL COMMENT '关联交易流水号',
    account_type TINYINT NOT NULL COMMENT '账户类型: 1-商户主户 2-待清算户 3-备付金户 4-用户钱包',
    account_id VARCHAR(64) NOT NULL COMMENT '账户ID',
    direction TINYINT NOT NULL COMMENT '方向: 1-借方(增加) 2-贷方(减少)',
    amount DECIMAL(20,2) NOT NULL COMMENT '变动金额',
    balance_before DECIMAL(20,2) NOT NULL COMMENT '变动前余额',
    balance_after DECIMAL(20,2) NOT NULL COMMENT '变动后余额',
    business_type VARCHAR(32) COMMENT '业务类型',
    remark VARCHAR(256) COMMENT '备注',
    create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_transaction (transaction_no),
    INDEX idx_account (account_type, account_id),
    INDEX idx_create_time (create_time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='账户变动明细表（Append-only）';
```

### 2.6 用户钱包表 `t_user_account`
```sql
CREATE TABLE t_user_account (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    user_id VARCHAR(32) NOT NULL UNIQUE COMMENT '用户ID',
    wallet_no VARCHAR(64) NOT NULL UNIQUE COMMENT '钱包编号',
    balance DECIMAL(20,2) NOT NULL DEFAULT 0.00 COMMENT '可用余额',
    frozen_balance DECIMAL(20,2) NOT NULL DEFAULT 0.00 COMMENT '冻结金额',
    version INT NOT NULL DEFAULT 0 COMMENT '乐观锁版本号',
    status TINYINT NOT NULL DEFAULT 1 COMMENT '状态: 1-正常 0-冻结',
    create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_user (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='用户钱包表';
```

### 2.7 对账差异表 `t_reconciliation_diff`
```sql
CREATE TABLE t_reconciliation_diff (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    reconcile_date DATE NOT NULL COMMENT '对账日期',
    channel_code VARCHAR(32) NOT NULL COMMENT '渠道编码',
    diff_type TINYINT NOT NULL COMMENT '差异类型: 1-长款 2-短款',
    diff_amount DECIMAL(20,2) NOT NULL COMMENT '差异金额',
    order_count INT NOT NULL DEFAULT 0 COMMENT '差异订单数',
    status TINYINT NOT NULL DEFAULT 0 COMMENT '处理状态: 0-待处理 1-处理中 2-已解决',
    handler VARCHAR(32) COMMENT '处理人',
    resolve_remark TEXT COMMENT '处理说明',
    create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    resolve_time DATETIME COMMENT '解决时间',
    INDEX idx_reconcile_channel (reconcile_date, channel_code),
    INDEX idx_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='对账差异表';
```

### 2.8 分账指令表 `t_split_order`
```sql
CREATE TABLE t_split_order (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    split_order_no VARCHAR(64) NOT NULL UNIQUE COMMENT '分账订单号',
    transaction_no VARCHAR(64) NOT NULL COMMENT '原交易流水号',
    merchant_id VARCHAR(32) NOT NULL COMMENT '发起商户',
    total_amount DECIMAL(20,2) NOT NULL COMMENT '分账总金额',
    split_type TINYINT NOT NULL COMMENT '分账类型: 1-实时分账 2-延时分账',
    status TINYINT NOT NULL DEFAULT 0 COMMENT '状态: 0-待执行 1-执行中 2-已完成 3-失败',
    execute_time DATETIME COMMENT '执行时间',
    create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_transaction (transaction_no),
    INDEX idx_merchant (merchant_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='分账指令表';
```

### 2.9 分账明细表 `t_split_detail`
```sql
CREATE TABLE t_split_detail (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    split_order_no VARCHAR(64) NOT NULL COMMENT '分账订单号',
    receiver_id VARCHAR(32) NOT NULL COMMENT '收款方ID',
    receiver_type TINYINT NOT NULL COMMENT '收款方类型: 1-商户 2-用户',
    split_amount DECIMAL(20,2) NOT NULL COMMENT '分账金额',
    split_ratio DECIMAL(5,4) COMMENT '分账比例',
    status TINYINT NOT NULL DEFAULT 0 COMMENT '状态: 0-待入账 1-已入账 2-失败',
    create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finish_time DATETIME COMMENT '完成时间',
    INDEX idx_split_order (split_order_no),
    INDEX idx_receiver (receiver_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='分账明细表';
```

---

## 三、核心业务流程

### 3.1 充值流程
```
用户支付 → 渠道回调 → 创建交易流水 → 记账（借：备付金户 / 贷：用户钱包）
         ↓
    更新用户钱包余额（乐观锁）
         ↓
    记录账户变动明细（两条：一借一贷）
```

**SQL 示例：**
```sql
-- 1. 插入交易流水
INSERT INTO t_transaction_log (...) VALUES (...);

-- 2. 更新用户钱包（乐观锁）
UPDATE t_user_account 
SET balance = balance + #{amount}, 
    version = version + 1 
WHERE user_id = #{userId} AND version = #{oldVersion};

-- 3. 更新备付金总账
UPDATE t_channel_reserve_account 
SET reserve_balance = reserve_balance + #{amount} 
WHERE channel_code = #{channelCode};

-- 4. 记录账户变动明细（两条）
INSERT INTO t_account_movement (direction='借', account_type=3, ...) VALUES (...);
INSERT INTO t_account_movement (direction='贷', account_type=4, ...) VALUES (...);
```

### 3.2 消费支付流程
```
发起支付 → 冻结用户资金 → 调用渠道扣款 → 解冻并记账
         ↓
    （借：用户钱包 / 贷：商户主户）
         ↓
    记入待清算账户（T+1结算）
```

**关键点：**
- 先冻结用户资金，防止重复支付
- 渠道扣款成功后才真正记账
- 资金先进入待清算户，T+1 日清算到商户主户

### 3.3 分账流程
```
交易成功 → 创建分账指令 → 冻结待分账金额
         ↓
    执行内部分账记账（多条明细）
         ↓
    解冻剩余金额 / 划转到各收款方
```

**精度处理原则：**
- 采用"最后一人承担误差"原则
- 前 N-1 个收款方按比例计算（四舍五入）
- 最后一个收款方 = 总金额 - 前 N-1 个收款方金额之和

### 3.4 退款流程
```
发起退款 → 校验原交易 → 创建退款流水
         ↓
    记账（借：商户主户 / 贷：用户钱包）
         ↓
    如有分账，触发分账退回指令
```

---

### 3.5 同步 vs 异步边界说明

**核心原则：账户余额变动必须同步完成，非核心的关联动作可以异步化。**

#### 3.5.1 必须同步处理的操作

以下操作直接影响资金安全和账务一致性，**必须在同一个本地事务中同步完成**，不可异步：

| 操作 | 原因 | 失败后果 |
|------|------|----------|
| 插入交易流水 `t_transaction_log` | 交易的唯一凭证，是后续所有操作的依据 | 无法追溯、无法对账 |
| 更新账户余额（乐观锁） | 直接反映可用资金，用户实时查询依赖此值 | 余额不准导致超发/透支 |
| 记录账户变动明细 `t_account_movement` | 复式记账的借贷双方必须同时落库 | 账务不平、审计缺失 |
| 冻结/解冻资金 | 防止重复使用同一笔资金 | 双重支付风险 |
| 更新备付金总账 | 监管合规要求，备付金必须实时准确 | 合规风险 |

**实现方式：** 上述操作放在同一个数据库事务中，要么全部成功，要么全部回滚。

```java
@Transactional(rollbackFor = Exception.class)
public void recharge(String userId, BigDecimal amount, String channelId) {
    // 1. 插入交易流水
    transactionLogMapper.insert(log);
    
    // 2. 更新用户钱包余额（乐观锁）
    int rows = userAccountMapper.increaseBalance(userId, amount, oldVersion);
    if (rows == 0) throw new OptimisticLockException("余额更新冲突");
    
    // 3. 更新备付金总账
    reserveAccountMapper.increaseReserve(channelId, amount);
    
    // 4. 记录两条变动明细（一借一贷）
    movementMapper.insertDebit(...);   // 借：备付金户
    movementMapper.insertCredit(...);  // 贷：用户钱包
    
    // 以上四步在同一事务中，任何一步失败则整体回滚
}
```

#### 3.5.2 可以异步处理的操作

以下操作不影响资金安全，即使延迟几秒甚至几分钟也不影响业务正确性，**适合通过 MQ 异步解耦**：

| 操作 | 异步原因 | 推荐方案 |
|------|----------|----------|
| 发送短信/APP推送通知 | 通知服务可能超时，不应阻塞主流程 | MQ + 重试机制 |
| 更新统计报表/仪表盘数据 | 聚合计算耗时，与交易无关 | MQ + 定时补偿 |
| 生成对账单文件 | 大文件生成耗资源，可延后 | 异步任务 + OSS上传 |
| 风控规则扫描 | 复杂规则引擎可能慢，不影响当前交易 | MQ + 事后告警 |
| 更新用户等级/积分 | 非资金类权益，允许短暂不一致 | MQ + 幂等消费 |
| 写入大数据平台/数仓 | ETL 链路本身是异步的 | CDC / Binlog订阅 |
| 发送微信/支付宝模板消息 | 第三方接口不稳定 | MQ + 指数退避重试 |

**实现方式：** 采用本地消息表方案，确保消息不丢失。

```java
@Transactional(rollbackFor = Exception.class)
public void rechargeWithAsyncNotify(String userId, BigDecimal amount, String channelId) {
    // === 同步部分：资金操作 ===
    transactionLogMapper.insert(log);
    userAccountMapper.increaseBalance(userId, amount, oldVersion);
    reserveAccountMapper.increaseReserve(channelId, amount);
    movementMapper.insertDebit(...);
    movementMapper.insertCredit(...);
    
    // === 本地消息表：保证消息投递 ===
    localMessageMapper.insert(new LocalMessage(
        "RECHARGE_NOTIFY",           // 消息类型
        JSON.toJSONString(notifyPayload), // 消息体
        "PENDING"                     // 待发送状态
    ));
    
    // 事务提交后，由独立的定时任务扫描 PENDING 消息并发送到 MQ
}
```

#### 3.5.3 判断标准

遇到新业务场景时，用以下三个问题判断是否可异步：

1. **如果这个操作失败了，用户的钱会不会出错？**
   - 会 → 必须同步
   - 不会 → 可以异步

2. **用户是否能立即感知到这个操作的结果？**
   - 能（如余额变化）→ 必须同步
   - 不能（如收到通知短信）→ 可以异步

3. **这个操作是否有外部依赖（第三方接口、其他微服务）？**
   - 有 → 优先异步，避免外部故障拖垮核心链路
   - 无 → 视复杂度决定

#### 3.5.4 常见误区

| 误区 | 正确做法 |
|------|----------|
| "为了性能把所有记账都异步化" | 余额更新必须同步，否则用户查到旧余额会引发客诉 |
| "异步就一定更快" | 本地消息表本身也有开销，简单通知可直接同步调用 |
| "异步就不需要保证可靠性" | 异步消息必须有重试+死信队列+人工兜底机制 |
| "分账可以完全异步" | 分账指令创建和资金冻结必须同步，实际划转可异步 |

---

## 四、效率优化策略

### 4.1 读写分离
- **余额查询**：从 Redis 缓存读取（key: `account:balance:{accountId}`）
- **余额更新**：直接操作数据库，同时异步更新缓存
- **缓存失效策略**：余额变动后立即删除缓存，下次查询时重建

### 4.2 异步解耦
- **非核心动作**：发送通知、更新统计报表、生成对账单等通过 MQ 异步处理
- **消息可靠性**：采用本地消息表方案，确保消息不丢失

### 4.3 热点账户拆分
- **问题**：大商户频繁交易导致行锁竞争
- **方案**：将大商户拆分为多个虚拟子账户（如 `merchant_001_sub_01` ~ `merchant_001_sub_10`）
- **汇总展示**：对外展示时汇总所有子账户余额

### 4.4 批量记账优化
- **场景**：日终清算、批量分账
- **方案**：使用 `INSERT ... SELECT` 批量插入变动明细，减少网络往返
- **注意**：单次批量不超过 1000 条，避免长事务

---

## 五、准确性保障机制

### 5.1 幂等性设计
- **唯一键约束**：`request_id` 作为唯一索引，重复请求直接返回首次结果
- **分布式锁**：使用 Redis SETNX 防止并发重复提交

### 5.2 乐观锁控制
- **版本号机制**：每次更新余额时检查 `version` 字段
- **重试策略**：更新失败时重新查询最新余额并重试（最多 3 次）

### 5.3 内部对账
- **每日封账**：计算当日 EOD 余额 = 昨日 EOD + 今日总借 - 今日总贷
- **发生额校验**：汇总所有账户变动明细，与余额表变化比对
- **差异处理**：发现差异立即告警，人工介入排查

### 5.4 外部对账
- **T+1 对账**：每日凌晨下载渠道对账单，与内部流水逐笔比对
- **差异分类**：长款（渠道有我们无）、短款（我们有渠道无）、金额不一致
- **自动处理**：小额差异自动调整，大额差异人工审核

---

## 六、分布式事务方案

### 6.1 本地消息表方案
```
开始本地事务
  ├─ 更新交易状态
  ├─ 插入本地消息表（状态：待发送）
提交本地事务
  ↓
异步任务扫描待发送消息
  ├─ 发送 MQ 消息
  ├─ 更新消息状态为已发送
  └─ 失败则重试（最多 5 次）
```

**优势：**
- 保证交易状态更新与消息投递的最终一致性
- 避免分布式事务的性能损耗
- 消息发送失败可重试，不影响主流程

### 6.2 补偿机制
- **定时任务**：每小时扫描超过 5 分钟未完成的交易
- **自动冲正**：超时未回调的交易自动标记为失败，释放冻结资金
- **人工干预**：提供后台工具手动触发补偿

---

## 七、日终余额（EOD Balance）管理

### 7.1 定义
- **作用**：每日账务封账的基准点
- **用途**：
  - 内部发生额汇总校验
  - 外部渠道对账（发现长/短款）
  - 监管备付金合规报送

### 7.2 计算公式
```
今日EOD = 昨日EOD + 今日总借方发生额 - 今日总贷方发生额
```

### 7.3 实施步骤
1. **截断时间点**：每日 23:59:59 停止当日交易计入
2. **汇总发生额**：按账户类型汇总当日所有变动明细
3. **计算 EOD**：基于昨日 EOD 计算今日 EOD
4. **持久化存储**：将 EOD 余额写入 `t_eod_balance_snapshot` 表
5. **生成对账文件**：导出标准格式对账文件供财务审核

---

## 八、监控与告警

### 8.1 核心指标
- **交易成功率**：低于 99% 触发告警
- **平均响应时间**：超过 500ms 触发告警
- **对账差异率**：超过 0.01% 触发告警
- **备付金充足率**：低于阈值触发告警

### 8.2 日志规范
- **全链路追踪**：每个请求携带 `trace_id`，贯穿交易、记账、清算全流程
- **关键节点日志**：交易创建、状态变更、余额更新、对账完成等节点必须记录
- **敏感信息脱敏**：卡号、身份证号等字段需脱敏后记录

---

## 九、扩展性设计

### 9.1 多币种支持
- **表结构**：`currency` 字段标识币种
- **汇率转换**：维护汇率表，支持实时查询
- **备付金隔离**：不同币种备付金独立管理

### 9.2 多租户隔离
- **字段隔离**：所有表增加 `tenant_id` 字段
- **索引优化**：联合索引包含 `tenant_id` 提升查询效率
- **权限控制**：应用层强制校验租户权限

### 9.3 分库分表策略
- **分片键选择**：`merchant_id` 或 `user_id` 作为分片键
- **路由规则**：一致性哈希算法均匀分布数据
- **全局表**：渠道配置、汇率表等小表全量复制

---

## 十、安全与合规

### 10.1 数据安全
- **加密存储**：敏感字段（如银行卡号）使用 AES-256 加密
- **访问控制**：数据库账号最小权限原则，应用层使用只读/读写分离账号
- **审计日志**：所有余额修改操作记录操作人、时间、IP

### 10.2 合规要求
- **备付金存管**：按照央行要求，备付金全额存管至指定银行
- **反洗钱监控**：大额交易（单笔超过 5 万）自动上报
- **数据留存**：交易流水至少保存 5 年

---

## 附录：常见场景 SQL 模板

### A. 查询商户余额
```sql
SELECT 
    merchant_id,
    balance AS available_balance,
    frozen_balance,
    balance + frozen_balance AS total_balance
FROM t_merchant_account
WHERE merchant_id = #{merchantId};
```

### B. 查询交易流水
```sql
SELECT * FROM t_transaction_log
WHERE merchant_id = #{merchantId}
  AND create_time >= #{startTime}
  AND create_time < #{endTime}
ORDER BY create_time DESC
LIMIT #{pageSize} OFFSET #{offset};
```

### C. 生成日终对账单
```sql
SELECT 
    account_type,
    account_id,
    SUM(CASE WHEN direction = 1 THEN amount ELSE 0 END) AS total_debit,
    SUM(CASE WHEN direction = 2 THEN amount ELSE 0 END) AS total_credit,
    COUNT(*) AS movement_count
FROM t_account_movement
WHERE DATE(create_time) = #{reconcileDate}
GROUP BY account_type, account_id;
```

### D. 检测异常交易
```sql
-- 同一用户短时间内多次交易
SELECT 
    user_id,
    COUNT(*) AS tx_count,
    MIN(create_time) AS first_tx,
    MAX(create_time) AS last_tx
FROM t_transaction_log
WHERE create_time >= DATE_SUB(NOW(), INTERVAL 1 HOUR)
GROUP BY user_id
HAVING tx_count > 10;
```
