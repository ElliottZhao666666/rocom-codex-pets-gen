# 资源目录规范

[返回 README](../README.md) · [颜色选择](../references/color-appearance.md) · [渲染计划](../references/render-plan.md)

这份文档定义 skill **接收什么样的目录**，供人和 AI 核对结构、字段与文件关系。它不介绍素材的获取或转换方法，也不提供可渲染的资源。

> **示例数据为随机构造，请勿直接使用。** 下文借用“菊花梨”作为显示名称，但示例编号、资源标识、尺寸、材质值、动作时长、预设编号、文件大小和 SHA-256 都是虚构数据，不代表该精灵的真实参数。`schema`、字段名、路径约束及明确列出的协议版本是格式要求，不是可随意修改的示例参数。真实制作必须保留自己资源中的原始数据，不能把示例值覆盖进去。

## 1. 一个目录对应什么

输入身份由 `(entity_id, form_asset, palette)` 共同确定：

- **一个实体**：菊花梨的目录不能包含其他精灵或进化实体。
- **一个模型形态**：“音速犬（本来的样子）”和“音速犬（看守麦田的样子）”分别保存，各自只含一个模型形态。
- **一个基础配色**：`normal` 为常规基础材质，`shiny` 为异色基础材质。二者即使共用模型或动作，也要分别保存；不能在同一目录里保留两套可切换基础材质。

目录名称只为方便阅读。程序以入口 JSON、运行清单与模型数据的一致性确定身份，不根据目录名猜测。

```text
PetResources/
├─ 菊花梨-常规/                        # 一个输入根目录
├─ 菊花梨-异色/                        # 另一个输入根目录
├─ 音速犬-本来的样子-常规/              # 独立模型形态
└─ 音速犬-看守麦田的样子-常规/          # 独立模型形态
```

每次向脚本传入其中一个根目录，不能传入整个 `PetResources/`。批量制作时逐个处理这些目录，不把它们合成一个输入。

炫彩、黑白、赛季和污染是附加效果选择，参见第 7 节。同一基础目录可以依次制作不同效果，但不同效果的**输出**也分别保存；异色与污染互斥。

## 2. 完整目录树

下例中的 `Demo_JuHuaLi_001` 是虚构资源标识。`tex/` 内文件名可不同，但引用必须准确。

```text
菊花梨-常规/
├─ entity.json                         # 必需：身份、入口、音频元数据
├─ manifest.toml                       # 必需：一个实体/形态的运行清单
├─ model.glb                           # 必需：用于采样的动画 GLB
├─ forms/
│  └─ Demo_JuHuaLi_001/                 # 必须恰好一个，与 asset 一致
│     ├─ model.glb                     # 必需：原几何、骨骼、UV 和材质槽
│     ├─ anim.rka                      # 必需：兼容渲染器的动画缓存
│     ├─ tex/
│     │  ├─ body.png                   # 当前基础配色
│     │  ├─ eyes.png                   # 原眼部图集
│     │  └─ body-mask.png              # 原材质/描边/炫彩数据贴图
│     ├─ voice/                        # 可选
│     │  ├─ Happy.wem                  # 原格式附件
│     │  └─ Happy.wav                  # 可播放副本
│     └─ sfx/                          # 可选，结构类似 voice/
├─ metadata/
│  ├─ materials.json                  # 必需，与 form.materials 相同
│  ├─ face_curves.json                # 必需，与 form.face 相同
│  ├─ morph_targets.json              # 必需，与 form.morph 相同
│  ├─ animations.json                 # 必需：动画清单
│  └─ source-files.json               # 必需：文件大小与 SHA-256
├─ effects.json                        # 可选扩展：使用颜色效果时必需
└─ effects/
   └─ glassy/
      ├─ glassy.json                  # 当前颜色/纹样/隐藏/赛季清单
      ├─ Tex_PetGlassy_007_D.png       # 当前适配器常规炫彩主纹理
      ├─ demo_shape.png               # 示例纹样纹理
      ├─ demo_season_main.png         # 示例赛季主纹理
      ├─ demo_season_star.png         # 示例赛季图案纹理
      ├─ demo_bw_main.png             # 示例黑白主纹理
      ├─ demo_bw_star.png             # 示例黑白图案纹理
      ├─ T_EMeng002.png               # 当前适配器污染效果所需
      └─ T_EMeng003.png               # 当前适配器污染效果所需
```

固定入口名为 `entity.json`、根 `model.glb`、`manifest.toml` 和上述五个 metadata 文件。`forms/<asset>/` 中的名字由当前实体决定。`voice/`、`sfx/` 与颜色效果可以不存在；但清单引用了的文件必须存在。

### 两份 model.glb 为什么不能互换

| 文件 | 用途 | 需要包含 |
|---|---|---|
| 根 `model.glb` | 枚举动作与采样骨骼 | glTF 2.0 二进制模型、骨骼、命名动画；可含当前配色的基础预览材质 |
| `forms/<asset>/model.glb` | 兼容原生渲染器使用 | 对应的原几何、骨骼、UV、材质槽，与 anim.rka 配套 |

两者的节点和骨骼索引必须能对应。根模型的基础 glTF 材质不等于完整的原生着色效果；表情图集、描边、炫彩等仍由运行清单及原渲染器处理。

## 3. entity.json：身份与入口

**以下为虚构示例，不是菊花梨实际数据。**

```json
{
  "schema": "rkpet2.entity.v1",
  "entity_id": 812345,
  "name": "菊花梨",
  "asset": "Demo_JuHuaLi_001",
  "stage": 1,
  "appearance": "normal",
  "appearance_label": "常规",
  "identity": {
    "entity_id": 812345,
    "form_asset": "Demo_JuHuaLi_001",
    "palette": "normal"
  },
  "model": "model.glb",
  "runtime_manifest": "manifest.toml",
  "animation_cache": "forms/Demo_JuHuaLi_001/anim.rka",
  "animation_count": 2,
  "audio": []
}
```

| 字段 | 类型/约束 | 对应关系 |
|---|---|---|
| `schema` | 当前为 `rkpet2.entity.v1` | 格式标识 |
| `entity_id` | 正整数 | 与 identity、species、form 的 ID 相同 |
| `name` | 非空字符串 | 显示名，不替代 ID |
| `asset` | 英文、数字、下划线或短横线 | 与唯一 forms 子目录及 form.asset 相同 |
| `stage` | 整数 | 与 form.stage 相同，不表示包含其他进化实体 |
| `appearance` | `normal` / `shiny` | 只表示已选基础配色 |
| `appearance_label` | 人类可读说明 | 不用于猜测颜色 |
| `identity` | 恰好描述当前 ID、资源标识和配色 | 三项分别与根字段一致 |
| `model` | `model.glb` | 动画采样入口 |
| `runtime_manifest` | `manifest.toml` | 原生运行入口 |
| `animation_cache` | `forms/<asset>/anim.rka` | 只属于当前形态 |
| `animation_count` | 动画数量 | 与根 GLB、clips、animations.json 对应 |
| `audio` | 元数据列表，可为空 | 引用的文件必须存在 |

如有音频，单项结构可为以下形式；数值仍为随机示例，不可使用：

```json
{
  "path": "forms/Demo_JuHuaLi_001/voice/Happy.wav",
  "channels": 1,
  "sample_rate": 48000,
  "frames": 86400,
  "seconds": 1.8
}
```

真实值应与音频文件一致。WAV 建议使用标准 PCM；WEM 是可保留的原格式附件，不是 Pets 上传载荷。无音频时 `audio: []` 即可。

## 4. manifest.toml：单一形态的运行清单

当前适配器要求 `schema = 1`、`runtime_abi = 22`。下面所有宠物相关数值及资源标识为虚构示例，不能作为实际渲染参数使用。

```toml
schema = 1
runtime_abi = 22

[species]
id = 812345
name = "菊花梨"
chain = [812345]

[[forms]]
id = 812345
name = "菊花梨"
stage = 1
asset = "Demo_JuHuaLi_001"
model = "forms/Demo_JuHuaLi_001/model.glb"
scale = 0.83
height_cm = 72.4
locomotion = "ground"

[forms.clips]
Idle = { clip = "Idle", ms = 2400, frames = 73 }
Happy2 = { clip = "Happy2", ms = 1800, frames = 55 }

[forms.face.Happy2]
eye = [[0, 1], [180, 2], [1700, 1]]
mouth = [[0, 1], [180, 3], [1700, 1]]

[forms.materials.DemoBody]
base_color = "forms/Demo_JuHuaLi_001/tex/body.png"
mask_alpha = false
outline = true
outline_width = 0.0037
glassy_id_tex = "forms/Demo_JuHuaLi_001/tex/body-mask.png"
glassy_star_tiling = 3.6
glassy_params = [1.22, 88.0, 1.35, 0.03, 0.08, 0.12, 0.31, 1.16, 0.42, 7.4, 0.92]
glassy_rim = [0.72, 0.88, 0.95, 1.3]

[forms.materials.DemoEyes]
base_color = "forms/Demo_JuHuaLi_001/tex/eyes.png"
mask_alpha = true
mask_clip = 0.34
face_track = "eye"
```

### 必须保持的关系

- `species.chain` 只包含当前 ID；`forms` 必须恰好一项，不能包含进化分支或另一种样子。
- `forms.asset` 与目录名一致，`forms.model` 指向该形态的原模型。
- `clips` 的键是逻辑动作名，内部 `clip` 对应根 GLB 的 animation.name。保留 Happy1、Happy2 等全部候选，不把它们改成同一个名字。
- `ms` 是正毫秒时长，`frames` 是原动作关键帧信息；需要与实际资源相符。
- `face` 的点为 `[毫秒, 图集格索引]`，时间严格升序且不为负；当前兼容格索引是 1..8。槽名和图集布局必须与原资源一致，不能按示例编表情。
- `materials` 的键与 GLB 材质名对应。示例中的 DemoBody / DemoEyes 也是虚构名称，不应重命名真实材质来迁就示例。
- 实际材质可能有更多贴图与参数，应完整保留。不得用这里的随机玻璃参数、边缘光或描边宽度覆盖原值。
- 不允许 `shiny_materials` 等第二套基础配色分支；异色目录已经在 materials 中选定异色材质。

## 5. metadata：与运行清单和模型互相核对

五个文件都必须存在；没有表情或形变时，也应保留相应的空对象。

| 文件 | 结构 | 必须满足 |
|---|---|---|
| `materials.json` | 对象 | 与 TOML 解析后的 `forms[0].materials` 完全相同 |
| `face_curves.json` | 对象 | 与 `forms[0].face` 完全相同；没有时 `{}` |
| `morph_targets.json` | 对象 | 与 `forms[0].morph` 完全相同；没有时 `{}` |
| `animations.json` | 对象列表 | 名称集合与根 GLB animations、clips 引用一致 |
| `source-files.json` | 非空对象列表 | 每项文件存在，大小与 SHA-256 匹配 |

不要把注释、省略号或字符串形式的 TOML 塞进 JSON。JSON 使用 UTF-8，字段类型保持一致。

### face_curves.json

对应上面虚构 TOML 的完整示例：

```json
{
  "Happy2": {
    "eye": [[0, 1], [180, 2], [1700, 1]],
    "mouth": [[0, 1], [180, 3], [1700, 1]]
  }
}
```

### animations.json

时长为随机示例；真实内容应对应实际 GLB：

```json
[
  {"name": "Idle", "seconds": 2.4},
  {"name": "Happy2", "seconds": 1.8}
]
```

### materials.json

这是与上面 TOML 对应的完整虚构对象。两处参数应一致，但它们都不是可用的真实参数：

```json
{
  "DemoBody": {
    "base_color": "forms/Demo_JuHuaLi_001/tex/body.png",
    "mask_alpha": false,
    "outline": true,
    "outline_width": 0.0037,
    "glassy_id_tex": "forms/Demo_JuHuaLi_001/tex/body-mask.png",
    "glassy_star_tiling": 3.6,
    "glassy_params": [1.22, 88.0, 1.35, 0.03, 0.08, 0.12, 0.31, 1.16, 0.42, 7.4, 0.92],
    "glassy_rim": [0.72, 0.88, 0.95, 1.3]
  },
  "DemoEyes": {
    "base_color": "forms/Demo_JuHuaLi_001/tex/eyes.png",
    "mask_alpha": true,
    "mask_clip": 0.34,
    "face_track": "eye"
  }
}
```

### source-files.json

下面只演示单项形状，大小和哈希为随机数值，请勿直接使用：

```json
[
  {
    "path": "forms/Demo_JuHuaLi_001/anim.rka",
    "size": 386421,
    "sha256": "a7d41f50b9e86c23f04a3d79d2c8b67564eabf139c2d50e87f36a1b9c04d7285"
  }
]
```

每项 `path` 相对于实体根目录，`size` 是字节整数，`sha256` 是 64 位十六进制摘要。所有登记项都会校验，不能使用占位哈希。清单通常不列自身，以免形成自引用摘要。

## 6. 路径、图集与动画规则

- 所有引用从实体根目录解析，使用 `/` 分隔，不从当前工作目录猜路径。
- 拒绝绝对路径、盘符、网络 URI、`..` 和指向目录外的链接。不要通过符号链接借用另一只精灵或另一配色。
- GLB 的外部 image / buffer URI 如存在，也必须位于同一根目录内。
- 表情槽、UV、图集索引、morph 与骨骼信息以真实资源为准。无 morph 时保留空定义，不伪造目标。
- `anim.rka` 必须是当前兼容渲染器可读且与该模型配套的缓存。这里仅约定文件关系，不定义其内部二进制编码。
- 输出目录必须在输入之外。多个颜色效果的成品不复用同一输出目录。

## 7. 可选效果扩展：炫彩、黑白、赛季与污染

常规或单纯异色不要求这一扩展。选择其他颜色类型时，需要同一实体目录内的 `effects.json` 和共享纹理。它们是效果数据，不是第二只精灵或另一模型形态。

### effects.json

固定格式标识是 `rocom.pet-effects.v1`。`glassy_directory` 是实体根目录内的相对路径，最后一级名称须为 `glassy`。`files` 必须覆盖 glassy.json 和本次选择所需的全部纹理；各项都要匹配实际大小及摘要。

以下是格式示例，只列两项以说明字段，不代表完整可渲染目录。数值和哈希都是随机数据，请勿直接使用：

```json
{
  "schema": "rocom.pet-effects.v1",
  "glassy_directory": "effects/glassy",
  "files": [
    {
      "path": "effects/glassy/glassy.json",
      "size": 6284,
      "sha256": "e17b04a6c2f998b35d60ea71b405c88d73e26f19a054b7d09c461e82f3a6b950"
    },
    {
      "path": "effects/glassy/demo_shape.png",
      "size": 47281,
      "sha256": "3bd187a06c9e24f8d67103be95a74c20f8d1396e0a52b7c4e91865fd302acb79"
    }
  ]
}
```

不应依赖电脑上其他位置恰好存在的公共素材目录；本次选择需要的文件要能在这个标准输入目录内验证。未选择的预设若缺少纹理，会在可选项中显示不可用；已登记文件缺失或被修改则会导致完整性检查失败。

### glassy.json

它是当前资源的预设清单，**不是 skill 内置的赛季列表**。以下完全为虚构的结构示例，“示例赛季”不是对任何游戏赛季的声明：

```json
{
  "colors": [
    {
      "id": 701,
      "name": "示例双色",
      "red_channel": [0.12, 0.66, 1.24],
      "green_channel": [1.48, 0.32, 0.08],
      "shine_strength": 8.6
    }
  ],
  "particles": [
    {
      "id": 903,
      "name": "示例纹样",
      "tex": "demo_shape",
      "star_stick_tiling": 2.07
    }
  ],
  "hidden": [
    {
      "id": 9401,
      "name": "示例赛季·流光",
      "season": true,
      "season_no": 12,
      "main_tex": "demo_season_main",
      "star_tex": "demo_season_star",
      "red_channel": [0.18, 0.31, 0.82, 1.0],
      "green_channel": [1.12, 0.73, 0.21, 1.0],
      "params": {"main_tex_flow_y": 0.07},
      "season_pets": []
    },
    {
      "id": 9700,
      "name": "黑白",
      "season": false,
      "main_tex": "demo_bw_main",
      "star_tex": "demo_bw_star",
      "red_channel": [0.58, 0.58, 0.58, 1.0],
      "green_channel": [0.02, 0.02, 0.02, 1.0]
    }
  ],
  "pollution": {
    "ui_color_1": 7634210,
    "ui_color_2": 12753942
  }
}
```

各列表内 ID 必须为唯一正整数，名称非空。`red_channel`、`green_channel` 保留原数值和原色空间含义，不能用界面色替代，也不能把大于 1 的值直接截断。

| 类型 | 数据依赖 | 选择规则 |
|---|---|---|
| 常规炫彩 | colors、particles、常规主纹理与所选纹样纹理 | 用户指定当前配色和纹样的 ID 或唯一精确名称 |
| 黑白 | hidden 中名为“黑白”的非赛季项及其纹理 | 保留独立类别，不假定固定数值 ID |
| 赛季 | hidden 中全部 `season: true` 项及各自纹理 | 每次动态读取，可按 preset_id、preset_name 或 season_no 选择 |
| 污染 | pollution 信息及当前适配器需要的两张 T_EMeng 纹理 | 独立类别，不能与 shiny 基础配色叠加 |

赛季数量、名称和编号上界不固定。`season_pets` 等关联信息应保留，不直接当作所有精灵使用通用赛季效果的白名单。未来新 shader 还需要兼容渲染器支持；不能因当前软件版本不支持，就渲染成另一种预设。

资源清单中的其他原始字段应保留，不为套用这个精简示例而删除。卡片图和界面图标可以保留，但不应代替三维材质所需纹理。

## 8. 给人和 AI 的核对顺序

1. 明确传入的就是一个实体根目录，而不是多个实体的父目录。
2. 核对 entity、identity、species、唯一 form 与目录名中的资源标识一致；检查基础 normal/shiny 是否匹配用户要求。
3. 核对两份 GLB、动画缓存、动作名称、表情、材质槽及所有引用文件。
4. 核对五份 metadata 与真实模型、运行清单及文件摘要一致。
5. 按颜色需求读取当前效果清单，验证所选预设及共享资源；只有偏好缺项时再询问用户。
6. 运行脚本校验；缺项时报告具体字段或路径，不根据这份文档的随机值补齐。

```powershell
python scripts/validate_input.py --input 'D:\PetResources\菊花梨-常规'
python scripts/color_appearance.py --input 'D:\PetResources\菊花梨-常规'
```

入口检查通过表示数据结构可读，不代表已经通过最终动画、清晰度、方向和 Pets 上传校验。之后的采样与制作请按 [SKILL.md](../SKILL.md) 和[渲染计划](../references/render-plan.md)执行。
