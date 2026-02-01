第一章：引言与架构概览 (Introduction & Architecture Overview)
================================================================================

项目愿景：通用数字名人模拟框架
------------------------------

本项目的目标是构建一个 **通用的数字名人模拟框架 (Universal Digital Celebrity Simulation Framework)**，使大型语言模型能够：

- 准确模拟特定人物的思维方式和价值观——不仅仅是“像谁说话”，而是“像谁思考”
- 在多种场景下保持人格一致性——无论是视频文稿、微博短评还是直播互动
- 动态吸收新知识而不改变核心人格——可以评论最新新闻，但立场始终如一
- 支持快速适配新的 KOL——提供标准化的数据采集和训练流程

.. important::

   **核心理念**：将“人格”分解为三个可独立管理的层次，实现“稳定性”与“适应性”的平衡。

角色一致性的挑战 (The Challenge of Character Consistency)
-----------------------------------------------------------

大型语言模型（LLM）在跨场景适应时，往往难以保持一致的角色特质。虽然它们在简短的单次交互中表现良好，但在面对以下情况时，“人格”往往会被稀释或发生漂移：

- **长期对话 (Long-term conversations)**：不仅是记忆丢失，更是性格的淡化。
- **跨平台适应性 (Cross-platform adaptability)**：例如，从严谨的播客讲稿切换到随意的推特吐槽时，很容易丢失核心立场。
- **信息冲突 (Conflicting information)**：当面对与角色设定相悖的新数据时，容易产生幻觉或直接崩人设。

本项目提出了一个 **多层级角色扮演框架 (Multi-Layer Role-Playing Framework)**，旨在将稳定的 **人格特质 (Stable Traits)** 与动态的 **情境知识 (Dynamic Knowledge)** 和 **行为风格 (Contextual Behavior)** 解耦。

三层框架理论 (The Three-Layer Framework)
----------------------------------------

受认知心理学和计算机科学原理的启发，我们将架构定义为三个不同的层级：

.. graphviz::

   digraph ThreeLayerArchitecture {
       rankdir=TB;
       node [shape=box, style="filled,rounded", fontname="Arial"];

       subgraph cluster_L1 {
           label = "Layer I: 特质层 (Trait Layer)";
           style = filled;
           color = lightblue;
           node [fillcolor=white];
           L1 [label="核心人格 (Core Personality)\n(Big Five, Values, Thinking Patterns)"];
       }

       subgraph cluster_L2 {
           label = "Layer II: 情境与知识层 (Contextual Layer)";
           style = filled;
           color = lightyellow;
           node [fillcolor=white];
           L2 [label="知识库 (Knowledge Base)\n(Biography, Beliefs, Experiences)"];
       }

       subgraph cluster_L3 {
           label = "Layer III: 风格与行为层 (Stylistic Layer)";
           style = filled;
           color = lightgreen;
           node [fillcolor=white];
           L3 [label="行为适应 (Behavior Adaptation)\n(Twitter, Blog, Podcast Style)"];
       }

       L1 -> L2 [label="立场约束 (Constraints)"];
       L2 -> L3 [label="内容注入 (Content Injection)"];
       L1 -> L3 [label="声音基调 (Voice Foundation)"];
   }

Layer I：核心特质层 (Trait Layer) — “怎么想”
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

- **定义 (Definition)**：角色的不可变核心。设定稳定的“大五人格”特质、核心价值观和基础思维模式。
- **工程实现 (Implementation)**：通过 **DPO (Direct Preference Optimization)** + **LoRA** 进行深度价值观对齐。
- **关键创新**：不只是学“怎么说话”，而是通过偏好学习告诉模型“什么是对的思考方式”。
- **作用**：确保角色无论讨论什么话题，其“思考方式”和“说话基调”都保持本色。

Layer II：情境与知识层 (Contextual Layer) — “知道什么”
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

- **定义 (Definition)**：角色的动态知识和记忆。包含角色的生平、世界知识、信仰和过往经历。
- **工程实现 (Implementation)**：**GraphRAG** + **Trait-Guided Reranker**。
- **关键创新**：特质引导的知识检索——用 Layer I 的价值观过滤检索结果，拒绝采纳与核心立场冲突的信息。
- **核心机制**：该层必须经过 Layer I 的过滤以解决知识冲突。

Layer III：风格与行为层 (Stylistic Layer) — “怎么说”
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

- **定义 (Definition)**：针对特定场景的行为适应。处理角色在不同媒介（微博 vs. 博客 vs. 播客）中的表达方式。
- **工程实现 (Implementation)**：SFT + Style Adapters（可切换风格适配器）。
- **关键创新**：模块化风格适配——同一内容可快速切换为不同平台的表达形式。
- **作用**：在不改变核心人格或知识库的前提下，调整内容的呈现形式。

框架特性对比
------------

.. list-table::
   :header-rows: 1

   * - 特性
     - 传统 Prompt Engineering
     - 本框架
   * - 人格稳定性
     - 易被上下文覆盖
     - 通过 DPO 深度锁定
   * - 长对话一致性
     - 逐渐漂移
     - 核心特质不变
   * - 知识冲突处理
     - 随机采信
     - 特质引导过滤
   * - 跨平台风格
     - 手动调整 prompt
     - 可切换适配器
   * - 新 KOL 适配
     - 重新设计 prompt
     - 标准化数据流程

通用性设计原则
--------------

本框架不绑定于特定 KOL，而是提供一套 **标准化的数据采集 → 标注 → 训练 → 部署流程**：

.. graphviz::

   digraph UniversalPipeline {
       rankdir=LR;
       node [shape=box, style="rounded,filled", fillcolor=white];

       subgraph cluster_data {
           label = "数据采集";
           D1 [label="Phase 0\n基础画像", fillcolor=lightblue];
           D2 [label="Phase 1\nDPO 数据", fillcolor=lightyellow];
           D3 [label="Phase 2\n知识图谱", fillcolor=lightgreen];
           D4 [label="Phase 3\n风格语料", fillcolor=lightpink];
       }

       subgraph cluster_train {
           label = "模型训练";
           T1 [label="Layer I\nDPO + LoRA"];
           T2 [label="Layer II\nReranker"];
           T3 [label="Layer III\nStyle Adapters"];
       }

       Deploy [label="部署上线", shape=ellipse];

       D1 -> D2 -> D3 -> D4;
       D2 -> T1;
       D3 -> T2;
       D4 -> T3;
       T1 -> Deploy;
       T2 -> Deploy;
       T3 -> Deploy;
   }

数据需求一览
------------

.. list-table::
   :header-rows: 1

   * - 数据类型
     - 用途
     - 规模
     - KOL 参与度
   * - 人格问卷
     - 量化人格特质
     - 1 套
     - 100%
   * - DPO 偏好数据
     - 价值观对齐
     - 1,000–3,000 对
     - ≥30%
   * - 结构化知识
     - 知识检索
     - 5,000+ 节点
     - ≥10%
   * - 风格平行语料
     - 风格迁移
     - 500–1,000 条/平台
     - ≥20%

研究路线图
----------

.. note::

   随后的章节将详细介绍：

   - **第二章**：技术实现细节
   - **第三章**：案例研究（以马督工为例）
   - **第四章**：评估方法
   - **第五章**：数据构建指南
   - **第六章**：标注规范 (SOW)
   - **第七章**：训练方法详解

适用场景
--------

.. list-table::
   :header-rows: 1

   * - 场景
     - 说明
   * - 虚拟主播/数字人
     - 保持一致人设的 AI 主播
   * - 品牌代言人
     - 符合品牌调性的 AI 客服
   * - 内容创作辅助
     - 帮助 KOL 批量生成多平台内容
   * - 教育/培训
     - 模拟历史人物或专家进行互动教学
   * - 游戏 NPC
     - 具有深度人格的游戏角色
