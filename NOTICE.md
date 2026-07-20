# Third-Party Notices

## Nanobot

拾光在 M0-0C 阶段复用了 Nanobot 最小教学版本的通用 Agent 核心设计，并对
所迁入代码进行了面向产品边界的重写。

- 上游项目：`HKUDS/nanobot`
- 上游地址：https://github.com/HKUDS/nanobot
- 实际迁移来源：只读目录 `/Users/zhangzihao/Documents/Nanobot 学习/nanobot`
- 本阶段核对的版本：从 `HKUDS/nanobot` 裁剪的最小教学版本
- 只读参考提交：`06f47fa54032d539b215c4b58d82564a6fa4aa48`
- 上游版权：Copyright (c) 2025-present Xubin Ren and the nanobot contributors
- 许可证：MIT License

MIT 许可证允许使用、复制、修改、合并、发布、分发、再许可和销售软件副本，但要求在软件的所有副本或实质性部分中保留原版权声明和许可声明。软件按“原样”提供，不附带任何明示或默示担保。

本 NOTICE 记录来源与归属，不表示拾光原创内容整体采用 MIT 许可证，也不改变上游许可证。后续迁移或分发 Nanobot 代码时，必须继续保留适用的版权和许可文本，并记录实际迁移文件及其来源版本。

### M0-0C 实际迁移与改写范围

本阶段实际读取并改写了以下最小教学模块；参考提交用于标识教学版本的上游
来源基线，实际迁移范围以本表列出的只读教学文件为准。本仓库不导入旧学习
目录，也不与其双向同步。

| 只读教学文件 | 正式产品文件 | 处理方式 |
|---|---|---|
| `nanobot/agent/runner.py` | `backend/nanobot_core/agent/runner.py` | 保留 model → tool → model 受限循环，重写消息隔离、结构化工具结果、多工具调用、空响应和确定性循环终止 |
| `nanobot/agent/loop.py` | `backend/nanobot_core/agent/loop.py` | 保留单轮编排职责，移除 workspace 创建、Markdown MemoryStore、JSONL SessionStore 和隐式持久化 |
| `nanobot/agent/context.py` | `backend/nanobot_core/agent/context.py` | 改为显式、业务无关的上下文构建，不包含文件读写、remember 或拾光业务 Prompt |
| `nanobot/agent/tools/base.py` | `backend/nanobot_core/tools/base.py` | 将手写 JSON 参数检查改为严格 Pydantic Schema，并新增可 JSON 序列化的 `ToolResult` |
| `nanobot/agent/tools/registry.py` | `backend/nanobot_core/tools/registry.py` | 保留集中注册和分发，重写重复注册、稳定排序和分类失败行为，不暴露异常详情 |
| `nanobot/providers/base.py` | `backend/nanobot_core/providers/base.py` | 将教学版 `LLMProvider`/`LLMResponse` 改为统一的 `ModelProvider`/`ModelResponse` 抽象，不含真实供应商实现 |
| `tests/test_runner.py`、`tests/test_tools.py`、`tests/test_loop_and_memory.py` | `backend/tests/core/*` | 使用完全离线 Fake、Stub 和固定输入重写；删除文件工具、文件会话和 Markdown 记忆测试 |
| `LICENSE` | `backend/nanobot_core/THIRD_PARTY_LICENSES/NANOBOT-MIT.txt` | 全文保留适用于迁入及改写部分的 Nanobot MIT License |

产品化改造包括：工具输入严格校验、统一成功/失败结果、稳定错误码、调用者消息
深拷贝隔离、一次响应多工具调用、循环边界和 Provider 空响应的确定性结果，以及
通过依赖注入提供的无持久化 AgentLoop。FastAPI、数据库、拾光业务、模型密钥和
真实网络均不属于该核心。

本阶段明确没有迁移 `openai_compat_provider.py`、通用文件系统工具、Markdown
MemoryStore、JSONL SessionStore 或 CLI。真实 OpenAI-compatible Provider 属于
后续 M0-1B。

上述 MIT 许可只适用于来源于 Nanobot 的迁入及改写部分，不表示拾光项目整体
采用 MIT License。

### MIT License 原文

```text
MIT License

Copyright (c) 2025-present Xubin Ren and the nanobot contributors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```
