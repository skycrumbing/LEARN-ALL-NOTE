# OA 流程系统（审批工作流）设计

> 场景：公司 OA 里报销、请假、合同、用章等单据要走审批流程。需要支持多节点流转、会签、条件分支、撤回、超时处理，并且业务类型可配置。
> 整理日期：2026-10-20

---

## 一、核心思想：三层分离

最常见的误区是把审批逻辑写死在业务代码里（`if (amount > 5000) 找总监 else 找经理`），每加一种流程都要改业务代码。正确做法是把审批拆成三层：

```
流程定义（静态模板）      一份"模板"：有哪些节点、什么条件走哪条路
       ↓ 实例化
流程实例（运行时单据）     某张具体报销单，正在走这个流程
       ↓ 当前节点生成
任务实例（待办）           张三的待办：审核报销单 #123
       ↓ 审批动作
      同意/驳回 → 下一个节点 → 下一个任务
```

- **定义**管"怎么流转"（模板，可设计、可版本化）
- **实例**管"走到哪了"（运行时状态）
- **任务**管"谁该干活"（具体人的待办）

业务系统只负责提交流程、调审批 API、监听流程结果回调。

---

## 二、整体架构

```
┌─────────────────────────────────────────────────────┐
│                    业务系统（OA）                      │
│  ┌────────┐  ┌──────────┐  ┌────────┐               │
│  │ 报销单  │  │ 请假单    │  │ 合同单  │   ...         │
│  └────┬───┘  └────┬─────┘  └────┬───┘               │
│       │ 提交流程    │             │                    │
└───────┴────────────┴─────────────┴───────────────────┘
                    │  发起/审批/撤回 API
                    ▼
        ┌──────────────────────────┐
        │      流程引擎              │
        │  • 流程定义（BPMN/JSON）   │
        │  • 实例推进与流转           │
        │  • 节点完成度计算          │
        │  • 事件回调（节点完成/审批） │
        └────────────┬─────────────┘
                     │  MQ / 回调通知
        ┌────────────┴─────────────┐
        │ 待办中心 / 消息推送 / 报表  │
        └──────────────────────────┘
```

---

## 三、节点类型与审批模式

### 3.1 节点类型

```
开始 → 审批节点 → 条件分支 → 并行网关 → 子流程 → 抄送 → 结束
         ↑                          ↑
     单签/或签/并签              同时走多条路
```

### 3.2 审批模式（核心复杂点）

| 模式 | 含义 | 完成条件 |
|------|------|---------|
| **单签** | 一人审 | 一人处理完即结束 |
| **或签** | 多人中任一人审 | 一人同意 → 通过；全部驳回才驳回 |
| **并签** | 多人全部要审 | 全同意 → 通过；一人驳回 → 驳回 |
| **依次签** | 按顺序审 | 上一个人审完才轮到下一个 |
| **按比例签** | 多数决 | 同意数 / 总数 ≥ 阈值 → 通过 |

---

## 四、数据模型（六张核心表）

```sql
-- 1. 流程定义（模板）
CREATE TABLE wf_process_definition (
    definition_id   VARCHAR(64) PRIMARY KEY,
    process_key     VARCHAR(64) NOT NULL UNIQUE COMMENT '流程标识，如 expense_apply',
    process_name    VARCHAR(128) NOT NULL,
    version         INT NOT NULL DEFAULT 1,
    bpmn_content    LONGTEXT COMMENT 'BPMN XML 或自定义 JSON 定义',
    status          TINYINT DEFAULT 1 COMMENT '1启用 0停用'
);

-- 2. 节点定义（模板里的每个节点）
CREATE TABLE wf_node_definition (
    node_id         VARCHAR(64) PRIMARY KEY,
    definition_id   VARCHAR(64) NOT NULL,
    node_name       VARCHAR(128),
    node_type       VARCHAR(32) COMMENT 'start/approve/cc/condition/end/parallel',
    approval_mode   VARCHAR(32) COMMENT 'single/or_sign/all_sign',
    assignee_rule   VARCHAR(512) COMMENT '审批人规则：指定用户/角色/部门负责人/表达式',
    sort            INT
);

-- 3. 流程实例（一张单据走流程的运行时）
CREATE TABLE wf_process_instance (
    instance_id     VARCHAR(64) PRIMARY KEY,
    definition_id   VARCHAR(64) NOT NULL,
    business_id     VARCHAR(64) NOT NULL COMMENT '业务单据ID，如报销单ID',
    initiator_id    VARCHAR(64) NOT NULL COMMENT '发起人',
    current_node    VARCHAR(64) COMMENT '当前节点',
    status          VARCHAR(32) COMMENT 'running/approved/rejected/cancelled',
    form_data       JSON COMMENT '表单数据快照（流程与业务解耦的关键）',
    create_time     DATETIME DEFAULT CURRENT_TIMESTAMP,
    finish_time     DATETIME
);

-- 4. 任务实例（某人在某节点的一条待办）
CREATE TABLE wf_task_instance (
    task_id         VARCHAR(64) PRIMARY KEY,
    instance_id     VARCHAR(64) NOT NULL,
    node_id         VARCHAR(64) NOT NULL,
    assignee_id     VARCHAR(64) NOT NULL COMMENT '处理人',
    status          VARCHAR(32) COMMENT 'pending/approved/rejected/transferred',
    action          VARCHAR(32),
    comment         VARCHAR(512),
    handle_time     DATETIME,
    KEY idx_assignee_status (assignee_id, status) COMMENT '待办列表查询'
);

-- 5. 审批记录（操作历史）
CREATE TABLE wf_approval_record (
    record_id       VARCHAR(64) PRIMARY KEY,
    instance_id     VARCHAR(64) NOT NULL,
    task_id         VARCHAR(64),
    operator_id     VARCHAR(64) NOT NULL,
    action          VARCHAR(32) NOT NULL COMMENT 'submit/agree/reject/transfer/...',
    comment         VARCHAR(512),
    operate_time    DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

> **关键设计点**：`form_data` 把表单数据快照存进流程实例，让**流程与业务表解耦**——即使业务表里报销单被改了，历史审批记录仍能看到当时的内容。

---

## 五、审批操作（伪代码）

```java
public void approve(String taskId, String operatorId, boolean pass, String comment) {
    Task task = taskRepo.of(taskId);
    assert(task.assigneeId.equals(operatorId), "不是你的待办");

    // ① 更新任务状态 + 写审批记录
    taskRepo.updateStatus(task, pass ? "approved" : "rejected", comment);
    recordRepo.insert(task.instanceId, task.nodeId, operatorId,
                      pass ? "agree" : "reject", comment);

    // ② 节点完成度计算（会签核心逻辑）
    NodeResult result = evalNodeCompletion(task.nodeId, pass);

    // ③ 流程流转
    if (result == PASS) {
        Instance inst = instanceRepo.of(task.instanceId);
        String next = findNextNode(inst.definitionId, task.nodeId);  // 走条件分支
        inst.currentNode = next;
        instanceRepo.update(inst);
        createTasksForNode(next, inst);          // 下一节点生成新待办
    } else if (result == REJECT) {
        instanceRepo.updateStatus(inst, "rejected");
    }
    notifyNextHandler(task.instanceId);           // 推送给下一个待办人
}
```

---

## 六、会签完成度算法

这是整个引擎里最容易出错的部分——一个会签节点会有多个任务，要持续维护完成度：

```java
public NodeResult evalNodeCompletion(String nodeId, boolean thisPass) {
    List<Task> tasks = taskRepo.byNode(nodeId);   // 当前节点所有任务
    int total    = tasks.size();
    int passed   = countByStatus(tasks, "approved");
    int rejected = countByStatus(tasks, "rejected");
    String mode  = nodeDef(approvalMode);         // or_sign / all_sign / ratio_sign

    switch (mode) {
        case "or_sign":  // 或签：任一人通过即通过；全部驳回才驳回
            if (passed > 0)        return PASS;
            if (rejected == total) return REJECT;
            return ONGOING;        // 还有人在审，继续等

        case "all_sign": // 并签：全通过才通过；一人驳回即驳回
            if (rejected > 0)      return REJECT;
            if (passed == total)   return PASS;
            return ONGOING;

        case "ratio_sign": // 按比例签
            double ratio = passed / total;
            if (ratio >= nodeDef.passThreshold)  return PASS;
            if (rejected == total)               return REJECT;
            return ONGOING;

        default: // single
            return thisPass ? PASS : REJECT;
    }
}
```

---

## 七、复杂场景

### 7.1 撤回 / 撤销

仅发起人可撤，且下一节点**还没人处理过**。处理时把当前节点所有 pending 任务作废，实例置为 `cancelled`。

### 7.2 转交 / 委托 / 加签

```
转交（transfer）    A 的待办 → 转给 B；A 的待办变 transferred，B 多一条 pending
委托（delegate）    A 把一段时间内所有待办委托给 B（A 休假）
加签（addSign）     在审批人前后/并行临时加一个人（领导拉人进来）
```

### 7.3 超时自动处理

```java
@Scheduled(cron = "0 * * * * ?")           // 每分钟扫一次
public void handleTimeoutTasks() {
    List<Task> tasks = taskRepo.timeoutNow(1);   // 超 1 小时未处理
    for (Task t : tasks) {
        switch (t.timeoutPolicy) {
            case "auto_pass":                              // 超时自动通过
                approve(t.taskId, "system", true, "超时自动通过");
                break;
            case "escalate":                               // 超时升级给上级
                transfer(t.taskId, t.assigneeId, getManager(t.assigneeId));
                break;
            case "remind":                                 // 超时催办
                notify(t.assigneeId, "你有待办超时了");
                break;
        }
    }
}
```

---

## 八、流程状态机

```
草稿 ──提交──▶ 审批中 ──全部通过──▶ 已完成
                │
                ├── 驳回 ──▶ 已驳回 ──重新提交──▶ 审批中
                │
                └── 撤回 ──▶ 已撤回 ──重新提交──▶ 审批中
```

- 状态只允许单向或明确允许的跳转，禁止非法状态（如已完成 → 审批中）
- 每次状态变更都要写 `approval_record`，方便审计回溯

---

## 九、引擎选型

| 引擎 | 维护 | 特点 |
|------|------|------|
| **Flowable** | ✅ 活跃 | Activiti 分支，国内最常用，BPMN 2.0，功能全 |
| **Camunda** | ✅ 活跃 | BPMN 实现最完整、性能最好、企业版收费 |
| **Activiti** | ⚠️ 停维护 | 老牌、文档多、轻量 |
| **Warm-Flow** | ✅ 国产活跃 | 轻量、上手快、BPMN 可选 |

**用引擎还是自研**：
- 流程简单（3-5 个线性节点、几乎不变）→ **自研**，几十张表搞定，完全可控
- 流程复杂多变（条件分支、并行、子流程）、需要可视化设计器、需要定义版本管理 → **用 Flowable / Camunda**

### 9.1 BPMN 表达示例

如果选引擎，流程通常用 BPMN XML 定义。报销审批（金额 < 5000 只走经理，≥ 5000 加总监）：

```xml
<process id="expense_apply" name="报销审批">
  <startEvent id="start"/>

  <userTask id="mgrApprove"  name="经理审批" assignee="${deptManager}"/>
  <exclusiveGateway id="amountCheck" name="金额分支"/>
  <userTask id="dirApprove"  name="总监审批" assignee="${director}"/>
  <endEvent   id="end"/>

  <sequenceFlow sourceRef="start"       targetRef="mgrApprove"/>
  <sequenceFlow sourceRef="mgrApprove"  targetRef="amountCheck"/>

  <sequenceFlow sourceRef="amountCheck" targetRef="dirApprove">
    <conditionExpression>${amount >= 5000}</conditionExpression>
  </sequenceFlow>
  <sequenceFlow sourceRef="amountCheck" targetRef="end">
    <conditionExpression>${amount &lt; 5000}</conditionExpression>
  </sequenceFlow>
  <sequenceFlow sourceRef="dirApprove"  targetRef="end"/>
</process>
```

自研时可以用类似的 JSON 结构（节点 + 出边 + 条件表达式）存进 `bpmn_content`。

---

## 十、关键细节与坑

1. **待办列表性能**：`assignee_id + status` 建联合索引；量大后用 ES 或分库
2. **流程版本管理**：改了定义后，进行中的实例**继续用旧版本还是迁移到新版本**？必须提前定
3. **审批人离职**：要有代理机制 / 管理员改派 / 走上级兜底
4. **表单与流程解耦**：`form_data` 存快照，别去查业务表（否则历史审批记录会跟着变）
5. **幂等**：审批按钮可能被双击、网络重试——`taskId + operatorId + action` 必须幂等
6. **流程与业务回调**：用 MQ 解耦，别让引擎直接调业务接口（业务挂了流程就卡死）

---

## 十一、一句话总结

**流程定义、流程实例、任务实例三层分离，`form_data` 快照解耦业务表；会签完成度计算是核心难点；流程简单自研、流程多变选 Flowable；状态变更写审计记录，审批操作必须幂等。**