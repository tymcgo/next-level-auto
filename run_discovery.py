from src.discovery import parse_ro_csv, build_moment_inventory
import json

moments = parse_ro_csv("sample_ro_history.csv")
print(f"Parsed {len(moments)} moments")
for m in moments[:3]:
    print(f"  {m.vin[:6]}... {m.moment_type.value} ${m.estimate_total_cents/100:.2f}")
inv = build_moment_inventory(moments)
print(json.dumps(inv, indent=2))
