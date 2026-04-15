# Demand Conversion Pipeline

这个项目会把 Word 里的需求表，按顺序变成：提示词、LLM 响应、测试用例，再导出 Excel。
主入口是 `pipeline_runner.py`。

完整流程：`Word -> Prompt chunks -> LLM responses -> Parsed test cases -> Excel`

## 运行前准备

- Python 3.11
- 使用项目专用 Conda 环境，不要用 `base`

```bash
conda run -n demand_conversion python -m pip install -r requirements.txt
```

- 把 API key 放进环境变量，不要写进 JSON。默认读取 `OPENAI_API_KEY`，也可以在配置里改成别的变量名。

## 配置文件

所有运行配置都放在 `pipeline_config.json`。
可以先复制模板：

```bash
cp pipeline_config.sample.json pipeline_config.json
```

路径都是**相对于这个 JSON 文件本身**来解析的。

### paths

- `docx`：需求 Word 文件
- `artifacts_dir`：中间产物和断点状态目录
- `prompt_cache_dir`：prompt 对应响应的缓存目录
- `responses_dir`：原始 LLM 文本响应目录
- `output_excel`：最终 Excel 输出位置

### llm

现在 LLM 配置支持多 provider。

公共字段：
- `provider`：底层协议类型
- `model`：模型名
- `api_key_env`：API key 对应的环境变量名
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
- `anthropic`（已预留，还没正式实现）

### openai_compatible 示例

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

> `pipeline_config.sample.json` 里这个示例故意保留为中性模板，避免把已经过期的供应商地址或模型名继续当成默认答案。
>
> 当前已验证可用组合：`https://yunwu.ai/v1` + `gpt-5.3-codex` + `responses`

`options.endpoint` 目前支持：
- `chat_completions`
- `responses`

### custom_http 示例

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

`request_format` 目前支持：
- `prompt_only`
- `prompt_model`
- `messages_model`

### 兼容旧配置

如果旧 JSON 里还没有 `provider`，代码会自动按 `openai_compatible` 处理。
也就是说，老配置不用立刻全部重写。

### batch

- `batch_size`：每个 prompt chunk 里塞多少个需求块

### flags

- `resume`：按 `artifacts_dir/pipeline_state.json` 继续跑
- `dry_run`：跳过真实 LLM 调用和 Excel 导出
- `preview`：在解析需求时额外写出 `requirements_preview.md`
- `skip_llm`：保留字段，当前 CLI 不直接触发

命令行参数 `--resume`、`--dry-run`、`--preview` 会覆盖 JSON 里的同名配置。

## 运行方式

```bash
conda run -n demand_conversion python pipeline_runner.py --config pipeline_config.json --dry-run --preview
```

常用参数：
- `--dry-run`：不调 LLM，不导出 Excel，适合先检查结构
- `--resume`：从上次成功阶段继续
- `--preview`：生成需求预览 markdown

## 快速开始

如果你是第一次跑，建议按下面顺序：

### 1. 安装依赖

```bash
conda run -n demand_conversion python -m pip install -r requirements.txt
```

### 2. 准备配置

如果你还没有正式配置文件，先复制模板：

```bash
cp pipeline_config.sample.json pipeline_config.json
```

然后至少确认这几项：
- `paths.docx`：指向你要处理的 Word 文件
- `llm.provider`
- `llm.base_url`
- `llm.model`
- `llm.api_key_env`
- `llm.options.endpoint`

对于 `openai_compatible`：
- `llm.base_url` 必填
- `llm.model` 必填
- `llm.options.endpoint` 建议用 `responses`

### 3. 设置 API key

默认使用：

```bash
export OPENAI_API_KEY=你的key
```

如果你在 JSON 里把 `api_key_env` 改成别的名字，就设置对应的环境变量。

### 4. 先跑一遍 dry-run

```bash
conda run -n demand_conversion python pipeline_runner.py --config pipeline_config.json --dry-run --preview
```

这一步的目的不是拿最终 Excel，而是先确认：
- Word 能不能被正确解析
- `requirements_preview.md` 看起来是否正常
- prompt 分块是否符合预期

### 5. 确认无误后正式跑

```bash
conda run -n demand_conversion python pipeline_runner.py --config pipeline_config.json --preview
```

如果配置文件里本身就是 `"dry_run": false`，也可以直接去掉 `--preview`：

```bash
conda run -n demand_conversion python pipeline_runner.py --config pipeline_config.json
```

### 6. 中断后继续跑

```bash
conda run -n demand_conversion python pipeline_runner.py --config pipeline_config.json --resume
```

`--resume` 会结合 `artifacts/pipeline_state.json` 和已有产物决定从哪一步继续。

## 产物说明

运行后你通常会看到 4 类产物：需求解析结果、发给 LLM 的 prompt、LLM 返回内容、最终测试用例。

### 1. 需求解析阶段

- `artifacts/requirements.json`
  - Word 需求文档解析后的结构化结果。
  - 每一项对应一个需求块，后续 prompt 生成就是基于它。
  - 如果你怀疑“Word 没被正确拆出来”，先看这个文件。

- `artifacts/requirements_preview.md`（开启 `--preview` 时）
  - 给人直接看的预览版，方便快速确认章节、标题、描述有没有被抽对。
  - 适合第一次接入新 Word 文档时先人工浏览。

### 2. Prompt 生成阶段

- `artifacts/prompt_chunks/chunk_*.txt`
  - 每个文件就是一段真正发给 LLM 的 prompt。
  - `batch.batch_size` 会影响这里一共切成多少个 chunk。
  - 如果你想排查“为什么模型生成得不好”，先看这些 prompt 是否写对、切分是否合理。

### 3. LLM 调用阶段

- `prompt_cache/chunk_*.json`
  - 每个 chunk 对应一份缓存，里面会保存：
    - `raw_text`：模型返回正文
    - `metadata`：provider、model、usage、endpoint 等信息
  - 这个目录不在 `artifacts_dir` 下，而是单独由 `prompt_cache_dir` 控制。
  - 适合排查：
    - 当前结果是不是旧缓存复用的
    - 实际调用了哪个 provider / model
    - token 使用量是多少

- `artifacts/responses/chunk_*.txt` 或你配置的 `responses_dir`
  - 每个 chunk 的原始 LLM 文本输出。
  - 这些文件已经是“模型回复后的纯文本”，不含缓存元数据。
  - 如果 `parsed_cases.json` 解析结果不对，优先回头看这里，确认是不是模型输出格式本身就有问题。

### 4. 测试用例产出阶段

- `artifacts/parsed_cases.json`
  - 解析后的标准测试用例 JSON。
  - 每条记录通常包含：
    - `module`
    - `name`
    - `operation`
    - `expected`
  - 这是最适合做二次清洗、批量修正、质量审查的文件。
  - 如果你要程序化处理用例，优先用这个文件，不要直接改 Excel。

- `artifacts/convert.txt`
  - 把最终测试用例重新序列化成文本格式后的产物。
  - 更适合做人工 diff、快速浏览、复制给别的工具。
  - 当你想比较“两次生成结果哪里不一样”时，这个文件通常比 Excel 更好比。

- `artifacts/pipeline_state.json`
  - 记录各阶段是否完成、完成时间、产物数量。
  - `--resume` 就是依赖这个文件判断从哪一步继续。
  - 如果你发现续跑行为不符合预期，先检查这里。

- `output/output_test_cases.xlsx`
  - 最终导出的 Excel。
  - 一般给人工 review、发给测试、导入模板时看这个文件。
  - 如果 Excel 内容不对，通常不要直接在 Excel 里修，应该回到 `parsed_cases.json` 或更上游的 `responses/chunk_*.txt` 去改。

### 一个简单排查顺序

如果最后结果不对，建议按这个顺序看：

1. `requirements_preview.md` / `requirements.json`
   - 先确认 Word 解析有没有偏。
2. `prompt_chunks/chunk_*.txt`
   - 再确认 prompt 是否表达清楚。
3. `responses/chunk_*.txt`
   - 再看模型原始输出是不是已经跑偏。
4. `parsed_cases.json`
   - 最后确认是模型输出问题，还是解析/清洗问题。
5. `output/output_test_cases.xlsx`
   - Excel 只看最终呈现，不建议作为排查第一入口。

如果你想彻底重新跑一次，可以清理 `artifacts_dir`、`prompt_cache_dir`、`responses_dir`，或者直接换一个新的输出目录。

## 常见问题

### 1. 为什么 `--resume` 没生效？

先看 `artifacts/pipeline_state.json`：
- 对应阶段是否已经标记为完成
- 相关产物文件是否真的存在

`--resume` 不是只看命令行参数，也会同时检查已有产物是否可复用。
如果状态文件说已完成，但对应产物缺失或无效，代码会自动重跑该阶段。

### 2. 为什么生成结果不对？先看哪个文件？

建议按这个顺序排查：
1. `requirements_preview.md` / `requirements.json`
2. `prompt_chunks/chunk_*.txt`
3. `responses/chunk_*.txt`
4. `parsed_cases.json`
5. `output/output_test_cases.xlsx`

也就是说，先确认 Word 解析，再确认 prompt，再确认模型输出，最后再看用例解析和 Excel。

### 3. 为什么 `parsed_cases.json` 不对，但 Excel 也不对？

因为 Excel 是基于最终测试用例数据导出的。
如果 `parsed_cases.json` 已经不对，Excel 基本也会一起不对。

排查时优先修：
- `parsed_cases.json`
- 或更上游的 `responses/chunk_*.txt`

不建议把 Excel 当作源文件直接手改。

### 4. 为什么不建议直接修改 Excel？

因为 Excel 是最终展示层，不是最稳定的中间数据层。
如果你直接改 Excel：
- 下次重新导出会被覆盖
- 不方便做批量 diff
- 不方便程序化清洗

更适合改的是：
- `artifacts/parsed_cases.json`
- 或者再往上游改 prompt / response

### 5. 为什么模型调用失败或返回空内容？

先看：
- `prompt_cache/chunk_*.json` 里的 `metadata`
- `responses/chunk_*.txt` 是否为空
- 当前配置里的 `provider / base_url / model / endpoint` 是否匹配

对于 `openai_compatible`，优先确认：
- `base_url` 是否可用
- `model` 是否真能返回正文
- `endpoint` 是否应该使用 `responses`

当前代码在批量发送前会先做一次 preflight；如果模型返回空正文，会直接 fail fast，不会继续整批生成。

### 6. 想换输入 Word 文件怎么办？

直接改 `pipeline_config.json` 里的：

```json
"paths": {
  "docx": "source/你的文件.docx"
}
```

路径是相对于 `pipeline_config.json` 本身解析的，不是相对于当前终端目录。

### 7. 想彻底从头跑一遍怎么办？

有两种方式：

1. 删除或清空这些目录/文件后再跑：
   - `artifacts_dir`
   - `prompt_cache_dir`
   - `responses_dir`
2. 直接在配置里换一个新的输出目录

如果你只是想保留旧结果同时跑新一轮，推荐第二种。

## 测试

先检查配置是否能被正常读取：

```bash
conda run -n demand_conversion python - <<'PY'
from pathlib import Path
from pipeline.config import load_config
print(load_config(Path('pipeline_config.sample.json')))
PY
```

跑单测：

```bash
conda run -n demand_conversion python -m pytest test/test_pipeline.py -q
```

如果你刚改了 LLM 接入层，建议再补一遍：

```bash
conda run -n demand_conversion python -m compileall pipeline generate_requirement_prompts.py
```
