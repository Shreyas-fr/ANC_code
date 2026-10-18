echo "epoch,EXT5V_V,VDD_CORE_V,VDD_CORE_A,arm_clock,temp,throttled" > /tmp/power_D.csv
while true; do
  epoch=$(date +%s)
  ext5v=$(vcgencmd pmic_read_adc | grep EXT5V_V | cut -d= -f2 | tr -d V)
  vdd_v=$(vcgencmd pmic_read_adc | grep VDD_CORE_V | cut -d= -f2 | tr -d V)
  vdd_a=$(vcgencmd pmic_read_adc | grep VDD_CORE_A | cut -d= -f2 | tr -d A)
  clock=$(vcgencmd measure_clock arm | cut -d= -f2)
  temp=$(vcgencmd measure_temp | cut -d= -f2 | tr -d "'C")
  throttled=$(vcgencmd get_throttled | cut -d= -f2)
  echo "$epoch,$ext5v,$vdd_v,$vdd_a,$clock,$temp,$throttled" >> /tmp/power_D.csv
  
  abort=0
  if (( $(echo "$ext5v < 4.75" | bc -l) )); then abort=1; fi
  if python3 -c "import sys; sys.exit(0 if (int('$throttled', 16) & 1) else 1)"; then abort=1; fi
  if [ $abort -eq 1 ]; then
    echo "ABORT TRIGGERED: $ext5v $throttled" >> /tmp/power_D.csv
    pkill -INT -f pi_sender_v3.py
    exit 0
  fi
  sleep 1
done
