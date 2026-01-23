import numpy as np
import glob
import os
import matplotlib.pyplot as plt

PROCESSED_DIR = "processed_data"

def verify_npy():
    files = glob.glob(os.path.join(PROCESSED_DIR, "*.npy"))
    if not files:
        print(f"No .npy files found in {PROCESSED_DIR}")
        return

    print(f"Found {len(files)} processed files. Checking samples...")
    print("-" * 50)
    print(f"{'Filename':<45} | {'Shape':<10} | {'Min':<8} | {'Max':<8} | {'Mean':<8}")
    print("-" * 50)

    # Check first 5 and last 5
    sample_indices = list(range(min(5, len(files))))
    if len(files) > 10:
        sample_indices += list(range(len(files)-5, len(files)))
    
    valid_count = 0
    for i in sample_indices:
        f = files[i]
        fname = os.path.basename(f)
        try:
            data = np.load(f)
            shape = data.shape
            dmin = np.min(data)
            dmax = np.max(data)
            dmean = np.mean(data)
            
            print(f"{fname:<45} | {str(shape):<10} | {dmin:<8.2f} | {dmax:<8.2f} | {dmean:<8.2f}")
            
            # Simple validation rules
            if shape == (64, 64) and 150 < dmax < 350:
                valid_count += 1
            else:
                print(f"   >>> WARNING: Suspicious data range or shape!")
                
        except Exception as e:
            print(f"{fname:<45} | ERROR: {e}")

    print("-" * 50)
    print(f"Verified {len(sample_indices)} random samples.")
    
    # Check strict count
    print(f"\nTotal Stats:")
    print(f"Total Files: {len(files)}")
    print(f"Expected Size: ~16KB (float16) or ~32KB (float32)")

if __name__ == "__main__":
    verify_npy()
