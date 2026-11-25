# GitHub 发布手册（维护者）

建议仓库名：`tiger-roar-awards-advisor`。建议描述：Evidence-driven marketing value assessment and independent Tiger Roar Awards advisory Agent Skill. 建议主题：`agent-skill`, `marketing`, `award-submission`, `evidence-review`, `skillbuddy`, `python`。建议标签 `v2.0.0-rc.1`，GitHub Release 勾选 Pre-release。

## 公开前必查

- [ ] 权利人确认代码公开授权、许可证及第三方派生规则、案例摘要和图标发布权限；不使用未获授权的官方素材。
- [ ] 确认非官方声明与 Qomob.AI / SkillBuddy 署名；WorkBuddy 仅为原发行适配环境。
- [ ] 检查 Git 跟踪文件无真实客户资料、密钥、令牌、私有附件或未授权完整案例。
- [ ] 确认测试结果与验收边界，真实专业盲评与宿主实测仍待完成。
- [ ] 验证 MANIFEST.json；CI 配置已提供但尚未在 GitHub 上运行。
- [ ] 维护者确认仓库可见性、Issue/私密漏洞报告策略及发布说明。

## 推送

先创建空仓库（建议暂设 Private，待权利确认后再改 Public），不要自动初始化 README。解压发布包，进入包含 SKILL.md 的目录。以下占位符必须替换；此包不包含已配置的 remote，不执行任何远程写操作。

```bash
git init -b main
git add .
git diff --cached --stat
git status --short
git commit -m "Prepare Tiger Roar Awards Advisor v2.0.0-rc.1"
git remote add origin https://github.com/YOUR-ACCOUNT/tiger-roar-awards-advisor.git
git push -u origin main
# 审查通过、确认公开权利后再打标签：
git tag -a v2.0.0-rc.1 -m "Internal trial release candidate"
git push origin v2.0.0-rc.1
```

## Release 文案

Tiger Roar Awards Advisor v2.0.0-rc.1 — Evidence-Driven Marketing Intelligence.

基于 SkillBuddy B 版主干，恢复历史测试，加入证据归属、冲突检测、外部签核、83类顾问条件、未知区间、最终事实文本及媒体属性检查。76项本地自动化测试通过。8条公开案例研究线索不作为专业金标准。官方后台字段、真实业务盲评和宿主兼容性仍待验证。内部试用候选版，生产 NO-GO，独立第三方非官方产品。

## 封面与品牌素材

中英文 README 已引用仓库内的横版封面和正式 SkillBuddy Logo。参见 [品牌素材说明](BRAND_ASSETS.md)。发布前确认素材使用权；未选许可证前不得将项目宣传为已获开源授权。可在 GitHub 仓库 Settings 的 Social preview 中按平台尺寸要求另行上传经审核的封面。
