"""Injeta sat_events.json no template e grava a pagina final."""
import json
from pathlib import Path

HERE = Path(__file__).parent
tpl = (HERE / "radar_template.html").read_text(encoding="utf-8")
data = json.loads((HERE / "sat_events.json").read_text(encoding="utf-8"))
payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
out = tpl.replace('/*__DATA__*/{"stats":{},"events":[]}', payload)
assert out != tpl, "placeholder nao encontrado"
dest = HERE / "radar-sabado-31-10.html"
dest.write_text(out, encoding="utf-8")
print(f"ok {dest} {dest.stat().st_size} bytes, {len(data['events'])} eventos")
