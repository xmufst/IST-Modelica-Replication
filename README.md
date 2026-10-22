# IST Modelica反馈修复策略冻结复现包

版本：v1.0.0。冻结日期：2026-10-22。版本元数据以VERSION.json为准，发布可用性以GitHub实际Release页面为准。

本包支撑中文IST期刊稿的RQ1（策略效果与实际资源）和RQ2（显式fixed判据的事后敏感性与局部初始化审计）。包含20任务、每任务3份共享起点、21项历史条件与6项新增条件，共1620条条件记录；它们不是1620个独立建模问题。

完整数据位于本仓库v1.0.0 Release的复现包附件；网页源码视图只提供说明、索引与复核入口。请先下载完整附件并解压，不要在缺少数据的网页源码下载包中直接运行评分。

## 最短复核路径

需要Python 3.12及environment/requirements-offline.txt中的科学计算依赖，不需要LLM密钥、Agent框架、OpenModelica、Modelica库或联网推理。

在解压后的包根目录运行：

```text
python -m pip install -r environment/requirements-offline.txt
python reproduction/reproduce.py verify
python reproduction/reproduce.py score
python reproduction/reproduce.py sensitivity
python reproduction/reproduce.py statistics
python reproduction/reproduce.py audit
python reproduction/reproduce.py resources
```

也可运行 `python reproduction/reproduce.py all`。主要耗时来自解压和重新读取保存的MAT轨迹，不生成新轨迹。结果写入reproduced/，原始文件不覆盖。MAT无损压缩保存，使用时在.cache/mat/恢复，建议预留至少5GB可用空间。

`score`直接对3240个初始/最终端点调用冻结的原验收器，对照归档分项、NRMSE与归一化尺度。`score --scope checkpoints`另外评分1951个新增实际检查点。`sensitivity`仅移除initial_condition_not_fixed，并检验与原事后评分一致；`statistics`重建54项边际率和48项配对比较，使用各自原抽样算法、种子及Holm族。`audit`检查25份审计材料哈希及41个保存初值，不声称进行新的独立语义标注。`resources`从360份归档工作流重建调用、Token、费用与墙钟，并核对366次尝试。详细步骤见reproduction/README.md。

## 内容定位

|位置|内容|
|---|---|
|benchmark/requirements|20份任务原文|
|benchmark/reference_models|参考源码和作者清单|
|benchmark/reference_trajectories|冻结参考MAT，禁止由当前差异脚本覆盖|
|benchmark/acceptance_specs|原合同、行为断言及锁定记录|
|experiments/conditions.csv|27条件编号与原标识|
|experiments/endpoint_index.csv|3240端点到相对input.json的索引|
|experiments/checkpoint_index.csv|新增1951检查点索引|
|experiments/shared_initial|60个共享起点的原始提示和源码束|
|experiments/historical_21_conditions|1260条原工作流记录、源码、运行元数据与中间版本|
|experiments/controlled_6_conditions|360条工作流和评分、保存状态与检查点输入|
|artifacts/index.json|内容寻址MAT的未压缩SHA256与压缩文件身份|
|data|全部冻结CSV，保留原始字段名，不将technical_acceptance当作语义正确率|
|resources|调用、Token、费用、执行失败、重试与已保存日志|
|initialization_audit|25模型分类、源码、XML、编译方程、诊断查找及证据链|
|evaluation/original_acceptance|原评分代码字节不变|
|reproduction|新增加的离线封装，不改变原评分和研究条件|
|provenance|锁定哈希差异、原分析配方及原路径到归档路径映射|
|paper/result_map.csv|论文每个主要结果到文件和命令的映射|
|figures|正文及历史图形的独立文件|
|documentation|完整研究分析记录，旧S编号仅为归档索引，论文不再引用|

## 三种复现范围

1. 从保存的模型、元数据、参考MAT与候选MAT重新执行原规则评分、行为断言与NRMSE，不重新仿真。
2. 对全部端点重建显式fixed敏感性计数、任务聚类区间、双向不一致及校正检验。
3. 沿保存源码、XML、编译初始化和保存初值复核25模型的分类依据。这是局部证据检查，不是全模型语义正确性认证。

原始JSON内部保留历史绝对路径以保护原字节；可执行索引使用包内相对路径，评分入口不解析旧机器目录。provenance/asset_origin.csv连接原路径及新位置。归档输入中的run_meta路径字段为历史溯源，离线评分显式传入当前解压轨迹路径。

## 已知边界

69项锁定输入中68项匹配原指纹，参考轨迹生成脚本预存e5b5758d…与当前10f24a6f…不同，详见provenance/locked_input_audit.json。当前脚本仅按差异版本归档，本包不执行它。使用当时保存的参考源码与MAT评分，可复算既有结果；不能据此声称已经从锁定生成脚本完整重生成参考。

25份审计涉及15任务和41变量，5份有效替代与20份实现依赖，不外推其他架构或全部模型。对应初始化诊断原文未在已归档日志找到；工具补足不直接等于规范错误。首次中断保持未知，缺失Token与费用不补零。费用为实验价格估算。

## 发布与引用

仓库位置与冻结标签由VERSION.json记录，公开可访问状态以实际GitHub Release页面为准。GitHub地址只在实际创建和核验后填入；没有虚构DOI。作者需决定对代码和自建数据的许可，本版不代作者授予未确认许可。第三方库不随包重新分发，通过依赖清单安装。
