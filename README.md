# Demand Conversion Pipeline

把 Word 需求文档转换成测试用例 Excel 的自动化流水线。

主入口是 `pipeline_runner.py`，完整流程如下：

`Word -> requirements -> prompt chunks -> LLM responses -> parsed cases -> Excel`

## 当前能力

- 支持解析表格型需求文档
- 当表格解析不到有效需求时，会自动回退到段落型文档解析
- 支持 `openai_compatible` 和 `custom_http` 两类 LLM provider
- 支持 prompt 缓存、断点续跑、预览产物
- 支持为最终模块路径追加 `version_prefix`
- 支持为 Excel 导出统一写入 `assignee`
- 支持在每次运行时向 prompt 注入业务背景 `prompt_context`

## 目录入口

- `pipeline_runner.py`
  - 流水线 CLI 入口
- `pipeline/config.py`
  - 配置模型与加载逻辑
- `pipeline/stages.py`
  - 各阶段执行与 `resume` 逻辑
- `requirement_parser.py`
  - Word 需求解析
- `requirement_extractor.py`
  - 需求提取与预览辅助脚本
- `generate_requirement_prompts.py`
  - prompt 生成、DOCX 校验、LLM 输出回灌辅助脚本

## 环境准备

- Python 3.11
- 建议使用项目专用 Conda 环境 `demand_conversion`

安装依赖：

```bash
conda run -n demand_conversion python -m pip install -r requirements.txt
```

## 配置与密钥

运行配置使用 `pipeline_config.json`。先从模板复制：

PowerShell:

```powershell
Copy-Item pipeline_config.sample.json pipeline_config.json
```

Bash:

```bash
cp pipeline_config.sample.json pipeline_config.json
```

注意：

- `pipeline_config.json` 是本地配置，已经加入 `.gitignore`
- `.env`、`*.key`、`*.pem`、`*.p12`、`*.pfx` 等敏感文件也已忽略
- API key 不要写进 JSON，统一通过环境变量提供
- 所有相对路径都相对于 `pipeline_config.json` 文件本身解析

### 配置结构

`pipeline_config.sample.json` 当前结构如下：

```json
{
  "paths": {
    "docx": "source/wordv1.3.7.docx",
    "artifacts_dir": "artifacts",
    "prompt_cache_dir": "prompt_cache",
    "responses_dir": "artifacts/responses",
    "output_excel": "output/output_test_cases.xlsx"
  },
  "llm": {
    "provider": "openai_compatible",
    "base_url": "https://your-openai-compatible-host/v1",
    "model": "your-model-name",
    "api_key_env": "OPENAI_API_KEY",
    "timeout_seconds": 120,
    "max_concurrency": 1,
    "max_retries": 3,
    "retry_backoff_seconds": 5,
    "options": {
      "endpoint": "responses"
    }
  },
  "batch": {
    "batch_size": 5
  },
  "output": {
    "version_prefix": "未知版本",
    "assignee": "liwenqiu"
  },
  "flags": {
    "resume": false,
    "dry_run": true,
    "preview": true,
    "skip_llm": false
  }
}
```

### `paths`

- `docx`：输入 Word 文件
- `artifacts_dir`：中间产物与状态文件目录
- `prompt_cache_dir`：LLM prompt 缓存目录
- `responses_dir`：原始 LLM 文本输出目录
- `output_excel`：最终 Excel 输出路径

### `llm`

公共字段：

- `provider`
- `model`
- `api_key_env`
- `timeout_seconds`
- `max_concurrency`
- `max_retries`
- `retry_backoff_seconds`

按 provider 生效的字段：

- `base_url`
- `headers`
- `options`

当前支持：

- `openai_compatible`
- `custom_http`
- `anthropic`：配置模型已预留，但当前项目里还没有完整 provider 实现

#### `openai_compatible` 示例

```json
{
  "llm": {
    "provider": "openai_compatible",
    "base_url": "https://your-openai-compatible-host/v1",
    "model": "your-model-name",
    "api_key_env": "OPENAI_API_KEY",
    "timeout_seconds": 120,
    "max_concurrency": 1,
    "max_retries": 3,
    "retry_backoff_seconds": 5,
    "options": {
      "endpoint": "responses"
    }
  }
}
```

说明：

- `llm.base_url` 必填
- `llm.model` 必填
- `options.endpoint` 默认会补成 `responses`
- 当前支持的 endpoint：
  - `responses`
  - `chat_completions`

#### `custom_http` 示例

```json
{
  "llm": {
    "provider": "custom_http",
    "base_url": "https://your-service.example.com/api",
    "model": "testcase-v1",
    "api_key_env": "CUSTOM_LLM_KEY",
    "headers": {
      "Authorization": "Bearer ${API_KEY}",
      "X-App-Name": "demand-conversion"
    },
    "timeout_seconds": 120,
    "max_concurrency": 1,
    "max_retries": 3,
    "retry_backoff_seconds": 5,
    "options": {
      "method": "POST",
      "path": "/generate",
      "request_format": "prompt_model",
      "response_text_path": "data.output",
      "response_usage_path": "meta.usage"
    }
  }
}
```

`options.request_format` 当前支持：

- `prompt_only`
- `prompt_model`
- `messages_model`

### `batch`

- `batch_size`：每个 prompt chunk 包含多少条需求块

### `output`

- `version_prefix`
  - 在解析完测试用例后，统一追加到模块路径前缀
  - 例如原始模块是 `/登录/验证码`，可能变成 `/V1.3.7/登录/验证码`
- `assignee`
  - Excel 导出时写入用例负责人
- `prompt_context`
  - 运行时附加到每个 prompt 顶部的业务背景
  - 适合补充端到端流程、上下游依赖、业务规则

示例：

```json
{
  "output": {
    "version_prefix": "V1.3.7",
    "assignee": "liwenqiu",
    "prompt_context": "注册流程需要串联短信验证码、实名认证和风控审批。"
  }
}
```

### `flags`

- `resume`：读取 `artifacts/pipeline_state.json` 并尽量复用已有产物
- `dry_run`：跳过真实 LLM 调用与 Excel 导出
- `preview`：在需求解析阶段额外输出 `requirements_preview.md`
- `skip_llm`：保留字段，当前 CLI 没有直接暴露对应参数

命令行里的 `--resume`、`--dry-run`、`--preview` 会覆盖 JSON 中同名配置。

### 兼容旧配置

如果旧配置里没有 `llm.provider`，代码会自动按 `openai_compatible` 处理，不需要立刻整体重写旧 JSON。

## 设置环境变量

PowerShell:

```powershell
$env:OPENAI_API_KEY="your-key"
```

Bash:

```bash
export OPENAI_API_KEY=your-key
```

如果你把 `api_key_env` 改成别的变量名，就设置对应的环境变量。

## 运行方式

### 1. 先做 dry-run

```bash
conda run -n demand_conversion python pipeline_runner.py --config pipeline_config.json --dry-run --preview
```

这一步主要用于确认：

- Word 是否被正确解析
- `artifacts/requirements_preview.md` 是否正常
- `artifacts/prompt_chunks/chunk_*.txt` 的分块和内容是否合理

### 2. 正式运行

```bash
conda run -n demand_conversion python pipeline_runner.py --config pipeline_config.json --preview
```

如果配置里已经把 `dry_run` 设为 `false`，也可以直接：

```bash
conda run -n demand_conversion python pipeline_runner.py --config pipeline_config.json
```

### 3. 从断点续跑

```bash
conda run -n demand_conversion python pipeline_runner.py --config pipeline_config.json --resume
```

## 流水线阶段

### 1. Requirements

- 解析 `docx`
- 优先按表格结构抽取需求块
- 如果没有抽出有效表格需求，会回退到段落型解析
- 产出 `artifacts/requirements.json`
- 开启 `preview` 时额外产出 `artifacts/requirements_preview.md`

### 2. Prompt Chunks

- 将需求块按 `batch.batch_size` 切分
- 为每个 chunk 生成独立 prompt
- 如果配置了 `output.prompt_context`，会注入到每个 prompt 顶部
- 产出 `artifacts/prompt_chunks/chunk_*.txt`

### 3. LLM Responses

- 根据 `llm.provider` 调用模型
- 缓存写入 `prompt_cache/chunk_*.json`
- 原始文本输出写入 `artifacts/responses/chunk_*.txt` 或你配置的 `responses_dir`

### 4. Parsed Cases

- 从模型输出解析 Convert.txt 风格用例
- 统一追加 `output.version_prefix`
- 产出 `artifacts/parsed_cases.json`

### 5. Excel

- 根据解析结果生成最终 Excel
- 导出到 `output/output_test_cases.xlsx` 或你配置的 `output_excel`
- 同时写出 `artifacts/convert.txt`

## 辅助脚本

### `requirement_extractor.py`

适合单独验证 Word 解析效果。

导出结构化 JSON：

```bash
conda run -n demand_conversion python requirement_extractor.py --docx source/wordv1.3.7.docx --format json --output requirements.json
```

导出 Markdown 摘要：

```bash
conda run -n demand_conversion python requirement_extractor.py --docx source/wordv1.3.7.docx --format markdown --output requirements.md
```

生成预览：

```bash
conda run -n demand_conversion python requirement_extractor.py --docx source/wordv1.3.7.docx --preview tmp_table_preview.txt
```

### `generate_requirement_prompts.py`

这个脚本现在有三个主要子命令。

#### `validate-docx`

校验 DOCX，并输出需求 JSON 与预览文件：

```bash
conda run -n demand_conversion python generate_requirement_prompts.py validate-docx --docx source/wordv1.3.7.docx --output-json requirements.json --preview-md requirements_preview.md
```

#### `emit-prompts`

从 DOCX 或已有需求 JSON 生成 prompt chunks：

```bash
conda run -n demand_conversion python generate_requirement_prompts.py emit-prompts --docx source/wordv1.3.7.docx --batch-size 5 --output prompt_chunks.txt
```

#### `ingest-output`

把模型输出的 Convert.txt 风格文本回灌成 JSON：

```bash
conda run -n demand_conversion python generate_requirement_prompts.py ingest-output --input artifacts/responses/chunk_001.txt --output parsed_chunk_001.json
```

## 产物说明

### Requirements 阶段

- `artifacts/requirements.json`
  - 结构化需求块
- `artifacts/requirements_preview.md`
  - 便于人工检查的预览文件

### Prompt 阶段

- `artifacts/prompt_chunks/chunk_*.txt`
  - 每个 chunk 实际发给模型的 prompt

### LLM 阶段

- `prompt_cache/chunk_*.json`
  - 包含 `raw_text` 和 `metadata`
- `artifacts/responses/chunk_*.txt`
  - 模型原始文本输出

### Cases / Excel 阶段

- `artifacts/parsed_cases.json`
  - 标准化测试用例 JSON
- `artifacts/convert.txt`
  - 重新序列化后的 Convert.txt
- `artifacts/pipeline_state.json`
  - 各阶段完成状态与计数
- `output/output_test_cases.xlsx`
  - 最终 Excel

## 常见排查顺序

如果最终结果不对，建议按这个顺序排查：

1. `artifacts/requirements_preview.md`
2. `artifacts/requirements.json`
3. `artifacts/prompt_chunks/chunk_*.txt`
4. `artifacts/responses/chunk_*.txt`
5. `artifacts/parsed_cases.json`
6. `output/output_test_cases.xlsx`

## 缓存与续跑说明

- `--resume` 不只看命令行参数，还会结合 `artifacts/pipeline_state.json` 和已有文件判断是否复用
- 如果某阶段标记完成，但产物缺失，流水线会自动重跑该阶段
- 如果 `responses/chunk_*.txt` 为空，同时缓存里 `metadata.usage.completion_tokens > 0`，系统会把这类缓存视为无效并重新请求，避免“空正文却误判为成功”

## 测试与校验

检查 sample config 是否能被正常加载：

```bash
conda run -n demand_conversion python -c "from pathlib import Path; from pipeline.config import load_config; print(load_config(Path('pipeline_config.sample.json')))"
```

运行单测：

```bash
conda run -n demand_conversion python -m pytest test/test_pipeline.py -q
```

如果刚改过 LLM 接入层，建议再跑一次：

```bash
conda run -n demand_conversion python -m compileall pipeline generate_requirement_prompts.py
```
