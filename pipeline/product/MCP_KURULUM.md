# Göktürkçe AI Assistant — Model Context Protocol (MCP) Kurulum ve Kullanım Rehberi

Bu belge, Göktürkçe Yapay Zeka Servisini **Model Context Protocol (MCP)** ile Claude Desktop, Claude Code veya herhangi bir MCP uyumlu LLM istemcisine nasıl bağlayacağınızı açıklar.

---

## 🚀 1. Özet & Mimari

Göktürkçe MCP Sunucusu (`pipeline/product/mcp_server.py`), **Python FastMCP** altyapısı üzerine inşa edilmiştir.

### Sunulan Araçlar (Tools):
1. `gokturkce_translate`: Latin Türkçe metni Orhun Göktürkçe yazısına çevirir. Geleneksel Orhun ünlü düşürme / ligatür kurallarını ve Orhun ünlü uyumunu doğrular.
2. `gokturkce_verify_image`: Görseldeki (dosya yolu veya base64 dizesi) Göktürkçe metni otomatik segmentasyon ve MobileNetV2 modeli ile analiz ederek doğrular.

---

## 💻 2. Claude Desktop Konfigürasyonu (Windows)

Claude Desktop uygulamasını yerel `stdio` modunda çalıştırmak için aşağıdaki adımları izleyin:

### Dosya Yolu:
Windows üzerinde konfigürasyon dosyası şu adrestedir:
```text
%APPDATA%\Claude\claude_desktop_config.json
```
*(Tam yol: `C:\Users\<Kullanıcı_Adı>\AppData\Roaming\Claude\claude_desktop_config.json`)*

### `claude_desktop_config.json` İçeriği:
```json
{
  "mcpServers": {
    "gokturkce-assistant": {
      "command": "python",
      "args": [
        "C:\\Users\\pc\\gokturk_pipeline\\pipeline\\product\\mcp_server.py",
        "--transport",
        "stdio"
      ]
    }
  }
}
```

---

## 🌐 3. Uzaktan / HTTP Modu Kullanımı (Streamable HTTP / SSE)

MCP sunucusunu ağ üzerinden veya diğer istemcilere `X-API-Key` korumalı olarak açmak isterseniz:

### Çalıştırma Komutu:
```bash
python pipeline/product/mcp_server.py --transport streamable-http --host 127.0.0.1 --port 8001
```

### HTTP İstemci İstek Örneği:
HTTP modunda tüm isteklerin `X-API-Key` başlığı taşıması zorunludur (`api_keys.json` kontrolü):
```http
POST /mcp HTTP/1.1
Host: 127.0.0.1:8001
X-API-Key: internal-web-ui-key-998877
Content-Type: application/json
```
