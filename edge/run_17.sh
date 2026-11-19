#!/bin/bash

echo "=== 17b. Copy files ==="
scp dfn3_paced.py dfn3_paced_stages.sh shreyas@shreyas.local:~/anc_logs/
ssh shreyas@shreyas.local 'chmod +x ~/anc_logs/dfn3_paced_stages.sh'

echo "=== 17c. Run script ==="
ssh shreyas@shreyas.local 'nohup ~/anc_logs/dfn3_paced_stages.sh > ~/anc_logs/dfn3_paced_stages.log 2>&1 < /dev/null &'

echo "=== Waiting for load test to complete ==="
while ssh -o ConnectTimeout=5 shreyas@shreyas.local 'pgrep -f "[d]fn3_paced_stages.sh" >/dev/null'; do
    sleep 10
done

echo "=== 17d. Extract results ==="
scp -o ConnectTimeout=5 shreyas@shreyas.local:~/anc_logs/power_paced.csv . || (echo "PI IS UNREACHABLE" && exit 1)
scp -o ConnectTimeout=5 shreyas@shreyas.local:~/anc_logs/dfn3_paced_t2.json . || true
scp -o ConnectTimeout=5 shreyas@shreyas.local:~/anc_logs/dfn3_paced_t3.json . || true
scp -o ConnectTimeout=5 shreyas@shreyas.local:~/anc_logs/stage.txt . || true

awk -F, '
NR>1 {
  stage=$12; ext5v=$3; vdda=$5; clk=$6; temp=$7; throt=$8; mem=$9
  if (stage == "") stage = "unknown"
  if (stage ~ /^rest_/) next
  
  if (!(stage in seen)) {
    stages[++n] = stage
    seen[stage] = 1
    min_ext5v[stage] = ext5v; max_ext5v[stage] = ext5v
    max_vdda[stage] = vdda
    min_clk[stage] = clk; max_clk[stage] = clk
    max_temp[stage] = temp
    min_mem[stage] = mem
  }
  
  if (ext5v < min_ext5v[stage]) min_ext5v[stage] = ext5v
  if (ext5v > max_ext5v[stage]) max_ext5v[stage] = ext5v
  sum_ext5v[stage] += ext5v
  count[stage]++
  
  if (vdda > max_vdda[stage]) max_vdda[stage] = vdda
  
  if (clk < min_clk[stage]) min_clk[stage] = clk
  if (clk > max_clk[stage]) max_clk[stage] = clk
  
  if (temp > max_temp[stage]) max_temp[stage] = temp
  if (mem < min_mem[stage]) min_mem[stage] = mem
  
  throt_key = stage SUBSEP throt
  if (!(throt_key in throt_seen)) {
      throt_seen[throt_key] = 1
      throt_list[stage] = throt_list[stage] throt " "
  }
}
END {
  printf "%-15s | %-18s | %-8s | %-21s | %-8s | %-15s | %-10s\n", "Stage", "EXT5V (min/u/max)", "VDD_A", "Clk (min/max)", "Temp", "Throttled", "MemMin"
  print "--------------------------------------------------------------------------------------------------------------------------"
  for (i=1; i<=n; i++) {
    s = stages[i]
    printf "%-15s | %4.2f / %4.2f / %4.2f | %-8s | %9d / %9d | %4.1f C | %-15s | %-10s\n", s, min_ext5v[s], sum_ext5v[s]/count[s], max_ext5v[s], max_vdda[s], min_clk[s], max_clk[s], max_temp[s], throt_list[s], min_mem[s]
  }
}
' power_paced.csv

echo ""
echo "=== Final state ==="
cat stage.txt || true

echo ""
echo "=== Tail of CSV ==="
tail -n 10 power_paced.csv

echo ""
echo "=== JSON contents ==="
for f in dfn3_paced_t2.json dfn3_paced_t3.json; do
    echo "$f:"
    cat $f 2>/dev/null || echo "MISSING"
done
