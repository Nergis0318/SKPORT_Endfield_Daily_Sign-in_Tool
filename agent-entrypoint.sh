#!/bin/bash
# agent 서비스 전용: 가상 디스플레이 + noVNC + 상시 에이전트(manager.py)
set -e
export DISPLAY=:99
rm -f /tmp/.X99-lock
Xvfb :99 -screen 0 1280x800x24 >/tmp/xvfb.log 2>&1 &
sleep 1
x11vnc -display :99 -forever -shared -nopw -localhost -quiet -bg >/tmp/x11vnc.log 2>&1 || true
echo "관리 UI + VNC: http://localhost:8080 (VNC: /vnc.html)"
exec uv run python manager.py
