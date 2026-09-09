# Git 代理使用指南

## 典型问题

浏览器能登录 GitHub，也能 ping 通 github.com，但终端里 git 拉取/推送失败：

```text
fatal: unable to access 'https://github.com/...':
Failed to connect to github.com:443 after 21000 ms
```

原因通常是“代理只对浏览器生效”，Git/命令行没有走代理。

## 先确认 Git 是否用了代理

```powershell
git config --global --get http.proxy
git config --global --get https.proxy
```

如果两条都没有输出，说明 Git 正在直连。

也可以检查系统代理状态：

```powershell
netsh winhttp show proxy
Get-ItemProperty -Path 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings' |
    Select-Object ProxyEnable, ProxyServer
```

## 一次性使用代理（推荐先试这个）

代理软件开启后，常见的本机 HTTP 端口是 7890：

```powershell
git -c http.proxy=http://127.0.0.1:7890 `
    -c https.proxy=http://127.0.0.1:7890 `
    pull --ff-only origin main
```

推送到 GitHub 同理：

```powershell
git -c http.proxy=http://127.0.0.1:7890 `
    -c https.proxy=http://127.0.0.1:7890 `
    push origin main
```

如果代理软件只提供 SOCKS5，可把地址写成：

```text
socks5://127.0.0.1:7890
```

## 永久让当前用户使用代理

```powershell
git config --global http.proxy http://127.0.0.1:7890
git config --global https.proxy http://127.0.0.1:7890
```

取消代理：

```powershell
git config --global --unset http.proxy
git config --global --unset https.proxy
```

## 本机没有代理端口在监听时

先确认代理软件真的开着，并查看它显示的本地端口：

```powershell
Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
    Where-Object { $_.LocalPort -in 7890,7891,1080,10808,10809,8080,8888 } |
    Select-Object LocalAddress, LocalPort, OwningProcess
```

没有任何输出时，说明命令行没有可用的代理端口，需要先在代理软件里开启允许局域网/全局代理，或手动记录代理地址。

## 2026-09-09 实测记录

- 系统代理显示关闭，WinHTTP 直连，Git 未配置代理，`github.com:443` TCP 连接超时；
- 使用代理后成功：

```powershell
git -c http.proxy=http://127.0.0.1:7890 `
    -c https.proxy=http://127.0.0.1:7890 `
    pull --ff-only origin main
```
