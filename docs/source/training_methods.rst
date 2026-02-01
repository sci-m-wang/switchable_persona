第七章：训练方法详解 (Training Methods)
================================================================================

本章介绍三层架构的训练方法、配置建议与评估要点。

概述：三层训练策略
------------------

.. graphviz::

   digraph TrainingOverview {
       rankdir=TB;
       node [shape=box, style="filled,rounded", fontname="Arial"];

       subgraph cluster_methods {
           label = "训练方法对应关系";
           style = filled;
           color = lightgrey;

           L1 [label="Layer I: 特质层\nDPO + LoRA", fillcolor=lightblue];
           L2 [label="Layer II: 知识层\nGraphRAG + Reranker", fillcolor=lightyellow];
           L3 [label="Layer III: 风格层\nSFT + Style Adapters", fillcolor=lightgreen];
       }

       Base [label="基座模型\n(Qwen-2.5-72B / GLM-4)", fillcolor=white];

       Base -> L1 [label="价值观对齐"];
       L1 -> L2 [label="约束传递"];
       L2 -> L3 [label="内容注入"];
   }

一、Layer I：DPO 训练 (Direct Preference Optimization)
------------------------------------------------------------

为什么选择 DPO
~~~~~~~~~~~~~~

.. list-table::
   :header-rows: 1

   * - 方法
     - 原理
     - 优点
     - 缺点
   * - SFT
     - 监督学习正样本
     - 简单直接
     - 只学“怎么说”，不学“怎么不说”
   * - RLHF
     - 奖励模型 + PPO
     - 效果好
     - 复杂、训练不稳定
   * - DPO
     - 直接优化偏好
     - 简单有效
     - 依赖高质量偏好数据

训练流程（建议）
~~~~~~~~~~~~~~~~

- 可选：先 SFT 预热（KOL 独白/宣言式内容）
- DPO 训练：输入 ``prompt/chosen/rejected`` 对比数据
- 产物：Layer I LoRA 适配器（人格与价值观的“深层锁定”）

DPO 训练代码（示例）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from trl import DPOTrainer, DPOConfig
   from peft import LoraConfig

   peft_config = LoraConfig(
       r=64,
       lora_alpha=128,
       lora_dropout=0.05,
       target_modules=["q_proj","k_proj","v_proj","o_proj","gate_proj","up_proj","down_proj"],
       bias="none",
       task_type="CAUSAL_LM"
   )

   dpo_config = DPOConfig(
       beta=0.1,
       learning_rate=5e-6,
       per_device_train_batch_size=2,
       gradient_accumulation_steps=4,
       max_length=2048,
       max_prompt_length=512,
       num_train_epochs=3,
       warmup_ratio=0.1,
       logging_steps=10,
       save_steps=100,
       bf16=True,
   )

二、Layer II：Reranker 训练与 GraphRAG 集成
------------------------------------------------------------

Embedding 与 Reranker
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

- Embedding：用于粗召回（向量检索 Top-K）
- Reranker：用于二次排序，并引入 “特质一致性” 约束

Reranker 目标
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

对候选内容计算综合得分：

- 语义相关性 (relevance)
- 立场一致性 (trait_alignment)

最终：``score = relevance * trait_alignment``

三、Layer III：风格适配训练
------------------------------------------------------------

推荐方案
~~~~~~~~

- SFT + 可切换 Style Adapters（按平台分别训练）
- 推理时：基座 + Layer I + 指定风格适配器

风格适配器训练（示例）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   # 为每种风格训练独立的 LoRA 适配器
   style_configs = {
       "weibo": {"lora_r": 16, "epochs": 3, "max_length": 256},
       "video_script": {"lora_r": 32, "epochs": 2, "max_length": 2048},
       "zhihu": {"lora_r": 24, "epochs": 3, "max_length": 1024}
   }

四、持续学习与版本管理（摘要）
------------------------------------------------------------

- Layer I：季度/年度更新（仅在核心立场变化时触发）
- Layer II：周/月更新（新内容入库）
- Layer III：月度更新（新梗与平台语气变化）

训练完成标准（示例）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

- Layer I：偏好区分准确率 > 90%，人工评估立场一致
- Layer II：MRR@5 达标，立场过滤有效
- Layer III：风格分类准确率 > 95%，人工评估“像本人”
