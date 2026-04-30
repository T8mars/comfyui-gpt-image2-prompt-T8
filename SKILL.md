# ComfyUI 自定义节点开发技能手册 — GPT Image 2 Prompt 项目全流程

> 基于 [awesome-gpt-image-2-prompts](https://github.com/EvoLinkAI/awesome-gpt-image-2-prompts) 仓库构建的 ComfyUI 自定义节点完整开发记录。
> 涵盖：架构设计、5 个节点实现、前端 JS 扩展、API 路由、数据构建脚本，以及实际踩坑与解决方案。

---

## 一、项目架构总览

### 1.1 目录结构

```
comfyui-gpt-image2-prompt/          ← NODE_DIR（节点根目录）
├── __init__.py                     ← ComfyUI 入口：注册节点 + API 路由 + WEB_DIRECTORY
├── pyproject.toml                  ← ComfyUI Registry 配置（name / PublisherId / Icon）
├── nodes.py                        ← 5 个节点类定义（Python 后端）
├── api_routes.py                   ← aiohttp 路由（图片服务 / 数据查询 / 刷新 API）
├── build_local_prompts.py          ← 数据构建脚本（解析 README → JSON + 复制图片）
├── web/js/gpt_image2_prompt.js     ← 前端 LiteGraph 扩展（预览图 / 分类筛选 / 刷新按钮）
├── data/
│   ├── local_prompts.json          ← 预设提示词数据（由 build 脚本生成）
│   ├── images/                     ← 本地图片副本（自包含）
│   │   ├── portrait_case1/output.jpg
│   │   ├── poster_case1/output.jpg
│   │   └── ...
│   ├── custom_prompts/
│   │   ├── custom_prompts.json     ← 用户自定义模板
│   │   └── custom_xxx.jpg          ← 用户保存的预览图
│   └── update_state.json           ← 上次更新时间戳
├── images/                         ← 源仓库图片目录（git clone 后存在）
└── README.md                       ← 节点使用文档
```

### 1.2 核心设计原则

| 原则 | 说明 |
|------|------|
| **完全自包含** | 节点运行时不依赖仓库根目录，所有资源在 `NODE_DIR/data/` 内 |
| **本地图片** | 禁止运行时在线加载图片，全部从本地文件系统提供 |
| **三层数据获取** | README 解析 → images/ 目录扫描 → git 历史恢复，确保覆盖最大化 |
| **安全覆写保护** | rebuild 结果为 0 或大幅减少时拒绝覆盖已有数据 |
| **热刷新** | 保存新模板后无需重启 ComfyUI 即可在 Selector/Preview 节点看到 |

### 1.3 五个节点功能

| 节点 | 功能 | 关键点 |
|------|------|--------|
| **Prompt Selector** 🎨 | 选择预设提示词 + 分类筛选 + 本地预览图 + 可编辑输出 | `OUTPUT_NODE = True`，返回 `{"ui": ..., "result": ...}` |
| **Prompt Preview** 🖼️ | 纯预览节点，显示提示词文本 + 图片 | 前端实时预览（combo callback + polling） |
| **Prompt Updater** 🔄 | 从 GitHub pull + 重新构建本地数据 | 调用 `build_local_prompts.py` 子进程 |
| **Custom Prompt Saver** 💾 | 保存用户自定义提示词 + 预览图 | 支持重名覆盖、IMAGE tensor → JPEG 转换 |
| **Execution Checker** ✅ | 健康检查（数据完整性 / 网络可达性） | 返回 `(STRING, BOOLEAN)` 双输出 |

---

## 二、关键实现细节

### 2.1 ComfyUI 节点注册（`__init__.py`）

```python
from .nodes import NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS

# 注册 API 路由
try:
    from . import api_routes
except Exception as e:
    print(f"Warning: API routes not loaded: {e}")

WEB_DIRECTORY = "./web/js"  # 前端 JS 自动加载
```

**要点**：
- `WEB_DIRECTORY` 指向 `web/js/` 目录，ComfyUI 自动加载其中的 `.js` 文件
- API 路由在 `import` 时通过装饰器自动注册到 `server.PromptServer.instance.routes`
- 用 try/except 包裹 API 导入，防止加载失败导致整个节点不可用

### 2.2 节点返回值格式（核心坑点）

ComfyUI 节点有两种返回格式：

```python
# ❌ 简单 tuple 返回 → 前端 onExecuted 收不到数据
return (value1, value2)

# ✅ ui + result 字典 → 前端 onExecuted 能收到 ui 字段
return {
    "ui": {"status": [msg], "image_path": [path]},  # → 前端 output.status[0]
    "result": (value1, value2),                       # → 下游节点输入
}
```

**踩坑**：前端 `onExecuted(output)` 只接收 `"ui"` 字段的内容，不接收 `"result"`。所有需要向前端传递数据的节点必须使用字典格式。需要设置 `OUTPUT_NODE = True` 才会触发 `onExecuted`。

### 2.3 图片路径体系

```
JSON 中存储：  "image_path": "images/portrait_case1/output.jpg"    ← 相对于 DATA_DIR
本地绝对路径：  DATA_DIR / "images/portrait_case1/output.jpg"
API 请求：     /gpt_image2_prompt/image?path=images/portrait_case1/output.jpg
前端 URL：     `${window.location.origin}/gpt_image2_prompt/image?path=${encodeURIComponent(imagePath)}`
```

**自定义模板图片**：
```
JSON 中存储：  "image_path": "custom_prompts/custom_xxx.jpg"       ← 同样相对于 DATA_DIR
本地绝对路径：  DATA_DIR / "custom_prompts/custom_xxx.jpg"
```

### 2.4 IMAGE tensor 保存为 JPEG

```python
# ComfyUI IMAGE 格式: [B, H, W, C] float32, 值域 0~1
img_array = preview_image[0].cpu().numpy()
img_array = (img_array * 255).clip(0, 255).astype(np.uint8)
img = Image.fromarray(img_array)
img.save(abs_path, "JPEG", quality=85)
```

### 2.5 combo widget 动态刷新

ComfyUI 的 combo widget 值在 `INPUT_TYPES()` 时加载一次后不会自动更新。热刷新方案：

```python
# 后端：/refresh_choices API 返回最新选项列表
@server.PromptServer.instance.routes.get("/gpt_image2_prompt/refresh_choices")
async def refresh_choices(request):
    choices = _get_prompt_choices()
    categories = _get_categories()
    return web.json_response({"choices": choices, "categories": categories, "grouped": grouped})
```

```javascript
// 前端：调用 API 更新 widget.options.values
async function refreshNodeChoices(node, comboWidget, categoryWidget) {
    const resp = await api.fetchApi(REFRESH_API);
    const data = await resp.json();
    comboWidget.options.values = data.choices;
    node.setDirtyCanvas(true, true);
}
```

---

## 三、前端 JS 扩展核心模式

### 3.1 基本结构

```javascript
import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

app.registerExtension({
    name: "GPTImage2Prompt",
    async beforeRegisterNodeDef(nodeType, nodeData, appInstance) {
        if (nodeData.name === "GPTImage2PromptSelector") {
            // 重写 onNodeCreated
            const orig = nodeType.prototype.onNodeCreated;
            nodeType.prototype.onNodeCreated = function () {
                orig?.apply(this, arguments);
                // 初始化逻辑...
            };

            // 重写 onExecuted
            const origExec = nodeType.prototype.onExecuted;
            nodeType.prototype.onExecuted = function (output) {
                origExec?.apply(this, arguments);
                // output 是节点返回的 "ui" 字段
            };
        }
    },
});
```

### 3.2 DOM Widget（图片预览）

ComfyUI 原生 widget 不支持显示图片，必须用 `addDOMWidget`：

```javascript
const container = document.createElement("div");
// ... 创建 img 元素、placeholder、label ...

const domWidget = node.addDOMWidget(
    "image_preview",    // widget 名称
    "custom",           // 类型
    container,          // DOM 元素
    {
        getValue() { return ""; },
        setValue() {},
        getMinHeight() { return 200; },
    }
);
// 关键：阻止序列化，否则保存工作流时报错
domWidget.serializeValue = async () => undefined;
```

### 3.3 Widget 拦截双保险（callback + polling）

ComfyUI 的 combo widget 切换事件不总是触发 callback（例如通过 API 或其他方式修改值时）。需要双重机制：

```javascript
// 方法1：Hook callback
const origCb = comboWidget.callback;
comboWidget.callback = function (value) {
    if (origCb) origCb.call(this, value);
    node._resolveAndPreview(value);
};

// 方法2：requestAnimationFrame 轮询（备份）
let lastValue = comboWidget.value;
const poll = () => {
    if (!node.graph) return; // 节点已移除则停止
    const current = comboWidget.value;
    if (current !== lastValue) {
        lastValue = current;
        node._resolveAndPreview(current);
    }
    requestAnimationFrame(poll);
};
requestAnimationFrame(poll);
```

### 3.4 等待 Widget 就绪

节点创建时 widget 可能还未初始化完成，需要轮询等待：

```javascript
let setupAttempts = 0;
const setupWidgets = async () => {
    setupAttempts++;
    const comboWidget = node.widgets?.find(w => w.name === "prompt_selection");
    if (!comboWidget) {
        if (setupAttempts < 20) setTimeout(setupWidgets, 200);
        return;
    }
    // Widget 就绪，执行初始化...
};
setTimeout(setupWidgets, 150);
```

### 3.5 图片加载防缓存

```javascript
// 必须先清空 src 再设置新 src，否则浏览器可能复用缓存
imgEl.src = "";
setTimeout(() => { imgEl.src = url; }, 10);
```

### 3.6 跨节点联动

Saver/Updater 执行后自动刷新所有 Selector/Preview 节点：

```javascript
if (this.graph) {
    const allNodes = this.graph._nodes || [];
    for (const n of allNodes) {
        if (n.type === "GPTImage2PromptSelector" || n.type === "GPTImage2PromptPreview") {
            const combo = n.widgets?.find(w => w.name === "prompt_selection");
            const cat = n.widgets?.find(w => w.name === "category");
            if (combo) refreshNodeChoices(n, combo, cat);
        }
    }
}
```

---

## 四、API 路由设计

### 4.1 路由注册

```python
import server
from aiohttp import web

@server.PromptServer.instance.routes.get("/gpt_image2_prompt/image")
async def serve_image(request):
    rel_path = request.query.get("path", "")
    # 安全检查 + 文件返回
    return web.FileResponse(abs_path, headers={"Cache-Control": "public, max-age=86400"})
```

### 4.2 路由清单

| 路由 | 方法 | 用途 |
|------|------|------|
| `/gpt_image2_prompt/image?path=xxx` | GET | 提供本地图片 |
| `/gpt_image2_prompt/resolve_selection?selection=xxx` | GET | 解析选项 → 返回提示词 + 图片路径 |
| `/gpt_image2_prompt/choices_by_category` | GET | 分类分组的选项列表 |
| `/gpt_image2_prompt/refresh_choices` | GET | 刷新选项（热刷新用） |
| `/gpt_image2_prompt/prompts` | GET | 所有提示词数据 |
| `/gpt_image2_prompt/categories` | GET | 分类及计数 |
| `/gpt_image2_prompt/prompt/{type}/{index}` | GET | 单条提示词详情 |
| `/gpt_image2_prompt/delete_custom/{index}` | POST | 删除自定义模板 |
| `/gpt_image2_prompt/status` | GET | 插件状态信息 |
| `/gpt_image2_prompt/debug_image?path=xxx` | GET | 调试图片路径解析 |

### 4.3 安全防护

```python
# 防止路径遍历攻击
if ".." in rel_path:
    return web.Response(status=403, text="Forbidden")

# 确保路径在节点目录内
abs_path = os.path.normpath(os.path.join(IMAGE_BASE, rel_path_clean))
node_norm = os.path.normpath(NODE_DIR)
if not abs_path.startswith(node_norm):
    return web.Response(status=403, text="Forbidden")
```

---

## 五、数据构建脚本 `build_local_prompts.py`

### 5.1 四阶段流水线

```
Stage 1: 解析 README 文件 → 提取 Case (标题/作者/提示词/图片路径)
          ↓ 本地没有 case README → 自动从 GitHub 下载
Stage 2: 扫描 images/ 目录 → 补充 README 未覆盖的图片文件夹
Stage 3: 从 git 历史恢复 → 为空提示词的 case 搜索历史版本中的文本
Stage 4: 复制图片 → 从源目录复制到 data/images/ 实现自包含
     ↓
  保存 local_prompts.json
```

### 5.2 README 解析正则

```python
# Case 标题行
re.match(r'###\s*Case\s+(\d+):', line)

# HTML 图片
re.search(r'src="\.?/?\s*(images/[^"]+)"', line)

# Markdown 图片
re.search(r'!\[[^\]]*\]\(\.?/?\s*(images/[^)]+)\)', line)

# 代码块提取
lines[j].strip() == "```"  # 开头
lines[k].strip() == "```"  # 结尾
```

### 5.3 安全覆写检查

```python
# 0 结果保护
if old_preset_count > 0 and new_preset_count == 0:
    print("[SAFETY] NOT overwriting!")
    return

# 50% 阈值保护
if old_preset_count > 50 and new_preset_count < old_preset_count * 0.5:
    if "--force" not in sys.argv:
        return
```

---

## 六、踩坑记录与解决方案

### 坑 1：`pathlib` 在 Windows 上不可靠

**现象**：`Path.exists()` / `Path.is_dir()` / `Path.is_file()` 在 Windows 某些路径下返回 `False`，即使目录确实存在。

**根因**：Windows 路径含有特殊字符、长路径或中文时，`pathlib` 的 stat 调用可能失败。

**解决**：所有路径变量统一使用 `str` 类型，路径检查统一用 `os.path.isdir()` / `os.path.isfile()` / `os.path.exists()`。

```python
# ❌ 不可靠
SRC_IMAGES_DIR = NODE_DIR / "images"
if SRC_IMAGES_DIR.is_dir(): ...

# ✅ 可靠
SRC_IMAGES_DIR = str(NODE_DIR / "images")
if os.path.isdir(SRC_IMAGES_DIR): ...
```

**教训**：在 ComfyUI 这种由用户安装在任意路径下的项目中，永远优先使用 `os.path` 而非 `pathlib`。

---

### 坑 2：节点返回 tuple 导致前端收不到数据

**现象**：前端 `onExecuted(output)` 中 `output` 为空或 undefined。

**根因**：节点 `FUNCTION` 方法返回纯 tuple 时，ComfyUI 只将其传给下游节点输入，不传给前端。只有返回 `{"ui": {...}, "result": (...)}` 字典时，`"ui"` 部分才会传到前端。

**解决**：所有需要前端交互的节点（`OUTPUT_NODE = True`）必须返回字典格式。

```python
# ❌
return (status_str,)

# ✅
return {
    "ui": {"status": [status_str]},
    "result": (status_str,),
}
```

**注意**：`"ui"` 中的值必须是列表 `[value]`，前端读取时用 `output.status[0]`。

---

### 坑 3：Preview 节点不显示图片

**现象**：Selector 节点图片正常，Preview 节点始终显示 "Select a prompt to see preview"。

**根因**：Preview 节点只在 `onExecuted`（执行工作流后）更新图片，缺少实时预览机制。用户切换 combo 选项时不会触发工作流执行。

**解决**：给 Preview 节点添加与 Selector 一致的前端实时预览：
1. Hook combo widget 的 `callback`
2. `requestAnimationFrame` 轮询值变化
3. 通过 `resolve_selection` API 获取图片路径并显示

---

### 坑 4：Custom 保存后图片无法查看

**现象**：Custom Prompt Saver 保存图片后，在 Selector 中选择该自定义模板看不到图片。

**根因**：
- 保存时用 `thumbnail` 字段存储**绝对路径**
- 但 `resolve_selection` API 只读 `image_path` 字段（为空）
- 两套路径格式不一致

**解决**：统一使用 `image_path` 存储**相对路径**（相对于 DATA_DIR），与 preset 格式一致：

```python
# ❌ 绝对路径，不可移植
"thumbnail": "F:\\...\\custom_xxx.jpg"

# ✅ 相对路径，格式统一
"image_path": "custom_prompts/custom_xxx.jpg"
```

同时添加兼容逻辑处理遗留的 `thumbnail` 格式。

---

### 坑 5：保存新模板后无法立即搜索到

**现象**：Custom Prompt Saver 保存成功后，Selector/Preview 节点的下拉列表没有新模板，需重启 ComfyUI。

**根因**：combo widget 的选项列表在 `INPUT_TYPES()` 调用时固定，之后不会自动刷新。

**解决**：
1. 后端添加 `/refresh_choices` API
2. 前端在 Selector/Preview 节点添加 🔄 刷新按钮
3. Saver/Updater 执行后自动遍历图中所有 Selector/Preview 节点触发刷新

---

### 坑 6：`SRC_IMAGES_DIR` 指向错误目录

**现象**：`build_local_prompts.py` 中 `REPO_ROOT / "images"` 在用户安装环境下指向 `custom_nodes/images/`（不存在），而不是 `comfyui-gpt-image2-prompt/images/`。

**根因**：
- 开发环境：`NODE_DIR` 是 repo 子目录，`REPO_ROOT` 是仓库根目录（有 images/）
- 用户环境：`NODE_DIR` 直接在 `custom_nodes/` 下，`REPO_ROOT` 就是 `custom_nodes/`

**解决**：优先检查 `NODE_DIR/images/` 是否存在，不存在再回退到 `REPO_ROOT/images/`：

```python
_SRC_IN_NODE = str(NODE_DIR / "images")
_SRC_IN_REPO = str(REPO_ROOT / "images")
if os.path.isdir(_SRC_IN_NODE):
    SRC_IMAGES_DIR = _SRC_IN_NODE
elif os.path.isdir(_SRC_IN_REPO):
    SRC_IMAGES_DIR = _SRC_IN_REPO
```

---

### 坑 7：README 来源错误导致 rebuild 清空数据

**现象**：执行 Updater 后，327 条预设全部消失，变成 0 条。

**根因**：
1. `NODE_DIR/README.md` 是节点的中文使用文档，不含 prompt case
2. 脚本把它当作源 README 解析 → 0 条结果
3. 没有安全保护 → 直接覆盖了原有 327 条数据

**解决**（三重保护）：
1. `_is_case_readme()` 检查 README 是否包含 `### Case` 标记，过滤掉非 case README
2. 本地找不到 case README 时自动从 GitHub 下载
3. 安全检查：rebuild 产出 0 条或少于原数据 50% 时拒绝覆盖

---

### 坑 8：仓库 README 中很多 prompt 已清空

**现象**：GitHub 仓库更新后，很多 case 的 prompt 代码块变成空的（```` ``` ```` 后紧跟 ```` ``` ````）。

**根因**：上游仓库把 prompt 文本从 README 移到了 JSON 文件中。

**解决**：
1. 解析时接受只有图片没有 prompt 的 case（`image_path and image_path not in existing`）
2. Stage 3 通过 git 历史恢复：搜索旧版 commit 中的 README 找回 prompt 文本
3. 未来可考虑直接从上游 JSON 文件获取 prompt

---

### 坑 9：图片加载失败但无明确提示

**现象**：预览区域只显示 "Loading..." 不消失，或显示空白。

**根因**：
- img.src 设置后没有正确触发 onload/onerror
- API 返回了 404 但前端没有处理

**解决**：
1. img 元素设置 `onload` 和 `onerror` 回调
2. 先清空 `src = ""`，用 `setTimeout` 延迟 10ms 后设置新 src
3. API 返回 `has_image: true/false` 明确告知前端图片是否存在
4. 不存在时显示 "Image not on disk: xxx" 提示

---

### 坑 10：分类筛选后选项列表为空

**现象**：切换分类后下拉列表变空白或只显示 "No prompts in this category"。

**根因**：
- `_choicesByCategory` 缓存在节点创建时加载一次
- 选项字符串格式变化后无法匹配
- API 返回的分类名与前端 widget 值不一致

**解决**：
1. 分类变化时优先用 API 返回的分组数据（`_choicesByCategory[category]`）
2. 回退方案：字符串匹配过滤
3. 空结果时填充占位项而非让列表为空

---

### 坑 11：重名保存覆盖逻辑

**现象**：用户保存同名模板时创建了重复项而非更新。

**解决**：按 `name` 字段查找是否已存在，存在则原地替换：

```python
existing_idx = None
for idx, c in enumerate(customs):
    if c.get("name", "") == effective_name:
        existing_idx = idx
        break

if existing_idx is not None:
    # 复用 ID、删除旧图片、原地替换
    customs[existing_idx] = entry
else:
    customs.append(entry)
```

---

### 坑 12：git pull 的 cwd 在用户环境下不正确

**现象**：Updater 执行 git pull 时报找不到 git 仓库。

**根因**：`cwd=REPO_ROOT` 在用户环境下指向 `custom_nodes/`（不是 git repo）。

**解决**：自动检测哪个目录有 `.git`：

```python
git_cwd = None
for candidate in [NODE_DIR, REPO_ROOT]:
    git_dir = os.path.join(candidate, ".git")
    if os.path.isdir(git_dir) or os.path.isfile(git_dir):
        git_cwd = candidate
        break
```

---

## 七、ComfyUI 自定义节点开发速查

### 7.1 必要文件

| 文件 | 必要性 | 作用 |
|------|--------|------|
| `__init__.py` | 必须 | 导出 `NODE_CLASS_MAPPINGS`、`NODE_DISPLAY_NAME_MAPPINGS` |
| `pyproject.toml` | 推荐 | ComfyUI Registry 元数据 |
| 节点 Python 文件 | 必须 | 定义节点类 |
| `web/js/*.js` | 可选 | 前端扩展（需要 `WEB_DIRECTORY` 指向） |

### 7.2 节点类模板

```python
class MyNode:
    CATEGORY = "My Category"
    FUNCTION = "my_method"           # 要调用的方法名
    RETURN_TYPES = ("STRING",)       # 输出类型元组
    RETURN_NAMES = ("output",)       # 输出名称元组
    OUTPUT_NODE = True               # 设为 True 才会触发前端 onExecuted

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "text": ("STRING", {"default": "", "multiline": True}),
                "mode": (["option1", "option2"], {"default": "option1"}),
                "enabled": ("BOOLEAN", {"default": True}),
            },
            "optional": {
                "image": ("IMAGE",),
            },
        }

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return float("nan")  # 始终重新执行

    def my_method(self, text, mode, enabled, image=None):
        return {"ui": {"info": ["done"]}, "result": (text,)}
```

### 7.3 前端 JS 关键 API

```javascript
import { app } from "../../scripts/app.js";   // LiteGraph 应用实例
import { api } from "../../scripts/api.js";   // ComfyUI API 客户端

// 注册扩展
app.registerExtension({
    name: "MyExtension",
    async beforeRegisterNodeDef(nodeType, nodeData, appInstance) { ... },
    async setup() { ... },
});

// HTTP 请求
const resp = await api.fetchApi("/my_api/endpoint");

// 添加 DOM widget
node.addDOMWidget("name", "custom", domElement, { getValue, setValue, getMinHeight });

// 刷新画布
node.setDirtyCanvas(true, true);
```

### 7.4 aiohttp 路由

```python
import server
from aiohttp import web

@server.PromptServer.instance.routes.get("/my_api/data")
async def get_data(request):
    param = request.query.get("key", "")
    return web.json_response({"result": param})

@server.PromptServer.instance.routes.post("/my_api/action/{id}")
async def do_action(request):
    item_id = request.match_info["id"]
    return web.json_response({"status": "ok"})

# 返回文件
return web.FileResponse(file_path, headers={"Content-Type": "image/jpeg"})
```

---

## 八、关键经验总结

1. **Windows 路径**：永远用 `os.path` 而非 `pathlib`，尤其在 ComfyUI 这种用户安装路径不可控的项目中
2. **节点返回值**：需要前端交互 → `{"ui": {...}, "result": (...)}`；只需要下游传值 → `(value,)`
3. **前端 widget 拦截**：callback + requestAnimationFrame 双保险，不要只依赖 callback
4. **图片加载**：先清空 src 再设置 + setTimeout 延迟 + onload/onerror 回调
5. **数据安全**：rebuild 脚本必须有安全检查，防止意外清空已有数据
6. **自包含设计**：节点运行时不应依赖 git 仓库结构，所有资源应复制到节点目录内
7. **热刷新**：combo widget 需要专门的 API + 前端刷新逻辑，值不会自动更新
8. **路径兼容**：同时支持开发环境（子目录）和用户安装环境（直接在 custom_nodes 下）
9. **README 解析**：不能假设 README 文件就是源数据 README，要做内容检查
10. **降级策略**：本地没有源文件 → 从 GitHub 下载 → git 历史恢复，多级降级确保可用性
