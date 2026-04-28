# 网站：[https://ai.t8star.cn](https://ai.t8star.cn/register?aff=cbff0534884)
# Online workflow overseas：
https://www.runninghub.ai/?inviteCode=rh-v1121
# 在线工作流国内版：
https://www.runninghub.cn/?inviteCode=rh-v1121
# 👋🏻 Welcome to Zhenzhen

<img src="https://github.com/T8mars/Comfyui-zhenzhen/blob/main/pic/1.png" width="30%" alt="My favorite girl">
My favorite girl Go YounJung

# 网站价格和宗旨：

本站开设初衷是提供平价的API给粉丝朋友玩最新的海外模型，并非盈利目的，秉承这一理念，我们的价格毛利不到10%，去掉正常缴税和人工开发维护，服务器成本后几乎没有利润，所以并非盈利性质网站，没有任何议价空间，也不支持用于商业目的的二次开发，仅服务于粉丝朋友，望理解，每个月发票数量有限，需要自己承担所有税费5-25%

# 网站使用及Api调用教程：

网站使用教程：https://ai.t8star.cn/about

API调用及开发教程：https://ai.t8star.cn/api-set

# ComfyUI GPT Image 2 Prompts 🎨

一个 ComfyUI 自定义节点包，提供 **300+ 精选 GPT Image 2 提示词**，支持本地图片预览、分类筛选、一键更新和自定义提示词管理。

> 基于 [awesome-gpt-image-2-prompts](https://github.com/EvoLinkAI/awesome-gpt-image-2-prompts) 提示词集合库构建。

---

## ✨ 功能特性

- **300+ 精选提示词** — 涵盖人像、海报、角色设计、UI 原型、对比实验等多个类别
- **本地图片预览** — 所有预览图本地存储，无需加载外部 URL，即时渲染
- **分类筛选** — 按类别过滤提示词（portrait / poster / character / ui / comparison / custom）
- **可编辑提示词** — 选中后自动填入可编辑文本框，自由修改后输出
- **自定义模板保存** — 保存你自己的提示词和预览图作为可复用模板
- **一键更新** — 从 GitHub 拉取最新提示词并重建本地数据库，无需重启
- **热刷新** — 保存新模板后点击刷新按钮即可加载，无需重启 ComfyUI
- **健康检查** — 内置诊断节点，验证数据完整性和网络连接状态
- **完全自包含** — 所有资源存储在插件目录内，可移植，零外部依赖

---

## 📦 包含节点

### 1. GPT Image 2 Prompt Selector 🎨

主节点，用于浏览和选择提示词。

| 参数 | 类型 | 说明 |
|------|------|------|
| `category` | 下拉选择 | 按类别筛选提示词（`all` / `portrait` / `poster` / `character` / `ui` / `comparison` / `custom`） |
| `prompt_selection` | 下拉选择 | 从筛选后的列表中选择提示词 |
| `edit_prompt` | 多行文本 | 自动填入选中的提示词文本，可编辑 — 编辑内容即为最终输出 |

| 输出 | 类型 | 说明 |
|------|------|------|
| `prompt` | STRING | 最终提示词文本（编辑后或原始） |

**界面功能：**
- 选择提示词后实时显示预览图
- 分类筛选动态更新提示词列表
- 🔄 **刷新按钮**：保存新模板后点击即可重新加载列表

---

### 2. GPT Image 2 Prompt Preview 🖼️

轻量预览节点，用于查看提示词的图片和文本。

| 参数 | 类型 | 说明 |
|------|------|------|
| `prompt_selection` | 下拉选择 | 选择要预览的提示词 |

| 输出 | 类型 | 说明 |
|------|------|------|
| `prompt` | STRING | 提示词文本 |
| `image_path` | STRING | 预览图的相对路径 |

**界面功能：**
- 完整图片预览，带标题叠加层
- 提示词文本显示面板
- 🔄 **刷新按钮**

---

### 3. GPT Image 2 Prompt Updater 🔄

从上游 GitHub 仓库更新提示词数据库。

| 参数 | 类型 | 说明 |
|------|------|------|
| `rebuild_from_readme` | 布尔值 | 重新解析所有 README 文件并重建 `local_prompts.json` |
| `git_pull_first` | 布尔值 | 重建前先执行 `git pull` 拉取最新代码 |

| 输出 | 类型 | 说明 |
|------|------|------|
| `status` | STRING | 详细更新报告（数量、变更、错误） |

**功能特点：**
- 三阶段构建：README 解析 → 图片目录扫描 → Git 历史恢复
- 增量图片复制（跳过未变更的文件）
- 显示更新前后对比（新增/移除的提示词数量）
- 更新完成后自动刷新画布中所有 Selector 和 Preview 节点

---

### 4. GPT Image 2 Custom Prompt Saver 💾

保存你自己的提示词，可附带预览图。

| 参数 | 类型 | 说明 |
|------|------|------|
| `prompt_text` | 多行文本 | 要保存的提示词文本 |
| `prompt_name` | 文本 | 模板的简短名称/标题 |
| `category` | 下拉选择 | 类别标签（`custom` / `portrait` / `poster` / `character` / `ui` / `comparison`） |
| `preview_image` | IMAGE（可选） | 作为缩略图保存的图片 |

| 输出 | 类型 | 说明 |
|------|------|------|
| `status` | STRING | 保存结果信息 |

**功能特点：**
- 重名检测：如果已存在同名模板，**自动覆盖**
- 预览图以 JPEG 格式保存在 `data/custom_prompts/` 目录
- 保存后自动刷新画布中所有 Selector 和 Preview 节点

---

### 5. GPT Image 2 Execution Checker ✅

诊断节点，用于验证插件运行环境。

| 参数 | 类型 | 说明 |
|------|------|------|
| `check_data_files` | 布尔值 | 检查本地数据文件完整性 |
| `check_network` | 布尔值 | 测试 GitHub 网络可达性 |
| `passthrough_string` | STRING（可选输入） | 透传任意字符串，用于流水线测试 |

| 输出 | 类型 | 说明 |
|------|------|------|
| `status_report` | STRING | 详细诊断报告 |
| `is_healthy` | BOOLEAN | 整体健康状态 |

**检查项目：**
- `local_prompts.json` 是否存在及提示词数量
- 图片目录完整性
- 自定义提示词文件
- 上次更新时间戳
- GitHub 网络连通性（可选）

---

## 🚀 安装方法

### 方式一：ComfyUI Manager 安装（推荐）

在 ComfyUI Manager 中搜索 **"GPT Image 2 Prompts"** 并安装。

### 方式二：手动安装

```bash
cd ComfyUI/custom_nodes/
git clone https://github.com/EvoLinkAI/awesome-gpt-image-2-prompts.git
cd awesome-gpt-image-2-prompts/comfyui-gpt-image2-prompt/
python build_local_prompts.py
```

然后重启 ComfyUI。

---

## 🔧 首次配置

安装完成后，运行数据构建脚本生成本地提示词数据库：

```bash
cd ComfyUI/custom_nodes/awesome-gpt-image-2-prompts/comfyui-gpt-image2-prompt/
python build_local_prompts.py
```

或者使用 **GPT Image 2 Prompt Updater** 节点，将 `rebuild_from_readme` 设为 `Yes` 执行。

该脚本会依次执行：
1. 解析所有 README 文件，提取提示词和元数据
2. 扫描 `images/` 目录获取预览图
3. 从 Git 提交历史中恢复额外的提示词
4. 将所有图片复制到自包含的 `data/images/` 目录
5. 生成 `data/local_prompts.json` 数据库文件

---

## 📁 目录结构

```
comfyui-gpt-image2-prompt/
├── __init__.py              # ComfyUI 入口文件
├── nodes.py                 # 5 个节点类定义
├── api_routes.py            # HTTP API 路由（图片服务、刷新等）
├── build_local_prompts.py   # 数据构建脚本（README 解析 + 图片复制）
├── pyproject.toml           # 包元数据
├── web/
│   └── js/
│       └── gpt_image2_prompt.js  # 前端扩展（预览、筛选、刷新）
└── data/                    # （自动生成）所有运行时数据
    ├── local_prompts.json   # 解析后的提示词数据库
    ├── images/              # 本地预览图（每个 case 一个文件夹）
    │   ├── portrait_case1/output.jpg
    │   ├── poster_case2/output.jpg
    │   └── ...
    └── custom_prompts/      # 用户自建模板
        ├── custom_prompts.json
        └── *.jpg            # 自定义预览图
```

---

## 📡 API 接口

插件在 ComfyUI 服务器上注册了以下 HTTP API 接口：

| 接口路径 | 方法 | 说明 |
|----------|------|------|
| `/gpt_image2_prompt/prompts` | GET | 获取所有提示词（预设 + 自定义） |
| `/gpt_image2_prompt/choices_by_category` | GET | 按分类分组的提示词选项 |
| `/gpt_image2_prompt/refresh_choices` | GET | 获取最新选项和分类（热刷新） |
| `/gpt_image2_prompt/resolve_selection` | GET | 解析选择字符串为完整提示词数据 |
| `/gpt_image2_prompt/image?path=...` | GET | 提供本地预览图文件服务 |
| `/gpt_image2_prompt/categories` | GET | 分类列表及数量统计 |
| `/gpt_image2_prompt/status` | GET | 插件状态信息 |
| `/gpt_image2_prompt/delete_custom/{index}` | POST | 删除指定自定义提示词 |
| `/gpt_image2_prompt/debug_image?path=...` | GET | 调试图片路径解析 |

---

## 📝 提示词分类

| 分类 | 说明 | 示例 |
|------|------|------|
| `portrait` | 人像与肖像生成 | 电影感人像、工作室布光、艺术风格 |
| `poster` | 海报与平面设计 | 电影海报、活动横幅、宣传物料 |
| `character` | 角色设计与插画 | 游戏角色、动漫风格、概念设计 |
| `ui` | UI/UX 原型生成 | App 界面、仪表盘、网页布局 |
| `comparison` | 对比与实验 | 前后对比、风格比较、参数测试 |
| `custom` | 用户自建模板 | 你保存的自定义提示词 |

---

## 🔄 更新提示词

获取上游仓库的最新提示词：

1. 添加 **GPT Image 2 Prompt Updater** 节点
2. 将 `git_pull_first` 设为 `Yes` 拉取最新代码
3. 将 `rebuild_from_readme` 设为 `Yes` 重建数据库
4. 执行该节点

工作流中所有 Selector 和 Preview 节点会自动刷新。

---

## 🙏 致谢

- 提示词集合：[awesome-gpt-image-2-prompts](https://github.com/EvoLinkAI/awesome-gpt-image-2-prompts) by EvoLinkAI
- 构建于 [ComfyUI](https://github.com/comfyanonymous/ComfyUI)
