# Vic Transport IDs MCP · 集装箱号与空运单号校验 MCP

> Validate container numbers (ISO 6346 check digit), air waybill numbers (IATA mod 7) and decode container size/type codes, offline. Built to the official Model Context Protocol spec (revision 2026-07-28, Python SDK v2).
>
> 订舱、做提单、报关、查货之前，先确认箱号和空运单号没打错；一个数字错了，货可能追踪不到，甚至提到别人的箱。

**Direction 方向:** 国际物流 Logistics · **Version:** 1.0.0 · **License:** MIT · **Transport:** stdio, Streamable HTTP (stateless)

---

## 解决什么痛点 · Pain points

| 货代/外贸人常见的坑 | 后果 | 这个 MCP 怎么解决 |
|---|---|---|
| 邮件、装箱单里箱号手打错一位 | 追踪查不到，提单、报关资料要改单，产生改单费 | `validate_container_numbers` 按 ISO 6346 校验位检查，并给出正确的校验位 |
| 箱号少写最后一位 | 系统拒收 | 10 位箱号自动补出校验位 |
| 空运单号 11 位，中间空格、横杠混乱 | 查不到货 | `validate_awb_numbers` 统一成 123-45678901 并检查 mod 7 校验位 |
| 订舱单上的 45G1、22G1 看不懂，和订的柜型对不上 | 拿到错柜型 | `decode_container_size_type` 解码长度、高度、箱型 |
| 一封邮件里十几个单号 | 逐个核对太慢 | `extract_and_validate_ids` 从粘贴文本里找出并校验 |

## Tools · 工具

| Tool | 做什么 | 只读 |
|---|---|---|
| `validate_container_numbers` | 批量校验箱号格式、类别字母、校验位 | ✅ |
| `validate_awb_numbers` | 批量校验空运单号 | ✅ |
| `decode_container_size_type` | 解码 4 位尺寸箱型代码 | ✅ |
| `extract_and_validate_ids` | 从文本中提取并校验 | ✅ |

**Resource:** `transport-ids://iso6346`. **Prompt:** `pre_booking_check`（发给船公司前检查草稿，只给修改清单，不发送）。

## Install · 安装

Requires Python 3.10+ and [uv](https://docs.astral.sh/uv/):

```bash
git clone https://github.com/voidgazer009/vic-mcp-servers.git
cd vic-mcp-servers/servers/logistics/transport-ids
uv run vic-transport-ids-mcp          # stdio
uv run vic-transport-ids-mcp --http   # Streamable HTTP on http://127.0.0.1:8000/mcp
```

### Claude Desktop / Claude Code

```json
{
  "mcpServers": {
    "vic-transport-ids": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/vic-mcp-servers/servers/logistics/transport-ids", "vic-transport-ids-mcp"]
    }
  }
}
```

Claude Code: `claude mcp add vic-transport-ids -- uv run --directory /path/to/transport-ids vic-transport-ids-mcp`

### Cursor (`.cursor/mcp.json`) · VS Code / Copilot (`.vscode/mcp.json`)

Same `command` and `args` as above. For VS Code use the key `"servers"` instead of `"mcpServers"`.

### Codex CLI (`~/.codex/config.toml`)

```toml
[mcp_servers.vic-transport-ids]
command = "uv"
args = ["run", "--directory", "/path/to/transport-ids", "vic-transport-ids-mcp"]
```

## Try it · 试试这样问

- 「帮我检查这个箱号对不对：CSQU3054384」
- 「这几个箱号哪个有问题：MSKU 123456-7, TGHU0000000, CSQU3054383」
- 「空运单号 176-1234 5675 是有效的吗？」
- 「45G1 和 45R1 分别是什么柜型？」
- 「下面这封货代邮件里的箱号和运单号帮我全部核对一遍：……」

## How it works · 计算与规则

- **Container (ISO 6346):** 4 letters (3-letter owner code + category U/J/Z) + 6-digit serial + 1 check digit. Letters map to 10, 12, 13 … (multiples of 11 skipped); each of the first 10 characters is multiplied by 2^position; sum mod 11, and a remainder of 10 becomes 0. Example: CSQU305438 gives 6185, 6185 mod 11 = 3.
- **AWB (IATA):** 3-digit airline prefix + 7-digit serial + check digit = serial mod 7. Example: 1234567 mod 7 = 5.
- **Size/type:** char 1 length (2 = 20 ft, 4 = 40 ft, L = 45 ft), char 2 height (2 = 8 ft 6 in, 5 = 9 ft 6 in), chars 3-4 type group (G dry, R reefer, U open top, P flat rack, T tank).

## Limitations · 局限

- A valid number is only well-formed. It does not prove the container exists, who owns it or where it is. Real tracking needs the carrier or airline site.
- Owner codes and airline prefixes are not looked up in the BIC or IATA registers.
- Some carriers use legacy size codes (40HC, 4310); extraction by pattern can mistake other 11-digit numbers for AWBs.
- Network domains accessed: none (fully offline).

## Development

```bash
pip install -e ".[dev]" && pytest
python tools/audit.py servers/logistics/transport-ids   # from the repo root
```
