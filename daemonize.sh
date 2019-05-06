#!/bin/bash

PATH=/opt/microblazeel-xilinx-elf/bin:$PATH
echo $PATH
cd /home/xilinx
mkdir -p "/home/xilinx/tmp"
PIDFILE="/home/xilinx/tmp/myprogram.pid"

if [ -e "${PIDFILE}" ] && (ps -u $(whoami) -opid= |
                           grep -P "^\s*$(cat ${PIDFILE})$" &> /dev/null); then
  echo "Already running."
  exit 99
fi

/usr/bin/python3 /home/xilinx/main.py > /home/xilinx/tmp/myprogram.log 2>&1 &

echo $! > "${PIDFILE}"
chmod 644 "${PIDFILE}"
