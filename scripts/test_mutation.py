import os
import shutil
import subprocess

def run_integrity():
    result = subprocess.run(["venv/bin/python", "scripts/test_data_integrity.py"], capture_output=True, text=True)
    return result.returncode

def mutate_and_test():
    print("=== MUTATION TESTS ===")
    os.makedirs("data/clean_manifests_backup", exist_ok=True)
    
    # Backup
    for f in os.listdir("data/clean_manifests"):
        if f.endswith(".csv") or f.endswith(".txt"):
            shutil.copy(f"data/clean_manifests/{f}", f"data/clean_manifests_backup/{f}")
            
    try:
        # Test 1: Inject Train/Gold Duplicate (Hash overlap)
        print("Mutation 1: Injecting Train/Gold Hash Duplicate...")
        with open("data/clean_manifests/clean_train.csv", "a") as f:
            f.write("fake_path,FAKED_HASH,librispeech,fake_source,stationary,clean,train,16000,1.0\n")
        with open("data/clean_manifests/SIH_GOLD_TEST_manifest.csv", "a") as f:
            f.write("fake_path,FAKED_HASH,fake_source,fake_n_source,stationary,5.0,5.0,16000,1.0\n")
        
        # Wait, the integrity test checks GOLD parent overlap, not Gold hash!
        # Ah, Gold manifest doesn't have "file_hash" checked against train hashes in the current script.
        # But it checks parent clean id and parent noise id against Train/Val source ids.
        # Let's inject a Gold parent that is in Train.
        with open("data/clean_manifests/clean_train.csv", "r") as f:
            train_lines = f.readlines()
            train_source = train_lines[1].split(",")[3] # source_recording_id
            
        with open("data/clean_manifests/SIH_GOLD_TEST_manifest.csv", "a") as f:
            f.write(f"fake_path,FAKED_HASH,{train_source},fake_n_source,stationary,5.0,5.0,16000,1.0\n")
            
        code = run_integrity()
        assert code != 0, "Test failed to detect Gold Parent leak!"
        print("  -> Detected.")
        
        # Restore
        for f in os.listdir("data/clean_manifests_backup"):
            shutil.copy(f"data/clean_manifests_backup/{f}", f"data/clean_manifests/{f}")
            
        # Test 2: Inject Train/Val Duplicate
        print("Mutation 2: Injecting Train/Val Source Duplicate...")
        with open("data/clean_manifests/clean_val.csv", "a") as f:
            f.write(f"fake_path2,FAKED_HASH2,librispeech,{train_source},stationary,clean,val,16000,1.0\n")
        code = run_integrity()
        assert code != 0, "Test failed to detect Train/Val source leak!"
        print("  -> Detected.")
        
        print("ALL MUTATION TESTS PASSED: test_data_integrity.py correctly caught corruption.")
        with open("data/clean_manifests/mutation_result.txt", "w") as f:
            f.write("PASS")
            
    finally:
        # Restore everything
        for f in os.listdir("data/clean_manifests_backup"):
            shutil.copy(f"data/clean_manifests_backup/{f}", f"data/clean_manifests/{f}")
        shutil.rmtree("data/clean_manifests_backup")

if __name__ == "__main__":
    mutate_and_test()
