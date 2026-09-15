# SSL / TLS 证书与 HTTPS

## 学习内容

- [x] 证书有效期 vs 域名有效期
- [x] 订阅期 vs 凭证有效期（GoDaddy 续期机制）
- [x] CA/Browser Forum 398 天有效期上限
- [x] 证书三件套：私钥 / 服务器证书 / 中间证书链
- [x] 信任链验证机制
- [x] 证书签发流程（CSR → CA 签名）与浏览器验证流程
- [x] 域名验证（DNS TXT 记录）与证书签发状态
- [x] 公钥密码学与 TLS 混合加密握手
- [x] 公共 CA 与私有 CA 的区别
- [x] Nginx 部署 / 替换证书实操
- [x] openssl 常用验证命令

## 笔记文件

| 文件 | 说明 | 状态 |
|------|------|------|
| `godaddy-ssl-qa-record.md` | GoDaddy SSL 证书续期与 Nginx 部署实战记录（10 个 Q&A + 附录命令） | ✅ 已完成 |
