#!/bin/bash
echo "# Environment Verification" > /home/shreyas/sih26052_edge/runs/dfn3_pi_optimization/native_tract/FINAL_ENVIRONMENT.md
echo "**Pi Model:** $(cat /sys/firmware/devicetree/base/model)" >> /home/shreyas/sih26052_edge/runs/dfn3_pi_optimization/native_tract/FINAL_ENVIRONMENT.md
echo "**OS:** $(cat /etc/os-release | grep PRETTY_NAME | cut -d'"' -f2)" >> /home/shreyas/sih26052_edge/runs/dfn3_pi_optimization/native_tract/FINAL_ENVIRONMENT.md
echo "**Kernel:** $(uname -r)" >> /home/shreyas/sih26052_edge/runs/dfn3_pi_optimization/native_tract/FINAL_ENVIRONMENT.md
echo "**Architecture:** $(uname -m)" >> /home/shreyas/sih26052_edge/runs/dfn3_pi_optimization/native_tract/FINAL_ENVIRONMENT.md
echo "**CPU Count:** $(nproc)" >> /home/shreyas/sih26052_edge/runs/dfn3_pi_optimization/native_tract/FINAL_ENVIRONMENT.md
echo "**Available RAM:** $(free -h | awk '/^Mem:/ {print $2}')" >> /home/shreyas/sih26052_edge/runs/dfn3_pi_optimization/native_tract/FINAL_ENVIRONMENT.md
echo "**Rust Version:** $(~/.cargo/bin/rustc --version)" >> /home/shreyas/sih26052_edge/runs/dfn3_pi_optimization/native_tract/FINAL_ENVIRONMENT.md
echo "**Cargo Version:** $(~/.cargo/bin/cargo --version)" >> /home/shreyas/sih26052_edge/runs/dfn3_pi_optimization/native_tract/FINAL_ENVIRONMENT.md
echo "**Tract Version:** 0.21.4" >> /home/shreyas/sih26052_edge/runs/dfn3_pi_optimization/native_tract/FINAL_ENVIRONMENT.md
echo "**libDF Version:** 0.5.7-pre" >> /home/shreyas/sih26052_edge/runs/dfn3_pi_optimization/native_tract/FINAL_ENVIRONMENT.md
echo "**DeepFilterNet Version:** 0.5.6" >> /home/shreyas/sih26052_edge/runs/dfn3_pi_optimization/native_tract/FINAL_ENVIRONMENT.md
echo "**Model SHA256:** $(sha256sum /home/shreyas/sih26052_edge/models/dfn3_finetuned_tract.tar.gz | awk '{print $1}')" >> /home/shreyas/sih26052_edge/runs/dfn3_pi_optimization/native_tract/FINAL_ENVIRONMENT.md
echo "**Binary SHA256:** $(sha256sum /home/shreyas/sih26052_edge/runs/dfn3_pi_optimization/DeepFilterNet/target/release/benchmark | awk '{print $1}')" >> /home/shreyas/sih26052_edge/runs/dfn3_pi_optimization/native_tract/FINAL_ENVIRONMENT.md
echo "**CPU Governor:** $(cat /sys/devices/system/cpu/cpu3/cpufreq/scaling_governor)" >> /home/shreyas/sih26052_edge/runs/dfn3_pi_optimization/native_tract/FINAL_ENVIRONMENT.md
echo "**CPU Frequencies (min/max):** $(cat /sys/devices/system/cpu/cpu3/cpufreq/scaling_min_freq) / $(cat /sys/devices/system/cpu/cpu3/cpufreq/scaling_max_freq)" >> /home/shreyas/sih26052_edge/runs/dfn3_pi_optimization/native_tract/FINAL_ENVIRONMENT.md
echo "**Thermal State:** $(cat /sys/class/thermal/thermal_zone0/temp)" >> /home/shreyas/sih26052_edge/runs/dfn3_pi_optimization/native_tract/FINAL_ENVIRONMENT.md
echo "**Throttling Flags:** $(vcgencmd get_throttled)" >> /home/shreyas/sih26052_edge/runs/dfn3_pi_optimization/native_tract/FINAL_ENVIRONMENT.md
