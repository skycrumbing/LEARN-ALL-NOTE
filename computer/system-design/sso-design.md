# 单点登录（SSO）系统设计

> 场景：公司内部多套系统接入统一登录平台，用同一个账号一次登录、处处可用；不同系统按各自的角色、菜单、权限授权；各系统自己也能创建用户。
> 整理日期：2026-10-10

---

## 一、核心思想：认证与授权分离

**SSO 只回答「你是谁」，每个系统自己回答「你能干什么」。**

| | 认证 Authentication | 授权 Authorization |
|---|---|---|
| 回答的问题 | 你是哪个账号？ | 你能看哪些菜单、点哪些按钮？ |
| 谁负责 | **统一认证中心**（集中） | **每个业务系统自己**（分散） |
| 产出物 | 一个「身份凭证」（code/ticket/token） | 本系统的角色 + 菜单 + 权限 |

这是整个设计的灵魂。很多人一开始就把「统一登录」和「统一权限中心」揉在一起，导致各系统相互耦合。正确做法：

- 认证中心只发凭证、不关心业务权限；
- 各系统拿到身份（统一 `user_id`）后，查**自己**的用户-角色-菜单-权限表。

---

## 二、整体架构

```
               ┌────────────────────────────────┐
               │      统一认证中心（SSO / IDP）    │
               │   • 账号 + 密码/验证码/扫码/企微  │
               │   • 发放登录凭证（code/ticket）   │
               │   • 全局会话、单点登出、踢下线    │
               └───────────────┬────────────────┘
                               │  同一套凭证
        ┌──────────┬───────────┼───────────┬──────────┐
        ▼          ▼           ▼           ▼          ▼
   ┌─────────┐┌─────────┐┌─────────┐┌─────────┐┌─────────┐
   │  系统A   ││  系统B   ││  系统C   ││  系统D   ││   ...    │
   │ 自己的RBAC││ 自己的RBAC││ 自己的RBAC││ 自己的RBAC││         │
   └─────────┘└─────────┘└─────────┘└─────────┘└─────────┘
```

每个业务系统在认证体系里就是一个 **客户端（Client / Service Provider）**。「接入」的本质就是给每个系统装一个 SSO 拦截器/SDK：拦截未登录请求 → 跳认证中心 → 校验凭证 → 建本系统会话。

---

## 三、认证流程（协议无关主干）

```
1. 用户访问 系统A，未登录
   → 系统A 把用户 302 重定向到 认证中心（带「回跳地址 + 我是系统A」）
2. 认证中心检查自己有没有「全局会话」：
   ├─ 有  → 直接发凭证（跳到 3）→ 这就是"第二次不用再登录"的单点
   └─ 无  → 让用户输账号密码，校验通过后建立全局会话
3. 认证中心生成一次性凭证（code/ticket），重定向回 系统A
4. 系统A 拿凭证向认证中心换/校验 → 得到统一 user_id + 基本信息
5. 系统A 建立本地会话，用 user_id 查自己库里的 角色→菜单→权限 → 渲染
```

之后用户再点进 **系统B**：跳认证中心时全局会话还在 → 免登录直接发凭证 → 系统B 走第 4、5 步，但查到的是**系统B 自己的权限**。

> 关键点：**「单点」的载体是认证中心的全局会话，不是每个系统的本地会话。** 各系统仍然维护自己的本地会话/令牌，互不共享。

---

## 四、协议选型对比

| 协议 | 定位 | 优点 | 缺点 | 判断 |
|------|------|------|------|------|
| **OAuth2 + OIDC** | 现代标准 | 前端/后端/移动/API 全兼容、生态最好、标准 token | 概念多、要理解 code 与 token 区别 | ✅ **首选** |
| **CAS** | 经典 SSO | 极简、session 语义直白、全局登出天然支持 | 偏纯 Web、现代化弱 | 纯内网想快速落地 |
| **SAML 2.0** | 企业 XML 标准 | 跨组织成熟、兼容老企业软件 | XML 繁琐、偏重 | 接企业级/外部 SaaS |
| JWT 直发（无中心） | 轻量 | 无状态、认证中心零压力 | 全局登出难、凭证难吊销 | 少数场景才考虑 |

### 4.1 推荐：OIDC 的 Authorization Code + PKCE 流程

```
浏览器 ──访问──▶ 系统A(客户端)
        未登录
   ◀──302 跳转── 认证中心登录页（client_id + redirect_uri + state）
   ──输账号密码──▶ 认证中心校验通过，发【授权码 code】
   ◀──302 跳回── 系统A 带着 code 回来
                系统A 后端用 code + PKCE 换【access token / id token】
                → 从 id token 拿到统一 user_id，建本地会话
```

- **code** 是一次性、短时效、经浏览器转手的东西，被截获也没用（换 token 还要客户端密钥/PKCE）。
- **token** 是最终的凭证，只在系统后端与认证中心之间走，不进浏览器地址栏。

---

## 五、账号体系：统一账号 + 各系统自有档案

关键：**账号主数据集中在认证中心，各系统只存「本系统档案」并引用同一个 `user_id`。**

### 5.1 认证中心 —— 统一账号表

```sql
CREATE TABLE sso_user (
    user_id      BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '全局唯一用户ID',
    username     VARCHAR(64)  NOT NULL UNIQUE COMMENT '登录账号（全网唯一）',
    password     VARCHAR(128) NOT NULL COMMENT '密码（bcrypt 存储，不存明文）',
    mobile       VARCHAR(20)  COMMENT '手机号',
    email        VARCHAR(128) COMMENT '邮箱',
    real_name    VARCHAR(64)  COMMENT '真实姓名',
    status       TINYINT      NOT NULL DEFAULT 1 COMMENT '1启用 0禁用',
    create_time  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    update_time  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='统一账号表（认证中心）';
```

### 5.2 业务系统 —— 本系统用户档案

```sql
CREATE TABLE sys_user (
    id          BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '本系统记录ID',
    user_id     BIGINT NOT NULL COMMENT '引用 sso_user.user_id',
    nickname    VARCHAR(64)  COMMENT '本系统昵称',
    dept_id     BIGINT COMMENT '本系统部门',
    status      TINYINT NOT NULL DEFAULT 1,
    UNIQUE KEY uk_user (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='本系统用户档案';
```

同一个 `user_id` 在每个系统各有各的档案、各有各的角色——互不影响。

---

## 六、各系统如何创建用户

**原则：账号的「唯一真相源」在认证中心，业务系统不能自己乱建账号**，否则会出现「两个系统建了同一个 username」的冲突。用户名查重必须由认证中心统一保证。

### 6.1 创建流程

```
方式一（实时，推荐）：
  系统A 调认证中心接口 POST /sso/user/create
    { username, mobile, realName, ... } → 返回全局 user_id
  系统A 本地 insert sys_user(user_id) + 分配本系统角色

方式二（异步，用户量大/跨网络）：
  系统A 先落本地建档 → 发 MQ 通知认证中心建档
  需处理一致性问题：认证中心还没建档完成，用户就来登录的窗口期
```

创建用户时认证中心还会做：用户名唯一性校验、密码强度、手机/邮箱占用检查。账号一旦创建，`user_id` 全网驱动器各处许可。

---

## 七、授权模型：每个系统独立 RBAC

经典 **用户 — 角色 — 菜单 — 权限** 模型，菜单和权限点通常放一张表用 `menu_type` 区分：

```sql
CREATE TABLE sys_role (
    role_id   BIGINT PRIMARY KEY AUTO_INCREMENT,
    role_name VARCHAR(64) NOT NULL,
    role_code VARCHAR(64) NOT NULL UNIQUE
);

CREATE TABLE sys_user_role (
    user_id BIGINT NOT NULL COMMENT '引用 sys_user.user_id',
    role_id BIGINT NOT NULL,
    PRIMARY KEY (user_id, role_id)
);

CREATE TABLE sys_menu (
    menu_id   BIGINT PRIMARY KEY AUTO_INCREMENT,
    parent_id BIGINT NOT NULL DEFAULT 0 COMMENT '0=顶级菜单',
    menu_name VARCHAR(64),
    menu_type TINYINT COMMENT '1目录 2菜单 3按钮/权限点',
    path      VARCHAR(128),
    perms     VARCHAR(128) COMMENT '权限标识，如 system:user:add'
);

CREATE TABLE sys_role_menu (
    role_id BIGINT NOT NULL,
    menu_id BIGINT NOT NULL,
    PRIMARY KEY (role_id, menu_id)
);
```

登录后，系统A 拿着统一 `user_id` 查自己库：**同一个 user_id，在系统A 是管理员、在系统B 可能只是普通员工**——角色定义在各系统里，天然隔离。若要做到「部门内数据隔离」，再加一层数据权限 `data_scope`（本人/本部门/本部门及以下/全部）。

---

## 八、业务系统如何接入（嵌入）

每个系统集成一个 SSO 过滤器/SDK。核心问题只有一个：**「这个请求算不算已登录」怎么判断？** 答案取决于你给本系统选哪种「本地会话」模型。

### 8.1 两种本地会话模型

| | 有状态会话（Redis） | 无状态令牌（本地 JWT） |
|---|---|---|
| 凭证是什么 | 随机 sessionId（存 Cookie） | 本系统自己签发的 JWT（存 Cookie / Header） |
| 「有用户吗」放哪 | 服务端 Redis 里 `sessionId → 用户信息` | 令牌本身里（解出来就是） |
| 优点 | 能即时踢下线/禁用 | 无存储、无状态、好水平扩展 |
| 缺点 | 要维护 Redis、每次查一次 | 无法即时吊销，禁用要等令牌过期（或加黑名单） |

> 结论：需要「立刻踢人 / 立刻禁用」的选**有状态**；追求简单无状态的选 **JWT（短时效 + 黑名单兜底）**。


```java
// 业务系统的 SSO 过滤器 + 会话管理（伪代码，有状态版）
public void doFilter(req, res) {
    Long userId = hasValidLocalSession(req);    // 见下：Cookie→Redis→过期→状态
    if (userId != null) {
        setCurrentUser(userId);                 // 放进 ThreadLocal
        chain.next(req, res);
        return;
    }

    String code = req.getParameter("code");
    if (code == null) {
        // 未认证：跳认证中心，带上"我是谁" + 回跳地址（必须在白名单内）+ 防 CSRF 的 state
        res.sendRedirect(SSO_URL + "?client_id=A&redirect_uri=" + encode(backUrl) + "&state=" + randomState());
        return;
    }

    // 用 code 换用户身份（一个 code 只能用一次，这段做好超时/重试/幂等）
    UserInfo user = ssoClient.exchange(code, verifier);  // 返回统一 user_id + 基本信息
    if (user == null) {
        res.sendRedirect(backUrl + "?loginError=1");     // code 已失效/被重放，回登录页
        return;
    }
    saveLocalSession(user.getUserId());         // 建本地会话 + 写 Cookie + 设过期
    res.sendRedirect(backUrl);                  // 清掉地址栏里的 code，避免刷新重复换 code
}

// 单点登出时，认证中心回调本系统的这个接口来清会话
public void clearLocalSession(req, res) {
    String sid = getCookie(req);
    redis.del(sessionKey(sid));                 // 删会话
    res.clearCookie("SESSIONID");               // 删 Cookie
}
```

### 8.2 有状态会话：hasValidLocalSession 到底查什么

上面代码里的 `hasValidLocalSession(req)` 四步判断展开来看：

```
hasValidLocalSession(req) 的四步判断：

  ① 拿 Cookie      请求里有没有 SESSIONID？没有 → false（直接进登录流程）

  ② 查 Redis       redis.get(sessionId) 在不在？
                   不在/被删 → false（会话过期，或已被单点登出清掉）

  ③ 看过期         session 里的 expireTime 到了没？
                   到了 → false（并顺手删 key）

  ④ 看用户状态     该 user_id 是否被禁用/删除？
                   （本地黑名单缓存，或每次回源认证中心校验）
                   禁用 → false（并清掉本地会话）

  四步全过 → true，并把 user_id 放进请求上下文（ThreadLocal），
  后续 controller / service 直接取当前用户，不再重复校验。
```

### 8.3 无状态令牌：hasValidLocalSession 的另一种写法

本系统签发自己的短时效 access token（JWT），判断逻辑变成对称的四步：

```
  ① 拿 token       Cookie / Header 里有没有 token？没有 → false
  ② 验签名         用本系统密钥验签，被篡改 → false
  ③ 验过期         exp 是否已过？过了 → false
  ④ 验黑名单       该 user_id（或 token 的 jti）在黑名单里吗？
                   在 → false（禁用/登出后立即拉黑，弥补 JWT 无法吊销的缺点）

  四步全过 → true，从 token 里解出 user_id 放进 ThreadLocal
```

### 8.4 接入要额外做对的三件事

① 配好 `client_id`/密钥 + **回跳地址白名单**（防开放重定向）；② 「用 code 换身份」这一调用做**超时、重试、幂等**（一个 code 只能换一次）；③ **每次校验都兼顾用户最新状态**——「本地会话没过期」不等于「用户仍被允许」：禁用/删除要通过黑名单缓存或回源校验及时生效。

---

## 九、关键细节与常见坑

1. **全局登出**：在认证中心注销 → 要通知所有系统清会话/令牌（CAS 天然支持；OIDC 走 `end_session_endpoint` / 反向通道登出）。这是 SSO 最容易被忽略的坑。
2. **踢下线 / 单设备登录**：认证中心维护会话列表，支持「同账号互踢」「管理员强踢」。
3. **token 过期与刷新**：access token 短时效 + refresh token 续期，避免一个 token 永不过期。
4. **用户变更同步**：账号禁用/删除后，各系统要及时拉黑（本地黑名单、token 吊销、每次校验实时查状态）。
5. **安全**：回跳地址白名单（防开放重定向）、PKCE（防授权码截获）、`state` 参数（防 CSRF）。

---

## 十、一句话总结

**认证中心管「你是谁 + 全局会话」，各系统管「你能干什么」：同一个 `user_id` 全网唯一，角色/菜单/权限落在每个系统自己的库里；账号统一由认证中心建档，业务系统引用 `user_id` 并各自授权。**