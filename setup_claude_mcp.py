import os
import json
from pathlib import Path
import sys

def main():
    print("Göktürkçe MCP - Claude Desktop Kurulum Aracı")
    print("---------------------------------------------")
    
    appdata = os.environ.get("APPDATA")
    if not appdata:
        print("HATA: APPDATA ortam değişkeni bulunamadı. Sadece Windows desteklenmektedir.")
        return
    
    claude_config_path = Path(appdata) / "Claude" / "claude_desktop_config.json"
    
    if claude_config_path.exists():
        with open(claude_config_path, "r", encoding="utf-8") as f:
            try:
                config = json.load(f)
            except json.JSONDecodeError:
                print("UYARI: Mevcut claude_desktop_config.json bozuk, yeni bir tane oluşturuluyor.")
                config = {}
    else:
        config = {}
        claude_config_path.parent.mkdir(parents=True, exist_ok=True)
    
    if "mcpServers" not in config:
        config["mcpServers"] = {}
        
    project_dir = Path(__file__).parent.resolve()
    mcp_script = project_dir / "pipeline" / "product" / "mcp_server.py"
    
    if not mcp_script.exists():
        print(f"HATA: mcp_server.py bulunamadı: {mcp_script}")
        return
    
    config["mcpServers"]["gokturkce-assistant"] = {
        "command": sys.executable,
        "args": [
            str(mcp_script),
            "--transport",
            "stdio"
        ]
    }
    
    with open(claude_config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
        
    print(f"\n[BAŞARILI] Claude Desktop konfigürasyonu güncellendi:\n{claude_config_path}")
    print("\nGöktürkçe MCP başarıyla Claude Desktop'a eklendi!")
    print("Değişikliklerin etkili olması için lütfen Claude Desktop uygulamasını tamamen kapatıp yeniden açın.")

if __name__ == "__main__":
    main()
