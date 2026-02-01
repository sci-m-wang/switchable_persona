第五章：数据构建指南 (Data Construction Guide)
================================================================================

本章介绍构建数字名人模拟系统所需的各类数据集结构、构建流程与质量标准。

概述：三层数据架构
------------------

.. graphviz::

   digraph DataArchitecture {
       rankdir=TB;
       node [shape=box, style="filled,rounded", fontname="Arial"];

       subgraph cluster_data {
           label = "数据层次与训练目标";
           style = filled;
           color = lightgrey;

           D1 [label="Layer I 数据\n偏好对齐数据集 (DPO)", fillcolor=lightblue];
           D2 [label="Layer II 数据\n结构化知识图谱 (GraphRAG)", fillcolor=lightyellow];
           D3 [label="Layer III 数据\n风格迁移语料 (SFT)", fillcolor=lightgreen];
       }

       subgraph cluster_output {
           label = "训练目标";
           style = dashed;
           T1 [label="价值观对齐\n(What to think)", fillcolor=white];
           T2 [label="知识检索\n(What to know)", fillcolor=white];
           T3 [label="风格表达\n(How to say)", fillcolor=white];
       }

       D1 -> T1;
       D2 -> T2;
       D3 -> T3;
   }

.. list-table::
   :header-rows: 1

   * - 数据类型
     - 训练方法
     - 目标
     - 规模建议
   * - DPO 偏好数据
     - Direct Preference Optimization
     - 锁定核心价值观
     - 1,000–3,000 对
   * - GraphRAG 知识
     - 向量检索 + 图检索
     - 动态知识注入
     - 5,000+ 观点节点
   * - SFT 风格数据
     - Supervised Fine-Tuning
     - 平台风格适配
     - 500–1,000 条/平台

一、Layer I：偏好对齐数据集 (DPO Dataset)
------------------------------------------------------------

1. 设计原理
~~~~~~~~~~~

DPO 的核心目标是 **价值观对齐**：告诉模型“什么是符合人设的思考方式”，而非仅仅“如何说话”。

.. important::

   DPO 的关键在于让模型学会“拒绝”——拒绝政治正确但缺乏立场的“端水式”输出。

2. 数据结构 (Schema)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: json

   {
     "id": "dpo_001",
     "prompt": "如何看待现在的年轻人不愿意进工厂，只想送外卖？",
     "chosen": "...符合人设的胜出回答...",
     "rejected": "...通用AI的和稀泥回答...",
     "system_prompt": "...角色设定与思维约束...",
     "metadata": {
       "domain": "社会民生",
       "topic": "劳动力市场",
       "difficulty": "medium",
       "kol_verified": true,
       "annotator_id": "ann_012",
       "timestamp": "2024-01-15"
     }
   }

3. 构建流程
~~~~~~~~~~~

.. graphviz::

   digraph DPOPipeline {
       rankdir=LR;
       node [shape=box, style="rounded,filled", fillcolor=white];

       P1 [label="Step 1\n问题设计", fillcolor=lightblue];
       P2 [label="Step 2\n负样本生成", fillcolor=lightyellow];
       P3 [label="Step 3\n正样本创作", fillcolor=lightgreen];
       P4 [label="Step 4\nKOL 审核", fillcolor=lightpink];
       P5 [label="Step 5\n质量检验", fillcolor=lightgrey];

       P1 -> P2 -> P3 -> P4 -> P5;
   }

- Step 1：诱导性问题设计（争议话题；易引发中立回答）
- Step 2：负样本生成（默认模式生成高情商端水答复）
- Step 3：正样本创作（KOL原创/改写确认/核心团队）
- Step 4：KOL 审核（标记 ``kol_verified=true``）
- Step 5：质量检验（长度、相似度、立场分类、去重）

二、Layer II：结构化知识图谱 (GraphRAG Dataset)
------------------------------------------------------------

1. 设计原理
~~~~~~~~~~~

传统文本切片容易丢失观点之间关系、时间线与冲突消解逻辑。GraphRAG 用结构化存储增强可控检索：

- 实体 (Entity)：房地产税、996、碳中和…
- 关系 (Relation)：支持/反对/归因于/导致…
- 属性 (Attributes)：时间、来源、置信度、冲突优先级…

2. 观点节点 (Stance Node)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: json

   {
     "node_id": "stance_001",
     "entity": "房地产税",
     "stance_type": "support",
     "stance_statement": "房地产税是替代土地财政的必然选择",
     "relations": [
       {"predicate": "is_solution_for", "object": "土地财政依赖", "sentiment": "positive"}
     ],
     "arguments": ["地方政府对土地出让金的依赖不可持续"],
     "source": {"type": "video_transcript", "title": "EP402", "timestamp": "2023-05-01"},
     "consistency_metadata": {"confidence": 0.95, "conflict_priority": "high"}
   }

3. 构建流程
~~~~~~~~~~~

.. graphviz::

   digraph GraphRAGPipeline {
       rankdir=TB;
       node [shape=box, style="rounded,filled", fillcolor=white];

       S1 [label="Step 1: 数据源收集\n视频文稿/文章/访谈", fillcolor=lightblue];
       S2 [label="Step 2: 文本清洗\n去噪/分段/OCR纠错", fillcolor=lightyellow];
       S3 [label="Step 3: 观点抽取\n核心观点句识别", fillcolor=lightgreen];
       S4 [label="Step 4: 实体链接\n话题/立场标注", fillcolor=lightpink];
       S5 [label="Step 5: 关系构建\n三元组生成", fillcolor=lightyellow];
       S6 [label="Step 6: 冲突检测\n时间线对齐", fillcolor=lightgrey];

       S1 -> S2 -> S3 -> S4 -> S5 -> S6;
   }

三、Layer III：风格迁移数据集 (Style Transfer Dataset)
------------------------------------------------------------

.. important::

   风格迁移不改变内容（What to say），只改变形式（How to say）。

1. SFT 格式
~~~~~~~~~~~

.. code-block:: json

   {
     "id": "style_001",
     "instruction": "请将以下内容改写为微博风格，要求简短有力，可讽刺，可用表情。",
     "input": "...",
     "output": "...",
     "metadata": {
       "source_style": "formal_analysis",
       "target_style": "weibo_sarcasm",
       "topic": "经济",
       "kol_verified": true
     }
   }

2. 平行语料格式
~~~~~~~~~~~~~~~

.. code-block:: json

   {
     "id": "parallel_001",
     "topic": "AI 与就业",
     "core_stance": "AI 将导致中产岗位流失，需要社会安全网",
     "variants": [
       {"style": "video_script", "text": "..."},
       {"style": "weibo_post", "text": "..."},
       {"style": "zhihu_answer", "text": "..."}
     ]
   }

四、数据质量控制体系
--------------------

.. list-table::
   :header-rows: 1

   * - 指标
     - 定义
     - 目标值
   * - KOL 审核率
     - 经 KOL 本人确认的数据占比
     - ≥30% (DPO)，≥10% (其他)
   * - 标注一致性
     - 双人标注 Kappa 系数
     - ≥0.8
   * - 格式合规率
     - 符合 Schema 的数据占比
     - 100%
   * - 去重率
     - 去除重复/高相似数据后的保留率
     - ≥90%

迭代更新机制
~~~~~~~~~~~~

.. graphviz::

   digraph UpdateCycle {
       rankdir=LR;
       node [shape=box, style="rounded,filled", fillcolor=white];

       New [label="新内容产生\n(KOL 发布)", fillcolor=lightblue];
       Extract [label="观点抽取", fillcolor=lightyellow];
       Verify [label="KOL 确认", fillcolor=lightgreen];
       Update [label="知识库更新", fillcolor=lightpink];

       New -> Extract -> Verify -> Update;
       Update -> New [style=dashed, label="周期性"];
   }

更新频率建议：

- Layer I (DPO)：季度更新，重大事件触发更新
- Layer II (GraphRAG)：周更新，跟踪新内容
- Layer III (Style)：月更新，适应新表达方式
