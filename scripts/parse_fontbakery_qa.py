import re
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
REPORT_HTML = ROOT_DIR / "outputs" / "tests" / "report.html"
OUT_SUMMARY_MD = ROOT_DIR / "outputs" / "tests" / "fontbakery_phase2_summary.md"

with open(REPORT_HTML, 'r', encoding='utf-8') as f:
    html = f.read()

out_lines = []
out_lines.append("# FontBakery QA Summary Report - Phase 2 (Orkun SANS Integration)\n")

# Extract summary table
summary_match = re.search(r'<td>(\d+)</td>\s*<td>(\d+)</td>\s*<td>(\d+)</td>\s*<td>(\d+)</td>\s*<td>(\d+)</td>\s*<td>(\d+)</td>\s*<td>(\d+)</td>', html)
if summary_match:
    out_lines.append("## Overall Metrics\n")
    out_lines.append(f"- **💥 ERROR**: {summary_match.group(1)}")
    out_lines.append(f"- **☠ FATAL**: {summary_match.group(2)}")
    out_lines.append(f"- **🔥 FAIL**: {summary_match.group(3)}")
    out_lines.append(f"- **⚠️ WARN**: {summary_match.group(4)}")
    out_lines.append(f"- **⏩ SKIP**: {summary_match.group(5)}")
    out_lines.append(f"- **ℹ️ INFO**: {summary_match.group(6)}")
    out_lines.append(f"- **✅ PASS**: {summary_match.group(7)}\n")

out_lines.append("## 🔥 FAIL Breakdown\n")

fail_items = re.finditer(r'<li class=\'details_item\'>(.*?)</li>', html, re.DOTALL)
fail_count = 0
for item in fail_items:
    content = item.group(1)
    if 'FAIL' in content:
        fail_count += 1
        text_match = re.search(r'<span class=\'details_text\'>(.*?)</span>', content, re.DOTALL)
        if text_match:
            clean_text = re.sub(r'<[^>]+>', ' ', text_match.group(1))
            clean_text = re.sub(r'\s+', ' ', clean_text).strip()
            
            pos = item.start()
            prev_html = html[:pos]
            h3_matches = list(re.finditer(r'<h3>(.*?)</h3>', prev_html, re.DOTALL))
            rule = "Unknown Rule"
            if h3_matches:
                rule = re.sub(r'<[^>]+>', ' ', h3_matches[-1].group(1)).strip()
                rule = re.sub(r'\s+', ' ', rule).strip()
            
            summary_matches = list(re.finditer(r'<summary>(.*?)</summary>', prev_html, re.DOTALL))
            context = "Unknown context"
            if summary_matches:
                context = re.sub(r'<[^>]+>', ' ', summary_matches[-1].group(1)).strip()
                context = re.sub(r'\s+', ' ', context).strip()
                
            out_lines.append(f"### {fail_count}. {rule}")
            out_lines.append(f"- **Font / Context**: `{context}`")
            out_lines.append(f"- **Reason**: {clean_text}\n")

out_lines.append("\n## ⚠️ WARN Summary\n")
warn_items = re.finditer(r'<li class=\'details_item\'>(.*?)</li>', html, re.DOTALL)
warn_count = 0
for item in warn_items:
    content = item.group(1)
    if 'WARN' in content:
        warn_count += 1
        text_match = re.search(r'<span class=\'details_text\'>(.*?)</span>', content, re.DOTALL)
        if text_match:
            clean_text = re.sub(r'<[^>]+>', ' ', text_match.group(1))
            clean_text = re.sub(r'\s+', ' ', clean_text).strip()
            
            pos = item.start()
            prev_html = html[:pos]
            h3_matches = list(re.finditer(r'<h3>(.*?)</h3>', prev_html, re.DOTALL))
            rule = "Unknown Rule"
            if h3_matches:
                rule = re.sub(r'<[^>]+>', ' ', h3_matches[-1].group(1)).strip()
                rule = re.sub(r'\s+', ' ', rule).strip()
            
            summary_matches = list(re.finditer(r'<summary>(.*?)</summary>', prev_html, re.DOTALL))
            context = "Unknown context"
            if summary_matches:
                context = re.sub(r'<[^>]+>', ' ', summary_matches[-1].group(1)).strip()
                context = re.sub(r'\s+', ' ', context).strip()
                
            out_lines.append(f"### {warn_count}. {rule}")
            out_lines.append(f"- **Font / Context**: `{context}`")
            out_lines.append(f"- **Reason**: {clean_text}\n")

with open(OUT_SUMMARY_MD, 'w', encoding='utf-8') as out_f:
    out_f.write('\n'.join(out_lines))

print(f"Summary written to {OUT_SUMMARY_MD}")
