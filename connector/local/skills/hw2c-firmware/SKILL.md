---
name: hw2c-firmware
description: 用 hw2c 把 EDA 网表/BOM 解析为六层 YAML、校验配置、读取需求/schema/示例；本机 stdio，无网络。
version: 0.1.0
---

# hw2c 固件构建（本机）

hw2c 把用户定义的硬件资源转换成基于 FreeRTOS 的 STM32 固件工程。这个 Connector
在**用户本机**运行，不上传网表或配置到任何服务端。

## 何时使用

- 用户给出 `.enet` / `.net` 网表和可选 BOM，想要 hw2c 可生成的配置；
- 用户贴出六层 YAML，要求检查字段或跨层引用；
- 用户问 hw2c 的硬件字段、引脚、示例工程、格式真源或需求条款。

## 工具

| 工具 | 入参 | 返回 |
|---|---|---|
| `parse_eda` | `netlist_text`（必填，文本不是路径）、`bom_text?`、`filename?` | `hardware_yaml` / `task_yaml` / `components_yaml` / `bind_yaml` / `params_yaml` / `pubsub_yaml` + `issues[]` |
| `validate_config` | `layers` = `{hardware, task?, components?, bind?, params?, pubsub?}`，值为 YAML 文本 | `{ok, issues:[{severity, code, message, layer, path}]}` |
| `list_examples` | 无 | `[{name, summary}]` |
| `get_example` | `name`，可选 `layer` | 六层 YAML（或指定层） |
| `get_mcu_pinout` | `part`（如 `STM32G0B1RET6`） | 自带示例中实际出现过的引脚/AF；未知型号返回空列表 |

## 资源

`hw2c://requirements`、`hw2c://requirements/{章节标题}`、
`hw2c://docs/user-guide/{layer}-yaml`、`hw2c://schema/{layer}`、
`hw2c://examples/{name}/{layer}.yaml`、`hw2c://format/{fota_format|ymodem_format}.json`、
`hw2c://models/{name}.yaml`。

schema 资源由权威 Pydantic 模型动态生成，不要手抄字段；格式真源也不要凭记忆回答。

## 提示词示例

- 「把这份网表和 BOM 解析成 hw2c 六层 YAML，并告诉我有哪些告警」
- 「检查这六层 YAML 能不能生成，重点看 bind 里的中断和任务引用」
- 「列出 hw2c 自带示例，找和我的 MCU 最接近的那个」

## 边界（重要）

当前版本**只提供解析、校验和知识查询**。生成固件、编译、烧录工具尚未注册；
用户要求"直接生成/编译/烧录"时，如实说明这版 Connector 还做不到，
不要假装完成，也不要改用 shell 绕过工具契约。

`validate_config` 的 `ok=false` 只由 CRITICAL/ERROR 触发，WARNING 不算失败但必须转述给用户。
