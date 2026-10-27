# 渲染计划

`scripts/render_source.py` 读取标准目录和一个私有 JSON 计划，输出原生透明帧；它不会上传宠物，也不会替代 Pets 的最终精灵表组装和质量检查。

## 兼容的离屏接口

适配器通过参数接收用户提供的渲染器路径，不内置安装路径。当前接口形态为：

```text
<renderer> --render <working-directory> --form <asset> --clips <clip-list>
           --at <0..1> --size <pixels> --yaw <degrees> --time <seconds>
           --no-fade --out <transparent.png>
```

输出是按 clips 顺序横向排列的原生 RGBA PNG，每个方格边长为 size。启用颜色效果时另传 `--packs-dir <glassy目录的父目录>` 与 `--mutation <已解析的效果>`。同一姿势组在各材质相位中保持完整，渲染输出再按对应索引取格。

## 采样计划

```powershell
python scripts/render_source.py --input "D:\PrivateAssets\example-normal" --output "D:\PetRuns\example" --renderer "D:\Tools\compatible-renderer.exe" --plan "D:\PetRuns\plan.json"
```

计划示例（示例节点号必须按实际模型检查，不可照搬）：

```json
{
  "tag": "candidate-idle-and-right",
  "size": 1024,
  "camera_yaw": 0,
  "appearance": {"color_type": "常规"},
  "rig": {
    "root_node": 1,
    "gaze_nodes": [
      {"node": 10, "weight": 0.35},
      {"node": 11, "weight": 0.65}
    ]
  },
  "frames": [
    {"clip": "Idle", "seconds": 0.0},
    {"clip": "Happy2", "seconds": 0.4, "root_yaw": 90},
    {"clip": "Idle", "seconds": 0.0, "gaze": 90},
    {
      "clip": "Idle",
      "seconds": 0.7,
      "face": {
        "eye": [[0, 5], [1000, 5]],
        "mouth": [[0, 1], [1000, 1]]
      }
    }
  ]
}
```

- `tag` 仅可包含英文、数字、下划线和短横线，用于隔离工作副本。
- `appearance` 是已按用户意愿确定的颜色选择；必须包含 `color_type`。九类与动态赛季选择字段见 [颜色选择](color-appearance.md)。缺少类型或预设细项时脚本返回需要补充的 questions，而不是默认一种效果。
- `size` 为每个原生方形渲染帧的边长，范围 192..2048，推荐 768 或 1024。最终 Pets 格子大小由现行协议决定。
- `clip` 为 manifest.clips 的逻辑动作名，采样对应的 GLB animation。`seconds` 必须在该动作时长内。
- `root_yaw` 是绕模型根节点的朝向调整，单位为度；0、+90、-90 可作为前、右、左方向的起点，但必须看实际渲染确认。
- `lock_root_horizontal: true` 可用于 manifest 明确声明 `root_motion_cm > 0` 的移动循环。它将根节点 x/z 平移固定在该动作起点，同时保留 y、骨骼步态及上下起伏。实际校正前后位置会写入日志。仅移除有来源依据的前移量，不按每帧包围盒重新居中，也不用于取消跳跃。
- `gaze` 以画面方向表示：0 上、90 右、180 下、270 左。适配器只在显式指定的原骨骼上分配转角，不是整个角色的转盘。`rig.gaze_yaw_degrees` 和 `rig.gaze_pitch_degrees` 分别控制水平及俯仰幅度，默认 32°、29°，范围大于 0° 且不超过 45°。应按角色结构选择清楚且不过度拉伸头颈的幅度。不同骨骼坐标系必须用四个基准方向实测确认。不匹配时调整适配器及计划，不能自动判为通过。
- `gaze_nodes` 的 node 是 GLB 节点索引，weight 是转角分配权重；应合计为 1。空列表允许普通动作渲染，但拒绝注视请求。
- `face` 可选；默认按原动作时间采样原始阶梯曲线。显式指定时也只能引用原有槽和图集格索引，不能绘制替代贴图。静态值写成起止两点是为了适配需要结束点的渲染器。
- `shader_time` 为独立的、有限且非负的材质时间（秒）。启用颜色效果时每帧必填；无效果时省略按 0 处理，也可用于其他原生动态材质。它不改变 `seconds` 所选骨骼姿势。帧计划不会自动猜测循环周期，应按实际状态时长和相位检查结果填写。
- 同一计划最多 128 帧。各材质时间批次都渲染完整同一姿势组，再提取对应格，以便构图依据一致。很大的位移可能让整批角色过小，先选择合适原动作区段。

原骨骼固定、材质时间变化的最小计划示例（配色与纹样 ID 必须在该输入的当前清单中存在）：

```json
{
  "tag": "glassy-phase-probe",
  "size": 1024,
  "appearance": {"color_type": "常规炫彩", "color_id": 33, "particle_id": 3},
  "frames": [
    {"clip": "Idle", "seconds": 0, "shader_time": 0},
    {"clip": "Idle", "seconds": 0, "shader_time": 0.5}
  ]
}
```

静态方向基准可用同一材质相位；完整动作行则需明确推进 shader_time，并检查最终循环。赛季渲染用当前清单的 preset_id / preset_name / season_no 选择，不把上例 ID 当默认。

输出包括 `native-frames/<tag>/NNN.png`、离屏原图及实际命令日志、`render-provenance.json`。这些都必须放在 skill 仓库之外。

后处理时对所有标准状态使用一个固定裁切矩形、比例与偏移，用预乘 alpha 缩小到最终帧。不可用“每帧各自填满格子”的方式消除大小变化和跳跃位移。保存这个变换及每帧来源，方便复核。

用于标准状态最终制作的计划还应为每帧添加 `state`（例如 `idle`）和该状态内从零连续编号的 `frame`。同一计划包含全部标准状态，不能对每行分别计算缩放。然后运行：

```powershell
python scripts/normalize_frames.py --frames-dir "D:\PetRuns\example\native-frames\candidate-idle-and-right" --plan "D:\PetRuns\plan.json" --output "D:\PetRuns\example\normalized"
```

默认输出 192×208 格子、最大内容视区 174×186，并保存共同变换记录。这一步产生的 `frames/` 与 `decoded/` 交给当前 Pets skill 的官方检查与组装脚本。注视方向作为独立的连贯族处理，再由官方 v2 组装器对齐到已审核的待机参考。

动画 GLB 的采样支持 LINEAR、STEP、TRS 和一致宽度的 morph 权重。遇到 cubic、复杂的不同 morph 组或其他不支持情况会停止；不可假装已还原。
