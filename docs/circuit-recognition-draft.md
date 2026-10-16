# 电路识别草稿（EW-031）

用户确认的交互是：识别缺数字时停在题面，补填后提交现有求解接口。草稿是识别证据，不是已校验的领域题面；不能直接进入求解器或写入题号目录。

## 结果兼容

`CircuitRecognitionResult` 新增可选 `draft: CircuitDraft | null`，缺省为 null。

| outcome | puzzle / 顶层 display_palette | draft |
| --- | --- | --- |
| recognized | 保持现有完整题面、对应色板与 notation 要求 | null |
| incomplete | puzzle=null，display_palette=[] | 可靠的可编辑草稿，或 null |
| no_board / already_completed / timeout / invalid_image / failed | 保持既有约束 | null |

新增字段不改变识别成功门槛。完整题面仍须通过 `CircuitPuzzle`、受限求解与独立校验，才会得到 recognized。无草稿时前端继续现有换图/失败提示；旧客户端可以忽略新增字段。

## v1 草稿字段

- `rule_version`: `line-count-v1`。
- `rows` / `columns`: 严格整数，2～10。
- `channels`: 1～4项，按 index=0…n-1 排列。每项的 `row_targets` / `column_targets` 长度匹配棋盘；值是非负严格整数或 null，已知值不超过对应行/列长度。
- `cells`: 长度 rows×columns，行优先。`kind` 只允许 empty、blocked、fixed；fixed 必须给出有效 channel，其他格的 channel 必须是 null。**v1 不产生 kind=null 或 fixed channel=null。**
- `pieces`: 1～32个完整库存拼块，复用 `CircuitPiece` 的严格坐标、归一化和连通性校验，通道必须有效。没有 `pieces=null`，也不允许前端编辑形状或所属通道。
- `palette`: 与通道完整对应、有序的 `CircuitDisplayColor`；只用于显示，原色相语义保持。incomplete 的色板仅放在草稿内。
- `missing`: 非空、不重复的机器可读枚举列表，取值如下。它仅决定提示文案；前端校验应检查实际题面字段，不依赖此列表认定可求解。

| 原因 | 含义 |
| --- | --- |
| row_targets | 至少一个行目标为 null |
| column_targets | 至少一个列目标为 null |
| rejected | 数字已读到，但一致性或领域模型未接受 |
| unsatisfiable | 原求解器对完整识别题面返回无解 |
| solver_limit | 原求解器达到时间/工作量限制 |
| validation_failed | 原独立校验未通过 |

row_targets / column_targets 标记与实际 null 必须对应。草稿允许目标总数、库存面积或固定格约束矛盾，以便用户修正数字/障碍/固定格；严格求解模型的所有领域校验均保留。

## 安全边界与读取

棋盘定位、通道、格子分类及**完整库存**必须先通过现有保守视觉阶段，而且不能已有玩家放置的拼块。定位/分类/库存不可靠、中间态、空库存无完成证据等仍返回无草稿；完成态仍走已有 already_completed 规则。不提供新增通道、空白建题、编辑库存形状、截图坐标或答案叠加。

数字/罗马数字只运行原有一批约束 OCR，解析失败、低置信或超出行长的**已有字形**为 null；确定布局内没有物理符号的项仍按已有规则为 0。短条保留现有严格解码作为成功路径；失败时仅重读已提取的内存短条计数，不重复图像定位或 OCR。重复计数、超容量或不稳定偏移的对应数字为 null，无法安全分配数字时全部目标为 null，不猜值。

已读全但一致性失败的草稿不会自动求解。原领域拒绝、无解、超限或独立校验失败会附上原因；不改为 recognized，不导出内部 solution。目录仍只可查询已有候选，草稿不记录为 observation，不参与完整题面对账。

## 前端提交和示例

前端可编辑行列数字、障碍格和固定格。所有目标补齐且必要结构完整后，组装现有 `CircuitPuzzle` 提交 `/api/v1/puzzles/circuit/solve`；不要把 draft 信封或 missing/palette/cells 原样当求解请求，原 422 错误处理保持。

两份小型 JSON 供 mock 使用：

- [缺数字](../api/tests/fixtures/circuit-draft-missing.json)
- [数字完整但总数矛盾](../api/tests/fixtures/circuit-draft-rejected.json)

两份均为**人工合成的 2×2 示例**，不含原图、真实题号或用户资料，不代表真实 OCR 结果。真实私有样本验证与结果另存本机忽略证据目录，不进入 Git。
