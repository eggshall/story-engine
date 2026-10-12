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

STORY_CONFIG_PATH="$CFG_ENV" \
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
