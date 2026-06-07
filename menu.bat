@echo off
chcp 65001 >nul
title SmartCity - Painel
:: Lancador: abre o painel de controle em PowerShell (cores nativas, REST nativo).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0painel.ps1"
