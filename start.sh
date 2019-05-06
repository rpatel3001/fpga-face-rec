#!/bin/sh -i

sqlite_web -H 192.168.2.99 /home/xilinx/capstone/database.sqlite3 &
sudo service pl_server start
sudo python3 maindmaresize.py &
