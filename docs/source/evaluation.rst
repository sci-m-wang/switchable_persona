第四章：评估与实验 (Evaluation & Experiments)
================================================================================

评估策略 (Evaluation Strategy)
------------------------------------------------------------

量化 LLM 的“人格”极具挑战性。本项目提出一套多维度的评估指标。

评估指标 (Metrics)
------------------------------------------------------------

1. 人格一致性 (P-Score: Personality Consistency)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

- **定义**：模型生成回复的 Embedding 与“金标准”回复（来自真实语料）之间的余弦相似度。
- **计算方式**：使用微调过的中文语义相似度模型（如 ``bge-large-zh``）进行计算。

2. 立场稳定性 (S-Score: Stance Stability)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

- **定义**：模型在不同格式下（长文 vs 短文）是否持有相同的底层观点？
- **方法**：跨模态一致性检验。

3. 风格区分度 (Style-Score)
~~~~~~~~~~~~~~~~~~~~~~~~~~~

- **定义**：分类器能否仅根据文本风格，正确识别出目标平台（微博 vs 播客）？

实验流程图 (Evaluation Flow)
------------------------------------------------------------

.. graphviz::

   digraph EvalFlow {
       rankdir=LR;
       node [shape=box, style="rounded,filled", fillcolor=white];

       Input [label="测试问题集\n(QA Dataset)", shape=note];
       Model [label="待测模型\n(Framework)", fillcolor=lightyellow];

       subgraph cluster_Output {
           label = "多场景生成";
           style=dashed;
           Out_Video [label="视频文稿\n(Video Script)"];
           Out_Weibo [label="微博评论\n(Weibo Post)"];
       }

       Judge [label="LLM 裁判\n(GPT-4 Judge)", shape=diamond, fillcolor=lightblue];
       Result [label="一致性报告\n(Consistency Report)"];

       Input -> Model;
       Model -> Out_Video;
       Model -> Out_Weibo;

       Out_Video -> Judge;
       Out_Weibo -> Judge;

       Judge -> Result [label="提取观点并比对\n(Compare Stance)"];
   }

实验结果 (Simulated Results)
------------------------------------------------------------

A/B 测试对比
~~~~~~~~~~~~

将本 三层框架 (Three-Layer Framework) 与 基线模型 (Naive Baseline)（仅使用简单的“扮演某人”提示词）进行对比：

.. list-table::
   :header-rows: 1

   * - 指标
     - 基线模型 (Baseline)
     - 本框架 (Ours)
     - 提升幅度
   * - P-Score (人格一致性)
     - 0.65
     - 0.88
     - +35%
   * - S-Score (立场稳定性)
     - 55%
     - 92%
     - +67%
   * - Style-Score (风格准确率)
     - 70%
     - 98%
     - +40%

**结论**：基线模型在微博场景下经常“崩人设”，变得过于礼貌或说教；本框架在长文与短评中均能维持更稳定的价值观与表达风格。
