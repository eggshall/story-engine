#!/usr/bin/env bash
# E2E 开发栈：起后端 + 起前端(带 VITE_API_KEY)，并做 HTTP 层鉴权校验。
#
# 用法:  bash scripts/e2e_dev_stack.sh          # 前台常驻，Ctrl-C 结束（真实模型）
#        bash scripts/e2e_dev_stack.sh --fake   # 假上游模式：模型指向本地假上游
#                                               # （不花钱、输出可断言，供浏览器 E2E 用）
#        bash scripts/e2e_dev_stack.sh --check  # 只做就绪与鉴权校验后退出
#
# 说明:
# - 不打印 api_key 内容，只打印长度；前端通过 VITE_API_KEY 注入。
# - --fake 模式用 STORY_CONFIG_PATH 指向临时配置（security.api_key 沿用真实配置，
#   所以鉴权链路仍然真实；只有 llm.models 换成本地假上游）。
# - 退出（含 Ctrl-C / 脚本结束）会清理自己起的三个进程，避免残留占用 8000/5173/8899。
set -u
# 仓库根：从脚本自身位置推导，避免硬编码本机绝对路径
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PATH="$HOME/.nvm/versions/node/v22.23.2/bin:$PATH"
export NVM_DIR="$HOME/.nvm"

MODE="${1:-}"
FAKE_PORT="${E2E_FAKE_PORT:-8899}"
FAKE_PID=""
# 数据目录隔离：把后端 `data/`（novels / library / style_profiles / user_profile）
# 指到临时目录，让浏览器 E2E **永远不往真实数据里写**。
# 起因（实测）：E2E 跑完在真实作品列表里多出一本「未命名作品」—— 那是 `generate` 端点
# 没收到 novel_id 时落盘的临时书；`data_dir()` 原先硬编码项目根，隔离不了。
# 用一个固定路径（不每次清空）：各 spec 自己会删掉建的书，残留留在 /tmp 里无害；
# 想彻底清就 `rm -rf /tmp/story-e2e-data`。
E2E_DATA_DIR="${E2E_DATA_DIR:-/tmp/story-e2e-data}"
mkdir -p "$E2E_DATA_DIR"

# 硬闸：端口已被占用就**拒绝启动**。
# 理由（实测事故，2026-10-12）：上一轮的开发栈没停（或被杀时没跑到 cleanup trap 留下孤儿进程），
# 新一轮照起，新后端绑不上 8000 → E2E 的请求打进**旧进程**，症状有两种，都很难认：
#   ① 新加的接口报 405 Method Not Allowed（旧后端没有这条路由）；
#   ② 旧进程没有本轮的环境变量（比如 STORY_DATA_DIR 隔离），于是把测试书**写进真实 data/**。
# 与其事后从症状反推，不如一开始就不许两个栈共存。
for _p in 8000 5173 "$FAKE_PORT"; do
  if (echo > "/dev/tcp/127.0.0.1/${_p}") 2>/dev/null; then
    echo "✗ 端口 ${_p} 已被占用 —— 先停掉上一轮的开发栈再跑本脚本。" >&2
    echo "  排查：ss -ltnp | grep -E ':8000|:5173'  然后  pkill -f 'uvicorn story_engine'  /  pkill -f 'vite --host'" >&2
    echo "  （不这么做的话，E2E 会打到旧进程上：轻则 405，重则把测试数据写进真实 data/）" >&2
    exit 3
  fi
done

cleanup() {
  for pid in "${FRONT:-}" "${BACK:-}" "$FAKE_PID"; do
    [ -n "$pid" ] && kill "$pid" 2>/dev/null
  done
  # 兜底：vite 若因 exec 优化未生效而存活（子 shell 被杀后它被 reparent），按命令行精确收掉。
  # 用括号断字，避免 pattern 出现在自身命令行时把自己也 SIGTERM（历史踩坑）。
  pkill -f "vite --hos[t] 127.0.0.1 --port 5173" 2>/dev/null
  # 临时配置里有真实 api_key（见 e2e_fake_config.py 的权限说明），退出即删
  [ -n "${CFG_ENV:-}" ] && rm -f "$CFG_ENV"
  wait 2>/dev/null
}
trap cleanup EXIT INT TERM

KEY="$(.venv/bin/python scripts/_read_api_key.py)"
echo "api_key 长度: ${#KEY}（不打印内容）"

CFG_ENV=""
if [ "$MODE" = "--fake" ]; then
  echo "=== 假上游模式：起本地假上游(127.0.0.1:${FAKE_PORT}) ==="
  .venv/bin/python scripts/fake_upstream_server.py --port "$FAKE_PORT" --mode ok \
    > /tmp/e2e_fake_upstream.log 2>&1 &
  FAKE_PID=$!
  for _ in $(seq 1 50); do
    (echo > "/dev/tcp/127.0.0.1/${FAKE_PORT}") 2>/dev/null && break
    sleep 0.2
  done
  echo "假上游 pid=$FAKE_PID 日志=/tmp/e2e_fake_upstream.log"
  CFG_ENV="$(.venv/bin/python scripts/e2e_fake_config.py --fake-port "$FAKE_PORT" \
    --out /tmp/e2e_fake_config.yaml)"
  echo "后端将使用临时配置: $CFG_ENV（模型指向假上游）"
fi

echo "后端数据目录（隔离）: $E2E_DATA_DIR"

STORY_CONFIG_PATH="$CFG_ENV" \
STORY_DATA_DIR="$E2E_DATA_DIR" \
.venv/bin/python -m uvicorn story_engine.api.main:app --host 127.0.0.1 --port 8000 \
  > /tmp/e2e_backend.log 2>&1 &
BACK=$!
( cd src/frontend && exec env VITE_API_KEY="$KEY" npx vite --host 127.0.0.1 --port 5173 \
  > /tmp/e2e_frontend.log 2>&1 ) &
# 注意 exec：让 $! 就是 vite 本身（否则它是子 shell 的 PID，cleanup 杀不掉 vite → 5173 被残留占用）
FRONT=$!
echo "backend pid=$BACK  frontend pid=$FRONT"

for _ in $(seq 1 40); do
  code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 2 -H "X-API-Key: $KEY" \
    http://127.0.0.1:8000/api/health || true)
  [ "$code" = "200" ] && break
  sleep 1
done
echo "后端 /api/health: $code"

for _ in $(seq 1 60); do
  code2=$(curl -s -o /dev/null -w '%{http_code}' --max-time 2 http://127.0.0.1:5173/ || true)
  [ "$code2" = "200" ] && break
  sleep 1
done
echo "前端 dev server: $code2"

echo "--- 鉴权 E2E（真实 HTTP）---"
printf "无 Key  -> 后端 /api/models : "; curl -s -o /dev/null -w '%{http_code}\n' --max-time 5 http://127.0.0.1:8000/api/models
printf "带 Key  -> 后端 /api/models : "; curl -s -o /dev/null -w '%{http_code}\n' --max-time 5 -H "X-API-Key: $KEY" http://127.0.0.1:8000/api/models
printf "经 vite 代理 + Key           : "; curl -s -o /dev/null -w '%{http_code}\n' --max-time 5 -H "X-API-Key: $KEY" http://127.0.0.1:5173/api/models

if [ "$MODE" = "--check" ]; then
  echo "校验完成，--check 模式退出（trap 会清理刚起的服务）"
  exit 0
fi

echo "--- 服务保持运行，供浏览器 E2E 使用（Ctrl-C 结束；退出自动清理）---"
wait
