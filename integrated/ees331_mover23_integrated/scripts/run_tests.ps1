# 参数原样传给同一 Python 入口；不改变当前目录。
& python (Join-Path $PSScriptRoot 'run_tests.py') @args
exit $LASTEXITCODE
