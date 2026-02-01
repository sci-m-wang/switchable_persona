第二章：技术实现 (Technical Implementation)
===========================================

本章介绍三层架构的工程实现方式，包括：训练与适配（Layer I）、检索与冲突消解（Layer II）、多平台风格输出（Layer III），以及端到端推理和部署建议。

系统架构总览
------------

.. graphviz::

   digraph SystemArchitecture {
       rankdir=TB;
       node [shape=box, style="filled,rounded", fontname="Arial"];
       compound=true;

       User [label="用户输入", shape=ellipse, fillcolor=lightblue];

       subgraph cluster_system {
           label = "数字名人模拟系统";
           style = filled;
           color = lightgrey;

           subgraph cluster_L1 {
               label = "Layer I: 特质层";
               style = filled;
               color = lightblue;
               DPO [label="DPO-LoRA\n价值观对齐", fillcolor=white];
               Trait [label="特质约束\nSystem Prompt", fillcolor=white];
           }

           subgraph cluster_L2 {
               label = "Layer II: 知识层";
               style = filled;
               color = lightyellow;
               RAG [label="GraphRAG\n知识检索", fillcolor=white];
               Rerank [label="Trait-Guided\nReranker", fillcolor=white];
           }

           subgraph cluster_L3 {
               label = "Layer III: 风格层";
               style = filled;
               color = lightgreen;
               Style [label="Style Adapter\n风格适配", fillcolor=white];
               Gen [label="LLM 生成", fillcolor=white];
           }
       }

       Output [label="多平台输出", shape=ellipse, fillcolor=lightpink];

       User -> Trait;
       User -> RAG;
       Trait -> DPO [style=dashed];
       DPO -> Rerank [label="立场约束"];
       RAG -> Rerank;
       Rerank -> Style [label="知识注入"];
       Trait -> Gen [label="人格基调"];
       Style -> Gen;
       Gen -> Output;
   }

Layer I：特质层 (Trait Layer - The Core)
------------------------------------------------------------

目标
~~~~

嵌入稳定的、能够抵抗长文本“漂移”的人格特质。核心是实现 **价值观对齐**：让模型学会“像谁思考”，而不仅仅是“像谁说话”。

技术选型：DPO + LoRA
~~~~~~~~~~~~~~~~~~~~

.. list-table::
   :header-rows: 1

   * - 方法
     - 稳定性
     - 抗干扰能力
     - 适用场景
   * - System Prompt
     - 低
     - 易被覆盖
     - 快速原型
   * - Few-Shot
     - 中
     - 有限
     - 简单任务
   * - SFT
     - 高
     - 只学表达
     - 风格模仿
   * - DPO + LoRA
     - 最高
     - 深度锁定
     - 价值观对齐

实现流程
^^^^^^^^

.. graphviz::

   digraph DPOImplementation {
       rankdir=LR;
       node [shape=box, style="rounded,filled", fillcolor=white];

       Base [label="基座模型\nQwen-2.5-72B", fillcolor=lightgrey];
       SFT [label="(可选) SFT 预热\n角色独白语料", fillcolor=lightyellow];
       DPO [label="DPO 训练\n偏好数据集", fillcolor=lightblue];
       LoRA [label="LoRA 适配器\nLayer I 权重", fillcolor=lightgreen];

       Base -> SFT -> DPO -> LoRA;
   }

LoRA 配置示例
^^^^^^^^^^^^^^^^^^^^

.. code-block:: python

   from peft import LoraConfig

   layer1_lora_config = LoraConfig(
       r=64,
       lora_alpha=128,
       lora_dropout=0.05,
       target_modules=[
           "q_proj", "k_proj", "v_proj", "o_proj",
           "gate_proj", "up_proj", "down_proj"
       ],
       bias="none",
       task_type="CAUSAL_LM"
   )

System Prompt 结构
^^^^^^^^^^^^^^^^^^

.. code-block:: json

   {
     "role": "system",
     "content": "你不是一个 AI 助手。你是 {KOL_NAME}。\n\n## 核心特质\n- 世界观: {worldview_description}\n- 方法论: {methodology_description}\n- 价值观: {values_list}\n\n## 思维方式\n当分析问题时，你会：\n1. 首先寻找数据和事实支撑\n2. 从结构性角度分析根本原因\n3. 拒绝空洞的情感共鸣和道德说教\n4. 给出明确的观点判断\n\n## 表达风格\n- 语气: {tone_description}\n- 禁忌: 不说 {forbidden_expressions}"
   }

Layer II：情境层 (Contextual Layer - The Mind)
----------------------------------------------

目标
~~~~

提供动态的、最新的、且 **符合角色视角** 的知识。

.. warning::

   标准 RAG 可能检索到与角色立场相悖的内容，从而导致“崩人设”。

核心方案：GraphRAG + Trait-Guided Reranker
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. graphviz::

   digraph TraitGuidedRAG {
       rankdir=TB;
       node [shape=box, style="rounded,filled", fillcolor=white];

       Query [label="用户查询", shape=ellipse, fillcolor=lightblue];

       subgraph cluster_retrieval {
           label = "Step 1: 混合检索";
           style = dashed;
           Vector [label="向量检索\n(语义相似)"];
           GraphSearch [label="图检索\n(关系遍历)"];
           Candidates [label="候选集\n(Top-K)"];
       }

       subgraph cluster_rerank {
           label = "Step 2: 特质引导重排序";
           style = dashed;
           color = red;
           TraitPrompt [label="Layer I 特质约束", fillcolor=lightpink];
           Reranker [label="Cross-Encoder\nReranker", fillcolor=lightyellow];
           Filter [label="立场过滤\n(拒绝冲突观点)"];
       }

       Context [label="最终上下文", fillcolor=lightgreen];

       Query -> Vector;
      Query -> GraphSearch;
       Vector -> Candidates;
      GraphSearch -> Candidates;
       Candidates -> Reranker;
       TraitPrompt -> Reranker;
       Reranker -> Filter;
       Filter -> Context;
   }

知识节点示例
~~~~~~~~~~~~

.. code-block:: json

   {
     "node_id": "stance_房地产税_001",
     "entity": "房地产税",
     "stance_type": "support",
     "stance_statement": "房地产税是替代土地财政的必然选择",
     "relations": [
       {
         "predicate": "is_solution_for",
         "object": "土地财政问题",
         "sentiment": "positive"
       }
     ],
     "arguments": [
       "地方政府对土地出让金的依赖不可持续"
     ],
     "source": {
       "type": "video_transcript",
       "title": "睡前消息 EP402",
       "timestamp": "2023-05-01"
     },
     "consistency_metadata": {
       "confidence": 0.95,
       "conflict_priority": "high"
     }
   }

Layer III：风格层 (Stylistic Layer - The Voice)
-----------------------------------------------

目标
~~~~

在不丢失人设的前提下，使输出格式适应特定媒介。

.. important::

   Layer III 只改变“怎么说”，不改变“说什么”。

风格定义（示例）
~~~~~~~~~~~~~~~~

.. code-block:: json

   {
     "style_id": "weibo_sarcasm",
     "name": "微博讽刺风",
     "specifications": {
       "length": {"min": 50, "max": 140, "unit": "characters"},
       "tone": ["sarcastic", "provocative", "direct"],
       "structure": "观点直击，不铺垫",
       "allowed_elements": ["emoji", "hashtag", "rhetorical_question"],
       "forbidden_elements": ["formal_citation", "hedging_language", "excessive_politeness"]
     }
   }

端到端推理流程
--------------

.. graphviz::

   digraph InferenceFlow {
       rankdir=TB;
       node [shape=box, style="rounded,filled", fillcolor=white];

       Input [label="用户输入\n+ 目标平台", shape=ellipse, fillcolor=lightblue];

       subgraph cluster_process {
           label = "推理流程";
           style = filled;
           color = lightgrey;

           P1 [label="1. 解析查询\n提取话题/意图", fillcolor=lightyellow];
           P2 [label="2. 知识检索\nGraphRAG + Rerank", fillcolor=lightyellow];
           P3 [label="3. 构建 Prompt\n组装各层组件", fillcolor=lightyellow];
           P4 [label="4. 加载适配器\nLayer I + Style", fillcolor=lightyellow];
           P5 [label="5. 生成回答\nLLM 推理", fillcolor=lightyellow];
           P6 [label="6. 后处理\n格式校验", fillcolor=lightyellow];
       }

       Output [label="风格化输出", shape=ellipse, fillcolor=lightgreen];

       Input -> P1 -> P2 -> P3 -> P4 -> P5 -> P6 -> Output;
   }

部署建议
--------

.. graphviz::

   digraph Deployment {
       rankdir=LR;
       node [shape=box, style="rounded,filled", fillcolor=white];

       Client [label="客户端", shape=ellipse];

       subgraph cluster_api {
           label = "API 层";
           Gateway [label="API Gateway\n负载均衡"];
       }

       subgraph cluster_inference {
           label = "推理服务";
           style = filled;
           color = lightyellow;
           vLLM [label="vLLM\n模型推理"];
           Adapter [label="适配器管理\n动态加载"];
       }

       subgraph cluster_data {
           label = "数据服务";
           style = filled;
           color = lightblue;
           VectorDB [label="Milvus\n向量检索"];
           GraphDB [label="Neo4j\n图数据库"];
           Cache [label="Redis\n缓存"];
       }

       Client -> Gateway;
       Gateway -> vLLM;
       vLLM -> Adapter;
       vLLM -> VectorDB;
       vLLM -> GraphDB;
       vLLM -> Cache;
   }
