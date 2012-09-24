#!/bin/bash
kill -9 `ps aux | grep goss | grep -v grep | awk '{print $2 " "}' | tr -d '\n'`
