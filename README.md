# GitHub Code Research Agent

一个基于 LangChain 的智能体：输入一句话需求，自动检索 GitHub 相关项目、下载代码、通过 RAG 分析源码、输出结构化推荐方案。

## 架构

```
用户需求 → Query Planner → GitHub Retriever → 仓库下载 → LLM 初筛 → RAG 代码分析 → 综合推荐
```

- **Query Planner**: 自然语言 → 结构化搜索条件
- **GitHub Retriever**: REST API（默认）/ MCP Server 双后端
- **Screening Agent**: LLM 过滤不相关仓库
- **RAG Code Reader**: FAISS 向量索引 + 代码分块检索
- **Synthesizer**: 逐个分析 → 对比表格 → 最优方案

## 快速开始

```bash
pip install -r requirements.txt
cp .env.example .env
# 编辑 .env: 填写 DEEPSEEK_API_KEY

python agent.py "建筑立面风格识别的 Python 项目"
```

## 适用场景

- 技术选型调研
- 代码复用分析
- AI 产品经理的技术评估
