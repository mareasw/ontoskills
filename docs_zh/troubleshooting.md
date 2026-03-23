---
title: 故障排除
description: 安装、商店访问、编译器设置和 OntoMCP 的常见问题
---

## `ontoskills install mcp` 失败

检查：

- Node.js 可用
- 当前版本的发布产物存在
- 你的机器可以下载 GitHub 发布资产

## 商店技能未出现在 OntoMCP 中

最常见的情况是技能已安装但未启用：

```bash
ontoskills enable mareasw/greeting/hello
```

如果已经启用，重建本地索引：

```bash
ontoskills rebuild-index
```

然后重启 MCP 进程。

## 编译器命令失败

先安装编译器：

```bash
ontoskills install core
```

然后初始化本体基础：

```bash
ontoskills init-core
```

## 导入的源仓库已编译，但技能仍然不可见

导入的源技能也需要启用：

```bash
ontoskills enable <qualified-id>
```

## 重置所有内容

要完全删除托管本地主目录：

```bash
ontoskills uninstall --all
```
