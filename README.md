# Binance DCA

[![uv](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json)](https://github.com/astral-sh/uv)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
![python_version](https://img.shields.io/badge/Python-3.13-3776AB.svg?style=flat&logo=python&logoColor=white)
[![pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit&logoColor=white)](https://github.com/pre-commit/pre-commit)

Binance DCA 自動定投腳本。

![demo](./demo.gif)

## 特點 (Features)

1. 繞過幣安內建的現貨 DCA 機器人的高額服務費 (2%)
2. POST Only 掛單，確保交易手續費是最低費率 (0.1% -> 0.075%)
3. 動態定價策略 (不會被做市商多扒一層皮)
4. 現貨帳戶餘額不足，自動從活期賺幣贖回資產進行定投買入。

## 設置方式

TODO