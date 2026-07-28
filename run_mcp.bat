@echo off
echo ========================================================
echo Göktürkçe Yapay Zeka - MCP Sunucusu (HTTP/SSE Modu)
echo ========================================================
echo.
echo Bu komut dosyasi, MCP sunucusunu ag uzerinden (HTTP/SSE) 
echo diger istemcilere acmak icin kullanilir.
echo Claude Desktop icin 'setup_claude_mcp.py' scriptini calistirin.
echo.
cd /d "%~dp0pipeline\product"
python mcp_server.py --transport streamable-http --host 127.0.0.1 --port 8001
pause
