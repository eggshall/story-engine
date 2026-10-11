#!/usr/bin/env bash
# E2E 开发栈：起后端 + 起前端(带 VITE_API_KEY)，并做 HTTP 层鉴权校验。
#
# 用法:  bash scripts/e2e_dev_stack.sh          # 前台常驻，Ctrl-C 结束
#        bash scripts/e2e_dev_stack.sh --check  # 只做就绪与鉴权校验后退出
#
# 说明: 不打印 api_key 内容，只打印长度；前端通过 VITE_API_KEY 注入（对应 api.ts 的构建期来源）。
set -u
cd /home/syzc/story-engine
export PATH=/home/syzc/.nvm/versions/node/v22.23.2/bin:$PATH
export NVM_DIR=/home/syzc/.nvm

KEY="$(.venv/bin/python scripts/_read_api_key.py)"
echo "api_key 长度: ${#KEY}（不打印内容）"

.venv/bin/python -m uvicorn story_engine.api.main:app --host 127.0.0.1 --port 8000 \
  > /tmp/e2e_backend.log 2>&1 &
BACK=$!
( cd src/frontend && VITE_API_KEY="$KEY" npx vite --host 127.0.0.1 --port 5173 \
  > /tmp/e2e_frontend.log 2>&1 ) &
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

if [ "${1:-}" = "--check" ]; then
  echo "校验完成，--check 模式退出（服务仍在后台运行，注意手动清理）"
  exit 0
fi

echo "--- 服务保持运行，供浏览器 E2E 使用（Ctrl-C 结束）---"
wait
