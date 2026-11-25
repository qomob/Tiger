# V2.0 RC1 运行指南
Python 3.10+；离线；OpenSSL（支持 Ed25519）用于独立签核验证，ffprobe可选用于媒体探测。无网络写操作。平台没有脚本能力时提供人工草稿，标 NOT_RUN。所有命令在 Skill 根目录运行。

```sh
python3 scripts/roar.py catalog --group special --profiles
python3 scripts/roar.py fees --major 2 --excellent 1
python3 scripts/roar.py score special-01 8 7 8 6
python3 scripts/roar.py audit examples/v2/project.json --evidence-root examples/v2
```

score仅算术；audit退出码0=INTERNAL_REVIEW_ATTESTED（不是官方可提交），2=REVIEW，3=BLOCKED。例子为合成、无签核，预期2。旧JSON无V2 envelope仅返回MIGRATION_REQUIRED；不可继续调用V1审核放行。

## 项目格式
参考 `examples/v2/project.json`。顶层精确字段：schema_version=2, base（原V1项目字段）, author_id, reviewer_id, source_records, fact_meta, assessments, final_files, media_files, portfolio。所有路径相对 --evidence-root；不得访问客户未授权目录，不允许路径穿越。base中的human_checks布尔值是待签核陈述，不是独立证据；未确认置false或省略（明确失败可能阻断）。base.scores可省略；如提供只展示算术。

- `source_records`键为摘录路径；值为 project_id, owner, type（client_system/client_document/platform_export/third_party/self_report/synthetic）, original_path, original_sha256, review_status。attested_original仅供真实审查人确认后填写；self_report/synthetic即使签核也不计入支持评分。程序核对原件字节与hash；不能自行判定原件真实性。
- `fact_meta`键为base事实ID；project_id, line（UTF-8摘录从1计数）, kind（context/mechanism/metric/artifact/authorization/counterevidence）, metric（非metric填null）, locator（原件真实页/表/坐标）, causal_status（descriptive/not_applicable/unproven/attested_design）。metric对象要求 name/unit/scope/start/end/comparison/value/definition，单位与数值按真实口径。程序检查数值在原文出现，精确字面匹配不等于语义一致；审查人须核实单位、基期、符号及上下文。相同规范化字段键的不同数值冲突阻断；别名和统计口径跨源语义由人复核。
- `assessments`键为已选类别ID；`fit`中 subject/mechanism 各有 status、evidence_ids、reason；每个 `dimensions` 键为官方维度名称，值为 score（0–10）、support、counter、reason、anchor。未知维度省略或填 null；未签核维度为未知。anchor 分段见 workflows/jury.md。评分低于7必须有反证；支持与反证不能重叠；机制不能只用指标或背景；结果维度须有指标或作品证据。分数仍是人类判断的签核结果，不是程序对营销质量的客观测量。
- `final_files`为类别→{path,sha256}；文件UTF-8，逐行拼接对应base.drafts的text且每行末尾一个LF。额外一行或hash变动即阻断；不支持任意文档/复杂叙事自动认证。允许没有最终稿而进行内部价值诊断，交付状态仍REVIEW。
- `media_files`与base.media逐项对齐；本地{path,sha256}。ffprobe可用时探测真实媒体（非内容审核）；在线媒体保持REVIEW。JPG声明也需真实字节数。`portfolio`为年度记录列表，每项{project_id,category_id}；同项目跨类别按作品数计，须与base.company_case_count一致，实际同一作品别名消歧由人完成。

## 外部签核（只有真正独立的人可以执行）
操作者在模型控制范围外预先配置、核验并保管信任关系。私钥不得放在 Skill、项目目录、聊天、模型可读文件或插件中。**不得由AI自行生成/选择受信任密钥或代签。** 人工确认项目及原件后，可在独立环境创建规范化快照，由受信任审核人签名；将固定公钥与签名通过可信渠道交给审核执行方。下面仅是接口说明，不是授权 AI 代签。审查人需保证看过与snapshot一致的全部内容及引用的真实文件。

```sh
python3 scripts/roar.py snapshot project.json snapshot.json
# 审核人仅在独立可信环境签名：
openssl pkeyutl -sign -inkey /trusted/reviewer-private.pem -rawin -in snapshot.json -out review.sig
# 审核执行方使用事先独立配置的公钥，而非项目作者自选公钥：
python3 scripts/roar.py audit project.json --evidence-root evidence --public-key /trusted/reviewer-public.pem --signature review.sig
```

数字签名保护快照完整性，不证明现实世界真实性或审查人能力；本地CLI不能强制宿主密钥隔离、账户权限、信任根、撤销、独立审查人身份或防止不可信调用者替换公钥。真正企业使用需由宿主在受控环境调用、管理固定公钥与版本，冻结文件、限制读取路径，进行审查权限分离。签名不是官方批准，官方后台仍待核验。
