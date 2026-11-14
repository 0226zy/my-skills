# my-skills

个人 Agent 技能库。每个技能是一个目录 + `SKILL.md`（YAML frontmatter + 指令正文），可安装到 DeepSeek Harness 的本地技能根，也可被其他支持 SKILL.md 的 Agent 直接读取。

## 技能列表

| 技能 | 一句话 | 触发示例 |
|---|---|---|
| [`learning-path-designer`](skills/learning-path-designer/SKILL.md) | 把"要一份书单"改造成一套可执行的学习系统，并输出排版好的 PDF 手册：科普说明 → 知识大纲 → 概念图 → 可核验资源 → 阶段计划 + 检索题 + 间隔复习 | `学习下面的领域：` + `科普领域：xx` |

## 安装

```bash
git clone https://github.com/0226zy/my-skills.git
cd my-skills
./install.sh
```

默认安装到 `$DSH_HOME/skills`（未设置时用 `~/.dsh/skills`），这是 DeepSeek Harness 的用户级技能根：

- 所有会话可见，不绑定具体工作目录
- DSH 会监听该目录，增删改技能后目录自动刷新，无需重启

```bash
./install.sh list                # 列出本仓库的技能
./install.sh check               # 校验已安装副本与仓库一致
./install.sh uninstall <name>    # 移除某个技能
```

安装前会校验 frontmatter：`name` 必须与目录名一致且为 kebab-case，`description` 必须非空且不超过 500 字符（DSH 会按该上限截断，超出会让触发词失效）。

## 目录结构

```text
my-skills/
├── install.sh
├── README.md
└── skills/
    └── learning-path-designer/
        ├── SKILL.md
        └── scripts/
            └── render.py
```

之所以放在 `skills/` 子目录而不是仓库根：DSH 只扫描技能根的一层目录（`<root>/<name>/SKILL.md`），仓库根同时放 `README.md` 会被误判成技能并产生告警。`install.sh` 负责把 `skills/*` 整目录铺平到技能根。

## PDF 输出

`learning-path-designer` 的默认交付是 **PDF + Markdown 源文件**。渲染链路是零依赖的：

```text
Markdown → 自带样式表的 HTML → 无头 Chrome --print-to-pdf → A4 PDF
```

```bash
python3 skills/learning-path-designer/scripts/render.py plan.md plan.pdf
```

特性：

- A4 版面、封面、目录（带页码）、页眉页脚（`当前页 / 总页数`）
- 每个 `##` 章节自动另起一页；页数 ≥ 3 才会通过自检
- 只用标准 Markdown 子集（标题 / 表格 / 列表 / 引用框 / 代码块），不依赖 pandoc、wkhtmltopdf、LaTeX
- 中文字体走系统 `PingFang SC`，无需嵌入字体文件
- 依赖：macOS / Linux 上装有 Chrome 或 Chromium（可用 `CHROME_PATH` 指定）

## 设计取向

`learning-path-designer` 的取舍是反直觉的：用户要书单，但它不先给书单。

1. **先诊断再推荐** —— 没有起点就没有路径。默认零问启动（声明假设直接跑），用户要定制时才问五个问题。
2. **给图不给清单** —— 知识大纲是树（由哪几块组成），概念图是网（谁依赖谁），两者不互相复制。
3. **每个输入配一个输出** —— 没有检索题或产出任务的资源条目，视为未完成；答案统一放附录，正文不泄漏。
4. **不编造** —— 书名、作者、播客期号是模型幻觉高发区，凡是无法核验的一律标"待核实"。

## License

MIT
